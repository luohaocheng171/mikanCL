"""美化版外壳：pywebview + WebView2（Edge Chromium）。

设计目标：与经典 Qt 版共享同一套后端（Config / SourceManager / GameInstaller /
ContentClient / AccountStore / Java / 联机 / 存档 / 依赖扫描），前端只做展示。
长任务统一走 Job 线程池，前端轮询 tasks() 获取进度，因此下载与安装不会卡住界面。
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import sys
import threading
import time
import urllib.parse
import winreg
from collections import deque
from pathlib import Path

import webview

from .. import APP_VERSION, skins, themes
from ..preflight import preflight_report
from ..config import CACHE_DIR, DATA_DIR, INSTANCES_DIR, WIKI_DIR, detect_game_root

WEB_DIR = Path(__file__).resolve().parent / "web"
_RUNTIME_GUID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
_RUNTIME_DOWNLOAD = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"

# 动态壁纸只允许这几类媒体，避免把任意本地文件暴露给前端
_WALLPAPER_TYPES = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def _start_media_server() -> int:
    """启动本地媒体服务（支持 Range），用于把动态壁纸流式喂给 WebView2。"""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args):  # noqa: D401 - 静默日志
            return

        def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler 约定
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != "/media":
                self.send_error(404)
                return
            raw = (urllib.parse.parse_qs(parsed.query).get("p") or [""])[0]
            target = Path(raw)
            suffix = target.suffix.lower()
            if not target.is_file() or suffix not in _WALLPAPER_TYPES:
                self.send_error(404)
                return
            size = target.stat().st_size
            start, end, status = 0, max(0, size - 1), 200
            header = self.headers.get("Range") or ""
            if header.startswith("bytes="):
                part = header[6:].split("-", 1)
                try:
                    if part[0]:
                        start = int(part[0])
                    if len(part) > 1 and part[1]:
                        end = int(part[1])
                    elif not part[0]:
                        start = 0
                except ValueError:
                    start, end, status = 0, max(0, size - 1), 200
                else:
                    start = max(0, min(start, max(0, size - 1)))
                    end = max(start, min(end, max(0, size - 1)))
                    status = 206
            self.send_response(status)
            self.send_header("Content-Type", _WALLPAPER_TYPES[suffix])
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Cache-Control", "no-store")
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            try:
                with open(target, "rb") as file:
                    file.seek(start)
                    remaining = end - start + 1
                    while remaining > 0:
                        chunk = file.read(min(65536, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True, name="mikan-media").start()
    return int(server.server_address[1])



# ---------------------------------------------------------------------------
# WebView2 Runtime
# ---------------------------------------------------------------------------
def _bundled_runtime() -> Path | None:
    from ..config import APP_ROOT

    origins = [APP_ROOT]
    if getattr(sys, "frozen", False):
        origins.append(Path(sys.executable).resolve().parent)
    for base in origins:
        folder = Path(base) / "webview2"
        if (folder / "msedgewebview2.exe").is_file():
            return folder
    return None


def _registry_version() -> str:
    base = rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{_RUNTIME_GUID}"
    candidates = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients" + rf"\{_RUNTIME_GUID}"),
        (winreg.HKEY_LOCAL_MACHINE, base),
        (winreg.HKEY_CURRENT_USER, base),
    ]
    for root, path in candidates:
        try:
            with winreg.OpenKey(root, path) as key:
                version, _ = winreg.QueryValueEx(key, "pv")
        except OSError:
            continue
        if version and version != "0.0.0.0":
            return str(version)
    return ""


def runtime_status() -> tuple[bool, str]:
    """检测 WebView2 Runtime：优先内置固定版本，其次系统安装。"""
    custom = os.environ.get("WEBVIEW2_RUNTIME_PATH", "")
    if custom and Path(custom).exists():
        return True, "内置 WebView2 Runtime"
    bundled = _bundled_runtime()
    if bundled is not None:
        os.environ.setdefault("WEBVIEW2_RUNTIME_PATH", str(bundled))
        return True, "内置 WebView2 Runtime"
    version = _registry_version()
    if version:
        return True, f"WebView2 {version}"
    for base in (
        os.environ.get("ProgramFiles(x86)", ""),
        os.environ.get("ProgramFiles", ""),
    ):
        folder = Path(base) / "Microsoft" / "EdgeWebView" / "Application" if base else None
        if folder and folder.exists() and list(folder.glob("*/msedgewebview2.exe")):
            return True, "WebView2（安装目录）"
    return False, ""


def _prompt_missing_runtime() -> int:
    """缺运行时：给出下载入口后退出（框架已锁定，不回退经典版）。"""
    import ctypes

    text = (
        "美化版需要 Microsoft Edge WebView2 Runtime。\n\n"
        "Windows 10/11 通常已随 Edge 预装；若缺失可点击“是”打开官方下载页，"
        "安装后重新启动即可。\n\n"
        "也可以把 WebView2 Runtime 解包到安装目录的 webview2 文件夹，"
        "启动器会自动使用内置版本。\n\n"
        "是否现在打开下载页？"
    )
    choice = ctypes.windll.user32.MessageBoxW(
        0, text, "MikanCL 美化版", 0x00000004 | 0x00000040
    )
    if choice == 6:
        os.startfile(_RUNTIME_DOWNLOAD)  # noqa: S606
    return 2


# ---------------------------------------------------------------------------
# 版本扫描缓存：只解析发生变化的 version json，旧条目直接复用
# ---------------------------------------------------------------------------
_SCAN_CACHE: dict[str, dict] = {}
_SCAN_LOCK = threading.Lock()
_SCAN_INDEX = CACHE_DIR / "versions_index.json"


def _load_scan_index() -> dict[str, dict]:
    global _SCAN_CACHE
    with _SCAN_LOCK:
        if _SCAN_CACHE:
            return _SCAN_CACHE
        try:
            data = json.loads(_SCAN_INDEX.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                _SCAN_CACHE = {str(k): v for k, v in data.items() if isinstance(v, dict)}
        except (OSError, ValueError):
            _SCAN_CACHE = {}
        return _SCAN_CACHE


def _save_scan_index(cache: dict[str, dict]) -> None:
    try:
        _SCAN_INDEX.parent.mkdir(parents=True, exist_ok=True)
        tmp = _SCAN_INDEX.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, _SCAN_INDEX)
    except OSError:
        pass


def scan_versions_fast(game_dir: Path, force: bool = False) -> list[dict]:
    """快速扫描已安装版本：命中缓存时只做 stat，不重复解析 JSON。"""
    from ..version import detect_loader

    versions_dir = Path(game_dir) / "versions"
    if not versions_dir.is_dir():
        return []
    cache = _load_scan_index()
    result: list[dict] = []
    changed = force
    try:
        entries = list(os.scandir(versions_dir))
    except OSError:
        return []
    for entry in entries:
        if not entry.is_dir(follow_symlinks=False):
            continue
        folder = versions_dir / entry.name
        json_path = folder / f"{entry.name}.json"
        jar_path = folder / f"{entry.name}.jar"
        # 有版本 JSON 时按 JSON 解析；缺少 JSON 但目录里有游戏 Jar 时，
        # 仍按文件夹名列为已安装版本（例如从别处复制来的游戏）。
        if json_path.is_file():
            source_path = json_path
        elif jar_path.is_file():
            source_path = jar_path
        else:
            try:
                source_path = next(
                    (item for item in folder.iterdir() if item.is_file() and item.suffix.lower() == ".jar"),
                    None,
                )
            except OSError:
                source_path = None
        if source_path is None:
            continue
        try:
            stat = source_path.stat()
        except OSError:
            continue
        key = str(folder)
        stamp = [stat.st_mtime, stat.st_size, bool(json_path.is_file())]
        cached = cache.get(key)
        if not force and cached and cached.get("stamp") == stamp:
            result.append(cached)
            continue
        changed = True
        if not json_path.is_file():
            item = {
                "id": entry.name,
                "type": "custom",
                "loader": "",
                "base": "",
                "error": "",
                "modified": stat.st_mtime,
                "stamp": stamp,
            }
        else:
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("不是 JSON 对象")
                loader = detect_loader(entry.name, data)
                item = {
                    "id": entry.name,
                    "type": str(data.get("type") or "custom"),
                    "loader": loader,
                    "base": str(data.get("inheritsFrom") or ""),
                    "error": "",
                    "modified": stat.st_mtime,
                    "stamp": stamp,
                }
            except (OSError, ValueError) as exc:
                item = {
                    "id": entry.name,
                    "type": "broken",
                    "loader": "损坏",
                    "base": "",
                    "error": str(exc),
                    "modified": stat.st_mtime,
                    "stamp": stamp,
                }
        cache[key] = item
        result.append(item)
    if changed:
        _save_scan_index(cache)
    result.sort(key=lambda v: v.get("modified") or 0, reverse=True)
    return result


# ---------------------------------------------------------------------------
# 长任务
# ---------------------------------------------------------------------------
class Job:
    """一个后台任务：状态、进度、日志、取消/暂停。"""

    def __init__(self, kind: str, title: str) -> None:
        self.id = f"job-{int(time.time() * 1000)}-{threading.get_ident()}"
        self.kind = kind
        self.title = title
        self.state = "running"  # running / paused / ok / failed / cancelled
        self.percent = 0.0
        self.stage = "准备中"
        self.detail = ""
        self.created = time.time()
        self.updated = self.created
        self.cancel = threading.Event()
        self.pause = threading.Event()
        self.logs: deque[str] = deque(maxlen=160)
        self.result: dict | None = None
        self.error = ""

    def log(self, message: str) -> None:
        text = str(message or "").strip()
        if text:
            self.logs.append(text)
            self.detail = text
            self.updated = time.time()

    def progress(self, percent: float, detail: str = "", stage: str = "") -> None:
        if stage:
            self.stage = stage
        if detail:
            self.detail = detail
        if percent is not None:
            try:
                self.percent = max(0.0, min(100.0, float(percent)))
            except (TypeError, ValueError):
                pass
        self.updated = time.time()

    def snapshot(self) -> dict:
        state = self.state
        if state == "running" and self.pause.is_set():
            state = "paused"
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "state": state,
            "percent": round(self.percent, 1),
            "stage": self.stage,
            "detail": self.detail,
            "error": self.error,
            "created": self.created,
            "updated": self.updated,
            "result": self.result or {},
            "logs": list(self.logs)[-24:],
        }


_JOBS: dict[str, Job] = {}
_JOBS_LOCK = threading.Lock()


def _spawn(kind: str, title: str, worker) -> Job:
    job = Job(kind, title)
    job.worker = worker
    with _JOBS_LOCK:
        _JOBS[job.id] = job
        # 只保留最近 60 条，避免长时间运行内存增长
        if len(_JOBS) > 60:
            oldest = sorted(_JOBS.values(), key=lambda j: j.created)[: len(_JOBS) - 60]
            for item in oldest:
                if item.state not in ("running", "paused"):
                    _JOBS.pop(item.id, None)

    def run() -> None:
        try:
            payload = worker(job)
            if job.cancel.is_set():
                job.state = "cancelled"
            else:
                job.state = "ok"
                job.percent = 100.0
                job.result = payload if isinstance(payload, dict) else {}
                job.stage = "已完成"
        except Exception as exc:  # noqa: BLE001 - 需要把失败原因交给界面
            from ..net import Cancelled

            if isinstance(exc, Cancelled) or job.cancel.is_set():
                job.state = "cancelled"
                job.stage = "已取消"
            else:
                job.state = "failed"
                job.error = str(exc)
                job.stage = "失败"
                job.log(f"[失败] {exc}")
        finally:
            job.updated = time.time()

    threading.Thread(target=run, name=f"mikan-{kind}", daemon=True).start()
    return job


def _jobs_snapshot() -> list[dict]:
    with _JOBS_LOCK:
        items = sorted(_JOBS.values(), key=lambda j: j.created, reverse=True)
    return [job.snapshot() for job in items]


# 批处理里需要加引号的字符集合（空格、&、|、重定向、括号等）
_BAT_SPECIAL = set(' \t&()[]{}^=;,!`\'"+|<>%')


def _bat_arg(value: str) -> str:
    text = str(value)
    if not text:
        return '""'
    text = text.replace("%", "%%")
    if any(ch in _BAT_SPECIAL for ch in text):
        return '"' + text.replace('"', '""') + '"'
    return text


def _ps_arg(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _script_text(plan, suffix: str) -> str:
    """生成 .bat / .ps1 / .sh 启动脚本内容（与经典版导出的格式一致）。"""
    cwd = str(plan.cwd)
    if suffix.lower() == ".sh":
        command = " ".join(shlex.quote(part) for part in plan.command)
        return f"#!/usr/bin/env bash\nset -e\ncd {shlex.quote(cwd)}\nexec {command}\n"
    if suffix.lower() == ".ps1":
        args = ",".join(_ps_arg(part) for part in plan.command)
        return (
            f"Set-Location {_ps_arg(cwd)}\n"
            f"$cmd = @({args})\n"
            "& $cmd[0] @($cmd[1..($cmd.Length-1)])\n"
        )
    line = " ".join(_bat_arg(part) for part in plan.command)
    return f'@echo off\ncd /d "{cwd}"\n{line}\n'


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", str(name or "")).strip(" .")
    return cleaned or "download"


def _unique_dest(directory: Path, name: str) -> Path:
    base = _safe_filename(name)
    stem, suffix = os.path.splitext(base)
    candidate = directory / base
    index = 2
    while candidate.exists() or candidate.with_suffix(candidate.suffix + ".part").exists():
        candidate = directory / f"{stem} ({index}){suffix}"
        index += 1
    return candidate


# ---------------------------------------------------------------------------
# 序列化辅助
# ---------------------------------------------------------------------------
def _fmt_size(value: object) -> str:
    try:
        size = int(value or 0)
    except (TypeError, ValueError):
        return "未知"
    units = ["B", "KB", "MB", "GB", "TB"]
    index = 0
    number = float(size)
    while number >= 1024 and index < len(units) - 1:
        number /= 1024
        index += 1
    return f"{number:.1f} {units[index]}"


def _icon_data_url(payload: bytes) -> str:
    import base64

    if not payload:
        return ""
    return "data:image/png;base64," + base64.b64encode(payload).decode()


def _version_payload(version: dict) -> dict:
    return {
        "id": version.get("id", ""),
        "type": version.get("type", ""),
        "loader": version.get("loader", ""),
        "base": version.get("base", ""),
        "error": version.get("error", ""),
        "modified": version.get("modified", 0),
    }


def _find_installed_loader(target: Path, mc_version: str, loader: str) -> str:
    """在目标目录找同版本加载器，避免整合包重复安装。"""
    versions = Path(target) / "versions"
    if not loader or not versions.is_dir():
        return ""
    lowered = loader.lower()
    prefixes = {
        "forge": ("forge-",),
        "neoforge": ("neoforge-",),
        "fabric": ("fabric-loader-",),
        "quilt": ("quilt-loader-",),
        "liteloader": ("liteloader-",),
    }.get(lowered, (f"{lowered}-",))
    for folder in versions.iterdir():
        if not folder.is_dir():
            continue
        name = folder.name.lower()
        if mc_version in name and any(name.startswith(p) for p in prefixes):
            return folder.name
    return ""


def _project_payload(project) -> dict:
    return {
        "source": project.source,
        "id": project.id,
        "title": project.display_title,
        "description": project.display_description,
        "type": project.project_type,
        "type_label": project.type_label,
        "author": project.author,
        "downloads": project.downloads,
        "icon": project.icon_url,
        "categories": list(project.categories)[:8],
        "slug": project.slug,
        "page": project.page_url,
    }


def _cversion_payload(version) -> dict:
    file = version.primary_file
    deps = list(version.dependencies or [])
    return {
        "id": version.id,
        "name": version.name or version.version_number,
        "number": version.version_number,
        "game_versions": list(version.game_versions)[:12],
        "loaders": list(version.loaders),
        "date": version.date,
        "downloads": version.downloads,
        "channel": version.channel,
        "filename": file.filename if file else "",
        "size": file.size if file else 0,
        "required": [
            {"project_id": str(d.get("project_id") or ""), "version_id": str(d.get("version_id") or "")}
            for d in deps
            if d.get("dependency_type") == "required"
        ],
        "optional": [
            {"project_id": str(d.get("project_id") or ""), "version_id": str(d.get("version_id") or "")}
            for d in deps
            if d.get("dependency_type") == "optional"
        ],
    }


class WebApi:
    """暴露给前端 JS 的接口（pywebview 会挂到 window.pywebview.api）。"""

    def __init__(self, config) -> None:
        self.config = config
        self.window = None
        self._accounts = None
        self._sources = None
        self._content = None
        self._javas: list = []
        self._javas_at = 0.0
        self._terracotta = None
        self._preview_cache: dict[str, str] = {}
        self._nbt_cache: dict[str, tuple] = {}
        self._media_port = 0
        self._media_lock = threading.Lock()
        self._extensions_dir = DATA_DIR / "extensions"

    # ---------- 懒加载资源 ----------
    def _store(self):
        if self._accounts is None:
            from ..auth import AccountStore

            self._accounts = AccountStore(default_name=self.config.player_name)
        return self._accounts

    def _source_manager(self):
        if self._sources is None:
            from ..net import SourceManager, apply_proxy

            apply_proxy(self.config.effective_proxy)
            from ..net import set_default_download_workers, set_download_speed_limit

            set_default_download_workers(int(self.config.download_threads or 16))
            set_download_speed_limit(int(self.config.download_speed_limit or 0))
            self._sources = SourceManager(self.config)
        return self._sources

    def _content_client(self):
        if self._content is None:
            from ..content import ContentClient

            self._content = ContentClient(self.config)
        return self._content

    def _java_list(self, force: bool = False):
        from ..java import detect_java_installed, merge_java_lists

        now = time.time()
        if not force and self._javas and now - self._javas_at < 600:
            return self._javas
        extra = [self.config.java_path] if self.config.java_path else []
        extra.extend(self.config.java_manual_paths or [])
        found = detect_java_installed(extra)
        self._javas = merge_java_lists(self._javas, found) if self._javas else found
        self._javas_at = now
        return self._javas

    def _java_for(self, version_id: str):
        from ..java import pick_java
        from ..version import infer_java_major

        preferred = str(getattr(self.config, "java_path", "") or "")
        java, _message = pick_java(
            self._java_list(), infer_java_major(version_id), preferred
        )
        return java

    def _game_dir_of(self, instance_id: str = "") -> Path:
        if instance_id:
            instance = self.config.get_instance(instance_id)
            if instance and instance.game_dir:
                return Path(instance.game_dir)
        return self.config.game_path

    def _refresh(self) -> None:
        """安装完成后清空扫描缓存，下一次 bootstrap 拿到最新列表。"""
        global _SCAN_CACHE
        with _SCAN_LOCK:
            _SCAN_CACHE = {}

    # =====================================================================
    # 启动数据
    # =====================================================================
    def bootstrap(self) -> dict:
        from .. import agreement
        from ..config import ISOLATION_LABELS
        from ..i18n import SUPPORTED_LANGUAGES
        from ..skins import entries as skin_entries

        cfg = self.config
        versions = [_version_payload(v) for v in scan_versions_fast(Path(cfg.game_path))]
        store = self._store()
        account = store.selected()
        palette = self._palette()
        # 主页「最近皮肤」：皮肤库 + 当前账号皮肤 + data/skins 下的 PNG，
        # 避免皮肤库为空（例如只通过皮肤包 / 工坊应用过皮肤）时主页显示空白。
        skin_list: list[dict] = []
        seen_skins: set[str] = set()

        def _add_skin(path: str, name: str = "", model: str = "") -> None:
            text = str(path or "").strip()
            if not text or not Path(text).is_file():
                return
            key = os.path.normcase(str(Path(text).resolve()))
            if key in seen_skins:
                return
            seen_skins.add(key)
            skin_list.append(
                {
                    "path": text,
                    "name": name or Path(text).stem,
                    "model": model or "classic",
                }
            )

        account_skin = getattr(account, "skin_path", "") or ""
        if account_skin:
            _add_skin(account_skin, getattr(account, "name", ""), getattr(account, "skin_model", ""))
        for entry in skin_entries(limit=12):
            _add_skin(entry.path, entry.name, entry.model)
        for file in sorted((DATA_DIR / "skins").glob("*.png"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True):
            _add_skin(str(file), file.stem)
        skin_list = skin_list[:12]
        return {
            "app": APP_VERSION,
            "ui_animations": bool(cfg.ui_animations),
            "glass_effect": bool(cfg.glass_effect),
            "glass_see_through": bool(cfg.glass_see_through),
            "glass_strength": int(cfg.glass_strength or 62),
            "glass_blur": int(getattr(cfg, "glass_blur", 20) or 0),
            "accent_color": cfg.accent_color,
            "text_color": getattr(cfg, "text_color", ""),
            "player": account.name,
            "account": {
                "id": account.id,
                "name": account.name,
                "type": account.type,
                "type_label": account.type_label,
                "uuid": account.uuid,
                "skin_path": account.skin_path,
                "skin_model": account.skin_model,
            },
            "selected_version": cfg.default_version_id or (versions[0]["id"] if versions else ""),
            "versions": versions,
            "instances": [
                {
                    "id": item.id,
                    "name": item.name,
                    "game_dir": item.game_dir,
                    "version_id": item.version_id,
                    "loader": item.loader,
                    "mc_version": item.mc_version,
                    "selected": item.id == cfg.selected_instance_id,
                }
                for item in cfg.instance_list()
            ],
            "selected_instance": cfg.selected_instance_id,
            "game_dirs": [
                {"id": e.id, "name": e.name, "path": e.path}
                for e in (cfg.game_dirs or [])
            ],
            "active_game_dir": cfg.active_game_dir,
            "game_dir": str(cfg.game_path),
            "java": self._java_summary(),
            "themes": [
                {
                    "name": theme.name,
                    "accent": theme.accent,
                    "light": themes.is_light(theme),
                }
                for theme in themes.all_themes().values()
            ],
            "theme": getattr(cfg, "theme_name", "") or "晨光",
            "color_mode": getattr(cfg, "color_mode", "light"),
            "palette": palette,
            "skins": skin_list,
            "languages": [
                {"code": code, "name": name}
                for code, name in SUPPORTED_LANGUAGES.items()
            ],
            "language": cfg.language,
            "isolation_mode": cfg.isolation_mode,
            "isolation_options": ISOLATION_LABELS,
            "frame_mode": cfg.frame_mode,
            "frame_locked": False,
            "features": self._feature_map(),
            "runtime": runtime_status()[1],
            "agreement": {
                "needs": agreement.needs_prompt(cfg),
                "texts": agreement.texts(cfg.language),
            },
            "tasks": _jobs_snapshot(),
        }

    def _java_summary(self) -> dict:
        javas = self._javas
        selected = self.config.java_path or ""
        return {
            "path": selected,
            "count": len(javas),
            "list": [
                {
                    "path": j.path,
                    "version": j.version,
                    "major": j.major,
                    "arch": f"{j.bits} 位",
                    "vendor": getattr(j, "vendor", ""),
                }
                for j in javas[:12]
            ],
        }

    # =====================================================================
    # 用户协议（与经典版同一份文本）
    # =====================================================================
    def accept_agreement(self) -> dict:
        from .. import agreement

        agreement.accept(self.config)
        return {"ok": True, "accepted_at": agreement.accepted_at(self.config)}

    def decline_agreement(self) -> dict:
        """不同意协议：销毁窗口退出，绝不进入主界面。"""
        if self.window is not None:
            threading.Timer(0.15, self.window.destroy).start()
        return {"ok": True}

    # =====================================================================
    # 版本 / 下载
    # =====================================================================
    def scan_versions(self, force: bool = False) -> list[dict]:
        items = [_version_payload(v) for v in scan_versions_fast(self.config.game_path, bool(force))]
        order = list(self.config.version_order or [])
        if order:
            rank = {version_id: index for index, version_id in enumerate(order)}
            items.sort(key=lambda item: rank.get(str(item.get("id")), len(order)))
        return items

    def version_order_save(self, order: list[str]) -> dict:
        """保存主页版本卡片的手动排序（拖动后调用）。"""
        ids = [str(v) for v in (order or []) if str(v)]
        self.config.version_order = ids
        try:
            self.config.save()
        except OSError as exc:
            return {"ok": False, "message": f"保存失败：{exc}"}
        return {"ok": True, "message": "版本顺序已保存"}

    def delete_version(self, version_id: str) -> dict:
        """删除已安装版本目录（不可恢复，前端需二次确认）。"""
        if not version_id:
            return {"ok": False, "message": "缺少版本号"}
        version_dir = self.config.game_path / "versions" / version_id
        if not version_dir.is_dir():
            return {"ok": False, "message": "版本不存在"}
        try:
            shutil.rmtree(version_dir)
        except OSError as exc:
            return {"ok": False, "message": f"删除失败：{exc}"}
        self._refresh()
        return {"ok": True, "message": f"已删除 {version_id}", "versions": self.scan_versions()}

    def manifest(self, force: bool = False) -> dict:
        try:
            payload, source_name, cached = self._source_manager().get_manifest(bool(force))
            # get_manifest 返回缓存包装 {fetched_at, source_id, source_name, data}
            data = payload.get("data")
            if not isinstance(data, dict):
                data = payload
            versions = [
                {
                    "id": str(item.get("id") or ""),
                    "type": str(item.get("type") or ""),
                    "release": str(item.get("releaseTime") or ""),
                }
                for item in (data.get("versions") or [])
                if isinstance(item, dict) and item.get("id")
            ]
            return {"ok": True, "source": source_name, "cached": cached, "versions": versions}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"获取版本清单失败：{exc}"}

    def _auto_skin(self, version_id: str, root=None) -> None:
        """新版本 / 整合包装完后自动为离线账号生成适配皮肤包，无需用户再操作。"""
        from ..auth import import_offline_skin
        from ..launcher import resolve_game_dirs

        try:
            account = self._store().selected()
        except Exception:  # noqa: BLE001 - 账号读取失败时跳过
            return
        if account is None or account.type != "offline" or not account.skin_path:
            return
        base = Path(root) if root is not None else self.config.game_path
        try:
            dirs = resolve_game_dirs(base, version_id, self.config.isolation_for(version_id)).skin_targets()
        except Exception:  # noqa: BLE001
            dirs = [base]
        for game_dir in dirs:
            try:
                import_offline_skin(account, game_dir, log=None, version_id=version_id)
            except Exception:  # noqa: BLE001 - 皮肤写入失败不影响安装
                continue

    def install_version(self, version_id: str, loader: str = "", loader_version: str = "") -> dict:
        version_id = str(version_id or "").strip()
        if not version_id:
            return {"ok": False, "message": "请先选择游戏版本"}
        if loader in ("forbric",):
            return self.install_forbric(version_id)
        title = f"安装 {version_id}" + (f" + {loader}" if loader else "")
        job = _spawn("version", title, lambda j: self._install_version_job(j, version_id, loader, loader_version))
        return {"ok": True, "job": job.id, "message": title}

    def _install_version_job(self, job: Job, version_id: str, loader: str, loader_version: str) -> dict:
        from ..installer import GameInstaller

        sources = self._source_manager()
        cfg = self.config

        def progress(item) -> None:
            job.progress(
                item.percent * (45.0 if loader else 100.0),
                item.detail,
                item.stage,
            )

        installer = GameInstaller(
            cfg,
            sources,
            progress_cb=progress,
            log_cb=job.log,
            cancel=job.cancel,
            pause=job.pause,
        )
        job.stage = "安装原版"
        if loader:
            installer.ensure_version(version_id)
            job.progress(45.0, "原版就绪", "安装加载器")
            java = self._java_for(version_id)
            from ..modloader import install_loader

            job.log(f"[加载器] {loader} {loader_version or '最新版'}")
            installed = install_loader(
                installer,
                loader,
                version_id,
                loader_version,
                java.path if java else "",
                log=job.log,
                cancel=job.cancel,
            )
            job.progress(100.0, f"已安装 {installed}", "完成")
            self._auto_skin(installed)
            self._refresh()
            return {"version_id": installed}
        manifest, _name, _cached = sources.get_manifest()
        data = manifest.get("data") if isinstance(manifest.get("data"), dict) else manifest
        entry = next(
            (item for item in (data.get("versions") or []) if item.get("id") == version_id),
            None,
        )
        if entry is None:
            raise RuntimeError(f"版本清单里找不到 {version_id}")
        installer.install_version(entry, version_id)
        self._auto_skin(version_id)
        self._refresh()
        return {"version_id": version_id}

    def install_forbric(self, mc_version: str) -> dict:
        from ..forbric import is_forbric_supported

        if not is_forbric_supported(mc_version):
            return {"ok": False, "message": "Forbric 目前仅支持 Minecraft 26.2，请切换版本后再试"}
        job = _spawn("forbric", f"Forbric 引导安装 {mc_version}", self._forbric_job)
        return {"ok": True, "job": job.id, "message": "已启动 Forbric 安装向导"}

    def _forbric_job(self, job: Job) -> dict:
        from .. import forbric

        job.stage = "获取安装器"
        jar_url, bat_url = forbric.fetch_latest_installer()
        jar = forbric.download_installer(jar_url, bat_url, log=job.log)
        java = self._java_for(forbric.FORBRIC_SUPPORTED_MC)
        if java is None:
            raise RuntimeError("没有可用的 Java，无法运行 Forbric 安装器")
        job.stage = "等待官方安装器"
        job.log("请在打开的安装器窗口里点击 Install，完成后版本会自动出现")
        process = forbric.launch_installer(jar, java.path, log=job.log)
        ok = forbric.wait_for_version(self.config.game_path, job.cancel, log=job.log)
        if process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass
        if not ok:
            raise RuntimeError("已取消 Forbric 安装")
        self._refresh()
        return {"version_id": forbric.FORBRIC_VERSION_ID}

    def loader_kinds(self) -> list[dict]:
        from ..modloader import LOADER_LABELS

        return [{"id": key, "name": value} for key, value in LOADER_LABELS.items()] + [
            {"id": "forbric", "name": "Forbric（实验性三合一）"}
        ]

    def loader_mc_versions(self, kind: str) -> dict:
        try:
            from ..modloader import list_loader_mc_versions

            return {"ok": True, "versions": list_loader_mc_versions(kind)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"获取游戏版本失败：{exc}", "versions": []}

    def loader_versions(self, kind: str, mc_version: str) -> dict:
        try:
            from ..modloader import list_loader_versions

            return {"ok": True, "versions": list_loader_versions(kind, mc_version)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"获取加载器版本失败：{exc}", "versions": []}

    def install_modpack_file(self) -> dict:
        """选择本地整合包文件并安装（.mrpack / .zip）。"""
        path = self._pick_file(("整合包 (*.mrpack;*.zip)", "所有文件 (*.*)"))
        if not path:
            return {"ok": False, "message": "未选择文件"}
        name = Path(path).stem
        job = _spawn("modpack", f"导入整合包 {name}", lambda j: self._modpack_file_job(j, Path(path)))
        return {"ok": True, "job": job.id, "message": f"开始导入 {name}"}

    def _modpack_file_job(self, job: Job, path: Path) -> dict:
        from ..installer import GameInstaller
        from ..modloader import install_loader

        content = self._content_client()
        job.stage = "解析整合包"
        meta = content.parse_modpack(path, log=job.log)
        job.log(f"[整合包] {meta.name} · MC {meta.mc_version} · {meta.loader or '原版'}")
        folder_name = f"{meta.name}-{meta.mc_version}".replace("/", "_").replace("\\", "_")
        target = INSTANCES_DIR / folder_name
        target.mkdir(parents=True, exist_ok=True)
        clone = self.config.with_game_dir(target)
        installer = GameInstaller(
            clone,
            self._source_manager(),
            progress_cb=lambda p: job.progress(p.percent * 0.5, p.detail, p.stage),
            log_cb=job.log,
            cancel=job.cancel,
            pause=job.pause,
        )
        job.stage = "安装原版"
        installer.ensure_version(meta.mc_version)
        version_id = ""
        if meta.loader:
            job.stage = "安装加载器"
            existing = _find_installed_loader(target, meta.mc_version, meta.loader)
            if existing:
                version_id = existing
            else:
                java = self._java_for(meta.mc_version)
                version_id = install_loader(
                    installer,
                    meta.loader,
                    meta.mc_version,
                    meta.loader_version,
                    java.path if java else "",
                    log=job.log,
                    cancel=job.cancel,
                )
        job.stage = "写入整合包内容"
        content.install_modpack_files(
            path,
            meta,
            target,
            log=job.log,
            cancel=job.cancel,
            pause=job.pause,
            progress=lambda percent, message: job.progress(50 + percent * 50, message, "写入整合包内容"),
        )
        self.config.add_instance(
            meta.name,
            str(target),
            version_id=version_id or meta.mc_version,
            loader=meta.loader,
            mc_version=meta.mc_version,
            modpack=meta.name,
            loader_version=meta.loader_version,
        )
        self._auto_skin(version_id or meta.mc_version, root=target)
        self._refresh()
        return {"instance": meta.name, "game_dir": str(target)}

    # ---------- 任务中心 ----------
    def repair_instance(self, instance_id: str = "") -> dict:
        """校验并补全实例的原版 / 加载器文件，等同经典版的「修复」。"""
        instance = self.config.get_instance(instance_id) if instance_id else None
        if instance is None:
            return {"ok": False, "message": "实例不存在"}
        job = _spawn(
            "repair",
            f"修复实例 {instance.name}",
            lambda j: self._repair_instance_job(j, instance_id),
        )
        return {"ok": True, "job": job.id, "message": f"开始修复 {instance.name}"}

    def _repair_instance_job(self, job: Job, instance_id: str) -> dict:
        from ..installer import GameInstaller
        from ..modloader import install_loader

        cfg = self.config
        instance = cfg.get_instance(instance_id)
        if instance is None:
            raise RuntimeError("实例不存在")
        target = Path(instance.game_dir or cfg.game_path)
        mc_version = instance.mc_version or instance.version_id
        if not mc_version:
            raise RuntimeError("实例未记录 Minecraft 版本，无法自动修复")
        install_cfg = cfg if target == cfg.game_path else cfg.with_game_dir(target)
        installer = GameInstaller(
            install_cfg,
            self._source_manager(),
            progress_cb=lambda p: job.progress(p.percent, p.detail, p.stage),
            log_cb=job.log,
            cancel=job.cancel,
            pause=job.pause,
        )
        job.stage = f"检查原版 {mc_version}"
        installer.ensure_version(mc_version)
        version_id = instance.version_id or mc_version
        if instance.loader:
            job.stage = f"检查加载器 {instance.loader}"
            java = self._java_for(mc_version)
            version_id = install_loader(
                installer,
                instance.loader,
                mc_version,
                instance.loader_version,
                java.path if java else "",
                log=job.log,
                cancel=job.cancel,
            )
        if instance.version_id != version_id:
            instance.version_id = version_id
            try:
                cfg.save()
            except OSError:
                pass
        self._refresh()
        job.progress(100.0, f"实例 {instance.name} 已修复", "完成")
        return {"version_id": version_id}

    def tasks(self) -> list[dict]:
        return _jobs_snapshot()

    def task_cancel(self, job_id: str) -> dict:
        job = _JOBS.get(job_id)
        if job is None:
            return {"ok": False, "message": "任务不存在"}
        job.cancel.set()
        job.pause.clear()
        return {"ok": True}

    def task_pause(self, job_id: str) -> dict:
        job = _JOBS.get(job_id)
        if job is None:
            return {"ok": False, "message": "任务不存在"}
        job.pause.set()
        return {"ok": True}

    def task_resume(self, job_id: str) -> dict:
        job = _JOBS.get(job_id)
        if job is None:
            return {"ok": False, "message": "任务不存在"}
        job.pause.clear()
        return {"ok": True}

    def task_clear(self) -> dict:
        with _JOBS_LOCK:
            for key in [k for k, j in _JOBS.items() if j.state not in ("running", "paused")]:
                _JOBS.pop(key, None)
        return {"ok": True}

    def task_delete(self, job_id: str) -> dict:
        """删除单条下载任务：运行中的先取消，再从列表移除（不会删除已下载文件）。"""
        job = _JOBS.get(job_id)
        if job is None:
            return {"ok": False, "message": "任务不存在"}
        job.cancel.set()
        job.pause.clear()
        with _JOBS_LOCK:
            _JOBS.pop(job_id, None)
        return {"ok": True, "message": "任务已删除"}

    def task_retry(self, job_id: str) -> dict:
        """重试失败/取消的任务：复用原 worker，创建一个新任务。"""
        with _JOBS_LOCK:
            job = _JOBS.get(job_id)
        if job is None:
            return {"ok": False, "message": "任务不存在"}
        state = job.snapshot()["state"]
        if state in ("running", "paused"):
            return {"ok": False, "message": "任务正在进行中"}
        worker = getattr(job, "worker", None)
        if worker is None:
            return {"ok": False, "message": "该任务不支持重试"}
        new_job = _spawn(job.kind, job.title, worker)
        with _JOBS_LOCK:
            _JOBS.pop(job_id, None)
        return {"ok": True, "job": new_job.id, "message": "已重新开始任务"}

    # =====================================================================
    # 启动游戏
    # =====================================================================
    def launch_check(self, version_id: str, instance_id: str = "") -> dict:
        """启动前 checklist：阻止项交前端确认，警告直接展示。"""
        try:
            cfg = self.config
            memory = int(cfg.version_setting(version_id).memory_mb or cfg.memory_mb or 4096)
            report = preflight_report(self._game_dir_of(instance_id), memory)
            return {"ok": True, "blocked": report["blocked"], "warnings": report["warnings"]}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "blocked": [], "warnings": [], "message": str(exc)}

    def _launch_plan(self, version_id: str, instance_id: str = ""):
        """构建启动计划（适用版本隔离、账号、参数与自动进服）。"""
        from ..auth import ensure_authlib_injector
        from ..launcher import LaunchOptions, build_launch_plan, prepare_isolated_dir, split_server
        from ..version import load_version

        cfg = self.config
        root_dir = self._game_dir_of(instance_id)
        game_dir = prepare_isolated_dir(root_dir, version_id, cfg.isolation_for(version_id))
        merged = load_version(root_dir, version_id)
        java = self._java_for(version_id)
        if java is None:
            raise RuntimeError("没有可用的 Java，请先在「下载 → Java」安装或选择 Java 路径")
        setting = cfg.version_setting(version_id)
        store = self._store()
        account = store.selected()
        uuid = account.uuid
        access_token = account.access_token
        user_type = "legacy"
        authlib_jar = ""
        auth_server = ""
        if account.type == "microsoft":
            if account.token_expired and account.refresh_token:
                from ..auth import MicrosoftAuth

                fresh = MicrosoftAuth(cfg.microsoft_client_id).refresh(account)
                store.update(fresh)
                uuid = fresh.uuid
                access_token = fresh.access_token
            user_type = "msa"
            if not access_token:
                raise RuntimeError("微软账号尚未登录，请到「账号」页完成登录")
        elif account.type == "authlib":
            auth_server = account.auth_server
            authlib_jar = str(ensure_authlib_injector(cfg))
        server, port = "", 25565
        if setting.auto_connect and setting.server.strip():
            server, port = split_server(setting.server, int(setting.port or 25565))
        elif cfg.active_server() is not None:
            active = cfg.active_server()
            server, port = split_server(active.host, int(active.port or 25565))
        elif cfg.auto_connect_enabled and str(cfg.auto_connect_server or "").strip():
            server, port = split_server(
                str(cfg.auto_connect_server), int(cfg.auto_connect_port or 25565)
            )
        extra_jvm = " ".join(
            part for part in (cfg.extra_jvm_args, setting.extra_jvm_args) if str(part).strip()
        )
        extra_game = " ".join(
            part for part in (cfg.extra_game_args, setting.extra_game_args) if str(part).strip()
        )
        memory = int(setting.memory_mb or cfg.memory_mb or 4096)
        if account.type == "offline":
            try:
                from ..auth import apply_local_skin

                apply_local_skin(account, game_dir, version_id)
            except Exception:  # noqa: BLE001 - 离线皮肤失败不应阻塞启动
                pass
        return build_launch_plan(
            LaunchOptions(
                version=merged,
                game_dir=game_dir,
                root_dir=root_dir,
                player_name=account.name,
                java=java,
                memory_mb=memory,
                smart_jvm=bool(cfg.smart_jvm),
                pre_touch=bool(cfg.opt_pre_touch),
                fixed_heap=bool(cfg.opt_fixed_heap),
                width=int(cfg.width or 0),
                height=int(cfg.height or 0),
                extra_jvm_args=extra_jvm,
                extra_game_args=extra_game,
                uuid=uuid,
                access_token=access_token,
                user_type=user_type,
                authlib_jar=authlib_jar,
                auth_server=auth_server,
                auto_connect=bool(server),
                server=server,
                server_port=port,
                proxy_url=str(cfg.effective_proxy if cfg.proxy_jvm else ""),
                window_title=str(setting.window_title or cfg.window_title or ""),
                priority=str(setting.priority or cfg.process_priority or "normal"),
                offline=account.type == "offline",
            )
        )

    def _launch_now(self, version_id: str, instance_id: str = "", job: Job | None = None) -> dict:
        """补全版本文件并真正启动游戏（必须运行在后台线程）。"""
        from ..installer import GameInstaller
        from ..launcher import post_launch, start_game

        cfg = self.config
        root_dir = self._game_dir_of(instance_id)

        def on_progress(item) -> None:
            if job is not None:
                job.progress(
                    8 + float(getattr(item, "percent", 0) or 0) * 0.55,
                    str(getattr(item, "detail", "") or getattr(item, "stage", "")),
                    "补全版本",
                )

        def on_log(line: str) -> None:
            if job is not None:
                job.log(line)

        installer = GameInstaller(
            cfg,
            self._source_manager(),
            progress_cb=on_progress,
            log_cb=on_log,
            cancel=(job.cancel if job is not None else threading.Event()),
        )
        installer.config = cfg.with_game_dir(root_dir)
        installer.ensure_version(version_id)
        if cfg.auto_backup_saves:
            try:
                from ..launcher import prepare_isolated_dir
                from ..saves import auto_backup_saves

                backup_dir = prepare_isolated_dir(root_dir, version_id, cfg.isolation_for(version_id))
                auto_backup_saves(backup_dir, cfg.backup_root, version_id, log=on_log)
            except Exception as exc:  # noqa: BLE001 - 备份失败不阻塞启动
                on_log(f"[备份] 跳过自动备份：{exc}")
        if job is not None:
            job.progress(65, "构建启动参数", "启动")
        plan = self._launch_plan(version_id, instance_id)
        session = start_game(plan, on_line=on_log)
        setting = cfg.version_setting(version_id)
        post_launch(
            session.process,
            priority=str(setting.priority or cfg.process_priority or "normal"),
            title=str(setting.window_title or cfg.window_title or ""),
        )
        cfg.launch_count = int(cfg.launch_count or 0) + 1
        try:
            cfg.save()
        except OSError:
            pass
        every = int(cfg.support_prompt_every or 10)
        prompt = bool(every) and cfg.launch_count % every == 0
        return {
            "version": version_id,
            "message": "游戏已启动，日志在 data/logs",
            "warnings": list(plan.warnings),
            "support_prompt": prompt,
            "session": session,
        }

    def launch(self, version_id: str, instance_id: str = "", force: bool = False) -> dict:
        cfg = self.config
        version = str(version_id or "").strip()
        if not version:
            return {"ok": False, "message": "请先选择一个版本"}
        report = self.launch_check(version, instance_id)
        if report.get("blocked") and not force:
            return {
                "ok": False,
                "message": "启动前检查未通过",
                "blocked": report["blocked"],
                "warnings": report.get("warnings", []),
            }

        def worker(job: Job):
            job.progress(5, "启动前检查", "启动")
            payload = self._launch_now(version, instance_id, job)
            payload.pop("session", None)
            job.progress(100, "已启动", "已完成")
            action = str(cfg.after_launch_action or "nothing")
            if self.window is not None and action in ("hide", "close"):
                try:
                    if action == "close":
                        self.window.destroy()
                    else:
                        self.window.hide()
                except Exception:  # noqa: BLE001 - 窗口动作失败不影响游戏
                    pass
            return payload

        job = _spawn("launch", f"启动 {version}", worker)
        return {"ok": True, "job": job.id, "warnings": report.get("warnings", [])}

    def launch_batch(
        self, version_ids: list[str], instance_id: str = "", force: bool = False
    ) -> dict:
        """多选启动：逐个启动并等待上一个进程退出，任一失败继续下一个。"""
        ids: list[str] = []
        for raw in version_ids or []:
            text = str(raw or "").strip()
            if text and text not in ids:
                ids.append(text)
        if not ids:
            return {"ok": False, "message": "请先选择要启动的版本"}
        ids = ids[:10]

        def worker(job: Job):
            results = []
            for index, vid in enumerate(ids):
                if job.cancel.is_set():
                    job.log("已取消批量启动")
                    break
                job.stage = f"批量启动 {index + 1}/{len(ids)}"
                job.progress(index * 100 / len(ids), f"正在启动 {vid}", job.stage)
                try:
                    payload = self._launch_now(vid, instance_id, None)
                    session = payload.pop("session", None)
                    results.append({"version": vid, "ok": True})
                    job.log(f"{vid}：已启动")
                    if session is not None:
                        try:
                            session.process.wait()
                        except Exception:  # noqa: BLE001
                            pass
                except Exception as exc:  # noqa: BLE001
                    results.append({"version": vid, "ok": False, "message": str(exc)})
                    job.log(f"{vid}：启动失败：{exc}")
            job.progress(100, "批量启动结束", "已完成")
            return {"results": results}

        job = _spawn("batch", f"批量启动 {len(ids)} 个版本", worker)
        return {"ok": True, "job": job.id}

    def export_script(self, version_id: str, instance_id: str = "") -> dict:
        """把启动命令导出为 bat / ps1 / sh 脚本。"""
        try:
            plan = self._launch_plan(version_id, instance_id)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"无法生成启动命令：{exc}"}
        target = self._pick_save(
            f"启动-{version_id}.bat",
            ("批处理 (*.bat)", "PowerShell (*.ps1)", "Shell 脚本 (*.sh)"),
        )
        if not target:
            return {"ok": False, "message": "已取消"}
        path = Path(target)
        suffix = path.suffix.lower()
        if suffix not in (".bat", ".ps1", ".sh"):
            suffix = ".bat"
            path = Path(target + suffix)
        try:
            path.write_text(
                _script_text(plan, suffix), encoding="utf-8" if suffix == ".sh" else "utf-8-sig"
            )
            if suffix == ".sh":
                os.chmod(path, 0o755)
        except OSError as exc:
            return {"ok": False, "message": f"写入失败：{exc}"}
        return {"ok": True, "message": f"启动脚本已导出：{path}", "path": str(path)}

    def accel_start(self, text: str, threads: int = 16, directory: str = "") -> dict:
        """下载加速：从一段文本里提取直链，用多线程分段下载器下载。"""
        urls: list[str] = []
        for match in re.finditer(r"https?://[^\s\"'<>]+", str(text or ""), re.I):
            url = match.group(0).rstrip("，。；：！？、,.;:!?)]}）】》>")
            if len(url) > len("https://") and url not in urls:
                urls.append(url)
        if not urls:
            return {"ok": False, "message": "没有识别到可下载链接"}
        cfg = self.config
        target_dir = Path(directory or cfg.download_accel_dir or (DATA_DIR / "downloads"))
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return {"ok": False, "message": f"无法创建保存目录：{exc}"}
        cfg.download_accel_dir = str(target_dir)
        try:
            cfg.save()
        except OSError:
            pass
        jobs = [self._accel_one(url, target_dir, threads) for url in urls[:20]]
        return {"ok": True, "jobs": jobs, "count": len(jobs), "directory": str(target_dir)}

    def _accel_one(self, url: str, target_dir: Path, threads: int) -> dict:
        from ..net import Candidate, Http, probe_download_size

        parsed = urllib.parse.urlsplit(url)
        name = urllib.parse.unquote(Path(parsed.path).name) or "download.bin"
        dest = _unique_dest(target_dir, name)
        workers = max(1, min(64, int(threads or self.config.download_threads or 16)))

        def worker(job: Job):
            try:
                total, ranged = probe_download_size(url)
            except Exception:  # noqa: BLE001 - 探测失败就按未知大小下载
                total, ranged = 0, False
            received = {"bytes": 0}
            lock = threading.Lock()
            last = {"time": 0.0}

            def on_bytes(count: int) -> None:
                with lock:
                    received["bytes"] += int(count or 0)
                    now = time.time()
                    if now - last["time"] < 0.3:
                        return
                    last["time"] = now
                    done = received["bytes"]
                if total:
                    job.progress(min(99, done * 100 / total), f"{_fmt_size(done)} / {_fmt_size(total)}", "下载")
                else:
                    job.progress(0, f"已下载 {_fmt_size(done)}", "下载")

            Http().download(
                [Candidate(url=url, headers={}, source_name="用户链接")],
                dest,
                size=total or None,
                cancel=job.cancel,
                pause=job.pause,
                on_bytes=on_bytes,
                parallel=True,
                workers=workers,
            )
            size = dest.stat().st_size if dest.exists() else received["bytes"]
            job.progress(100, f"已保存到 {dest.name}", "已完成")
            return {"path": str(dest), "size": size, "name": dest.name, "url": url}

        job = _spawn("accel", f"加速下载 {dest.name}", worker)
        job.log(f"来源：{url}")
        return {"id": job.id, "name": dest.name, "url": url}

    def accel_pick_dir(self) -> dict:
        directory = self._pick_dir("选择下载保存目录")
        if not directory:
            return {"ok": False, "message": "已取消"}
        self.config.download_accel_dir = directory
        try:
            self.config.save()
        except OSError:
            pass
        return {"ok": True, "directory": directory}

    def theme_import(self) -> dict:
        path = self._pick_file(("JSON 文件 (*.json)",))
        if not path:
            return {"ok": False, "message": "已取消"}
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return {"ok": False, "message": f"主题文件读取失败：{exc}"}
        theme = themes.register(data)
        if theme is None:
            return {"ok": False, "message": "主题文件格式不正确，需包含 name / colors 字段"}
        return {"ok": True, "name": theme.name, "message": f"已导入主题：{theme.name}"}

    def theme_export(self, name: str) -> dict:
        theme = themes.get(name)
        if theme is None:
            return {"ok": False, "message": "主题不存在"}
        target = self._pick_save(f"{theme.name}.json", ("JSON 文件 (*.json)",))
        if not target:
            return {"ok": False, "message": "已取消"}
        try:
            Path(target).write_text(
                json.dumps(themes.asdict(theme), ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            return {"ok": False, "message": f"写入失败：{exc}"}
        return {"ok": True, "message": f"主题模板已导出：{target}", "path": target}

    def feature_set(self, key: str, enabled: bool) -> dict:
        try:
            self.config.set_feature(str(key), bool(enabled))
        except OSError as exc:
            return {"ok": False, "message": f"保存失败：{exc}"}
        return {"ok": True, "features": self._feature_map()}

    def _feature_map(self) -> dict:
        from ..config import FEATURE_DEFAULTS

        return {key: self.config.feature_enabled(key) for key in FEATURE_DEFAULTS}



    # =====================================================================
    # 内容中心
    # =====================================================================
    def search_content(
        self,
        source: str,
        kind: str,
        query: str = "",
        game_version: str = "",
        loader: str = "",
        offset: int = 0,
        category: str = "",
    ) -> dict:
        try:
            projects = self._content_client().search(
                source,
                kind,
                query=query,
                game_version=game_version,
                loader=loader,
                offset=int(offset or 0),
                limit=20,
            )
            if category:
                from .. import mod_cn

                projects = [
                    project
                    for project in projects
                    if category
                    in mod_cn.categories_for(
                        project.title,
                        project.description,
                        project.categories,
                        project.project_type,
                    )
                ]
            return {"ok": True, "projects": [_project_payload(p) for p in projects]}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"搜索失败：{exc}", "projects": []}

    def content_categories(self) -> dict:
        """PCL 风格的用途分类（全部 / 优化 / 科技 / 魔法…）。"""
        from .. import mod_cn

        return {
            "ok": True,
            "categories": [{"key": key, "label": label} for key, label in mod_cn.CATEGORY_LABELS.items()],
        }

    def content_project_versions(self, source: str, project_id: str) -> dict:
        """轻量获取项目支持的 Minecraft 版本，用于详情页先选版本再加载文件。"""
        try:
            values = self._content_client().project_game_versions(source, project_id)
            return {"ok": True, "versions": [str(v) for v in values]}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"获取支持的版本失败：{exc}", "versions": []}

    def content_dependencies(self, source: str, ids: list[str]) -> dict:
        """按项目 id 批量解析前置 Mod 的名称与图标。"""
        try:
            projects = self._content_client().fetch_projects_by_ids(
                source, [str(item) for item in (ids or [])]
            )
            return {"ok": True, "projects": [_project_payload(p) for p in projects]}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"解析前置失败：{exc}", "projects": []}

    def content_versions(
        self, source: str, project_id: str, game_version: str = "", loader: str = ""
    ) -> dict:
        try:
            versions = self._content_client().versions(
                source, project_id, game_version=game_version, loader=loader
            )
            return {"ok": True, "versions": [_cversion_payload(v) for v in versions[:40]]}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"获取版本失败：{exc}", "versions": []}

    def install_content(
        self,
        source: str,
        project_id: str,
        version_id: str,
        kind: str,
        instance_id: str = "",
    ) -> dict:
        job = _spawn(
            "content",
            f"安装内容 {project_id}",
            lambda j: self._content_job(j, source, project_id, version_id, kind, instance_id),
        )
        return {"ok": True, "job": job.id, "message": "已加入安装队列"}

    def _content_job(
        self, job: Job, source: str, project_id: str, version_id: str, kind: str, instance_id: str
    ) -> dict:
        content = self._content_client()
        game_dir = self._game_dir_of(instance_id)
        job.stage = "获取项目"
        projects = content.fetch_projects_by_ids(source, [project_id], project_type=kind)
        if not projects:
            raise RuntimeError("找不到该项目，可能已被隐藏或删除")
        project = projects[0]
        versions = content.versions(source, project_id)
        version = next((v for v in versions if v.id == version_id), None)
        if version is None:
            raise RuntimeError("找不到指定版本文件")
        job.log(f"[安装] {project.display_title} {version.name}")
        job.stage = "下载并写入游戏目录"
        paths = content.install_content(
            project,
            version,
            game_dir,
            log=job.log,
            cancel=job.cancel,
            install_dependencies=True,
            pause=job.pause,
        )
        job.progress(100.0, f"已写入 {len(paths)} 个文件", "完成")
        return {"files": [str(p) for p in paths]}

    # ---------------- 另存为 ----------------
    def _downloads_dir(self) -> Path:
        folder = Path.home() / "Downloads"
        return folder if folder.is_dir() else Path.home()

    def save_content_as(
        self,
        source: str,
        project_id: str,
        version_id: str,
        kind: str,
        filename: str = "",
    ) -> dict:
        """下载单个内容文件到用户指定的位置，不写入游戏目录。"""
        if not version_id:
            return {"ok": False, "message": "请先选择版本文件"}
        name = _safe_filename(filename or f"{project_id}-{version_id}.jar")
        target = self._pick_save(str(self._downloads_dir() / name), ("所有文件 (*.*)",))
        if not target:
            return {"ok": False, "message": "已取消"}
        job = _spawn(
            "download",
            f"另存为 {name}",
            lambda j: self._save_content_job(j, source, project_id, version_id, kind, Path(target)),
        )
        return {"ok": True, "job": job.id, "message": f"开始另存为 {name}"}

    def _save_content_job(
        self, job: Job, source: str, project_id: str, version_id: str, kind: str, dest: Path
    ) -> dict:
        content = self._content_client()
        job.stage = "获取项目"
        projects = content.fetch_projects_by_ids(source, [project_id], project_type=kind)
        if not projects:
            raise RuntimeError("找不到该项目，可能已被隐藏或删除")
        project = projects[0]
        job.stage = "获取文件信息"
        version = next((v for v in content.versions(source, project_id) if v.id == version_id), None)
        if version is None or version.primary_file is None:
            raise RuntimeError("找不到指定版本文件")
        file = version.primary_file
        job.log(f"[另存为] {project.title} {version.version_number} → {dest}")
        total = int(file.size or 0)
        state = {"bytes": 0, "time": time.monotonic(), "sent": 0}

        def report(count: int) -> None:
            state["bytes"] += count
            now = time.monotonic()
            elapsed = now - state["time"]
            if elapsed < 0.3:
                return
            speed = (state["bytes"] - state["sent"]) / elapsed
            state["time"] = now
            state["sent"] = state["bytes"]
            percent = state["bytes"] / total * 100 if total > 0 else 0.0
            detail = f"{state['bytes'] / 1048576:.1f} MB"
            if total > 0:
                detail += f" / {total / 1048576:.1f} MB"
            job.progress(min(99.0, percent), f"{detail} · {speed / 1048576:.1f} MB/s", "下载中")

        content.save_as(
            source, file, dest, cancel=job.cancel, pause=job.pause, on_bytes=report
        )
        job.progress(100.0, f"已保存至 {dest}", "完成")
        return {"path": str(dest)}

    def save_vanilla_jar(self, version_id: str) -> dict:
        """仅下载某个版本的原版客户端 Jar，另存到用户指定的位置。"""
        version_id = str(version_id or "").strip()
        if not version_id:
            return {"ok": False, "message": "请先选择游戏版本"}
        name = f"Minecraft-{_safe_filename(version_id)}-client.jar"
        target = self._pick_save(
            str(self._downloads_dir() / name), ("Jar 文件 (*.jar)", "所有文件 (*.*)")
        )
        if not target:
            return {"ok": False, "message": "已取消"}
        dest = Path(target)
        if not dest.suffix:
            dest = dest.with_suffix(".jar")
        job = _spawn(
            "download",
            f"客户端 Jar {version_id}",
            lambda j: self._save_vanilla_job(j, version_id, dest),
        )
        return {"ok": True, "job": job.id, "message": "开始下载客户端 Jar"}

    def _save_vanilla_job(self, job: Job, version_id: str, dest: Path) -> dict:
        import json as _json

        from ..net import Http

        job.stage = "获取版本信息"
        client = None
        local = self.config.game_path / "versions" / version_id / f"{version_id}.json"
        if local.is_file():
            try:
                raw = _json.loads(local.read_text(encoding="utf-8"))
                client = (raw.get("downloads") or {}).get("client")
            except (OSError, ValueError):
                client = None
            if isinstance(client, dict) and client.get("url"):
                job.log(f"[另存为] 使用本地版本信息 {local.name}")
        if not (isinstance(client, dict) and client.get("url")):
            sources = self._source_manager()
            manifest, _name, _cached = sources.get_manifest()
            data = manifest.get("data") if isinstance(manifest.get("data"), dict) else manifest
            entry = next(
                (item for item in (data.get("versions") or []) if item.get("id") == version_id),
                None,
            )
            url = str((entry or {}).get("url") or "")
            if not url:
                raise RuntimeError(f"版本清单里找不到 {version_id} 的版本信息")
            errors: list[str] = []
            raw = None
            for candidate in sources.resource_candidates(url):
                try:
                    raw = Http(timeout=30).get_json(candidate)
                    break
                except Exception as exc:  # noqa: BLE001 - 逐个源尝试
                    errors.append(str(exc))
            if raw is None:
                raise RuntimeError("无法获取版本信息：" + "；".join(errors[-3:]))
            client = (raw.get("downloads") or {}).get("client")
        if not (isinstance(client, dict) and client.get("url")):
            raise RuntimeError(f"{version_id} 没有 downloads.client，无法仅下载客户端 Jar")
        url = str(client["url"])
        total = int(client.get("size") or 0)
        job.stage = "下载中"
        state = {"bytes": 0, "time": time.monotonic(), "sent": 0}

        def report(count: int) -> None:
            state["bytes"] += count
            now = time.monotonic()
            elapsed = now - state["time"]
            if elapsed < 0.3:
                return
            speed = (state["bytes"] - state["sent"]) / elapsed
            state["time"] = now
            state["sent"] = state["bytes"]
            percent = state["bytes"] / total * 100 if total > 0 else 0.0
            detail = f"{state['bytes'] / 1048576:.1f} MB"
            if total > 0:
                detail += f" / {total / 1048576:.1f} MB"
            job.progress(min(99.0, percent), f"{detail} · {speed / 1048576:.1f} MB/s", "下载中")

        Http(timeout=60).download_to_path(
            self._source_manager().resource_candidates(url),
            dest,
            size=total,
            sha1=str(client.get("sha1") or ""),
            cancel=job.cancel,
            pause=job.pause,
            log=job.log,
            on_bytes=report,
        )
        job.progress(100.0, f"已保存至 {dest}", "完成")
        return {"path": str(dest)}

    def save_loader_installer(
        self, kind: str, mc_version: str, loader_version: str = ""
    ) -> dict:
        """仅下载某个 Mod 加载器的官方安装器，另存到用户指定的位置。"""
        from ..modloader import LOADER_LABELS, loader_installer_candidates

        kind = str(kind or "").strip()
        mc = str(mc_version or "").strip()
        if kind not in LOADER_LABELS:
            return {"ok": False, "message": "该加载器没有可单独下载的安装器"}
        if not mc:
            return {"ok": False, "message": "请先选择 Minecraft 版本"}
        ver = _safe_filename(loader_version or "latest")
        mc_name = _safe_filename(mc)
        names = {
            "fabric": f"fabric-installer-{ver}.jar",
            "quilt": f"quilt-installer-{ver}.jar",
            "forge": f"forge-{mc_name}-{ver}-installer.jar",
            "neoforge": f"neoforge-{ver}-installer.jar",
            "liteloader": f"liteloader-{mc_name}-{ver}.jar",
        }
        name = names.get(kind, f"{kind}-installer-{ver}.jar")
        target = self._pick_save(
            str(self._downloads_dir() / name), ("Jar 文件 (*.jar)", "所有文件 (*.*)")
        )
        if not target:
            return {"ok": False, "message": "已取消"}
        dest = Path(target)
        if not dest.suffix:
            dest = dest.with_suffix(".jar")
        job = _spawn(
            "download",
            f"加载器安装器 {kind}",
            lambda j: self._save_loader_job(j, kind, mc, loader_version, dest),
        )
        return {"ok": True, "job": job.id, "message": f"开始下载 {name}"}

    def _save_loader_job(
        self, job: Job, kind: str, mc_version: str, loader_version: str, dest: Path
    ) -> dict:
        from ..modloader import loader_installer_candidates
        from ..net import Http

        job.stage = "解析下载地址"
        _name, candidates = loader_installer_candidates(kind, mc_version, loader_version)
        job.stage = "下载中"
        state = {"bytes": 0, "time": time.monotonic(), "sent": 0}

        def report(count: int) -> None:
            state["bytes"] += count
            now = time.monotonic()
            elapsed = now - state["time"]
            if elapsed < 0.3:
                return
            speed = (state["bytes"] - state["sent"]) / elapsed
            state["time"] = now
            state["sent"] = state["bytes"]
            job.progress(0.0, f"{state['bytes'] / 1048576:.1f} MB · {speed / 1048576:.1f} MB/s", "下载中")

        Http(timeout=60).download_to_path(
            candidates,
            dest,
            cancel=job.cancel,
            pause=job.pause,
            log=job.log,
            on_bytes=report,
        )
        job.progress(100.0, f"已保存至 {dest}", "完成")
        return {"path": str(dest)}

    def search_by_ids(self, source: str, project_ids: list[str]) -> dict:
        try:
            projects = self._content_client().fetch_projects_by_ids(source, list(project_ids))
            return {"ok": True, "projects": [_project_payload(p) for p in projects]}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": str(exc), "projects": []}

    # =====================================================================
    # 账号
    # =====================================================================
    def accounts(self) -> dict:
        store = self._store()
        return {
            "selected": store.selected_id,
            "list": [
                {
                    "id": a.id,
                    "name": a.name,
                    "type": a.type,
                    "type_label": a.type_label,
                    "uuid": a.uuid,
                    "server": a.auth_server,
                    "expired": a.token_expired,
                }
                for a in store.accounts
            ],
        }

    def select_account(self, account_id: str) -> dict:
        store = self._store()
        if store.get(account_id) is None:
            return {"ok": False, "message": "账号不存在"}
        store.set_selected(account_id)
        self.config.selected_account_id = account_id
        try:
            self.config.save()
        except OSError:
            pass
        return {"ok": True, "accounts": self.accounts()}

    def add_offline(self, name: str) -> dict:
        name = str(name or "").strip()
        if not name:
            return {"ok": False, "message": "请输入玩家名"}
        store = self._store()
        account = store.make_offline(name)
        store.add(account)
        store.set_selected(account.id)
        self.config.player_name = name
        self.config.selected_account_id = account.id
        try:
            self.config.save()
        except OSError:
            pass
        return {"ok": True, "accounts": self.accounts()}

    def remove_account(self, account_id: str) -> dict:
        store = self._store()
        if len(store.accounts) <= 1:
            return {"ok": False, "message": "至少保留一个账号"}
        store.remove(account_id)
        return {"ok": True, "accounts": self.accounts()}

    def ms_login_start(self) -> dict:
        try:
            from ..auth import MicrosoftAuth

            flow = MicrosoftAuth(self.config.microsoft_client_id).start_device_flow()
            self._ms_flow = flow
            return {
                "ok": True,
                "code": flow.user_code,
                "url": flow.verification_uri,
                "message": flow.message,
                "expires": flow.expires_in,
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"微软登录失败：{exc}"}

    def ms_login_poll(self) -> dict:
        flow = getattr(self, "_ms_flow", None)
        if flow is None:
            return {"ok": False, "message": "请先获取设备码"}
        job = _spawn("account", "微软正版登录", lambda j: self._ms_poll_job(j, flow))
        return {"ok": True, "job": job.id, "message": "正在等待微软授权…"}

    def _ms_poll_job(self, job: Job, flow) -> dict:
        from ..auth import MicrosoftAuth

        account = MicrosoftAuth(self.config.microsoft_client_id).poll(flow, job.cancel, job.log)
        store = self._store()
        existing = next((a for a in store.accounts if a.id == account.id), None)
        if existing is not None:
            store.update(account)
        else:
            store.add(account)
        store.set_selected(account.id)
        return {"account": account.name}

    def authlib_login(self, server: str, username: str, password: str) -> dict:
        job = _spawn(
            "account",
            f"外置登录 {username}",
            lambda j: self._authlib_job(j, server, username, password),
        )
        return {"ok": True, "job": job.id, "message": "正在登录外置账号…"}

    def _authlib_job(self, job: Job, server: str, username: str, password: str) -> dict:
        from ..auth import authlib_login

        job.log(f"[外置登录] {server}")
        account = authlib_login(server, username, password)
        store = self._store()
        existing = next((a for a in store.accounts if a.id == account.id), None)
        if existing is not None:
            store.update(account)
        else:
            store.add(account)
        store.set_selected(account.id)
        return {"account": account.name}

    def refresh_account(self, account_id: str) -> dict:
        from ..auth import Account, MicrosoftAuth, AuthError

        store = self._store()
        account = store.get(account_id)
        if account is None or account.type != "microsoft":
            return {"ok": False, "message": "只有微软账号支持刷新"}
        try:
            fresh = MicrosoftAuth(self.config.microsoft_client_id).refresh(account)
            store.update(fresh)
            return {"ok": True, "message": "令牌已刷新", "accounts": self.accounts()}
        except AuthError as exc:
            return {"ok": False, "message": str(exc)}

    # =====================================================================
    # 皮肤
    # =====================================================================
    def import_skin(self, model: str = "", overwrite: bool = True) -> dict:
        path = self._pick_file(("皮肤图片 (*.png)", "所有文件 (*.*)"))
        if not path:
            return {"ok": False, "message": "未选择皮肤文件"}
        return self.apply_skin_file(path, model=model, overwrite=overwrite)

    def apply_skin_file(self, path: str, model: str = "", overwrite: bool = True) -> dict:
        from ..auth import validate_skin_file
        from ..skinpack import SkinPackError, apply_player_skin_bytes, purge_old_packs

        try:
            width, height = validate_skin_file(path)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"不是有效的皮肤文件：{exc}"}
        store = self._store()
        account = store.selected()
        chosen = "slim" if str(model).lower() in ("slim", "alex") else "classic"
        active = chosen if model else (account.skin_model or "classic")
        try:
            target = DATA_DIR / "skins" / f"{account.name}.png"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            self._preview_cache.pop(str(target), None)
            # 入库时记录复制后的稳定路径，避免原文件被移动后主页缩略图失效
            entry = skins.remember(target, active, name=Path(path).stem)
        except OSError as exc:
            return {"ok": False, "message": f"保存皮肤失败：{exc}"}
        account.skin_path = str(target)
        account.skin_model = active
        store.update(account)
        # 自动检测已安装的游戏版本：覆盖式导入时逐个版本生成适配资源包，
        # 新装的版本也会在安装完成回调里重新调用这里，保证皮肤自动生效。
        # 这里直接用 skinpack 写入（不再依赖 import_offline_skin），
        # 正版 / 外置登录账号也能生效，并按各版本 pack_format 生成正确的包。
        versions: list[str] = []
        if overwrite:
            for item in self.scan_versions():
                vid = str(item.get("id") or "")
                if vid and vid not in versions:
                    versions.append(vid)
        target_version = self.config.default_version_id or ""
        if target_version and target_version not in versions:
            versions.append(target_version)
        if not versions:
            versions.append("")
        try:
            image = target.read_bytes()
        except OSError as exc:
            return {"ok": False, "message": f"读取皮肤失败：{exc}"}
        applied = 0
        for version in versions:
            try:
                targets = self.config.resolve_game_dirs(version).skin_targets()
            except Exception:  # noqa: BLE001
                targets = [self.config.game_path]
            for game_dir in targets:
                try:
                    purge_old_packs(Path(game_dir))
                    apply_player_skin_bytes(
                        image,
                        account.name,
                        active,
                        Path(game_dir),
                        version,
                        install_pack=True,
                        enable_pack=True,
                    )
                    applied += 1
                except (SkinPackError, OSError):
                    continue
        return {
            "ok": True,
            "message": f"皮肤已应用（{width}×{height} · {'纤细 Alex' if active == 'slim' else '经典 Steve'}，已适配 {applied} 个游戏目录）",
            "model": active,
            "preview": self.preview(str(target)),
            "skins": [
                {"path": e.path, "name": e.name, "model": e.model}
                for e in skins.entries(limit=12)
            ],
        }

    def apply_skin_path(self, path: str, model: str = "", overwrite: bool = True) -> dict:
        return self.apply_skin_file(path, model=model, overwrite=overwrite)

    def skin_save_editor(
        self, data_url: str, name: str = "", model: str = "classic", apply: bool = True
    ) -> dict:
        """保存像素工坊结果：PNG 入库（皮肤库）并可立即应用。"""
        import base64
        import binascii
        import re

        from ..skins import remember

        text = str(data_url or "")
        if "," not in text or "base64" not in text.split(",", 1)[0]:
            return {"ok": False, "message": "无效的图片数据"}
        payload = text.split(",", 1)[1]
        try:
            raw = base64.b64decode(payload)
        except (binascii.Error, ValueError):
            return {"ok": False, "message": "图片数据损坏"}
        if len(raw) < 200:
            return {"ok": False, "message": "图片数据为空"}
        safe = re.sub(r"[^\w\-]+", "_", (name or "").strip()) or time.strftime("skin-%Y%m%d-%H%M%S")
        folder = DATA_DIR / "skins" / "editor"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{safe}.png"
        try:
            target.write_bytes(raw)
        except OSError as exc:
            return {"ok": False, "message": f"写入失败：{exc}"}
        entry = remember(target, "slim" if str(model).lower() in ("slim", "alex") else "classic")
        result = {"ok": True, "path": entry.path, "message": "已保存到皮肤库"}
        if apply:
            applied = self.apply_skin_path(entry.path)
            if not applied.get("ok"):
                result["message"] = applied.get("message", "已保存，但应用到账号失败")
        return result

    def skin_export_png(self, data_url: str, name: str = "") -> dict:
        """把工坊画布导出为 PNG（另存为）。"""
        import base64
        import binascii
        import re

        text = str(data_url or "")
        if "," not in text or "base64" not in text.split(",", 1)[0]:
            return {"ok": False, "message": "无效的图片数据"}
        try:
            raw = base64.b64decode(text.split(",", 1)[1])
        except (binascii.Error, ValueError):
            return {"ok": False, "message": "图片数据损坏"}
        safe = re.sub(r"[^\w\-]+", "_", (name or "skin").strip()) or "skin"
        target = self._pick_save(f"{safe}.png", ("PNG 图片 (*.png)",))
        if not target:
            return {"ok": False, "message": "未选择保存位置"}
        try:
            Path(target).write_bytes(raw)
        except OSError as exc:
            return {"ok": False, "message": f"导出失败：{exc}"}
        return {"ok": True, "message": f"已导出：{target}", "path": str(target)}

    def skin_model(self, model: str) -> dict:
        """切换 Steve（classic，4px 手臂）/ Alex（slim，3px 手臂）模型并立即生效。"""
        from ..auth import import_offline_skin

        store = self._store()
        account = store.selected()
        account.skin_model = "slim" if str(model).lower() in ("slim", "alex") else "classic"
        store.update(account)
        if account.skin_path:
            try:
                import_offline_skin(
                    account,
                    self.config.game_path,
                    log=None,
                    version_id=self.config.default_version_id or "",
                )
            except Exception:  # noqa: BLE001 - 写入失败不应阻塞界面
                pass
        return {"ok": True, "model": account.skin_model, "message": "已切换皮肤模型"}

    def preview(self, path: str) -> str:
        """本地图片转 data URL（WebView2 的 file:// 页面不能直接读本地文件）。"""
        import base64

        cached = self._preview_cache.get(path)
        if cached:
            return cached
        try:
            payload = Path(path).read_bytes()
        except OSError:
            return ""
        data = "data:image/png;base64," + base64.b64encode(payload).decode()
        if len(self._preview_cache) > 200:
            self._preview_cache.clear()
        self._preview_cache[path] = data
        return data

    def open_skin_library(self) -> dict:
        folder = DATA_DIR / "skins" / "library"
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(str(folder))  # noqa: S606
        return {"ok": True}

    # =====================================================================
    # Java
    # =====================================================================
    def java_scan(self, force: bool = True) -> dict:
        try:
            self._java_list(force)
            return {"ok": True, "java": self._java_summary()}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"扫描 Java 失败：{exc}"}

    def java_select(self, path: str) -> dict:
        self.config.java_path = str(path or "")
        if path and path not in self.config.java_manual_paths:
            self.config.java_manual_paths.append(str(path))
        try:
            self.config.save()
        except OSError:
            pass
        return {"ok": True, "java": self._java_summary()}

    def java_distributions(self) -> list[dict]:
        from ..java import list_java_distributions

        return list_java_distributions()

    def java_versions(self, dist_id: str, major: int, package: str = "jdk") -> dict:
        try:
            from ..java import fetch_distribution_versions

            rows = fetch_distribution_versions(
                dist_id, int(major), limit=10, package=package or "jdk"
            )
            return {"ok": True, "versions": rows}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"获取 Java 版本失败：{exc}", "versions": []}

    def java_install(self, asset: dict, mode: str = "zip") -> dict:
        if not isinstance(asset, dict) or not asset.get("url"):
            return {"ok": False, "message": "版本信息不完整"}
        title = f"安装 Java {asset.get('version') or ''}".strip()
        job = _spawn("java", title, lambda j: self._java_install_job(j, asset, mode))
        return {"ok": True, "job": job.id, "message": title}

    def _java_install_job(self, job: Job, asset: dict, mode: str) -> dict:
        from ..java import download_java, install_java_with_installer, probe_java

        def on_bytes(count: int) -> None:
            total = int(asset.get("size") or 0)
            if total:
                job.progress(min(99.0, count * 100.0 / total), _fmt_size(count) + " / " + _fmt_size(total))

        if mode == "installer":
            java = install_java_with_installer(
                asset,
                log=job.log,
                on_bytes=on_bytes,
                cancel=job.cancel,
                pause=job.pause,
                on_total=lambda total: job.log(f"[Java] 总大小 {_fmt_size(total)}"),
            )
        else:
            target = DATA_DIR / "java"
            java = download_java(
                int(asset.get("major") or 0),
                target,
                log=job.log,
                on_bytes=on_bytes,
                cancel=job.cancel,
                pause=job.pause,
                on_total=lambda total: job.log(f"[Java] 总大小 {_fmt_size(total)}"),
                url=str(asset.get("url") or ""),
                target_name=str(asset.get("name") or ""),
                size=int(asset.get("size") or 0),
            )
        self._javas_at = 0.0
        self._java_list(True)
        return {"path": getattr(java, "path", ""), "version": getattr(java, "version", "")}

    # =====================================================================
    # 基岩版
    # =====================================================================
    def bedrock_catalog(self) -> dict:
        from .. import bedrock

        data = bedrock.load_catalog()
        return {
            "majors": data.get("majors") or [],
            "releases": data.get("releases") or [],
            "installed": bedrock.installed_package(),
            "running": bedrock.is_game_running(),
        }

    def bedrock_fetch_store(self, ring: str = "Retail") -> dict:
        from .. import bedrock

        try:
            raw = bedrock.fetch_store_packages(ring, timeout=40)
            entries = bedrock.build_store_entries(raw)
            return {"ok": True, "entries": entries}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"商店目录获取失败（可能被 Cloudflare 拦截）：{exc}", "entries": []}

    def bedrock_install_local(self) -> dict:
        path = self._pick_file(("基岩版安装包 (*.appx;*.msix;*.appxbundle;*.msixbundle)", "所有文件 (*.*)"))
        if not path:
            return {"ok": False, "message": "未选择安装包"}
        job = _spawn("bedrock", f"安装基岩版 {Path(path).name}", lambda j: self._bedrock_job(j, path))
        return {"ok": True, "job": job.id, "message": "开始部署基岩版"}

    def _bedrock_job(self, job: Job, path: str) -> dict:
        from .. import bedrock

        job.stage = "部署 Appx"
        bedrock.install_appx(Path(path), job.cancel, log=job.log)
        package = bedrock.installed_package() or {}
        return {"version": str(package.get("version") or ""), "message": "基岩版安装完成"}

    def bedrock_install_store(self, entry: dict) -> dict:
        """商店直链安装：多线程下载后用 Add-AppxPackage 部署。"""
        if not isinstance(entry, dict) or not entry.get("url"):
            return {"ok": False, "message": "安装包信息不完整"}
        name = str(entry.get("name") or "bedrock.appx")
        job = _spawn("bedrock", f"下载基岩版 {entry.get('version') or ''}", lambda j: self._bedrock_store_job(j, entry, name))
        return {"ok": True, "job": job.id, "message": "已加入下载队列"}

    def _bedrock_store_job(self, job: Job, entry: dict, name: str) -> dict:
        from .. import bedrock

        dest_dir = DATA_DIR / "bedrock"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / name
        size = int(entry.get("size") or 0)

        def on_bytes(done: int) -> None:
            if size:
                job.progress(min(60.0, done * 60.0 / size), f"{_fmt_size(done)} / {_fmt_size(size)}", "下载安装包")

        job.stage = "下载安装包"
        downloader = bedrock.MultiPartDownload(
            str(entry["url"]),
            dest,
            workers=int(self.config.download_threads or 8),
            size=size,
            cancel=job.cancel,
            pause=job.pause,
            on_bytes=on_bytes,
        )
        downloader.run()
        job.stage = "部署 Appx"
        job.progress(62.0, "正在调用系统安装器（大包可能需要几分钟）")
        bedrock.install_appx(dest, job.cancel, log=job.log)
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            pass
        package = bedrock.installed_package() or {}
        return {"version": str(package.get("version") or "")}

    def bedrock_open_page(self, url: str) -> dict:
        if not str(url or "").startswith(("http://", "https://")):
            return {"ok": False, "message": "链接无效"}
        os.startfile(url)  # noqa: S606
        return {"ok": True}

    def bedrock_launch(self) -> dict:
        from .. import bedrock

        ok, message = bedrock.launch_installed()
        return {"ok": ok, "message": message}

    def bedrock_uninstall(self) -> dict:
        from .. import bedrock

        ok, message = bedrock.uninstall_installed()
        return {"ok": ok, "message": message}

    # =====================================================================
    # 设置
    # =====================================================================
    def settings_get(self) -> dict:
        from ..config import AFTER_LAUNCH_ACTIONS, ISOLATION_LABELS, PROCESS_PRIORITIES
        from ..i18n import SUPPORTED_LANGUAGES

        cfg = self.config
        return {
            "player_name": cfg.player_name,
            "game_dir": str(cfg.game_path),
            "memory_mb": int(cfg.memory_mb or 4096),
            "java_path": cfg.java_path,
            "download_threads": int(cfg.download_threads or 16),
            "download_speed_limit": int(cfg.download_speed_limit or 0),
            "modrinth_cdn_mirror": cfg.modrinth_cdn_mirror,
            "curseforge_api_base": cfg.curseforge_api_base,
            "curseforge_api_key": cfg.curseforge_api_key,
            "curseforge_cdn_mirror": cfg.curseforge_cdn_mirror,
            "microsoft_client_id": cfg.microsoft_client_id,
            "authlib_injector_url": cfg.authlib_injector_url,
            "sources": self.sources_list(),
            "start_animation": bool(cfg.start_animation),
            "extra_jvm_args": cfg.extra_jvm_args,
            "window_title": cfg.window_title,
            "language": cfg.language,
            "languages": [{"code": c, "name": n} for c, n in SUPPORTED_LANGUAGES.items()],
            "theme_name": cfg.theme_name,
            "color_mode": getattr(cfg, "color_mode", "light"),
            "background_image": cfg.background_image,
            "dynamic_wallpaper": cfg.dynamic_wallpaper,
            "ui_animations": bool(cfg.ui_animations),
            "glass_effect": bool(cfg.glass_effect),
            "glass_see_through": bool(cfg.glass_see_through),
            "glass_strength": int(cfg.glass_strength or 62),
            "glass_blur": int(getattr(cfg, "glass_blur", 20) or 0),
            "accent_color": cfg.accent_color,
            "text_color": getattr(cfg, "text_color", ""),
            "isolation_mode": cfg.isolation_mode,
            "isolation_options": ISOLATION_LABELS,
            "process_priority": cfg.process_priority,
            "priority_options": PROCESS_PRIORITIES,
            "after_launch_action": cfg.after_launch_action,
            "after_options": AFTER_LAUNCH_ACTIONS,
            "proxy_enabled": bool(cfg.proxy_enabled),
            "proxy_url": cfg.proxy_url,
            "proxy_jvm": bool(cfg.proxy_jvm),
            "auto_backup_saves": bool(cfg.auto_backup_saves),
            "backup_dir": cfg.backup_dir,
            "close_to_tray": bool(cfg.close_to_tray),
            "agreement_prompt": bool(cfg.agreement_prompt),
            "selected_source_id": cfg.selected_source_id,
            "download_threads_max": 328,
            "smart_jvm": bool(cfg.smart_jvm),
            "opt_pre_touch": bool(cfg.opt_pre_touch),
            "opt_fixed_heap": bool(cfg.opt_fixed_heap),
            "preload_jvm": bool(cfg.preload_jvm),
            "preload_java_path": cfg.preload_java_path,
            "support_prompt_every": int(cfg.support_prompt_every or 10),
            "features": self._feature_map(),
            "frame_mode": cfg.frame_mode,
            "frame_locked": bool(cfg.frame_locked),
            "game_dirs": [{"id": e.id, "name": e.name, "path": e.path} for e in (cfg.game_dirs or [])],
            "active_game_dir": cfg.active_game_dir,
        }

    def settings_set(self, patch: dict) -> dict:
        """保存设置；只接受白名单字段，保证前后端字段一致。"""
        if not isinstance(patch, dict):
            return {"ok": False, "message": "参数无效"}
        cfg = self.config
        changed = False
        for key, value in patch.items():
            if key in ("memory_mb", "download_threads", "download_speed_limit"):
                try:
                    number = int(value)
                except (TypeError, ValueError):
                    continue
                if key == "memory_mb":
                    cfg.memory_mb = max(512, min(65536, number))
                elif key == "download_threads":
                    cfg.download_threads = max(1, min(328, number))
                else:
                    cfg.download_speed_limit = max(0, number)
                changed = True
            elif key == "glass_strength":
                try:
                    cfg.glass_strength = max(0, min(100, int(value)))
                except (TypeError, ValueError):
                    continue
                changed = True
            elif key == "glass_blur":
                try:
                    cfg.glass_blur = max(0, min(40, int(value)))
                except (TypeError, ValueError):
                    continue
                changed = True
            elif key == "accent_color":
                text = str(value or "").strip()
                if not re.fullmatch(r"#[0-9a-fA-F]{6}", text):
                    continue
                cfg.accent_color = text.lower()
                changed = True
            elif key == "text_color":
                text = str(value or "").strip()
                if text and not re.fullmatch(r"#[0-9a-fA-F]{6}", text):
                    continue
                cfg.text_color = text.lower()
                changed = True
            elif key == "theme_name":
                name = str(value or "").strip()
                if name not in themes.all_themes():
                    continue
                theme = themes.get(name)
                cfg.theme_name = name
                if themes.is_light(theme):
                    cfg.light_theme_name = name
                    cfg.color_mode = "light"
                else:
                    cfg.dark_theme_name = name
                    cfg.color_mode = "dark"
                changed = True
            elif key in (
                "player_name",
                "java_path",
                "language",
                "background_image",
                "dynamic_wallpaper",
                "isolation_mode",
                "process_priority",
                "after_launch_action",
                "proxy_url",
                "modrinth_cdn_mirror",
                "curseforge_api_base",
                "curseforge_api_key",
                "curseforge_cdn_mirror",
                "microsoft_client_id",
                "authlib_injector_url",
                "extra_jvm_args",
                "window_title",
            ):
                setattr(cfg, key, str(value))
                changed = True
            elif key in (
                "ui_animations",
                "glass_effect",
                "glass_see_through",
                "proxy_enabled",
                "proxy_jvm",
                "auto_backup_saves",
                "close_to_tray",
                "start_animation",
                "agreement_prompt",
                "smart_jvm",
                "opt_pre_touch",
                "opt_fixed_heap",
                "preload_jvm",
            ):
                if hasattr(cfg, key):
                    setattr(cfg, key, bool(value))
                changed = True
            elif key == "preload_java_path":
                cfg.preload_java_path = str(value or "")
                changed = True
            elif key == "support_prompt_every":
                try:
                    cfg.support_prompt_every = max(1, min(1000, int(value)))
                except (TypeError, ValueError):
                    pass
                changed = True
        if changed:
            if "download_threads" in patch or "download_speed_limit" in patch:
                from ..net import set_default_download_workers, set_download_speed_limit

                set_default_download_workers(int(cfg.download_threads or 16))
                set_download_speed_limit(int(cfg.download_speed_limit or 0))
            if any(
                k in patch
                for k in (
                    "modrinth_cdn_mirror",
                    "curseforge_api_base",
                    "curseforge_api_key",
                    "curseforge_cdn_mirror",
                    "proxy_enabled",
                    "proxy_url",
                    "microsoft_client_id",
                    "authlib_injector_url",
                )
            ):
                # 内容源 / 代理 / 登录参数变化后丢弃旧客户端，下次调用按新配置重建
                self._content = None
                self._sources = None
            try:
                cfg.save()
            except OSError as exc:
                return {"ok": False, "message": f"保存失败：{exc}"}
            if "glass_see_through" in patch or "glass_strength" in patch or "glass_blur" in patch:
                try:
                    self.glass_apply()
                except Exception:  # noqa: BLE001 - 原生毛玻璃失败不应影响设置保存
                    pass
        if "theme_name" in patch or "accent_color" in patch or "text_color" in patch:
            return {"ok": True, "palette": self._palette()}
        return {"ok": True}

    # ---------- 下载源管理（与经典版设置页共用同一份配置） ----------
    def sources_list(self) -> list[dict]:
        cfg = self.config
        items = []
        for src in cfg.sources:
            data = src.to_dict()
            data["selected"] = src.id == cfg.selected_source_id
            items.append(data)
        return items

    def source_save(self, data: dict, source_id: str = "") -> dict:
        from ..config import DownloadSource

        cfg = self.config
        if not isinstance(data, dict):
            return {"ok": False, "message": "参数无效"}
        manifest = str(data.get("manifest_url") or "").strip()
        name = str(data.get("name") or "").strip() or "自定义源"
        mapping = str(data.get("mapping") or "none")
        if not manifest.startswith(("http://", "https://")):
            return {"ok": False, "message": "版本清单地址必须是 http/https 链接"}
        if mapping != "none" and not str(data.get("download_base") or "").strip():
            return {"ok": False, "message": "该映射方式需要填写有效的镜像根地址"}
        target = cfg.get_source(source_id) if source_id else None
        if target is not None and target.builtin:
            return {"ok": False, "message": "内置源不可编辑，可新建自定义源"}
        if target is None:
            sid = cfg.new_source_id()
            payload = dict(data, id=sid, builtin=False)
            cfg.sources.append(DownloadSource.from_dict(payload, sid))
        else:
            payload = dict(data, id=target.id, builtin=False)
            updated = DownloadSource.from_dict(payload, target.id)
            cfg.sources = [updated if s.id == target.id else s for s in cfg.sources]
        try:
            cfg.save()
        except OSError as exc:
            return {"ok": False, "message": f"保存失败：{exc}"}
        self._sources = None
        return {"ok": True, "sources": self.sources_list()}

    def source_remove(self, source_id: str) -> dict:
        cfg = self.config
        target = cfg.get_source(source_id)
        if target is None:
            return {"ok": False, "message": "下载源不存在"}
        if target.builtin:
            return {"ok": False, "message": "内置源不可删除"}
        cfg.sources = [s for s in cfg.sources if s.id != source_id]
        if cfg.selected_source_id == source_id:
            remaining = [s for s in cfg.sources if s.enabled]
            cfg.selected_source_id = remaining[0].id if remaining else "official"
        try:
            cfg.save()
        except OSError as exc:
            return {"ok": False, "message": f"保存失败：{exc}"}
        self._sources = None
        return {"ok": True, "sources": self.sources_list()}

    def source_toggle(self, source_id: str) -> dict:
        cfg = self.config
        target = cfg.get_source(source_id)
        if target is None:
            return {"ok": False, "message": "下载源不存在"}
        if target.builtin:
            return {"ok": False, "message": "内置源始终可用"}
        target.enabled = not target.enabled
        if not target.enabled and cfg.selected_source_id == target.id:
            remaining = [s for s in cfg.sources if s.enabled]
            cfg.selected_source_id = remaining[0].id if remaining else "official"
        try:
            cfg.save()
        except OSError as exc:
            return {"ok": False, "message": f"保存失败：{exc}"}
        self._sources = None
        return {"ok": True, "sources": self.sources_list()}

    def source_select(self, source_id: str) -> dict:
        cfg = self.config
        target = cfg.get_source(source_id)
        if target is None or not target.enabled:
            return {"ok": False, "message": "该下载源不可用"}
        cfg.selected_source_id = target.id
        try:
            cfg.save()
        except OSError as exc:
            return {"ok": False, "message": f"保存失败：{exc}"}
        self._sources = None
        return {"ok": True, "sources": self.sources_list()}

    def source_test(self, source_id: str) -> dict:
        target = self.config.get_source(source_id)
        if target is None:
            return {"ok": False, "message": "下载源不存在"}
        job = _spawn("source", f"测试源 {target.name}", lambda j: self._source_test_job(j, target.id))
        return {"ok": True, "job": job.id, "message": f"正在测试 {target.name}"}

    def _source_test_job(self, job: Job, source_id: str) -> dict:
        from ..net import test_source

        target = self.config.get_source(source_id)
        if target is None:
            raise RuntimeError("下载源不存在")
        job.stage = "测试清单"
        ok, message = test_source(target)
        job.progress(100.0, message, "完成")
        job.log(f"[源测试] {target.name}：{message}")
        if not ok:
            raise RuntimeError(message)
        return {"name": target.name, "message": message}

    def switch_frame(self, mode: str) -> dict:
        """切换界面框架（classic / webview）；保存后重启启动器生效。"""
        if mode not in ("classic", "webview"):
            return {"ok": False, "message": "框架参数无效"}
        cfg = self.config
        if cfg.frame_mode == mode:
            return {"ok": True, "unchanged": True, "frame_mode": mode}
        cfg.frame_mode = mode
        cfg.frame_mode_asked = True
        cfg.frame_locked = False
        try:
            cfg.save()
        except OSError as exc:
            return {"ok": False, "message": f"保存失败：{exc}"}
        return {"ok": True, "frame_mode": mode, "restart": True}

    def restart_app(self) -> dict:
        """保存数据后以相同参数重启启动器（切换框架后生效）。"""
        cfg = self.config
        try:
            cfg.cancel_debounced_save()
            cfg.save()
        except Exception:  # noqa: BLE001 - 退出阶段不再抛异常
            pass
        _schedule_restart()
        os._exit(0)

    def _palette(self, theme_name: str = "") -> dict:
        """主题调色板 + 用户自定义强调色：取色板改的 accent_color 优先于主题内置色。"""
        name = theme_name or getattr(self.config, "theme_name", "") or "晨光"
        theme = themes.get(name)
        palette = themes.palette(theme)
        light = themes.is_light(theme)
        accent = str(getattr(self.config, "accent_color", "") or "").strip()
        if re.fullmatch(r"#[0-9a-fA-F]{6}", accent):
            palette["accent"] = accent.lower()
            palette["accent_text"] = themes.relight(accent.lower(), -18 if light else 22)
            palette["selected"] = themes.mix(palette["card"], accent.lower(), 0.22)
        text = str(getattr(self.config, "text_color", "") or "").strip()
        if re.fullmatch(r"#[0-9a-fA-F]{6}", text):
            palette["text"] = text.lower()
            palette["muted"] = themes.mix(palette["background"], text.lower(), 0.55)
            palette["muted_dim"] = themes.mix(palette["background"], palette["muted"], 0.65)
        palette["light"] = light
        return palette

    def set_color_mode(self, mode: str) -> dict:
        """切换明亮 / 黑暗模式：两套主题分别记忆，切回来还是原来的观感。"""
        want = "light" if str(mode or "").lower() == "light" else "dark"
        cfg = self.config
        current = themes.get(cfg.theme_name)
        if themes.is_light(current):
            cfg.light_theme_name = cfg.theme_name
        else:
            cfg.dark_theme_name = cfg.theme_name
        cfg.color_mode = want
        target = cfg.light_theme_name if want == "light" else cfg.dark_theme_name
        target_theme = themes.all_themes().get(target)
        if target_theme is None or themes.is_light(target_theme) != (want == "light"):
            target = themes.first_of_mode(want)
        cfg.theme_name = target
        try:
            cfg.save()
        except OSError as exc:
            return {"ok": False, "message": f"保存失败：{exc}"}
        # 窗体底板颜色跟着明暗模式走，切换后立即重绘，避免日间模式还透出深色底
        try:
            self.glass_apply()
        except Exception:  # noqa: BLE001
            pass
        return {
            "ok": True,
            "mode": want,
            "theme": target,
            "palette": self._palette(target),
        }

    def set_theme(self, name: str) -> dict:
        if name not in themes.all_themes():
            return {"ok": False, "message": "主题不存在"}
        theme = themes.get(name)
        self.config.theme_name = name
        if themes.is_light(theme):
            self.config.light_theme_name = name
            self.config.color_mode = "light"
        else:
            self.config.dark_theme_name = name
            self.config.color_mode = "dark"
        self.config.accent_color = theme.accent or self.config.accent_color
        try:
            self.config.save()
        except OSError:
            pass
        return {"ok": True, "palette": self._palette(name), "mode": self.config.color_mode}

    def pick_background(self) -> dict:
        """选择自定义背景图；预览由前端用 preview() 转 data URL 呈现。"""
        path = self._pick_file(("图片 (*.png;*.jpg;*.jpeg;*.webp)", "所有文件 (*.*)"))
        if not path:
            return {"ok": False, "message": "未选择图片"}
        self.config.background_image = str(path)
        try:
            self.config.save()
        except OSError as exc:
            return {"ok": False, "message": f"保存失败：{exc}"}
        return {"ok": True, "path": str(path)}

    # ---------- 动态壁纸 ----------
    def _ensure_media_port(self) -> int:
        if self._media_port:
            return self._media_port
        with self._media_lock:
            if not self._media_port:
                try:
                    self._media_port = _start_media_server()
                except OSError:
                    self._media_port = 0
        return self._media_port

    def _wallpaper_url(self, path: str) -> tuple[str, str]:
        target = Path(str(path or ""))
        suffix = target.suffix.lower()
        if suffix not in _WALLPAPER_TYPES or not target.is_file():
            return "", ""
        kind = "video" if _WALLPAPER_TYPES[suffix].startswith("video/") else "image"
        port = self._ensure_media_port()
        if not port:
            return "", kind
        return f"http://127.0.0.1:{port}/media?p={urllib.parse.quote(str(target))}", kind

    def pick_dynamic_wallpaper(self) -> dict:
        """选择动态壁纸：视频（MP4 / WebM）或动图（GIF / WebP）。"""
        path = self._pick_file(
            (
                "动态壁纸 (*.mp4;*.webm;*.gif;*.webp)",
                "视频 (*.mp4;*.webm)",
                "动图 (*.gif;*.webp)",
                "所有文件 (*.*)",
            )
        )
        if not path:
            return {"ok": False, "message": "未选择动态壁纸"}
        url, kind = self._wallpaper_url(path)
        if not url:
            return {"ok": False, "message": "该文件不是受支持的视频或动图"}
        self.config.dynamic_wallpaper = str(path)
        try:
            self.config.save()
        except OSError as exc:
            return {"ok": False, "message": f"保存失败：{exc}"}
        return {"ok": True, "path": str(path), "url": url, "kind": kind}

    def clear_dynamic_wallpaper(self) -> dict:
        self.config.dynamic_wallpaper = ""
        try:
            self.config.save()
        except OSError:
            pass
        return {"ok": True}

    def wallpaper_media(self, path: str = "") -> dict:
        target = str(path or self.config.dynamic_wallpaper or "")
        if not target:
            return {"ok": False, "message": "未设置动态壁纸"}
        url, kind = self._wallpaper_url(target)
        if not url:
            return {"ok": False, "message": "动态壁纸文件不存在或格式不支持"}
        return {"ok": True, "url": url, "kind": kind}

    # ---------- 扩展（插件） ----------
    def _extension_manifests(self) -> list[dict]:
        try:
            self._extensions_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        items: list[dict] = []
        disabled = set(self.config.extensions_disabled or [])
        for folder in sorted(self._extensions_dir.iterdir()):
            if not folder.is_dir():
                continue
            entry = folder / "extension.json"
            if not entry.is_file():
                continue
            try:
                data = json.loads(entry.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError) as exc:
                items.append(
                    {
                        "id": folder.name,
                        "name": folder.name,
                        "version": "",
                        "author": "",
                        "description": "",
                        "icon": "!",
                        "type": "web",
                        "enabled": False,
                        "error": f"清单读取失败：{exc}",
                    }
                )
                continue
            if not isinstance(data, dict):
                continue
            entry_file = str(data.get("entry") or "index.html")
            html = folder / entry_file
            items.append(
                {
                    "id": folder.name,
                    "name": str(data.get("name") or folder.name),
                    "version": str(data.get("version") or ""),
                    "author": str(data.get("author") or ""),
                    "description": str(data.get("description") or ""),
                    "icon": str(data.get("icon") or "✚")[:2],
                    "type": "web",
                    "enabled": folder.name not in disabled,
                    "error": "" if html.is_file() else f"入口文件 {entry_file} 不存在",
                }
            )
        # 经典版 Python 插件也列出，方便用户知道插件目录里有什么
        plugins_dir = DATA_DIR / "plugins"
        if plugins_dir.is_dir():
            for path in sorted(plugins_dir.glob("*.py")):
                if path.name.startswith("_"):
                    continue
                name = path.stem
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                    match = re.search(r'PLUGIN_NAME\s*=\s*["\']([^"\']+)', text)
                    if match:
                        name = match.group(1)
                except OSError:
                    pass
                items.append(
                    {
                        "id": "py:" + path.stem,
                        "name": name,
                        "version": "",
                        "author": "",
                        "description": "经典版 Python 插件（页面仅经典版可用）",
                        "icon": "🐍",
                        "type": "python",
                        "enabled": True,
                        "error": "",
                    }
                )
        return items

    def extensions_list(self) -> dict:
        return {"ok": True, "items": self._extension_manifests(), "dir": str(self._extensions_dir)}

    def extension_toggle(self, ext_id: str, enabled: bool = True) -> dict:
        key = str(ext_id or "")
        if not key or key.startswith("py:"):
            return {"ok": False, "message": "该插件不支持在此处启停"}
        disabled = [item for item in (self.config.extensions_disabled or []) if item != key]
        if not enabled:
            disabled.append(key)
        self.config.extensions_disabled = disabled
        try:
            self.config.save()
        except OSError:
            pass
        return {"ok": True, "enabled": bool(enabled)}

    def extension_remove(self, ext_id: str) -> dict:
        key = str(ext_id or "")
        if not key or "/" in key or "\\" in key or key.startswith("."):
            return {"ok": False, "message": "扩展 id 无效"}
        target = (self._extensions_dir / key).resolve()
        try:
            if self._extensions_dir.resolve() not in target.parents:
                return {"ok": False, "message": "扩展 id 无效"}
            if target.is_dir():
                shutil.rmtree(target)
        except OSError as exc:
            return {"ok": False, "message": f"删除失败：{exc}"}
        self.config.extensions_disabled = [
            item for item in (self.config.extensions_disabled or []) if item != key
        ]
        try:
            self.config.save()
        except OSError:
            pass
        return {"ok": True}

    def extension_import(self) -> dict:
        """从 .zip / .mikan-ext 安装扩展；压缩包根部或单层目录里需要有 extension.json。"""
        path = self._pick_file(("扩展包 (*.zip;*.mikan-ext)", "所有文件 (*.*)"))
        if not path:
            return {"ok": False, "message": "已取消"}
        return self._install_extension_zip(Path(path))

    def _install_extension_zip(self, archive: Path) -> dict:
        import tempfile
        import zipfile

        temp = Path(tempfile.mkdtemp(prefix="mikan-ext-"))
        try:
            with zipfile.ZipFile(archive) as bundle:
                for item in bundle.infolist():
                    name = item.filename.replace("\\", "/")
                    if name.startswith("/") or ".." in Path(name).parts:
                        return {"ok": False, "message": "扩展包包含不安全的路径"}
                bundle.extractall(temp)
            root = temp
            if not (root / "extension.json").is_file():
                children = [item for item in root.iterdir() if item.is_dir()]
                if len(children) == 1 and (children[0] / "extension.json").is_file():
                    root = children[0]
            manifest_path = root / "extension.json"
            if not manifest_path.is_file():
                return {"ok": False, "message": "扩展包缺少 extension.json"}
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError) as exc:
                return {"ok": False, "message": f"扩展清单解析失败：{exc}"}
            if not isinstance(manifest, dict):
                return {"ok": False, "message": "扩展清单格式无效"}
            entry = str(manifest.get("entry") or "index.html")
            if not (root / entry).is_file():
                return {"ok": False, "message": f"扩展入口 {entry} 不存在"}
            raw_id = str(manifest.get("id") or root.name)
            ext_id = re.sub(r"[^a-zA-Z0-9_-]", "-", raw_id).strip("-") or "extension"
            target = self._extensions_dir / ext_id
            self._extensions_dir.mkdir(parents=True, exist_ok=True)
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(root, target)
        except (OSError, zipfile.BadZipFile) as exc:
            return {"ok": False, "message": f"安装扩展失败：{exc}"}
        finally:
            shutil.rmtree(temp, ignore_errors=True)
        self.config.extensions_disabled = [
            item for item in (self.config.extensions_disabled or []) if item != ext_id
        ]
        try:
            self.config.save()
        except OSError:
            pass
        return {"ok": True, "id": ext_id, "message": f"扩展「{manifest.get('name') or ext_id}」已安装"}

    def extension_page(self, ext_id: str) -> dict:
        key = str(ext_id or "")
        if "/" in key or "\\" in key:
            return {"ok": False, "message": "扩展 id 无效"}
        folder = self._extensions_dir / key
        manifest_path = folder / "extension.json"
        if not manifest_path.is_file():
            return {"ok": False, "message": "扩展不存在"}
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            entry = folder / str(manifest.get("entry") or "index.html")
            html = entry.read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError) as exc:
            return {"ok": False, "message": f"扩展读取失败：{exc}"}
        name = str(manifest.get("name") or key)
        return {"ok": True, "id": key, "name": name, "html": html}

    def extension_open_folder(self) -> dict:
        try:
            self._extensions_dir.mkdir(parents=True, exist_ok=True)
            os.startfile(str(self._extensions_dir))  # noqa: S606
        except OSError as exc:
            return {"ok": False, "message": str(exc)}
        return {"ok": True}

    def set_game_dir(self, path: str = "") -> dict:
        if not path:
            path = self._pick_dir("选择 Minecraft 数据目录") or ""
        if not path:
            return {"ok": False, "message": "未选择目录"}
        self.config.game_dir = path
        try:
            self.config.save()
        except OSError as exc:
            return {"ok": False, "message": f"保存失败：{exc}"}
        self._refresh()
        return {"ok": True, "path": path, "versions": self.scan_versions()}

    def add_game_dir(self, name: str, path: str = "") -> dict:
        if not path:
            path = self._pick_dir("选择 Minecraft 数据目录") or ""
        if not path:
            return {"ok": False, "message": "未选择目录"}
        root = detect_game_root(path)
        existing = next(
            (
                entry
                for entry in self.config.game_dirs
                if os.path.normcase(os.path.normpath(entry.path))
                == os.path.normcase(os.path.normpath(str(root)))
            ),
            None,
        )
        if existing is None:
            entry = self.config.add_game_dir(name or root.name or "新目录", str(root))
        else:
            entry = existing
        # 添加后自动切换并重新扫描，目录里的游戏按文件夹名直接出现在已安装版本
        self.config.select_game_dir(entry.id)
        self._refresh()
        versions = self.scan_versions(force=True)
        return {
            "ok": True,
            "dir": entry.to_dict(),
            "detected": str(root),
            "versions": versions,
            "message": f"已添加数据目录：{entry.name}",
        }

    def remove_game_dir(self, dir_id: str) -> dict:
        ok = self.config.remove_game_dir(dir_id)
        return {"ok": ok, "message": "" if ok else "至少要保留一个数据目录"}

    def select_game_dir(self, dir_id: str) -> dict:
        ok = self.config.select_game_dir(dir_id)
        if ok:
            self._refresh()
        return {"ok": ok, "versions": self.scan_versions() if ok else []}

    def instances(self) -> list[dict]:
        cfg = self.config
        return [
            {
                "id": item.id,
                "name": item.name,
                "game_dir": item.game_dir,
                "version_id": item.version_id,
                "loader": item.loader,
                "mc_version": item.mc_version,
                "selected": item.id == cfg.selected_instance_id,
            }
            for item in cfg.instance_list()
        ]

    def add_instance(self, name: str, version_id: str, game_dir: str = "") -> dict:
        if not game_dir:
            game_dir = str(INSTANCES_DIR / (name or version_id or "instance"))
        entry = self.config.add_instance(name or version_id or "新实例", game_dir, version_id=version_id)
        self.config.select_instance(entry.id)
        return {"ok": True, "instances": self.instances()}

    def select_instance(self, instance_id: str) -> dict:
        self.config.select_instance(instance_id)
        instance = self.config.get_instance(instance_id)
        if instance is not None:
            self.config.default_version_id = instance.version_id
            try:
                self.config.save()
            except OSError:
                pass
            self._refresh()
        return {"ok": True, "instances": self.instances(), "versions": self.scan_versions()}

    def remove_instance(self, instance_id: str) -> dict:
        if instance_id == "default":
            return {"ok": False, "message": "默认实例不能删除"}
        self.config.remove_instance(instance_id)
        return {"ok": True, "instances": self.instances()}

    def instance_move(self, instance_id: str, delta: int) -> dict:
        """上移 / 下移实例并持久化排序。"""
        cfg = self.config
        items = list(cfg.instances or [])
        ids = [item.id for item in items]
        if instance_id not in ids:
            return {"ok": False, "message": "默认实例不支持排序", "instances": self.instances()}
        index = ids.index(instance_id)
        target = max(0, min(len(items) - 1, index + (1 if int(delta) > 0 else -1)))
        if target != index:
            items.insert(target, items.pop(index))
            cfg.instances = items
            try:
                cfg.save()
            except OSError as exc:
                return {"ok": False, "message": f"保存失败：{exc}"}
        return {"ok": True, "instances": self.instances()}

    def export_modpack(self, instance_id: str = "") -> dict:
        """把当前实例打包为 .mikan 备份或 CurseForge 整合包 zip。"""
        cfg = self.config
        instance_id = instance_id or cfg.selected_instance_id or ""
        inst = cfg.get_instance(instance_id) if instance_id else None
        if inst is None:
            return {"ok": False, "message": "请先选择一个实例"}
        name = inst.name or inst.version_id or "instance"
        target = self._pick_save(
            str(Path.home() / f"{name}-整合包.mikan"),
            ("MikanCL 实例备份 (*.mikan)", "CurseForge 整合包 (*.zip)"),
        )
        if not target:
            return {"ok": False, "message": "已取消"}
        if not Path(target).suffix:
            target += ".mikan"
        job = _spawn("modpack", f"导出 {name}", lambda j: self._export_modpack_job(j, inst.id, target))
        return {"ok": True, "job": job.id, "message": "正在打包实例…"}

    def _export_modpack_job(self, job, instance_id: str, target: str) -> dict:
        import json as _json
        import re
        import zipfile

        inst = self.config.get_instance(instance_id)
        if inst is None:
            raise RuntimeError("实例不存在")
        gd = self._game_dir_of(inst.id)
        loader_key = {
            "forge": "forge",
            "neoforge": "neoforge",
            "fabric": "fabric",
            "quilt": "quilt",
            "liteloader": "liteloader",
        }.get(inst.loader or "", "")
        loader_id = ""
        if loader_key:
            match = re.search(
                rf"{loader_key}(?:-loader)?[-_]?(\d+\.\d+(?:\.\d+)?)",
                inst.version_id or "",
                re.IGNORECASE,
            )
            loader_id = f"{loader_key}-{match.group(1)}" if match else loader_key
        manifest = {
            "minecraft": {
                "version": inst.mc_version or inst.version_id or "",
                "modLoaders": [{"id": loader_id, "primary": True}] if loader_id else [],
            },
            "manifestType": "minecraftModpack",
            "manifestVersion": 1,
            "name": f"{inst.name or inst.version_id} 整合包",
            "author": "MikanCL",
            "version": "1.0.0",
            "files": [],
        }
        items: list[tuple[Path, str]] = []
        for folder_name in ("mods", "resourcepacks", "shaderpacks", "config"):
            folder = gd / folder_name
            if not folder.is_dir():
                continue
            for path in folder.rglob("*"):
                if path.is_file():
                    items.append((path, f"{folder_name}/{path.relative_to(folder).as_posix()}"))
        options = gd / "options.txt"
        if options.is_file():
            items.append((options, "options.txt"))
        dest = Path(target)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            dest.unlink()
        job.stage = "打包实例"
        total = max(1, len(items))
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", _json.dumps(manifest, ensure_ascii=False, indent=2))
            archive.writestr(
                "instance.json",
                _json.dumps(
                    {"format": "mikan/1", "instance": inst.to_dict()},
                    ensure_ascii=False,
                    indent=2,
                ),
            )
            for index, (path, arcname) in enumerate(items, 1):
                job.progress(index * 100.0 / total, arcname, "打包实例")
                if job.cancel.is_set():
                    raise RuntimeError("已取消")
                archive.write(path, arcname)
        job.progress(100.0, str(dest), "完成")
        job.log(f"[导出] {dest}")
        return {"path": str(dest)}

    # =====================================================================
    # 依赖补全 / 工具
    # =====================================================================
    def dependencies_scan(self, version_id: str) -> dict:
        try:
            from ..dependencies import scan_missing, summarize_missing

            javas = self._java_list()
            _merged, items = scan_missing(self.config, version_id, javas)
            return {
                "ok": True,
                "items": [
                    {
                        "kind": item.kind,
                        "name": getattr(item, "name", ""),
                        "detail": getattr(item, "detail", ""),
                        "count": getattr(item, "count", 1),
                    }
                    for item in items
                ],
                "summary": summarize_missing(items),
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"扫描失败：{exc}", "items": [], "summary": ""}

    def third_party_modules(self) -> list[dict]:
        from ..dependencies import third_party_modules

        return third_party_modules(self.config, self._java_list())

    def install_dependency(self, module_id: str) -> dict:
        job = _spawn("dependency", f"获取依赖 {module_id}", lambda j: self._dependency_job(j, module_id))
        return {"ok": True, "job": job.id, "message": "开始下载依赖"}

    def _dependency_job(self, job: Job, module_id: str) -> dict:
        from ..dependencies import install_third_party

        path = install_third_party(
            module_id,
            self.config,
            log=job.log,
            progress=lambda percent, detail: job.progress(percent * 100, detail, "下载依赖"),
            cancel=job.cancel,
        )
        return {"path": str(path)}

    def _version_game_dir(self, version_id: str):
        """版本对应的实际游戏目录（全部隔离时是 versions/<id>）。"""
        if not version_id:
            return self._game_dir_of(self.config.selected_instance_id or "")
        try:
            return Path(self.config.resolve_game_dirs(version_id).primary)
        except Exception:  # noqa: BLE001
            return self.config.game_path

    def mod_scan(self, version_id: str = "") -> dict:
        try:
            from ..content import detect_mod_conflicts, scan_mod_metadata
            from ..modgraph import build_mod_graph

            game_dir = self._version_game_dir(version_id) if version_id else self._game_dir_of(self.config.selected_instance_id or "")
            mods_dir = game_dir / "mods"
            metadata = scan_mod_metadata(mods_dir) if mods_dir.is_dir() else {}
            graph = build_mod_graph(metadata)
            conflicts = detect_mod_conflicts(metadata)
            return {
                "ok": True,
                "nodes": [
                    {
                        "id": n.modid,
                        "name": n.name,
                        "version": n.version,
                        "loader": n.loader,
                        "missing": n.missing,
                    }
                    for n in graph.nodes
                ],
                "edges": [
                    {"from": e.source, "to": e.target, "range": e.version_range, "ok": e.ok}
                    for e in graph.edges
                ],
                "cycles": graph.cycles,
                "conflicts": [
                    {
                        "type": item.get("type", ""),
                        "modid": item.get("modid", ""),
                        "files": [Path(p).name for p in item.get("files") or []],
                        "detail": item.get("detail", ""),
                    }
                    for item in conflicts
                ],
                "mods_dir": str(mods_dir),
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"扫描 Mod 失败：{exc}"}

    def mods_list(self, version_id: str = "") -> dict:
        """列出指定版本 / 当前实例的 Mod 文件（.jar 启用 / .jar.disabled 禁用）。"""
        game_dir = self._version_game_dir(version_id) if version_id else self.config.game_path
        mods_dir = game_dir / "mods"
        items = []
        try:
            files = [p for p in mods_dir.iterdir() if p.is_file()]
        except OSError:
            files = []
        for path in files:
            name = path.name
            if name.lower().endswith(".jar"):
                enabled = True
            elif name.lower().endswith((".jar.disabled", ".disabled")):
                enabled = False
            else:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            items.append(
                {
                    "path": str(path),
                    "name": name,
                    "enabled": enabled,
                    "size": stat.st_size,
                }
            )
        items.sort(key=lambda item: item["name"].lower())
        return {"ok": True, "dir": str(mods_dir), "items": items}

    def mod_toggle(self, path: str) -> dict:
        source = Path(path)
        if not source.is_file():
            return {"ok": False, "message": "Mod 文件不存在"}
        if source.name.lower().endswith(".jar"):
            target = source.with_name(source.name + ".disabled")
        elif source.name.lower().endswith(".disabled"):
            target = source.with_name(source.name[: -len(".disabled")])
        else:
            return {"ok": False, "message": "不支持的文件类型"}
        try:
            source.rename(target)
        except OSError as exc:
            return {"ok": False, "message": f"切换失败：{exc}"}
        return {"ok": True, "enabled": target.name.lower().endswith(".jar"), "path": str(target)}

    def mod_delete(self, path: str) -> dict:
        target = Path(path)
        if not target.is_file():
            return {"ok": False, "message": "Mod 文件不存在"}
        try:
            target.unlink()
        except OSError as exc:
            return {"ok": False, "message": f"删除失败：{exc}"}
        return {"ok": True, "message": "已删除 Mod"}

    def packs_list(self, kind: str) -> dict:
        """列出资源包 / 光影包（.zip 启用，.disabled 为禁用）。"""
        folder_name = {"resourcepacks": "resourcepacks", "shaderpacks": "shaderpacks"}.get(kind)
        if folder_name is None:
            return {"ok": False, "message": "不支持的目录类型"}
        folder = self._game_dir_of(self.config.selected_instance_id or "") / folder_name
        folder.mkdir(parents=True, exist_ok=True)
        items = []
        try:
            files = [p for p in folder.iterdir() if p.is_file()]
        except OSError:
            files = []
        for path in files:
            lower = path.name.lower()
            if lower.endswith(".zip"):
                enabled, label = True, path.name
            elif lower.endswith(".zip.disabled") or lower.endswith(".disabled"):
                enabled, label = False, path.name[: -len(".disabled")]
            else:
                continue
            try:
                size = path.stat().st_size
            except OSError:
                size = 0
            items.append({"path": str(path), "name": label, "enabled": enabled, "size": size})
        items.sort(key=lambda item: item["name"].lower())
        return {"ok": True, "dir": str(folder), "items": items}

    def pack_toggle(self, path: str) -> dict:
        source = Path(path)
        if not source.is_file():
            return {"ok": False, "message": "文件不存在"}
        name = source.name.lower()
        if name.endswith(".zip"):
            target = source.with_name(source.name + ".disabled")
        elif name.endswith(".disabled"):
            target = source.with_name(source.name[: -len(".disabled")])
        else:
            return {"ok": False, "message": "不支持的文件类型"}
        try:
            source.rename(target)
        except OSError as exc:
            return {"ok": False, "message": f"切换失败：{exc}"}
        return {"ok": True, "enabled": not target.name.lower().endswith(".disabled"), "path": str(target)}

    def pack_delete(self, path: str) -> dict:
        target = Path(path)
        if not target.is_file():
            return {"ok": False, "message": "文件不存在"}
        try:
            target.unlink()
        except OSError as exc:
            return {"ok": False, "message": f"删除失败：{exc}"}
        return {"ok": True, "message": "已删除"}

    def pack_open(self, kind: str) -> dict:
        folder_name = {"mods": "mods", "resourcepacks": "resourcepacks", "shaderpacks": "shaderpacks"}.get(kind)
        if folder_name is None:
            return {"ok": False, "message": "不支持的目录类型"}
        folder = self._game_dir_of(self.config.selected_instance_id or "") / folder_name
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(str(folder))  # noqa: S606 - Windows 专用
        return {"ok": True, "dir": str(folder)}

    def version_settings(self, version_id: str) -> dict:
        from ..config import ISOLATION_LABELS

        cfg = self.config
        version_id = str(version_id or "")
        if not version_id:
            return {"ok": False, "message": "请先选择版本"}
        setting = cfg.version_setting(version_id)
        return {
            "ok": True,
            "version": version_id,
            "setting": setting.to_dict(),
            "global_memory": int(cfg.memory_mb or 4096),
            "isolation_options": ISOLATION_LABELS,
        }

    def version_settings_save(self, version_id: str, payload: dict) -> dict:
        cfg = self.config
        version_id = str(version_id or "")
        if not version_id:
            return {"ok": False, "message": "请先选择版本"}
        setting = cfg.ensure_version_setting(version_id)
        data = payload or {}
        for key in ("extra_jvm_args", "extra_game_args", "window_title", "server", "priority", "isolation"):
            if key in data:
                setattr(setting, key, str(data.get(key) or ""))
        if "memory_mb" in data:
            try:
                memory = int(data.get("memory_mb") or 0)
            except (TypeError, ValueError):
                memory = 0
            setting.memory_mb = max(0, min(65536, memory))
        if "port" in data:
            try:
                setting.port = max(1, min(65535, int(data.get("port") or 25565)))
            except (TypeError, ValueError):
                setting.port = 25565
        if "auto_connect" in data:
            setting.auto_connect = bool(data.get("auto_connect"))
        try:
            cfg.save()
        except OSError as exc:
            return {"ok": False, "message": f"保存失败：{exc}"}
        return {"ok": True, "setting": setting.to_dict(), "message": "版本设置已保存"}

    def saves_list(self) -> dict:
        from ..saves import list_backups, list_saves

        game_dir = self.config.game_path
        backup_root = Path(self.config.backup_dir) if self.config.backup_dir else DATA_DIR / "backups"
        return {
            "ok": True,
            "saves": [
                {
                    "folder": s.folder,
                    "name": s.name,
                    "last_played": s.last_played,
                    "size": s.size,
                    "mode": s.game_mode,
                    "version": s.version_name,
                }
                for s in list_saves(game_dir)
            ],
            "backups": [
                {
                    "path": str(b.path),
                    "world": b.world,
                    "created": b.created,
                    "size": b.size,
                    "auto": b.auto,
                }
                for b in list_backups(backup_root, self.config.default_version_id)
            ],
        }

    def saves_backup(self, folder: str = "") -> dict:
        from ..saves import backup_all_saves, backup_save

        game_dir = self.config.game_path
        backup_root = Path(self.config.backup_dir) if self.config.backup_dir else DATA_DIR / "backups"
        version_id = self.config.default_version_id or "default"
        try:
            if folder:
                path = backup_save(game_dir, folder, backup_root, version_id)
                return {"ok": True, "message": f"已备份到 {path}"}
            paths = backup_all_saves(game_dir, backup_root, version_id)
            return {"ok": True, "message": f"已备份 {len(paths)} 个存档"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"备份失败：{exc}"}

    def saves_restore(self, backup_path: str) -> dict:
        from ..saves import restore_backup

        try:
            name = restore_backup(Path(backup_path), self.config.game_path)
            return {"ok": True, "message": f"已恢复存档 {name}"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"恢复失败：{exc}"}

    def saves_delete(self, folder: str) -> dict:
        from ..saves import delete_world

        ok = delete_world(self.config.game_path, folder)
        return {"ok": ok, "message": "已删除" if ok else "删除失败"}

    def clean_game(self) -> dict:
        from ..version import clean_game_dir

        try:
            deleted, freed, failed = clean_game_dir(self.config)
            self._refresh()
            message = f"已清理 {deleted} 个文件（{_fmt_size(freed)}）"
            if failed:
                message += f"，{failed} 项被占用未删除"
            return {"ok": True, "message": message}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"清理失败：{exc}"}

    # =====================================================================
    # 截图图库 / 崩溃报告 / 皮肤包 / 种子地形 / NBT
    # =====================================================================
    def _screenshots_dir(self) -> Path:
        cfg = self.config
        instance = cfg.selected_instance()
        base = cfg.instance_path(instance.id)
        if getattr(instance, "version_id", ""):
            try:
                return cfg.resolve_game_dirs(instance.version_id, base).targets("screenshots")[0]
            except Exception:  # noqa: BLE001 - 目录解析失败回退实例根目录
                pass
        return base / "screenshots"

    def gallery_list(self) -> dict:
        folder = self._screenshots_dir()
        try:
            files = [
                p
                for p in folder.iterdir()
                if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".gif"}
            ]
        except OSError:
            files = []
        items = []
        for path in files:
            try:
                stat = path.stat()
            except OSError:
                continue
            items.append(
                {"path": str(path), "name": path.name, "size": stat.st_size, "mtime": stat.st_mtime}
            )
        items.sort(key=lambda item: item["mtime"], reverse=True)
        return {"ok": True, "dir": str(folder), "items": items}

    def gallery_export(self, paths: list[str]) -> dict:
        if not paths:
            return {"ok": False, "message": "请先选择截图"}
        default = "screenshots-" + time.strftime("%Y%m%d-%H%M%S") + ".zip"
        target = self._pick_save(default, ("Zip 压缩包 (*.zip)",))
        if not target:
            return {"ok": False, "message": "未选择保存位置"}
        import zipfile

        written = 0
        try:
            with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                for raw in paths:
                    path = Path(raw)
                    if path.is_file():
                        archive.write(path, path.name)
                        written += 1
        except OSError as exc:
            return {"ok": False, "message": f"导出失败：{exc}"}
        return {"ok": True, "message": f"已导出 {written} 张截图到 {target}", "path": str(target)}

    def gallery_delete(self, paths: list[str]) -> dict:
        failed = 0
        for raw in paths:
            try:
                Path(raw).unlink(missing_ok=True)
            except OSError:
                failed += 1
        message = f"已删除 {len(paths) - failed} 张截图"
        if failed:
            message += f"，{failed} 张失败"
        return {"ok": failed == 0, "message": message}

    def crashes_list(self) -> dict:
        folder = DATA_DIR / "logs" / "crashes"
        try:
            files = [p for p in folder.iterdir() if p.is_file()]
        except OSError:
            files = []
        items = []
        for path in files:
            try:
                stat = path.stat()
            except OSError:
                continue
            items.append(
                {"path": str(path), "name": path.name, "size": stat.st_size, "mtime": stat.st_mtime}
            )
        items.sort(key=lambda item: item["mtime"], reverse=True)
        return {"ok": True, "dir": str(folder), "items": items}

    def crash_read(self, path: str) -> dict:
        target = Path(path)
        if not target.is_file():
            return {"ok": False, "message": "崩溃日志不存在"}
        try:
            size = target.stat().st_size
            limit = 220 * 1024
            if size > limit:
                with target.open("rb") as handle:
                    handle.seek(size - limit)
                    text = "[已截断：仅显示日志尾部]\n" + handle.read().decode(
                        "utf-8", errors="replace"
                    )
            else:
                text = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return {"ok": False, "message": str(exc)}
        return {"ok": True, "name": target.name, "text": text}

    def crash_copy(self, path: str) -> dict:
        from PySide6.QtWidgets import QApplication

        target = Path(path)
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return {"ok": False, "message": str(exc)}
        lines = [
            line
            for line in text.splitlines()
            if "Caused by" in line or "Exception" in line or "Error" in line
        ]
        summary = "\n".join(lines[-12:]) or "\n".join(text.splitlines()[-12:])
        QApplication.clipboard().setText(f"{target.name}\n{summary}")
        return {"ok": True, "message": "崩溃摘要已复制到剪贴板"}

    def crash_delete(self, paths: list[str]) -> dict:
        failed = 0
        for raw in paths:
            try:
                Path(raw).unlink(missing_ok=True)
            except OSError:
                failed += 1
        message = f"已删除 {len(paths) - failed} 份崩溃日志"
        if failed:
            message += f"，{failed} 份失败"
        return {"ok": failed == 0, "message": message}

    def skin_library(self) -> dict:
        """皮肤库：返回最近保存的皮肤与预览图（供快速切换）。"""
        items = []
        for entry in skins.entries(limit=48):
            items.append(
                {
                    "path": entry.path,
                    "name": entry.name,
                    "model": entry.model,
                    "preview": self.preview(entry.path),
                }
            )
        return {"ok": True, "items": items}

    def skin_pack_versions(self) -> dict:
        """皮肤包可选的游戏版本：已安装版本 + 常见版本。"""
        installed = [item["id"] for item in self.scan_versions()]
        samples = [
            "1.5.2", "1.8.9", "1.12.2", "1.16.5", "1.20.1",
            "1.20.4", "1.21.8", "1.21.9", "1.21.11", "26.1", "26.3", "26.4",
        ]
        versions = []
        for version in installed + samples:
            if version and version not in versions:
                versions.append(version)
        return {"ok": True, "versions": versions, "installed": installed}

    def skin_pack_export(
        self,
        player: str,
        model: str = "classic",
        version_id: str = "",
        source: str = "",
        cape: str = "",
    ) -> dict:
        from ..skinpack import SkinPackError, export_skin_pack, pack_filename

        skin_path = str(source or "").strip()
        if not skin_path:
            account = self._store().selected()
            skin_path = account.skin_path or ""
        if not skin_path:
            return {"ok": False, "message": "当前账号没有皮肤文件，请先导入皮肤或选择本地 PNG"}
        if not str(player or "").strip():
            return {"ok": False, "message": "请填写目标玩家名"}
        target = self._pick_save(pack_filename(player), ("皮肤包 (*.zip)",))
        if not target:
            return {"ok": False, "message": "未选择保存位置"}
        try:
            path = export_skin_pack(
                target, skin_path, player, model or "classic", version_id or "", cape or None
            )
        except SkinPackError as exc:
            return {"ok": False, "message": str(exc)}
        except OSError as exc:
            return {"ok": False, "message": f"导出失败：{exc}"}
        return {"ok": True, "message": f"皮肤包已导出：{path}", "path": str(path)}

    def _install_skin_pack_file(
        self, raw: str, version: str, enable_pack: bool = False
    ) -> dict:
        """把皮肤包 / PNG 安装到指定版本对应的全部游戏目录。"""
        from ..skinpack import (
            SkinPackError,
            apply_player_skin_bytes,
            purge_old_packs,
            read_skin_pack,
        )

        data = read_skin_pack(raw)
        account = self._store().selected()
        name = str(data.get("player") or "").strip() or getattr(account, "name", "") or "Steve"
        model = (
            str(data.get("model") or "").strip()
            or getattr(account, "skin_model", "")
            or "classic"
        )
        image = data.get("image") or b""
        if not image:
            return {"ok": False, "message": "皮肤包里没有皮肤图片"}
        written: list[str] = []
        for game_dir in self.config.resolve_game_dirs(version).skin_targets():
            game_dir.mkdir(parents=True, exist_ok=True)
            purge_old_packs(game_dir)
            info = apply_player_skin_bytes(
                image,
                name,
                model,
                game_dir,
                version,
                install_pack=True,
                enable_pack=bool(enable_pack),
                cape=data.get("cape") or None,
            )
            written.append(str(info.get("skin", "")))
        return {
            "ok": True,
            "message": f"已导入到 {len(written)} 个游戏目录（{version or '通用'} · {name}）",
            "player": name,
            "model": model,
            "written": written,
        }

    def skin_pack_install(self, enable_pack: bool = False, version_id: str = "") -> dict:
        from ..skinpack import SkinPackError

        raw = self._pick_file(("皮肤包 (*.zip)", "皮肤图片 (*.png)", "所有文件 (*.*)"))
        if not raw:
            return {"ok": False, "message": "未选择皮肤包"}
        version = str(version_id or self.config.default_version_id or "").strip()
        if not version:
            installed = self.scan_versions()
            version = installed[0]["id"] if installed else ""
        try:
            return self._install_skin_pack_file(raw, version, enable_pack)
        except SkinPackError as exc:
            return {"ok": False, "message": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"安装失败：{exc}"}

    def skin_pack_import_version(self, version_id: str = "", enable_pack: bool = False) -> dict:
        """把皮肤包导入到用户指定的已安装版本（双端一致的功能入口）。"""
        from ..skinpack import SkinPackError

        version = str(version_id or "").strip()
        if not version:
            return {"ok": False, "message": "请先选择要导入的版本"}
        raw = self._pick_file(("皮肤包 (*.zip)", "皮肤图片 (*.png)", "所有文件 (*.*)"))
        if not raw:
            return {"ok": False, "message": "未选择皮肤包"}
        try:
            return self._install_skin_pack_file(raw, version, enable_pack)
        except SkinPackError as exc:
            return {"ok": False, "message": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"导入失败：{exc}"}

    def skin_pack_overwrite(
        self,
        player: str = "",
        model: str = "classic",
        source: str = "",
        cape: str = "",
        version_id: str = "",
        enable_pack: bool = False,
        elytra: bool = False,
    ) -> dict:
        """一键添加并覆盖旧皮肤包：先清理所有游戏目录的旧 MikanCL 包，再写入当前皮肤。"""
        from ..skinpack import SkinPackError, apply_player_skin_bytes, purge_old_packs

        name = str(player or "").strip()
        if not name:
            return {"ok": False, "message": "请填写目标玩家名"}
        skin_path = str(source or "").strip()
        if not skin_path:
            skin_path = self._store().selected().skin_path or ""
        if not skin_path or not Path(skin_path).is_file():
            return {"ok": False, "message": "当前账号没有皮肤文件，请先导入皮肤或选择本地 PNG"}
        try:
            image = Path(skin_path).read_bytes()
        except OSError as exc:
            return {"ok": False, "message": f"读取皮肤失败：{exc}"}
        version = str(version_id or self.config.default_version_id or "").strip()
        if not version:
            installed = self.scan_versions()
            version = installed[0]["id"] if installed else "1.21.8"
        cape_data = b""
        cape_path = str(cape or "").strip()
        if cape_path and Path(cape_path).is_file():
            try:
                cape_data = Path(cape_path).read_bytes()
            except OSError:
                cape_data = b""
        removed: list[str] = []
        written: list[str] = []
        try:
            for game_dir in self.config.resolve_game_dirs(version).skin_targets():
                game_dir.mkdir(parents=True, exist_ok=True)
                removed.extend(purge_old_packs(game_dir))
                info = apply_player_skin_bytes(
                    image,
                    name,
                    model or "classic",
                    game_dir,
                    version,
                    install_pack=True,
                    enable_pack=bool(enable_pack),
                    cape=cape_data or None,
                    elytra=cape_data if cape_data and elytra else None,
                )
                written.append(str(info.get("skin", "")))
        except SkinPackError as exc:
            return {"ok": False, "message": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"写入失败：{exc}"}
        return {
            "ok": True,
            "message": f"已清理 {len(removed)} 个旧皮肤包，写入 {len(written)} 个游戏目录（{version} · {name}）",
            "removed": len(removed),
            "written": written,
        }

    def _skin_pack_ready(self, version: str, name: str, image: bytes, model: str) -> bool:
        """检查某个版本的皮肤包是否与当前皮肤内容一致（不是只看文件存在）。

        旧逻辑只要 resourcepacks 里有任意 MikanCL-*.zip 就跳过，换皮肤后旧包
        不会重写，高版本就会继续显示旧皮肤；这里用内容指纹 + LocalSkin 校验。
        """
        from ..skinpack import pack_is_current

        if not name or not image:
            return False
        try:
            targets = self.config.resolve_game_dirs(version).skin_targets()
        except Exception:  # noqa: BLE001
            return False
        for game_dir in targets:
            skin_file = Path(game_dir) / "CustomSkinLoader" / "LocalSkin" / "skins" / f"{name}.png"
            if not skin_file.is_file():
                return False
            if not pack_is_current(game_dir, version, name, image, model):
                return False
        return True

    def skin_pack_fill_missing(
        self,
        player: str = "",
        model: str = "classic",
        source: str = "",
        cape: str = "",
        enable_pack: bool = True,
        elytra: bool = False,
    ) -> dict:
        """按已下载版本逐一校验，缺失或内容过期的皮肤包自动重写。"""
        from ..skinpack import SkinPackError, apply_player_skin_bytes, purge_old_packs

        account = self._store().selected()
        name = str(player or "").strip() or getattr(account, "name", "") or "Steve"
        skin_path = str(source or "").strip() or getattr(account, "skin_path", "") or ""
        if not skin_path or not Path(skin_path).is_file():
            return {"ok": False, "message": "当前账号没有皮肤文件，请先导入皮肤或选择本地 PNG"}
        try:
            image = Path(skin_path).read_bytes()
        except OSError as exc:
            return {"ok": False, "message": f"读取皮肤失败：{exc}"}
        cape_data = b""
        cape_path = str(cape or "").strip()
        if cape_path and Path(cape_path).is_file():
            try:
                cape_data = Path(cape_path).read_bytes()
            except OSError:
                cape_data = b""
        versions = [item["id"] for item in self.scan_versions() if item.get("id")]
        if not versions:
            return {"ok": False, "message": "还没有已下载的游戏版本"}
        filled: list[str] = []
        skipped: list[str] = []
        try:
            for version in versions:
                if self._skin_pack_ready(version, name, image, model):
                    skipped.append(version)
                    continue
                for game_dir in self.config.resolve_game_dirs(version).skin_targets():
                    game_dir.mkdir(parents=True, exist_ok=True)
                    purge_old_packs(game_dir)
                    apply_player_skin_bytes(
                        image,
                        name,
                        model or "classic",
                        game_dir,
                        version,
                        install_pack=True,
                        enable_pack=bool(enable_pack),
                        cape=cape_data or None,
                        elytra=cape_data if cape_data and elytra else None,
                    )
                filled.append(version)
        except SkinPackError as exc:
            return {"ok": False, "message": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"写入失败：{exc}"}
        return {
            "ok": True,
            "message": f"已为 {len(filled)} 个版本生成/更新皮肤包，跳过 {len(skipped)} 个已是最新",
            "filled": filled,
            "skipped": skipped,
        }

    def seed_preview(self, seed: str = "", mode: str = "classic", size: int = 256) -> dict:
        """生成地形高度图：复用 Java 噪声程序，结果放到后台任务里跑。"""
        text = str(seed or "").strip()
        if text:
            try:
                value = int(text)
            except ValueError:
                hashed = 0
                for ch in text:
                    hashed = (hashed * 31 + ord(ch)) & 0xFFFFFFFF
                value = hashed - 0x100000000 if hashed >= 0x80000000 else hashed
        else:
            value = int(time.time() * 1000) & 0x7FFFFFFFFFFFFFFF
        value = max(-(1 << 63), min((1 << 63) - 1, value))
        try:
            size = max(64, min(512, int(size)))
        except (TypeError, ValueError):
            size = 256
        mode_int = 0 if str(mode).lower() in ("classic", "0", "old") else 1
        job = _spawn(
            "terrain",
            f"生成地形 {value}",
            lambda j: self._terrain_job(j, value, size, mode_int),
        )
        return {"ok": True, "job": job.id, "seed": value}

    def _terrain_job(self, job: Job, seed: int, size: int, mode: int) -> dict:
        from types import SimpleNamespace

        from ..terrain_java import generate_heightmap_java, terrain_dir

        job.progress(6, "正在准备 Java 噪声程序…")
        ctx = SimpleNamespace(javas=self._java_list())
        data = generate_heightmap_java(
            seed, size, mode, ctx=ctx, java_path=self.config.java_path or ""
        )
        job.progress(82, "高度图已生成，正在准备预览…")
        png = terrain_dir() / "heightmap.png"
        return {
            "ok": True,
            "seed": seed,
            "size": size,
            "points": len(data),
            "png": str(png),
            "url": self.preview(str(png)),
        }

    def nbt_open(self) -> dict:
        raw = self._pick_file(("NBT 数据 (*.dat *.nbt)", "所有文件 (*.*)"))
        if not raw:
            return {"ok": False, "message": "未选择文件"}
        return self.nbt_read(raw)

    def nbt_read(self, path: str) -> dict:
        """读取 NBT（保留标签类型），返回可展示的树。"""
        from ..nbt import load_nbt_typed_file

        target = Path(path)
        if not target.is_file():
            return {"ok": False, "message": "文件不存在"}
        try:
            name, node = load_nbt_typed_file(target)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"读取 NBT 失败：{exc}"}

        def encode(item: tuple[int, object]) -> dict:
            tag, value = item
            if tag == 10:
                return {
                    "tag": 10,
                    "value": {key: encode(child) for key, child in value.items()},
                }
            if tag == 9:
                element_tag, children = value
                return {
                    "tag": 9,
                    "value": {
                        "element": element_tag,
                        "items": [encode(child) for child in children],
                    },
                }
            if tag == 12:
                return {"tag": 12, "value": [str(v) for v in value]}
            if tag in (7, 11):
                return {"tag": tag, "value": [int(v) for v in value]}
            return {"tag": tag, "value": value}

        self._nbt_cache[str(target)] = (name, node)
        return {
            "ok": True,
            "path": str(target),
            "root": name,
            "tree": encode(node),
            "backup": str(target.with_name(target.name + ".bak")),
        }

    def nbt_edit(self, path: str, pointer: list, value) -> dict:
        """修改叶子节点并立即写回；写回前自动生成 .bak 备份。"""
        from ..nbt import save_nbt_typed_file

        cached = self._nbt_cache.get(str(path))
        if cached is None:
            return {"ok": False, "message": "请先打开该文件"}
        root_name, node = cached
        current = node
        container = None
        slot = None
        try:
            for key in pointer or []:
                tag, payload = current
                if tag == 10:
                    slot = str(key)
                    container = payload
                    current = payload[slot]
                elif tag == 9:
                    element_tag, children = payload
                    slot = int(key)
                    container = children
                    current = children[slot]
                else:
                    return {"ok": False, "message": "路径指向的不是可编辑节点"}
        except (KeyError, IndexError, TypeError, ValueError):
            return {"ok": False, "message": "节点路径无效"}
        if container is None:
            return {"ok": False, "message": "根节点不能直接修改"}
        tag, _old = current
        if tag in (7, 11, 12) or tag in (9, 10):
            return {"ok": False, "message": "数组与复合节点不支持直接修改"}
        if tag in (1, 2, 3, 4, 5, 6):
            try:
                new_value = int(float(value))
            except (TypeError, ValueError):
                return {"ok": False, "message": "请输入数字"}
        else:
            new_value = str(value)
        original = Path(path)
        try:
            if original.is_file():
                shutil.copy2(original, original.with_name(original.name + ".bak"))
            container[slot] = (tag, new_value)
            save_nbt_typed_file(original, root_name, node)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"保存失败：{exc}"}
        self._nbt_cache[str(path)] = (root_name, node)
        return {"ok": True, "message": "已保存（原文件已备份为 .bak）"}

    def wiki_index(self) -> dict:
        """教程中心目录：按当前界面语言读取 data/wiki/<语言>/*.md。"""
        from ..ui.page_wiki import ensure_default_wiki

        lang = ensure_default_wiki(self.config.language)
        folder = WIKI_DIR / lang
        items = []
        try:
            files = sorted(folder.glob("*.md"))
        except OSError:
            files = []
        for path in files:
            title = path.stem
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    if line.startswith("# "):
                        title = line[2:].strip()
                        break
            except OSError:
                pass
            items.append({"slug": path.stem, "title": title})
        return {"language": lang, "items": items}

    def wiki_read(self, slug: str = "") -> dict:
        """读取单篇教程 Markdown 原文，找不到时回退第一篇。"""
        from ..ui.page_wiki import ensure_default_wiki

        lang = ensure_default_wiki(self.config.language)
        folder = WIKI_DIR / lang
        target = folder / (str(slug or "").strip() + ".md")
        if not slug or not target.is_file():
            try:
                files = sorted(folder.glob("*.md"))
            except OSError:
                files = []
            if not files:
                return {"ok": False, "message": "教程目录为空。"}
            target = files[0]
        try:
            text = target.read_text(encoding="utf-8")
        except OSError as exc:
            return {"ok": False, "message": f"读取教程失败：{exc}"}
        title = target.stem
        for line in text.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
        return {"ok": True, "slug": target.stem, "title": title, "markdown": text}

    def logs_tail(self, kind: str = "launcher", lines: int = 160) -> dict:
        from ..config import LOG_DIR

        path = LOG_DIR / ("launcher.log" if kind == "launcher" else "latest.log")
        if kind == "game":
            candidates = sorted(LOG_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
            if candidates:
                path = candidates[0]
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return {"ok": False, "message": f"读取日志失败：{exc}", "text": "", "path": str(path)}
        rows = text.splitlines()[-int(lines or 120):]
        return {"ok": True, "text": "\n".join(rows), "path": str(path)}

    def import_external(self) -> dict:
        """从 HMCL / PCL 目录导入版本与设置。"""
        from ..launcher_import import scan_profile

        path = self._pick_dir("选择 HMCL / PCL 所在目录")
        if not path:
            return {"ok": False, "message": "未选择目录"}
        try:
            profile = scan_profile(path)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"扫描失败：{exc}"}
        if profile is None:
            return {"ok": False, "message": "没有识别到 HMCL / PCL 配置"}
        versions = [
            {
                "version_id": v.version_id,
                "name": getattr(v, "description", "") or v.version_id,
                "game_dir": str(getattr(v, "game_dir", "") or ""),
                "loader": getattr(v, "loader", ""),
                "mc_version": getattr(v, "mc_version", ""),
                "loader_version": getattr(v, "loader_version", ""),
                "memory_mb": int(getattr(v, "memory_mb", 0) or 0),
            }
            for v in getattr(profile, "versions", [])
        ]
        return {
            "ok": True,
            "name": getattr(profile, "name", "") or getattr(profile, "kind", ""),
            "kind": getattr(profile, "kind", ""),
            "game_dir": str(getattr(profile, "game_dir", "") or ""),
            "versions": versions,
            "profile_dir": str(path),
        }

    def import_external_apply(self, path: str, version_ids: list[str]) -> dict:
        from ..launcher_import import import_profile, scan_profile

        profile = scan_profile(path)
        if profile is None:
            return {"ok": False, "message": "没有识别到 HMCL / PCL 配置"}
        try:
            stats = import_profile(self.config, profile, list(version_ids or []))
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"导入失败：{exc}"}
        return {"ok": True, "stats": stats, "instances": self.instances()}

    # =====================================================================
    # 联机
    # =====================================================================
    def servers(self) -> list[dict]:
        cfg = self.config
        return [
            {
                "id": s.id,
                "name": s.name or s.host,
                "host": s.host,
                "port": int(s.port or 25565),
                "note": s.note,
                "favorite": bool(s.favorite),
                "active": s.id == cfg.active_server_id,
            }
            for s in (cfg.servers or [])
        ]

    def server_activate(self, server_id: str = "") -> dict:
        """把某个服务器设为「启动即自动连接」，空值表示取消。"""
        cfg = self.config
        if server_id:
            if not any(s.id == server_id for s in (cfg.servers or [])):
                return {"ok": False, "message": "服务器不存在"}
            cfg.active_server_id = server_id
        else:
            cfg.active_server_id = ""
        try:
            cfg.save()
        except OSError as exc:
            return {"ok": False, "message": f"保存失败：{exc}"}
        return {"ok": True, "servers": self.servers()}

    def server_add(self, name: str, host: str, port: int = 25565, note: str = "") -> dict:
        from ..config import ServerEntry

        host = str(host or "").strip()
        if not host:
            return {"ok": False, "message": "请输入服务器地址"}
        entry = ServerEntry(
            id=f"server-{int(time.time())}",
            name=str(name or host),
            host=host,
            port=int(port or 25565),
            note=str(note or ""),
        )
        self.config.servers.append(entry)
        try:
            self.config.save()
        except OSError:
            pass
        return {"ok": True, "servers": self.servers()}

    def server_remove(self, server_id: str) -> dict:
        self.config.servers = [s for s in (self.config.servers or []) if s.id != server_id]
        if self.config.active_server_id == server_id:
            self.config.active_server_id = ""
        try:
            self.config.save()
        except OSError:
            pass
        return {"ok": True, "servers": self.servers()}

    def server_ping(self, host: str, port: int = 25565) -> dict:
        from ..serverping import ping_server

        try:
            result = ping_server(str(host), int(port or 25565), timeout=5.0)
            return {
                "ok": bool(result.online),
                "online": bool(result.online),
                "players": int(getattr(result, "players_online", 0)),
                "max_players": int(getattr(result, "players_max", 0)),
                "version": str(getattr(result, "version", "")),
                "latency": int(getattr(result, "latency", -1)),
                "motd": str(getattr(result, "motd", "")),
                "icon": _icon_data_url(getattr(result, "icon_png", b"")),
                "message": str(getattr(result, "error", "")),
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "online": False, "message": str(exc)}

    def terracotta_status(self) -> dict:
        from .. import terracotta

        service = self._terracotta
        return {
            "installed": terracotta.is_installed(),
            "running": bool(service and service.running()),
            "port": int(getattr(service, "port", 0) or 0),
        }

    def terracotta_install(self) -> dict:
        job = _spawn("terracotta", "安装陶瓦联机", lambda j: self._terracotta_install_job(j))
        return {"ok": True, "job": job.id, "message": "开始安装陶瓦联机"}

    def _terracotta_install_job(self, job: Job) -> dict:
        from .. import terracotta

        path = terracotta.install(
            log=job.log,
            progress=lambda percent, detail: job.progress(percent * 100, detail, "下载陶瓦联机"),
            cancel=job.cancel,
        )
        return {"path": str(path)}

    def terracotta_start(self) -> dict:
        from .. import terracotta

        if self._terracotta is None:
            self._terracotta = terracotta.Service()
        job = _spawn("terracotta", "启动陶瓦联机", lambda j: self._terracotta_start_job(j))
        return {"ok": True, "job": job.id, "message": "正在启动陶瓦联机"}

    def _terracotta_start_job(self, job: Job) -> dict:
        from .. import terracotta

        service = self._terracotta
        service.log = job.log
        port = service.start()
        job.log(f"[陶瓦] 本地端口 {port}")
        nodes = terracotta.public_nodes()
        return {"port": port, "nodes": nodes[:12]}

    def terracotta_state(self) -> dict:
        """读取陶瓦本地状态，含房主创建后的房间码（分享码）。"""
        from .. import terracotta

        payload = {
            "ok": True,
            "installed": terracotta.is_installed(),
            "running": False,
            "port": 0,
            "state": "not-installed" if not terracotta.is_installed() else "waiting",
            "room": "",
            "url": "",
            "profiles": [],
            "detail": "",
        }
        service = self._terracotta
        if service is None or not service.running():
            return payload
        payload["running"] = True
        payload["port"] = int(getattr(service, "port", 0) or 0)
        try:
            state = service.state()
        except Exception as exc:  # noqa: BLE001
            payload.update({"ok": False, "state": "error", "detail": str(exc)})
            return payload
        payload.update(
            {
                key: state.get(key)
                for key in ("state", "room", "url", "profiles", "detail", "message", "type")
                if key in state
            }
        )
        return payload

    def terracotta_host(self, player: str = "") -> dict:
        from .. import terracotta

        if self._terracotta is None:
            self._terracotta = terracotta.Service()
        job = _spawn(
            "terracotta", "创建陶瓦房间", lambda j: self._terracotta_host_job(j, player)
        )
        return {"ok": True, "job": job.id, "message": "正在等待游戏对局域网开放"}

    def _terracotta_host_job(self, job: Job, player: str) -> dict:
        service = self._terracotta
        service.log = job.log
        job.stage = "创建房间"
        service.host(player or "Player")
        return service.state()

    def terracotta_join(self, room: str, player: str = "") -> dict:
        from .. import terracotta

        room = str(room or "").strip()
        if not room:
            return {"ok": False, "message": "请填写房间码"}
        from ..terracotta import normalize_room_code

        room = normalize_room_code(room) or room
        if self._terracotta is None:
            self._terracotta = terracotta.Service()
        job = _spawn(
            "terracotta",
            f"加入陶瓦房间 {room}",
            lambda j: self._terracotta_join_job(j, room, player),
        )
        return {"ok": True, "job": job.id, "message": f"正在连接房间 {room}"}

    def _terracotta_join_job(self, job: Job, room: str, player: str) -> dict:
        service = self._terracotta
        service.log = job.log
        job.stage = "连接房间"
        service.join(room, player or "Player")
        return service.state()

    def terracotta_leave(self) -> dict:
        service = self._terracotta
        if service is not None and service.running():
            try:
                service.idle()
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "message": f"结束联机失败：{exc}"}
        return {"ok": True, "message": "已结束联机"}

    def terracotta_stop(self) -> dict:
        service = self._terracotta
        if service is not None:
            service.stop()
        return {"ok": True}

    # =====================================================================
    # 文件 / 窗口
    # =====================================================================
    def _pick_file(self, file_types: tuple[str, ...]) -> str:
        if self.window is None:
            return ""
        try:
            result = self.window.create_file_dialog(webview.OPEN_DIALOG, file_types=file_types)
        except Exception:  # noqa: BLE001
            return ""
        if not result:
            return ""
        return result[0] if isinstance(result, (list, tuple)) else str(result)

    def _pick_save(self, default_name: str, file_types: tuple[str, ...]) -> str:
        if self.window is None:
            return ""
        try:
            result = self.window.create_file_dialog(
                webview.SAVE_DIALOG, save_filename=default_name, file_types=file_types
            )
        except Exception:  # noqa: BLE001
            return ""
        if not result:
            return ""
        return str(result[0] if isinstance(result, (list, tuple)) else result)

    def _pick_dir(self, title: str = "") -> str:
        if self.window is None:
            return ""
        try:
            result = self.window.create_file_dialog(webview.FOLDER_DIALOG, directory=title or "")
        except Exception:  # noqa: BLE001
            return ""
        if not result:
            return ""
        return result[0] if isinstance(result, (list, tuple)) else str(result)

    def pick_skin_png(self) -> dict:
        path = self._pick_file(("皮肤图片 (*.png)", "所有文件 (*.*)"))
        return {"ok": bool(path), "path": path}

    def pick_folder(self, kind: str = "game") -> dict:
        """选择目录：游戏目录 / 实例目录 / 返回路径。"""
        path = self._pick_dir()
        return {"ok": bool(path), "path": path}

    def open_path(self, kind: str) -> dict:
        cfg = self.config
        mapping = {
            "game": cfg.game_path,
            "mods": cfg.game_path / "mods",
            "saves": cfg.game_path / "saves",
            "logs": cfg.game_path / "logs",
            "data": DATA_DIR,
            "java": DATA_DIR / "java",
            "backups": Path(cfg.backup_dir) if cfg.backup_dir else DATA_DIR / "backups",
            "screenshots": self._screenshots_dir(),
            "crashes": DATA_DIR / "logs" / "crashes",
            "skins": DATA_DIR / "skins" / "library",
            "terrain": DATA_DIR / "terrain",
        }
        if kind == "instance":
            target = self._game_dir_of(cfg.selected_instance_id or "")
            mapping["instance"] = target
        elif kind.startswith("version:"):
            vid = kind.split(":", 1)[1]
            mapping["version"] = self._version_game_dir(vid)
        elif kind.startswith("versiondir:"):
            vid = kind.split(":", 1)[1]
            mapping["versiondir"] = cfg.game_path / "versions" / vid
        elif kind.startswith("versionmods:"):
            vid = kind.split(":", 1)[1]
            mapping["versionmods"] = self._version_game_dir(vid) / "mods"
        target = mapping.get(kind) or mapping.get(kind.split(":", 1)[0])
        if target is None:
            return {"ok": False, "message": "未知目录"}
        try:
            target.mkdir(parents=True, exist_ok=True)
            os.startfile(str(target))  # noqa: S606
            return {"ok": True, "path": str(target)}
        except OSError as exc:
            return {"ok": False, "message": str(exc)}

    def open_browser(self, url: str = "") -> dict:
        """打开内置浏览器窗口（独立 WebView2 窗口，可直接播放 B 站视频）。"""
        text = str(url or "").strip()
        if not text:
            text = "https://www.bilibili.com"
        if not text.startswith(("http://", "https://")):
            text = "https://" + text
        try:
            webview.create_window("MikanCL 浏览器", text, width=1060, height=720)
        except Exception as exc:  # noqa: BLE001 - 窗口创建失败给出可读提示
            return {"ok": False, "message": f"打开浏览器失败：{exc}"}
        return {"ok": True, "url": text}

    def open_url(self, url: str) -> dict:
        text = str(url or "")
        if not text.startswith(("http://", "https://")):
            return {"ok": False, "message": "链接无效"}
        os.startfile(text)  # noqa: S606
        return {"ok": True}

    def _fast_close(self) -> None:
        """关闭窗口时先落盘再直接结束进程，跳过 WebView2 环境回收（否则会卡 1~2 秒）。"""
        try:
            self.config.cancel_debounced_save()
            self.config.save()
        except Exception:  # noqa: BLE001 - 退出阶段不再抛异常
            pass
        os._exit(0)

    def window_action(self, action: str) -> None:
        if self.window is None:
            return
        if action == "close":
            self._fast_close()
            return
        elif action == "minimize":
            self.window.minimize()
        elif action == "toggle_max":
            self.window_restore() if self._window_maximized() else self.window_maximize()

    # ---------- 无边框窗口缩放 ----------
    def _native_view(self):
        return getattr(self.window, "native", None)

    def _window_maximized(self) -> bool:
        view = self._native_view()
        return "Maximized" in str(getattr(view, "WindowState", "")) if view is not None else False

    def window_maximize(self) -> dict:
        try:
            if self.window is not None:
                self.window.maximize()
        except Exception:  # noqa: BLE001 - 个别系统不支持
            return {"ok": False}
        return {"ok": True}

    def window_rect(self) -> dict:
        """返回窗口逻辑坐标（与页面 CSS 像素一致），供前端拖拽缩放使用。"""
        view = self._native_view()
        if view is None:
            return {"ok": False, "x": 0, "y": 0, "w": 1120, "h": 720, "maximized": False}
        try:
            scale = float(getattr(view, "_scale", 1) or 1)
            location = view.Location
            return {
                "ok": True,
                "x": float(location.X) / scale,
                "y": float(location.Y) / scale,
                "w": float(view.Width) / scale,
                "h": float(view.Height) / scale,
                "maximized": "Maximized" in str(getattr(view, "WindowState", "")),
            }
        except Exception:  # noqa: BLE001 - 缩放失败时前端退化为不缩放
            return {"ok": False, "x": 0, "y": 0, "w": 1120, "h": 720, "maximized": False}

    def window_restore(self) -> dict:
        try:
            if self.window is not None:
                self.window.restore()
        except Exception:  # noqa: BLE001
            pass
        return {"ok": True}

    def window_set_rect(self, x: float = 0, y: float = 0, w: float = 0, h: float = 0) -> dict:
        """拖动边框时由前端高频调用：先移动再缩放，保证左/上边拖拽跟手。"""
        if self.window is None:
            return {"ok": False}
        try:
            width = max(960, int(round(float(w))))
            height = max(600, int(round(float(h))))
            self.window.move(int(round(float(x))), int(round(float(y))))
            self.window.resize(width, height)
        except Exception:  # noqa: BLE001
            return {"ok": False}
        return {"ok": True}

    # ---------- 透视桌面的原生毛玻璃 ----------
    def _hwnd(self) -> int:
        view = self._native_view()
        if view is None:
            return 0
        try:
            return int(view.Handle.ToInt64())
        except Exception:  # noqa: BLE001
            try:
                return int(getattr(view, "Handle", 0) or 0)
            except Exception:  # noqa: BLE001
                return 0

    @staticmethod
    def _dwm_backdrop(hwnd: int, value: int) -> bool:
        """Win11 22621+ 的系统背景类型：3 = 亚克力，1 = 无。"""
        import ctypes

        try:
            attr = ctypes.c_int(int(value))
            res = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd), 38, ctypes.byref(attr), ctypes.sizeof(attr)
            )
            return int(res) == 0
        except Exception:  # noqa: BLE001 - Win10 没有该属性
            return False

    @staticmethod
    def _accent_blur(hwnd: int, state: int, strength: int) -> None:
        """Win10 回退：SetWindowCompositionAttribute 亚克力模糊，强度控制染色浓度。"""
        import ctypes

        class AccentPolicy(ctypes.Structure):
            _fields_ = [
                ("AccentState", ctypes.c_int),
                ("AccentFlags", ctypes.c_int),
                ("GradientColor", ctypes.c_uint),
                ("AnimationId", ctypes.c_int),
            ]

        class WindowCompositionAttributeData(ctypes.Structure):
            _fields_ = [
                ("Attribute", ctypes.c_int),
                ("Data", ctypes.c_void_p),
                ("SizeOfData", ctypes.c_size_t),
            ]

        if state:
            # 染色只做很淡的一层，让桌面透出来；过重的深色 alpha 会变成一块灰板
            alpha = max(8, min(72, int(6 + max(0, min(100, strength)) * 0.5)))
            tint = (alpha << 24) | 0x0010130C  # AABBGGRR：深绿黑 #0c1310
            policy = AccentPolicy(int(state), 0, tint, 0)
        else:
            policy = AccentPolicy(0, 0, 0, 0)
        data = WindowCompositionAttributeData(
            19, ctypes.cast(ctypes.pointer(policy), ctypes.c_void_p), ctypes.sizeof(policy)
        )
        try:
            ctypes.windll.user32.SetWindowCompositionAttribute(ctypes.c_void_p(hwnd), ctypes.byref(data))
        except Exception:  # noqa: BLE001
            pass

    def _form_paint(self, mode: str, strength: int, blur: int) -> None:
        """设置窗体底色与整体透明度。

        alpha：整体 alpha 半透明，桌面透出且鼠标完全正常，强度/模糊都直接影响通透度；
        off  ：恢复正常不透明外观。
        """
        view = self._native_view()
        if view is None:
            return
        try:
            from System.Drawing import Color
            from System.Windows.Forms import MethodInvoker
        except Exception:  # noqa: BLE001 - 非 Windows / 缺 pythonnet 时直接放弃
            return

        # 窗体底板跟随明暗模式：日间用浅色底，避免透明窗口后面透出一块深色「黑板」
        light = str(getattr(self.config, "color_mode", "dark")).lower() == "light"
        base = (244, 248, 253) if light else (11, 21, 18)
        if mode == "alpha":
            color = Color.FromArgb(255, base[0], base[1], base[2])
            # 强度越高内容越实；模糊（磨砂厚度）越大也越实，0 时为最通透状态
            opacity = max(0.76, min(0.97, 0.88 + strength * 0.001 + blur * 0.0008))
        else:
            color = Color.FromArgb(255, base[0], base[1], base[2])
            opacity = 1.0

        def _apply() -> None:
            try:
                view.TransparencyKey = Color.Empty
                view.BackColor = color
                view.Opacity = opacity
            except Exception:  # noqa: BLE001
                pass

        try:
            if view.InvokeRequired:
                view.Invoke(MethodInvoker(_apply))
            else:
                _apply()
        except Exception:  # noqa: BLE001
            pass

    def glass_apply(self) -> dict:
        """按配置开启/关闭桌面透视毛玻璃；失败时前端仍保留 CSS 毛玻璃。"""
        if sys.platform != "win32":
            return {"ok": False, "message": "仅支持 Windows"}
        enabled = bool(getattr(self.config, "glass_see_through", False))
        strength = max(0, min(100, int(getattr(self.config, "glass_strength", 62) or 62)))
        blur = max(0, min(40, int(getattr(self.config, "glass_blur", 20) or 0)))
        hwnd = self._hwnd()
        if not hwnd:
            return {"ok": False, "message": "窗口尚未就绪"}
        try:
            if enabled:
                self._form_paint("alpha", strength, blur)
            else:
                self._dwm_backdrop(hwnd, 1)
                self._accent_blur(hwnd, 0, strength)
                self._form_paint("off", strength, blur)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": str(exc)}
        return {"ok": True, "enabled": enabled, "strength": strength, "blur": blur}


