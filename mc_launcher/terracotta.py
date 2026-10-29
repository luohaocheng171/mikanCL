"""陶瓦联机（Terracotta）集成：下载安装、进程管理与本地 HTTP API 封装。

Terracotta 是 HMCL 团队使用的开源 P2P 联机工具（AGPL-3.0，作者 Burning_TNT），
本项目仅以「未修改的二进制 + 进程间 HTTP 接口」方式调用，符合其 AGPL 附加例外。
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Callable

from .config import DATA_DIR

TERRACOTTA_VERSION = "0.4.2"
NODE_LIST_URL = "https://terracotta.glavo.site/nodes"

# 官方发行包（.tar.gz）下载模板，按顺序回退；${...} 与官方 terracotta.json 对齐
_DOWNLOAD_BASES = [
    "https://cnb.cool/HMCL-Terracotta/Terracotta/-/releases/download/v{version}/terracotta-{version}-{classifier}-pkg.tar.gz",
    "https://gitee.com/burningtnt/Terracotta/releases/download/v{version}/terracotta-{version}-{classifier}-pkg.tar.gz",
    "https://github.com/burningtnt/Terracotta/releases/download/v{version}/terracotta-{version}-{classifier}-pkg.tar.gz",
]

# 各平台发行包内文件的 SHA-512（取自 HMCL 的 terracotta.json）
_PACKAGES: dict[str, dict] = {
    "windows-x86_64": {
        "terracotta-0.4.2-windows-x86_64.exe": "6e98d1f2380ed22fb5a2dd4aafce6c773e9cf69100c8bb8e49e7d6983756bdb9a31f80e06bcfbe5a2742144fe806d3d687dec54d8f09d87c659341f99dd9fd80",
        "VCRUNTIME140.DLL": "3d4b24061f72c0e957c7b04a0c4098c94c8f1afb4a7e159850b9939c7210d73398be6f27b5ab85073b4e8c999816e7804fef0f6115c39cd061f4aaeb4dcda8cf",
    },
    "windows-arm64": {
        "terracotta-0.4.2-windows-arm64.exe": "30a15c5c53e5817c5a3634532172559327474741d3b2c7ef4e8a30acc6f59cdcf3570bf5f583e3cbe9e2abc8253e977c1abda1e9f36c88c4e99240da257347d0",
        "VCRUNTIME140.DLL": "5cb5ce114614101d260f4754c09e8a0dd57e4da885ebb96b91e274326f3e1dd95ed0ade9f542f1922fad0ed025e88a1f368e791e1d01fae69718f0ec3c7b98c8",
    },
    "linux-x86_64": {
        "terracotta-0.4.2-linux-x86_64": "fac328ba8957a711b03557bb913940f22d61b76608cd203fdf51024b6f94b19f5bc91c9b8a9fa80baf6968e1e6873c1880fd4cf54a2f8e3c6cf1e6ac161f8d0c",
    },
    "linux-arm64": {
        "terracotta-0.4.2-linux-arm64": "d807744c2041c98686e4b505324713badea7a0f31e8810be49ae053a63fb6dfc474ac58d678fb93eea0dd5cccff7372d9ec6135a1046f4b306cad35cd90ecacd",
    },
}


class TerracottaError(Exception):
    """陶瓦联机相关错误。"""


# ---------------------------------------------------------------------------
# 安装
# ---------------------------------------------------------------------------
def classifier() -> str:
    """返回当前平台的发行包标识，例如 windows-x86_64。"""
    machine = platform.machine().lower()
    arch = {
        "amd64": "x86_64",
        "x86_64": "x86_64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }.get(machine, machine)
    system = "windows" if sys.platform.startswith("win") else (
        "macos" if sys.platform == "darwin" else "linux"
    )
    key = f"{system}-{arch}"
    if key not in _PACKAGES:
        raise TerracottaError(f"当前平台不受支持：{key}")
    return key


def install_dir() -> Path:
    return DATA_DIR / "terracotta" / f"{TERRACOTTA_VERSION}-{classifier()}"


def binary_path() -> Path:
    """返回可执行文件路径（未安装时返回预期路径，不保证存在）。"""
    for name in _PACKAGES[classifier()]:
        if name.lower().endswith(".exe") or not name.lower().endswith(".dll"):
            return install_dir() / name
    raise TerracottaError("发行包内容异常")


def is_installed() -> bool:
    try:
        return binary_path().is_file()
    except TerracottaError:
        return False


def _sha512(path: Path) -> str:
    digest = hashlib.sha512()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, dest: Path, on_bytes: Callable[[int, int], None] | None) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "MikanCL"})
    with urllib.request.urlopen(request, timeout=60) as response:
        total = int(response.headers.get("Content-Length") or 0)
        written = 0
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as handle:
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                written += len(chunk)
                if on_bytes is not None:
                    on_bytes(written, total)


def install(
    log: Callable[[str], None] | None = None,
    progress: Callable[[float, str], None] | None = None,
    cancel=None,
) -> Path:
    """下载并安装陶瓦联机，返回可执行文件路径。已安装则直接返回。"""
    target = binary_path()
    if target.is_file():
        if log:
            log(f"[陶瓦] 已安装：{target}")
        return target

    name = classifier()
    expected = _PACKAGES[name]
    work = install_dir().parent / f".download-{uuid.uuid4().hex[:8]}"
    work.mkdir(parents=True, exist_ok=True)
    archive = work / f"terracotta-{TERRACOTTA_VERSION}-{name}-pkg.tar.gz"
    last_error: Exception | None = None

    for base in _DOWNLOAD_BASES:
        url = base.format(version=TERRACOTTA_VERSION, classifier=name)
        try:
            if log:
                log(f"[陶瓦] 下载 {url}")
            state = {"last": 0.0}

            def on_bytes(done: int, total: int) -> None:
                if progress is None:
                    return
                now = time.monotonic()
                if now - state["last"] < 0.2 and (total <= 0 or done < total):
                    return
                state["last"] = now
                ratio = (done / total) if total > 0 else 0.0
                progress(min(0.9, ratio * 0.9), f"{done / 1048576:.1f} MB")

            _download(url, archive, on_bytes)
            break
        except (urllib.error.URLError, OSError, ValueError) as exc:
            last_error = exc
            if log:
                log(f"[陶瓦] 下载失败（{exc}），尝试下一个镜像…")
            continue
    else:
        shutil.rmtree(work, ignore_errors=True)
        raise TerracottaError(f"陶瓦联机下载失败：{last_error}")

    if cancel is not None and cancel.is_set():
        shutil.rmtree(work, ignore_errors=True)
        raise TerracottaError("已取消")

    if progress:
        progress(0.92, "解压中")
    extract = work / "pkg"
    extract.mkdir(exist_ok=True)
    try:
        with tarfile.open(archive, "r:gz") as tar:
            try:
                # Python 3.12+：拒绝绝对路径与符号链接逃逸
                tar.extractall(extract, filter="data")
            except TypeError:
                # Python 3.10 / 3.11 没有 filter 参数
                tar.extractall(extract)
    except (tarfile.TarError, OSError) as exc:
        shutil.rmtree(work, ignore_errors=True)
        raise TerracottaError(f"陶瓦联机解压失败：{exc}") from exc

    if progress:
        progress(0.96, "校验文件")
    install_dir().mkdir(parents=True, exist_ok=True)
    for filename, digest in expected.items():
        source = next(extract.rglob(filename), None)
        if source is None:
            shutil.rmtree(work, ignore_errors=True)
            raise TerracottaError(f"发行包中缺少 {filename}")
        if _sha512(source) != digest:
            shutil.rmtree(work, ignore_errors=True)
            raise TerracottaError(f"{filename} 校验失败，文件可能已损坏")
        destination = install_dir() / filename
        shutil.copy2(source, destination)
        if not filename.lower().endswith(".dll"):
            try:
                os.chmod(destination, 0o755)
            except OSError:
                pass
    shutil.rmtree(work, ignore_errors=True)
    if progress:
        progress(1.0, "安装完成")
    if log:
        log(f"[陶瓦] 安装完成：{target}")
    return target


# ---------------------------------------------------------------------------
# 进程 + HTTP API
# ---------------------------------------------------------------------------
def public_nodes() -> list[str]:
    """获取官方中继节点列表；失败时返回空列表（程序会自行使用默认节点）。"""
    try:
        request = urllib.request.Request(NODE_LIST_URL, headers={"User-Agent": "MikanCL"})
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
        nodes = []
        for item in data if isinstance(data, list) else []:
            url = str((item or {}).get("url") or "") if isinstance(item, dict) else ""
            if url.startswith(("http://", "https://", "tcp://", "udp://", "wg://")):
                nodes.append(url)
        return nodes
    except (urllib.error.URLError, OSError, ValueError):
        return []


class Service:
    """管理一个 Terracotta 后台进程，并调用其本地 HTTP API。"""

    def __init__(self, log: Callable[[str], None] | None = None):
        self.log = log or (lambda _m: None)
        self.process: subprocess.Popen | None = None
        self.port_file: Path | None = None
        self.port = 0
        self._node_cache: list[str] | None = None

    # -- 生命周期 ---------------------------------------------------------
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self, timeout: float = 60.0) -> int:
        """启动进程并等待它把 HTTP 端口写入端口文件。"""
        if self.running():
            return self.port
        exe = binary_path()
        if not exe.is_file():
            raise TerracottaError("陶瓦联机尚未安装")
        handle, name = tempfile.mkstemp(prefix="mikancl-terracotta-", suffix=".http")
        os.close(handle)
        self.port_file = Path(name)
        self.port_file.unlink(missing_ok=True)
        # --hmcl2 为 HMCL 的守护模式：常驻运行，并把 {"port": n} 写入端口文件
        args = [str(exe), "--hmcl2", str(self.port_file)]
        self.log(f"[陶瓦] 启动 {exe.name}")
        creation = 0x08000000 if sys.platform.startswith("win") else 0  # CREATE_NO_WINDOW
        self.process = subprocess.Popen(
            args,
            cwd=str(exe.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation,
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise TerracottaError(f"陶瓦联机进程已退出（代码 {self.process.returncode}）")
            try:
                text = self.port_file.read_text(encoding="utf-8").strip()
            except OSError:
                text = ""
            port = 0
            if text:
                try:
                    port = int(json.loads(text).get("port") or 0)
                except (ValueError, AttributeError):
                    port = int(text) if text.isdigit() else 0
            if port:
                self.port = port
                self.log(f"[陶瓦] 本地 API 端口 {self.port}")
                return self.port
            time.sleep(0.25)
        raise TerracottaError("等待陶瓦联机启动超时")

    def stop(self) -> None:
        process = self.process
        self.process = None
        self.port = 0
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    process.kill()
                except OSError:
                    pass
        if self.port_file is not None:
            try:
                self.port_file.unlink(missing_ok=True)
            except OSError:
                pass
            self.port_file = None
        self.log("[陶瓦] 进程已停止")

    # -- HTTP ------------------------------------------------------------
    def _get(self, path: str, query: list[tuple[str, str]] | None = None, timeout: float = 8.0) -> str:
        if not self.port:
            raise TerracottaError("陶瓦联机未启动")
        url = f"http://127.0.0.1:{self.port}{path}"
        if query:
            url += "?" + urllib.parse.urlencode(query, doseq=True)
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                return response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace").strip()
            except (OSError, ValueError):
                pass
            raise TerracottaError(f"本地 API 返回 {exc.code}：{detail or exc.reason}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise TerracottaError(f"本地 API 调用失败：{exc}") from exc

    def state(self) -> dict:
        text = self._get("/state")
        try:
            payload = json.loads(text)
        except ValueError:
            return {"state": "unknown"}
        return payload if isinstance(payload, dict) else {"state": "unknown"}

    def _nodes(self) -> list[str]:
        if self._node_cache is None:
            self._node_cache = public_nodes()
            self.log(f"[陶瓦] 中继节点 {len(self._node_cache)} 个")
        return self._node_cache

    def host(self, player: str) -> None:
        query = [("player", player or "Player")]
        query += [("public_nodes", node) for node in self._nodes()]
        self._get("/state/scanning", query, timeout=20)

    def join(self, room: str, player: str) -> None:
        query = [("room", room.strip()), ("player", player or "Player")]
        query += [("public_nodes", node) for node in self._nodes()]
        self._get("/state/guesting", query, timeout=20)

    def idle(self) -> None:
        self._get("/state/ide")

    def logs(self) -> str:
        try:
            return self._get("/log?fetch=true", timeout=10)
        except TerracottaError as exc:
            return str(exc)
