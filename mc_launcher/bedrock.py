"""基岩版（Minecraft Bedrock）：版本目录、多线程下载、Appx 安装、启动与卸载。

两条数据来源：
1. 微软商店官方接口（store.rg-adguard.net）—— 获取当前正式版 / 预览版的真实直链，可多线程下载；
2. MCAPPX 版本库（www.mcappx.com）—— 内置离线目录，覆盖历史版本（含 1.8.1），
   其直链受 Cloudflare 人机验证保护，下载失败时引导用户用浏览器打开下载页。
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .config import DATA_DIR
from .net import Cancelled, DownloadError

PACKAGE_NAME = "Microsoft.MinecraftUWP"
PACKAGE_FAMILY = "Microsoft.MinecraftUWP_8wekyb3d8bbwe"
STORE_PRODUCT_URL = "https://www.microsoft.com/store/productId/9NBLGGH2JHXJ"
STORE_PAGE = "https://apps.microsoft.com/detail/9NBLGGH2JHXJ"
MCAPPX_PAGE = "https://www.mcappx.com/bedrock/"
DOWNLOAD_ROOT = DATA_DIR / "bedrock"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_ARCH_ORDER = {"x64": 0, "x86": 1, "arm64": 2, "arm": 3, "neutral": 9}

STORE_RINGS = {
    "Retail": "正式版",
    "RP": "预览版",
}


# ---------------------------------------------------------------------------
# 目录
# ---------------------------------------------------------------------------
def catalog_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "bedrock_catalog.json"


_CATALOG_CACHE: dict | None = None


def load_catalog(force: bool = False) -> dict:
    """读取内置的 MCAPPX 目录（打包后随 exe 一起解包）。"""
    global _CATALOG_CACHE
    if _CATALOG_CACHE is not None and not force:
        return _CATALOG_CACHE
    path = catalog_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {"majors": [], "releases": []}
    data.setdefault("majors", [])
    data.setdefault("releases", [])
    _CATALOG_CACHE = data
    return data


# ---------------------------------------------------------------------------
# 微软商店直链
# ---------------------------------------------------------------------------
_SIZE_RE = re.compile(r"([0-9.]+)\s*(KB|MB|GB|TB)", re.I)
_NAME_RE = re.compile(
    r"^(.+?)_(\d+\.\d+\.\d+\.\d+)_(x64|x86|arm64|arm|neutral)_", re.I
)
_PACKAGE_EXT = (".appx", ".msix", ".appxbundle", ".msixbundle")


def _parse_size(text: str) -> int:
    match = _SIZE_RE.search(text or "")
    if not match:
        return 0
    value = float(match.group(1))
    unit = match.group(2).upper()
    scale = {"KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3, "TB": 1024 ** 4}[unit]
    return int(value * scale)


def _request_store_listing(ring: str, timeout: int) -> str:
    body = urllib.parse.urlencode(
        {"type": "url", "url": STORE_PRODUCT_URL, "ring": ring, "lang": "en-US"}
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://store.rg-adguard.net/api/GetFiles",
        data=body,
        headers={
            "User-Agent": _UA,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "text/html,application/xhtml+xml",
            "Origin": "https://store.rg-adguard.net",
            "Referer": "https://store.rg-adguard.net/",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        raise DownloadError(f"商店接口请求失败：{exc}") from exc


def fetch_store_packages(ring: str = "Retail", timeout: int = 60,
                         attempts: int = 3,
                         cancel: threading.Event | None = None) -> list[dict]:
    """向 rg-adguard 请求商店清单，返回可安装的 Appx 条目（含依赖包）。

    该接口偶尔会因频率限制返回空页面，这里做几次重试；仍为空则报错，
    避免界面把「被限流」误显示成「商店没有可用安装包」。
    `cancel` 用于界面退出时中止重试，避免后台线程把关闭流程拖住。
    """
    last_detail = ""
    for attempt in range(max(1, attempts)):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        text = _request_store_listing(ring, timeout)
        entries = _parse_store_listing(text, ring)
        if entries:
            return entries
        lowered = text.lower()
        if any(word in lowered for word in ("too many", "rate limit", "blocked", "captcha")):
            last_detail = "商店接口触发频率限制，请稍后再试（或配置代理）"
        else:
            last_detail = "商店接口没有返回可解析的安装包"
        if attempt + 1 < attempts:
            # 重试间隔分段睡眠，保证取消信号能在 0.2 秒内响应
            deadline = time.monotonic() + 1.5 * (attempt + 1)
            while time.monotonic() < deadline:
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                time.sleep(0.2)
    raise DownloadError(last_detail or "商店接口没有返回可解析的安装包")


def _parse_store_listing(text: str, ring: str) -> list[dict]:
    rows = re.findall(
        r'<a href="([^"]+)"[^>]*>([^<]+)</a>'
        r".*?<td align=\"center\">([^<]*)</td><td align=\"center\">([0-9a-fA-F]{40})</td>"
        r'<td align=\"center\">([^<]*)</td>',
        text,
        re.S,
    )
    entries: list[dict] = []
    for href, name, _expires, sha1, size_text in rows:
        name = html.unescape(name).strip()
        if not name.lower().endswith(_PACKAGE_EXT):
            continue
        match = _NAME_RE.match(name)
        package = match.group(1) if match else name.split("_")[0]
        version = match.group(2) if match else ""
        arch = (match.group(3) if match else "neutral").lower()
        entries.append(
            {
                "source": "store",
                "channel": ring,
                "package": package,
                "version": version,
                "arch": arch,
                "size": _parse_size(html.unescape(size_text)),
                "sha1": sha1.lower(),
                "url": html.unescape(href),
                "name": name,
                "release_date": "",
                "min_os": 0,
                "format": "Appx",
                "dependency": package.lower().startswith("microsoft.vclibs"),
            }
        )
    entries.sort(key=lambda item: (_ARCH_ORDER.get(item["arch"], 9), item["package"]))
    return entries


# ---------------------------------------------------------------------------
# 已安装状态 / 安装 / 启动 / 卸载
# ---------------------------------------------------------------------------
def _powershell(script: str, timeout: int = 120) -> tuple[int, str]:
    command = [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        "$OutputEncoding=[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; " + script,
    ]
    kwargs = {"capture_output": True, "text": True, "timeout": timeout,
              "encoding": "utf-8", "errors": "replace"}
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(command, **kwargs)
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired as exc:
        raise DownloadError("PowerShell 执行超时") from exc


def installed_package() -> dict | None:
    """查询当前已安装的基岩版（未安装时返回 None）。"""
    if sys.platform != "win32":
        return None
    script = (
        f"$p = Get-AppxPackage -Name {PACKAGE_NAME} | Select-Object -First 1;"
        "if(-not $p){exit 0};"
        "$p | Select-Object Name,Version,Architecture,PackageFamilyName,PackageFullName,"
        "InstallLocation | ConvertTo-Json -Compress"
    )
    code, output = _powershell(script, timeout=45)
    text = output.strip()
    if not text:
        return None
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                data = json.loads(line)
            except ValueError:
                continue
            if isinstance(data, dict) and data.get("Version"):
                return data
    return None


_PROCESSOR_ARCH = {0: "x86", 5: "arm", 9: "x64", 11: "neutral", 12: "arm64"}


def arch_name(value: object) -> str:
    """把 Get-AppxPackage 的 Architecture 枚举值转成可读架构名。"""
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        text = str(value or "").strip().lower()
        return text or "未知"
    return _PROCESSOR_ARCH.get(number, str(number))


def _app_user_model_id() -> str:
    """取「包族名!应用Id」，用于 shell:AppsFolder 启动。"""
    script = (
        f"$p = Get-AppxPackage -Name {PACKAGE_NAME} | Select-Object -First 1;"
        "if(-not $p){exit 2};"
        "$m = Get-AppxPackageManifest $p;"
        "$apps = @($m.Package.Applications.Application);"
        "if($apps.Count -eq 0){exit 3};"
        "$id = $apps[0].Id;"
        "Write-Output ($p.PackageFamilyName + '!' + $id)"
    )
    code, output = _powershell(script, timeout=60)
    text = [line.strip() for line in output.strip().splitlines() if line.strip()]
    aumid = ""
    for line in reversed(text):
        if "!" in line and "_" in line:
            aumid = line
            break
    if not aumid:
        aumid = f"{PACKAGE_FAMILY}!App"
    return aumid


def launch_installed() -> tuple[bool, str]:
    """启动已安装的基岩版；返回 (是否成功, 提示信息)。"""
    if sys.platform != "win32":
        return False, "仅 Windows 支持启动基岩版"
    if installed_package() is None:
        return False, "尚未安装基岩版，请先下载并安装"
    aumid = _app_user_model_id()
    try:
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{aumid}"])
    except Exception as exc:  # noqa: BLE001
        return False, f"启动失败：{exc}"
    return True, aumid


_GAME_EXE_CACHE: str | None = None
_GAME_EXE_FALLBACK = "Minecraft.Windows.exe"


def game_executable() -> str:
    """从清单读取主程序文件名（如 Minecraft.Windows.exe），用于判断游戏是否真的启动。"""
    global _GAME_EXE_CACHE
    if _GAME_EXE_CACHE:
        return _GAME_EXE_CACHE
    script = (
        f"$p = Get-AppxPackage -Name {PACKAGE_NAME} | Select-Object -First 1;"
        "if(-not $p){exit 2};"
        "$m = Get-AppxPackageManifest $p;"
        "$apps = @($m.Package.Applications.Application);"
        "if($apps.Count -eq 0){exit 3};"
        "Write-Output ([string]$apps[0].Executable)"
    )
    exe = ""
    try:
        _code, output = _powershell(script, timeout=45)
        values = [line.strip() for line in output.strip().splitlines() if line.strip()]
        if values and values[-1].lower().endswith(".exe"):
            exe = values[-1]
    except DownloadError:
        exe = ""
    _GAME_EXE_CACHE = exe or _GAME_EXE_FALLBACK
    return _GAME_EXE_CACHE


def is_game_running() -> bool:
    """用 tasklist 判断基岩版主进程是否在运行（用于启动后验证）。"""
    if sys.platform != "win32":
        return False
    exe = game_executable()
    kwargs: dict = {"capture_output": True, "text": True, "timeout": 20,
                    "encoding": "utf-8", "errors": "replace"}
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {exe}", "/NH"], **kwargs)
    except (OSError, subprocess.SubprocessError):
        return False
    return exe.lower() in (proc.stdout or "").lower()


_ACTIVATION_HINTS = {
    "0x803f8001": (
        "该应用未获得使用授权（0x803F8001）：请用拥有 Minecraft 的正版微软账号"
        "登录微软商店（或加入 Game Pass）后再启动。手动安装的安装包本身不含授权。"
    ),
    "0x8027025a": "应用启动超时（0x8027025A），请稍后重试，或重启系统后再试。",
    "0x80073d02": "另一个安装 / 启动操作正在进行（0x80073D02），请稍后重试。",
    "0x80073cf9": "启动失败（0x80073CF9），请确认磁盘空间充足且没有安装进程占用。",
}


def activation_hint(seconds: int = 90) -> str:
    """读取最近一次应用激活失败事件并翻译为可读提示；没有事件时返回空串。"""
    if sys.platform != "win32":
        return ""
    script = (
        "$e = Get-WinEvent -LogName 'Microsoft-Windows-TWinUI/Operational' "
        "-ErrorAction SilentlyContinue | "
        "Where-Object { $_.Id -eq 5961 -and $_.TimeCreated -gt (Get-Date).AddSeconds("
        f"-{int(seconds)}"
        ") } | Select-Object -First 1;"
        "if($e){Write-Output $e.Message}"
    )
    try:
        _code, output = _powershell(script, timeout=45)
    except DownloadError:
        return ""
    text = (output or "").lower()
    for code, hint in _ACTIVATION_HINTS.items():
        if code in text:
            return hint
    return ""


def uninstall_installed() -> tuple[bool, str]:
    if sys.platform != "win32":
        return False, "仅 Windows 支持卸载基岩版"
    info = installed_package()
    if info is None:
        return False, "尚未安装基岩版"
    full_name = str(info.get("PackageFullName") or "")
    if not full_name:
        return False, "无法获取已安装包的完整名称"
    code, output = _powershell(f'Remove-AppxPackage -Package "{full_name}"', timeout=180)
    if code != 0:
        return False, output.strip()[:600] or "卸载失败"
    return True, "已卸载"


def _run_powershell_streaming(script: str, cancel: threading.Event | None,
                              timeout: int = 600, done_marker: str | None = None,
                              grace: int = 180) -> tuple[int, str]:
    """执行 PowerShell 并流式收集输出。

    读取交给独立线程 + 队列，避免 readline 长时间阻塞导致取消 / 超时失效；
    `done_marker` 出现后额外等待 `grace` 秒让 PowerShell 正常收尾（注册可能滞后）；
    marker 之后每来一行输出都会把宽限期重置，避免长时间日志把正常收尾误判成超时。
    """
    command = [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        "$OutputEncoding=[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; " + script,
    ]
    kwargs: dict = {"stdout": subprocess.PIPE, "stderr": subprocess.STDOUT, "text": True,
                    "encoding": "utf-8", "errors": "replace"}
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen(command, **kwargs)

    chunks: list[str] = []
    lines: "queue.Queue[object]" = queue.Queue()
    eof = object()

    def _reader() -> None:
        stream = proc.stdout
        try:
            if stream is not None:
                for line in iter(stream.readline, ""):
                    lines.put(line)
        except Exception:  # noqa: BLE001 - 进程被杀时读管道可能抛异常
            pass
        finally:
            lines.put(eof)

    threading.Thread(target=_reader, daemon=True, name="bedrock-ps-reader").start()

    seen_marker = False
    deadline = time.monotonic() + timeout
    grace_deadline: float | None = None
    while True:
        try:
            line = lines.get(timeout=0.2)
        except queue.Empty:
            line = None
        if line is eof:
            break
        if line:
            chunks.append(str(line))
            if done_marker and done_marker in str(line):
                seen_marker = True
                # 每来一行新输出都刷新宽限期：marker 之后的正常日志不应触发超时 kill
                grace_deadline = max(
                    grace_deadline or 0.0, time.monotonic() + grace
                )
        if cancel is not None and cancel.is_set():
            _kill(proc)
            raise Cancelled()
        limit = grace_deadline if grace_deadline is not None else deadline
        if time.monotonic() > limit:
            _kill(proc)
            break
    try:
        proc.wait(timeout=60)
    except subprocess.TimeoutExpired:
        _kill(proc)
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            pass
    code = proc.returncode if proc.returncode is not None else -1
    if seen_marker and code != 0:
        code = 0  # 标记已打印，退出码异常只是收尾被杀，按成功处理
    return code, "".join(chunks)


def _kill(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.kill()
    except Exception:  # noqa: BLE001
        pass


_INSTALL_HINTS = {
    "0x80073CF9": "安装失败（0x80073CF9）：请确认磁盘空间充足，且没有其他安装程序正在运行",
    "0x80073D02": "另一个应用安装正在进行（0x80073D02），请稍后重试",
    "0x80073CF3": "缺少运行库依赖（0x80073CF3），请重试一次以自动补装 VCLibs",
    "0x80073CF0": "无法打开安装包（0x80073CF0）：文件可能已损坏，请重新下载",
    "0x8007000D": "安装包数据无效（0x8007000D）：文件不完整或不是有效的 Appx，请重新下载",
    "0x800B0109": "证书校验失败（0x800B0109）：请确认系统时间已自动同步",
    "0x80070070": "磁盘空间不足（0x80070070），请清理空间后重试",
}

_INSTALL_MARKER = "INSTALL_OK"


def install_appx(path: Path, cancel: threading.Event | None = None,
                 log=None) -> None:
    """用 Add-AppxPackage 安装本地 Appx（微软签名的包无需开发者模式）。"""
    if sys.platform != "win32":
        raise DownloadError("仅 Windows 支持安装基岩版")
    path = Path(path)
    if not path.exists():
        raise DownloadError(f"安装包不存在：{path}")
    if log:
        log(f"[基岩版] 正在安装 {path.name}")
    script = (
        f'$ErrorActionPreference = "Stop";'
        f'Add-AppxPackage -Path "{path}" -ForceUpdateFromAnyVersion -ForceApplicationShutdown;'
        f'Write-Output "{_INSTALL_MARKER}"'
    )
    # 大包（800MB+）在机械硬盘上解包可能超过 20 分钟，超时设置得足够宽
    code, output = _run_powershell_streaming(
        script, cancel, timeout=1800, done_marker=_INSTALL_MARKER, grace=600
    )
    if _INSTALL_MARKER in output:
        if log:
            log(f"[基岩版] {path.name} 安装完成")
        return
    lowered = output.lower()
    for code_text, hint in _INSTALL_HINTS.items():
        if code_text.lower() in lowered:
            raise DownloadError(hint)
    detail = output.strip()[:800]
    raise DownloadError(f"安装失败：{detail or '未知错误'}")


# ---------------------------------------------------------------------------
# 多线程分段下载
# ---------------------------------------------------------------------------
def human_size(value: object) -> str:
    try:
        size = int(value or 0)
    except (TypeError, ValueError):
        size = 0
    if size <= 0:
        return "未知"
    if size >= 1024 ** 3:
        return f"{size / 1024 ** 3:.2f} GB"
    return f"{size / 1024 ** 2:.1f} MB"


def _request_head(url: str, timeout: int = 30) -> tuple[int, bool]:
    """返回 (总大小, 是否支持分段)；HEAD 不可用时用 Range 探测。"""
    headers = {"User-Agent": _UA, "Accept": "*/*", "Range": "bytes=0-0"}
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200) or 200)
            content_range = response.headers.get("Content-Range") or ""
            match = re.search(r"/(\d+)", content_range)
            total = int(match.group(1)) if match else 0
            if not total:
                length = response.headers.get("Content-Length") or "0"
                total = int(length) if length.isdigit() else 0
            accept = response.headers.get("Accept-Ranges", "").lower()
            ranged = status == 206 and total > 0
            return total, ranged or (accept == "bytes")
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            raise DownloadError(
                "HTTP 403：该下载节点启用了 Cloudflare 人机验证，启动器无法直接下载，"
                "请点击「打开下载页」用浏览器下载。"
            ) from exc
        raise DownloadError(f"HTTP {exc.code}：{exc.reason}") from exc
    except Exception as exc:  # noqa: BLE001
        raise DownloadError(f"连接下载节点失败：{exc}") from exc


class MultiPartDownload:
    """把文件切成多段并发下载，段文件落盘后合并；支持暂停、取消与断点续传。"""

    def __init__(self, url: str, dest: Path, workers: int = 8, size: int = 0,
                 cancel: threading.Event | None = None,
                 pause: threading.Event | None = None,
                 on_bytes=None, on_total=None, on_segment_done=None):
        self.url = url
        self.dest = Path(dest)
        self.workers = max(1, min(16, int(workers or 8)))
        self.size = int(size or 0)
        self.cancel = cancel
        self.pause = pause
        self.on_bytes = on_bytes
        self.on_total = on_total
        # 每完成一个分段回调一次，供下载中心显示「剩余文件」计数
        self.on_segment_done = on_segment_done
        self._lock = threading.Lock()
        self._done_bytes = 0
        self._segments_done = 0

    def _check(self) -> None:
        while self.pause is not None and self.pause.is_set():
            if self.cancel is not None and self.cancel.is_set():
                raise Cancelled()
            time.sleep(0.2)
        if self.cancel is not None and self.cancel.is_set():
            raise Cancelled()

    def _report(self, count: int) -> None:
        with self._lock:
            self._done_bytes += count
            done = self._done_bytes
        if self.on_bytes:
            # 回传已完成字节的绝对值，避免多线程累加导致进度重复计算
            self.on_bytes(done)

    def _segment_finished(self, total_segments: int) -> None:
        """分段完成计数：回调 (已完成, 总分段)，下载中心据此显示「剩余文件」。"""
        if not self.on_segment_done:
            return
        with self._lock:
            self._segments_done += 1
            done = self._segments_done
        try:
            self.on_segment_done(done, total_segments)
        except Exception:  # noqa: BLE001 - 进度回调不应影响下载
            pass

    def _segment(self, index: int, start: int, end: int, total_segments: int = 1) -> None:
        part = self.dest.with_name(f"{self.dest.name}.part{index}")
        length = end - start + 1
        offset = part.stat().st_size if part.exists() else 0
        if offset > length:
            # 段文件比应写的长度还长（上次中断时写多 / 分段范围变化）：先截掉多余字节，
            # 否则合并后总长度必然对不上，会误报成"下载失败"
            try:
                with open(part, "r+b") as fh:
                    fh.truncate(length)
            except OSError:
                pass
            offset = length
        if offset >= length:
            self._segment_finished(total_segments)
            return
        headers = {"User-Agent": _UA, "Accept": "*/*",
                   "Range": f"bytes={start + offset}-{end}"}
        request = urllib.request.Request(self.url, headers=headers)
        attempt = 0
        while True:
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    status = int(getattr(response, "status", 200) or 200)
                    if status not in (200, 206):
                        raise DownloadError(f"HTTP {status}")
                    with open(part, "ab") as fh:
                        while True:
                            self._check()
                            chunk = response.read(65536)
                            if not chunk:
                                break
                            fh.write(chunk)
                            self._report(len(chunk))
                if part.stat().st_size >= length:
                    self._segment_finished(total_segments)
                    return
                # 连接提前断开：以当前段文件长度继续
                attempt += 1
                if attempt > 6:
                    raise DownloadError("分段下载中断次数过多")
                offset = part.stat().st_size
                headers["Range"] = f"bytes={start + offset}-{end}"
                request = urllib.request.Request(self.url, headers=headers)
            except Cancelled:
                raise
            except Exception:  # noqa: BLE001
                attempt += 1
                if attempt > 6:
                    raise
                self._check()
                time.sleep(1.0)

    def run(self) -> Path:
        dest = self.dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        total, ranged = _request_head(self.url)
        if self.size:
            total = total or self.size
        if self.on_total and total:
            self.on_total(total)

        parts: list[Path] = []
        if not ranged or total <= 0:
            # 不支持分段：单流下载（仍保留 .part 续传语义）
            part = dest.with_name(dest.name + ".part")
            offset = part.stat().st_size if part.exists() else 0
            if total and offset >= total:
                os.replace(part, dest)
                self._segment_finished(1)
                return dest
            if offset:
                self._report(offset)
            headers = {"User-Agent": _UA, "Accept": "*/*"}
            if offset:
                headers["Range"] = f"bytes={offset}-"
            request = urllib.request.Request(self.url, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    with open(part, "ab" if offset else "wb") as fh:
                        while True:
                            self._check()
                            chunk = response.read(65536)
                            if not chunk:
                                break
                            fh.write(chunk)
                            self._report(len(chunk))
            except Cancelled:
                raise
            os.replace(part, dest)
            self._segment_finished(1)
            return dest

        segment_count = min(self.workers, max(1, total // (2 * 1024 * 1024)))
        segment_count = max(1, min(segment_count, self.workers))
        span = total // segment_count
        ranges: list[tuple[int, int]] = []
        for i in range(segment_count):
            start = i * span
            end = total - 1 if i == segment_count - 1 else (start + span - 1)
            ranges.append((start, end))
            parts.append(dest.with_name(f"{dest.name}.part{i}"))

        with ThreadPoolExecutor(max_workers=segment_count) as pool:
            resumed = sum(p.stat().st_size for p in parts if p.exists())
            if resumed:
                self._report(resumed)
            futures = [pool.submit(self._segment, i, start, end, segment_count)
                       for i, (start, end) in enumerate(ranges)]
            for future in futures:
                future.result()

        # 合并分段：先按各段应写长度截断残留字节，避免历史残留把总长度拼错
        combined = dest.with_name(dest.name + ".merge")
        with open(combined, "wb") as out:
            for part, (start, end) in zip(parts, ranges):
                expected = end - start + 1
                if part.exists() and part.stat().st_size > expected:
                    try:
                        with open(part, "r+b") as fh:
                            fh.truncate(expected)
                    except OSError:
                        pass
                with open(part, "rb") as fh:
                    shutil.copyfileobj(fh, out, 1024 * 1024)
        actual = combined.stat().st_size
        if total and actual != total:
            combined.unlink(missing_ok=True)
            raise DownloadError(f"文件长度不符（{actual}/{total}）")
        os.replace(combined, dest)
        for part in parts:
            part.unlink(missing_ok=True)
        return dest


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha1_of(path: Path) -> str:
    digest = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def target_file_name(entry: dict) -> str:
    """根据条目生成落地文件名（依赖包沿用其自身包名，避免混在游戏包里）。"""
    package = str(entry.get("package") or PACKAGE_NAME)
    version = str(entry.get("version") or "unknown")
    arch = str(entry.get("arch") or "x64")
    name = entry.get("name")
    if isinstance(name, str) and name.lower().endswith(_PACKAGE_EXT):
        return name
    return f"{package}_{version}_{arch}.appx"


def open_url(url: str) -> None:
    """用系统默认浏览器打开链接。"""
    try:
        os.startfile(url)  # noqa: S606 - Windows 专用
    except Exception:  # noqa: BLE001
        import webbrowser

        webbrowser.open(url)


def build_store_entries(entries: list[dict]) -> list[dict]:
    """把商店清单整理成按架构去重的展示条目（不含 VCLibs 等依赖包）。"""
    grouped: dict[tuple[str, str], dict] = {}
    for entry in entries:
        if entry.get("dependency"):
            continue
        name = str(entry.get("package") or "")
        if name and not name.lower().startswith(PACKAGE_NAME.lower()):
            continue
        key = (str(entry.get("version") or ""), str(entry.get("arch") or ""))
        grouped.setdefault(key, entry)
    rows = list(grouped.values())
    rows.sort(key=lambda item: (
        tuple(int(p) if p.isdigit() else 0 for p in str(item.get("version") or "").split(".")),
        _ARCH_ORDER.get(str(item.get("arch") or ""), 9),
    ), reverse=True)
    return rows


def dependency_entries(entries: list[dict], arch: str) -> list[dict]:
    return [e for e in entries if e.get("dependency") and e.get("arch") in (arch, "neutral")]


@dataclass
class BedrockInstallResult:
    path: Path
    installed: bool
    message: str = ""


@dataclass
class BedrockCatalogEntry:
    """统一展示用的行数据。"""

    version: str
    channel: str
    source: str
    arch: str
    size: int = 0
    date: str = ""
    page_url: str = ""
    download_url: str = ""
    sha256: str = ""
    sha1: str = ""
    package_id: str = ""
    format: str = "Appx"
    major: str = ""
    dependencies: list[dict] = field(default_factory=list)