def _warmup(api: "WebApi", config) -> None:
    """后台预热：Java 扫描与可选 JVM 预加载，不阻塞首屏。"""
    try:
        api._java_list()
    except Exception:  # noqa: BLE001 - 预热失败不响应用户
        pass
    try:
        from ..java import preload_jvm

        if bool(getattr(config, "preload_jvm", False)):
            target = str(
                getattr(config, "preload_java_path", "") or getattr(config, "java_path", "") or ""
            )
            if target:
                preload_jvm(target)
    except Exception:  # noqa: BLE001
        pass


def _schedule_restart() -> None:
    """退出后延迟 2 秒重启自身，避开单实例锁竞争。"""
    import subprocess

    try:
        if getattr(sys, "frozen", False):
            target = [sys.executable]
            cwd = str(Path(sys.executable).resolve().parent)
        else:
            # 源码运行没有 mc_launcher/__main__.py，必须用 run.py 重启
            target = [sys.executable, "run.py"]
            cwd = str(Path(__file__).resolve().parents[2])
        # 直接传完整命令行字符串给 CreateProcess（不要用 ["cmd","/c",...] 列表：
        # Python 会把 start "" 转义成 \"\"，cmd 解析失败）。
        # start 后面必须是带引号的空标题 ""，否则第一个参数会被当成要运行的程序，
        # 弹出「Windows 找不到文件 'MikanCL'」；标题也不能写不带引号的 MikanCL。
        # 延迟用 ping 而不是 timeout：timeout 依赖控制台输入，在分离进程里会失败。
        command = (
            'cmd /c ping -n 3 127.0.0.1 >nul & start "" '
            + subprocess.list2cmdline(target)
        )
        flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(
            command,
            cwd=cwd,
            creationflags=flags,
            close_fds=True,
        )
    except Exception:  # noqa: BLE001 - 自动重启失败不影响用户手动启动
        pass


