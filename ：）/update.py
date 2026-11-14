"""启动器自更新：从 GitHub 仓库 luohaocheng171/mikanCL 抓取版本并替换自身。

流程：
    info = check_update()              # 抓取最新 release（API → 重定向 → HTML 三级回退）
    path = download_update(info, ...)  # 下载 exe 到 data/updates/
    apply_update(path)                 # 写一个等待本进程退出的 bat，替换 exe 并重启

Windows 下正在运行的 exe 无法直接覆盖，因此由批处理等待 PID 退出后再替换。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import APP_VERSION, USER_AGENT
from .config import DATA_DIR
from .relaunch import clean_env

REPO = "luohaocheng171/mikanCL"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
REPO_LATEST = f"https://github.com/{REPO}/releases/latest"
REPO_RELEASES = f"https://github.com/{REPO}/releases"
UPDATE_DIR = DATA_DIR / "updates"


class UpdateError(Exception):
    """更新流程中的可读错误。"""


def _request(url: str, timeout: float = 12.0):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json, text/html;q=0.9, */*;q=0.8",
        },
    )
    return urllib.request.urlopen(request, timeout=timeout)


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = [int(item) for item in re.findall(r"\d+", value or "")][:4]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_newer(latest: str, current: str | None = None) -> bool:
    return _version_tuple(latest) > _version_tuple(current or APP_VERSION)


def _clean_tag(tag: str) -> str:
    text = (tag or "").strip()
    if text.lower().startswith("v"):
        text = text[1:]
    # 兼容 v5.2.0 / release-5.2.0 / 5.2.0 等写法
    match = re.search(r"\d+(?:\.\d+){0,3}", text)
    return match.group(0) if match else text


def _pick_asset(assets: list[dict]) -> dict | None:
    exes = [item for item in assets if str(item.get("name", "")).lower().endswith(".exe")]
    if exes:
        return exes[0]
    zips = [item for item in assets if str(item.get("name", "")).lower().endswith(".zip")]
    return zips[0] if zips else None


def _from_api() -> dict | None:
    try:
        with _request(API_LATEST) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError):
        return None
    if not isinstance(payload, dict) or not payload.get("tag_name"):
        return None
    asset = _pick_asset(payload.get("assets") or [])
    return {
        "tag": _clean_tag(str(payload.get("tag_name"))),
        "name": str(payload.get("name") or payload.get("tag_name")),
        "notes": str(payload.get("body") or ""),
        "page": str(payload.get("html_url") or REPO_LATEST),
        "published": str(payload.get("published_at") or ""),
        "asset_url": str((asset or {}).get("browser_download_url") or ""),
        "asset_name": str((asset or {}).get("name") or ""),
        "source": "api",
    }


def _from_redirect() -> dict | None:
    try:
        with _request(REPO_LATEST) as response:
            final = response.geturl()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return None
    match = re.search(r"/tag/([^/?#]+)", final or "")
    if not match:
        return None
    tag = _clean_tag(urllib.parse.unquote(match.group(1)))
    return {
        "tag": tag,
        "name": f"MikanCL {tag}",
        "notes": "",
        "page": final,
        "published": "",
        "asset_url": "",
        "asset_name": "",
        "source": "redirect",
    }


def _from_html() -> dict | None:
    try:
        with _request(REPO_RELEASES) as response:
            html = response.read().decode("utf-8", "replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return None
    tags = re.findall(r"/releases/tag/([^\"'?#]+)", html)
    cleaned = []
    for tag in tags:
        value = _clean_tag(urllib.parse.unquote(tag))
        if re.match(r"^\d", value) and value not in cleaned:
            cleaned.append(value)
    if not cleaned:
        return None
    cleaned.sort(key=_version_tuple, reverse=True)
    return {
        "tag": cleaned[0],
        "name": f"MikanCL {cleaned[0]}",
        "notes": "",
        "page": f"https://github.com/{REPO}/releases/tag/{cleaned[0]}",
        "published": "",
        "asset_url": "",
        "asset_name": "",
        "source": "html",
    }


def check_update() -> dict:
    """返回最新版本信息；失败时返回 {"ok": False, "message": ...}，不抛异常。"""
    for loader in (_from_api, _from_redirect, _from_html):
        info = loader()
        if info and info.get("tag"):
            info["ok"] = True
            info["current"] = APP_VERSION
            info["has_update"] = is_newer(info["tag"])
            info["downloadable"] = bool(info.get("asset_url"))
            return info
    return {
        "ok": False,
        "message": "无法连接 GitHub 更新源，请检查网络或稍后再试。",
        "current": APP_VERSION,
        "has_update": False,
    }


def download_update(info: dict, *, progress=None, cancel=None) -> Path:
    """下载更新包到 data/updates/，返回本地路径。"""
    url = str((info or {}).get("asset_url") or "")
    name = str((info or {}).get("asset_name") or "")
    if not url:
        raise UpdateError("该版本没有可下载的安装包，请到 GitHub Releases 手动下载。")
    UPDATE_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w.\-]+", "_", name or f"MikanCL-{info.get('tag')}.exe")
    target = UPDATE_DIR / safe
    part = target.with_suffix(target.suffix + ".part")
    try:
        with _request(url, timeout=30) as response, open(part, "wb") as handle:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            while True:
                if cancel is not None and cancel.is_set():
                    raise UpdateError("已取消下载更新")
                chunk = response.read(262144)
                if not chunk:
                    break
                handle.write(chunk)
                done += len(chunk)
                if progress:
                    percent = (done / total * 100.0) if total else 0.0
                    progress(percent, done, total)
        os.replace(part, target)
        return target
    except UpdateError:
        try:
            part.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        try:
            part.unlink(missing_ok=True)
        except OSError:
            pass
        raise UpdateError(f"下载更新失败：{exc}") from exc


def current_executable() -> Path | None:
    """返回当前 exe 路径；源码运行时返回 None。"""
    if not getattr(sys, "frozen", False):
        return None
    try:
        return Path(sys.executable).resolve()
    except OSError:
        return None


def apply_update(new_file: Path, *, relaunch: bool = True) -> dict:
    """写替换脚本并以脱离方式启动；调用方随后需要关闭启动器。"""
    target = current_executable()
    if target is None:
        return {"ok": False, "message": "源码模式不支持自动替换，请手动替换文件。"}
    new_file = Path(new_file)
    if not new_file.is_file():
        return {"ok": False, "message": "更新包不存在，请重新下载。"}
    if new_file.suffix.lower() != ".exe":
        return {"ok": False, "message": "更新包不是 exe，请到 GitHub Releases 手动更新。"}
    script = UPDATE_DIR / "apply_update.bat"
    try:
        UPDATE_DIR.mkdir(parents=True, exist_ok=True)
        script.write_text(
            "@echo off\r\n"
            "setlocal\r\n"
            f'set "TARGET={target}"\r\n'
            f'set "SOURCE={new_file}"\r\n'
            f'set "PID={os.getpid()}"\r\n'
            ":wait\r\n"
            'tasklist /FI "PID eq %PID%" 2>nul | find "%PID%" >nul\r\n'
            "if not errorlevel 1 (\r\n"
            "  ping -n 2 127.0.0.1 >nul\r\n"
            "  goto wait\r\n"
            ")\r\n"
            "for /l %%i in (1,1,30) do (\r\n"
            '  move /y "%SOURCE%" "%TARGET%" >nul 2>&1\r\n'
            "  if not exist \"%SOURCE%\" goto done\r\n"
            "  ping -n 2 127.0.0.1 >nul\r\n"
            ")\r\n"
            ":done\r\n"
            + (f'start "" "%TARGET%"\r\n' if relaunch else "")
            + 'del "%~f0" >nul 2>&1\r\n',
            encoding="mbcs",
        )
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )
        subprocess.Popen(
            ["cmd", "/c", str(script)],
            creationflags=flags,
            close_fds=True,
            cwd=str(UPDATE_DIR),
            # 别把 onefile 的 _PYI_* 变量带给更新后重新打开的 exe（会复用已删除的 _MEI）
            env=clean_env(),
        )
    except OSError as exc:
        return {"ok": False, "message": f"无法启动更新脚本：{exc}"}
    return {
        "ok": True,
        "message": "更新包已下载，启动器关闭后会自动替换并重新打开。",
        "target": str(target),
    }


def cleanup_old_files(delay_seconds: float = 0.0) -> None:
    """清理残留的 .part 与旧压缩包；任何错误都忽略。"""
    if delay_seconds:
        time.sleep(delay_seconds)
    try:
        if not UPDATE_DIR.is_dir():
            return
        for item in UPDATE_DIR.iterdir():
            if item.suffix == ".part":
                item.unlink(missing_ok=True)
    except OSError:
        pass