def run(config) -> int:
    """启动美化版窗口；缺少 WebView2 / 渲染失败返回 2，由入口给出修复指引。"""
    ok, _label = runtime_status()
    if not ok:
        return _prompt_missing_runtime()

    api = WebApi(config)
    # 只允许顶栏左侧的空白/标题区域拖动窗口；按钮区域不匹配该选择器。
    # pywebview 自带 drag-region 实现，比在 JS 里反复调用 SendMessage 稳定得多。
    try:
        webview.settings["DRAG_REGION_SELECTOR"] = ".pywebview-drag-region"
    except Exception:  # noqa: BLE001 - 旧版本 pywebview 没有该设置项
        pass
    # 自动化测试/排障：设置 MIKAN_CDP_PORT 后开放 DevTools 协议端口，正常运行不开启
    cdp_port = os.environ.get("MIKAN_CDP_PORT", "").strip()
    if cdp_port.isdigit():
        try:
            webview.settings["REMOTE_DEBUGGING_PORT"] = int(cdp_port)
        except Exception:  # noqa: BLE001
            pass
    window = webview.create_window(
        "MikanCL",
        url=str(WEB_DIR / "index.html"),
        js_api=api,
        width=1120,
        height=720,
        min_size=(960, 600),
        frameless=True,
        # 注意：transparent=True 时必须让 pywebview 走它自己的 show/hide hack（见 winforms.py），
        # 不能再传 hidden=True，否则会走 hidden 分支、跳过透明初始化，窗口只剩一层不透明白底。
        hidden=False,
        # 关闭 easy_drag：否则在窗口任意位置按下鼠标都会拖动窗口，滑块无法拖动
        easy_drag=False,
        # 透明窗口用于「透视桌面」毛玻璃；关闭该模式时页面底色不透明，外观不受影响
        transparent=True,
        background_color=("#f4f8fd" if str(getattr(config, "color_mode", "dark")).lower() == "light" else "#0b1512"),
    )
    api.window = window
    _shown = {"value": False}

    def _show_when_ready() -> None:
        """首屏绘制完成后再显示窗口，避免启动时先看到一片黑色底。"""
        if not _shown["value"]:
            _shown["value"] = True
            try:
                window.show()
            except Exception:  # noqa: BLE001 - 个别环境不支持 show
                pass
        try:
            api.glass_apply()
        except Exception:  # noqa: BLE001 - 原生毛玻璃失败不影响页面
            pass

    try:
        window.events.loaded += _show_when_ready
    except Exception:  # noqa: BLE001 - 旧版 pywebview 没有该事件时忽略
        pass
    # pywebview 注入时会递归遍历 js_api 的公开属性；Window/Config 这类对象必须排除，
    # 否则会遍历 WebView2 原生 COM 对象，导致接口注入极慢甚至失败。
    for _obj in (window, config):
        try:
            _obj._serializable = False
        except Exception:  # noqa: BLE001 - 只影响注入优化，失败可忽略
            pass

    def _guard_close() -> bool:
        if not bool(getattr(config, "close_to_tray", False)):
            return True
        try:
            window.minimize()
        except Exception:  # noqa: BLE001 - 最小化失败时允许正常退出
            return True
        return False

    try:
        window.events.closing += _guard_close
    except Exception:  # noqa: BLE001 - 旧版 pywebview 没有该事件时忽略
        pass
    threading.Thread(target=_warmup, args=(api, config), name="mikan-warmup", daemon=True).start()
    try:
        webview.start(
            gui="edgechromium",
            debug=bool(os.environ.get("MIKAN_WEBVIEW_DEBUG")),
            private_mode=False,
            storage_path=str(DATA_DIR / "webview2"),
        )
    except Exception as exc:  # noqa: BLE001 - 渲染器初始化失败
        import traceback

        try:
            (DATA_DIR / "logs").mkdir(parents=True, exist_ok=True)
            with open(DATA_DIR / "logs" / "webview_error.log", "a", encoding="utf-8") as log:
                log.write(f"{exc}\n{traceback.format_exc()}\n")
        except OSError:
            pass
        return 2
    return 0
