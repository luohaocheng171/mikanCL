"""Java 运行时探测与版本匹配。"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .net import Candidate, DownloadError, Http

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
ADOPTIUM_LATEST = "https://api.adoptium.net/v3/assets/latest/{major}/hotspot"


@dataclass(frozen=True)
class JavaInfo:
    path: str
    version: str
    major: int
    bits: int = 64

    @property
    def label(self) -> str:
        return f"Java {self.major}  ({self.version}, {self.bits} 位)"


def _run(path: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [path, "-version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        creationflags=CREATE_NO_WINDOW,
    )


def probe_java(path: str) -> JavaInfo | None:
    path = str(path).strip('"')
    if not path:
        return None
    if os.path.isdir(path):
        for name in ("javaw.exe", "java.exe", "bin/javaw.exe", "bin/java.exe"):
            candidate = Path(path) / name
            if candidate.exists():
                path = str(candidate)
                break
    if not Path(path).exists():
        return None
    try:
        result = _run(path)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    output = (result.stderr or "") + (result.stdout or "")
    match = re.search(r'version "([^"]+)"', output)
    if not match:
        return None
    version = match.group(1)
    try:
        major = 8 if version.startswith("1.") else int(re.split(r"[.\-+]", version)[0])
    except ValueError:
        return None
    bits = 64 if "64-Bit" in output or "64 位" in output else 32
    return JavaInfo(path=os.path.normpath(path), version=version, major=major, bits=bits)


def _candidate_dirs() -> list[Path]:
    dirs: list[Path] = []
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        dirs.append(Path(java_home))
    for key, value in (
        ("ProgramFiles", "Java"),
        ("ProgramFiles", "Eclipse Adoptium"),
        ("ProgramFiles", "Eclipse Foundation"),
        ("ProgramFiles", "Microsoft"),
        ("ProgramFiles", "BellSoft"),
        ("ProgramFiles", "Zulu"),
        ("ProgramFiles", "Amazon Corretto"),
        ("ProgramFiles", "OpenLogic"),
        ("ProgramFiles(x86)", "Java"),
        ("LOCALAPPDATA", "Programs"),
        ("LOCALAPPDATA", "Microsoft"),
    ):
        root = os.environ.get(key)
        if root:
            dirs.append(Path(root) / value)
    # 常见启动器自带的 Java
    for launcher in (".minecraft/runtime", ".hmcl/java", ".mclauncher/java"):
        appdata = os.environ.get("APPDATA")
        if appdata:
            dirs.append(Path(appdata) / launcher)
        dirs.append(Path.home() / launcher)
    return dirs


def detect_java_installed() -> list[JavaInfo]:
    """扫描系统上常见的 Java 安装目录（含启动器自带运行时）。"""
    paths: list[Path] = []
    which = shutil.which("java")
    if which:
        paths.append(Path(which))
    which_w = shutil.which("javaw")
    if which_w:
        paths.append(Path(which_w))

    for root in _candidate_dirs():
        if not root.exists():
            continue
        paths.append(root)
        try:
            children = list(root.iterdir())[:60]
        except OSError:
            continue
        for child in children:
            if child.is_dir():
                paths.append(child)
                bin_dir = child / "bin"
                if bin_dir.is_dir():
                    paths.append(bin_dir)
                runtime_bin = child / "bin" / "java.exe"
                if runtime_bin.exists():
                    paths.append(runtime_bin)
                # .minecraft/runtime 下可能存在 java.exe
                nested = list(child.glob("*/bin/java.exe"))[:3]
                paths.extend(nested)
                paths.extend(list(child.glob("*/bin"))[:3])

    registry_paths = _registry_java_paths()
    paths.extend(Path(p) for p in registry_paths)

    result: dict[str, JavaInfo] = {}
    for path in paths:
        candidates: list[str]
        if path.is_file():
            candidates = [str(path)]
        else:
            candidates = [str(path / "bin" / "javaw.exe"), str(path / "bin" / "java.exe"), str(path)]
        for candidate in candidates:
            if not candidate.lower().endswith(".exe") or not Path(candidate).exists():
                continue
            info = probe_java(candidate)
            if info:
                key = os.path.normcase(info.path).replace("javaw.exe", "java.exe")
                existing = result.get(key)
                if existing is None or existing.bits < info.bits:
                    result[key] = info
                break
    return sorted(result.values(), key=lambda j: (-j.major, j.path))


def _registry_java_paths() -> list[str]:
    if sys.platform != "win32":
        return []
    try:
        import winreg  # type: ignore
    except ImportError:
        return []
    found: list[str] = []
    roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\JavaSoft\JDK"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\JavaSoft\Java Development Kit"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\JavaSoft\Java Runtime Environment"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\JavaSoft\Java Development Kit"),
    ]
    for hive, root in roots:
        try:
            with winreg.OpenKey(hive, root) as key:
                count = winreg.QueryInfoKey(key)[0]
                names = [winreg.EnumKey(key, i) for i in range(count)]
        except OSError:
            continue
        for name in names:
            try:
                with winreg.OpenKey(hive, f"{root}\\{name}") as sub:
                    java_home, _ = winreg.QueryValueEx(sub, "JavaHome")
                    if java_home:
                        found.append(str(java_home))
            except OSError:
                continue
    return found


def pick_java(javas: list[JavaInfo], required: int, preferred: str = "") -> tuple[JavaInfo | None, str]:
    """选择最合适的 Java，返回 (Java, 提示)。"""
    if not javas:
        return None, "未检测到 Java，请在设置中手动指定 javaw.exe 或安装 Java。"
    if preferred:
        info = probe_java(preferred)
        if info is None:
            return None, f"指定的 Java 无法使用：{preferred}"
        if info.major != required:
            if info.major < required:
                return info, f"该版本建议 Java {required}，当前仅 Java {info.major}，可能无法启动。"
            return info, f"该版本建议 Java {required}，当前为 Java {info.major}，可能存在兼容性问题。"
        return info, ""

    exact = [j for j in javas if j.major == required]
    if exact:
        return exact[0], ""
    newer = sorted([j for j in javas if j.major > required], key=lambda j: (j.major, j.bits))
    if newer:
        return newer[0], f"未找到 Java {required}，将使用 Java {newer[0].major}，可能不兼容。"
    highest = max(javas, key=lambda j: (j.major, j.bits))
    return highest, f"未找到 Java {required} 或更高版本，将使用 Java {highest.major}，很可能无法启动。"


def adoptium_asset(major: int, timeout: int = 20) -> dict:
    """查询 Adoptium 最新 JRE 的下载信息。"""
    url = (
        ADOPTIUM_LATEST.format(major=int(major))
        + "?os=windows&arch=x64&image_type=jre"
    )
    data = Http().get_json_url(url, timeout=timeout)
    if not isinstance(data, list) or not data:
        raise DownloadError(f"Adoptium 未提供 Java {major} 的 Windows JRE")
    binary = data[0].get("binary") if isinstance(data[0], dict) else None
    package = (binary or {}).get("package") or {}
    link = str(package.get("link") or "")
    if not link:
        raise DownloadError(f"Adoptium 返回的 Java {major} 下载地址为空")
    return {
        "url": link,
        "name": str(package.get("name") or f"jre-{major}.zip"),
        "size": int(package.get("size") or 0) or None,
        "major": int(major),
    }


def find_java_in(root: Path) -> str:
    for name in ("javaw.exe", "java.exe"):
        matches = list(root.rglob(f"bin/{name}"))
        if matches:
            return str(matches[0])
    return ""


def download_java(
    major: int,
    dest_root: str | Path,
    log: Callable[[str], None] | None = None,
    on_bytes: Callable[[int], None] | None = None,
) -> JavaInfo:
    """从 Adoptium 下载并解压 JRE 到 <dest_root>/jre-<major>。"""
    root = Path(dest_root)
    target = root / f"jre-{major}"
    existing = find_java_in(target)
    if existing:
        info = probe_java(existing)
        if info is not None and info.major == int(major):
            return info

    asset = adoptium_asset(major)
    if log:
        log(f"[Java] 正在下载 Java {major}：{asset['name']}")
    archive = root / f"jre-{major}.zip"
    root.mkdir(parents=True, exist_ok=True)
    Http(timeout=60).download(
        [Candidate(asset["url"], source_name="Adoptium")],
        archive,
        size=asset.get("size"),
        on_bytes=on_bytes,
    )
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True, exist_ok=True)
    if log:
        log(f"[Java] 正在解压到 {target}")
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(target)
    archive.unlink(missing_ok=True)

    java_path = find_java_in(target)
    if not java_path:
        raise DownloadError("解压完成但未找到 java 可执行文件")
    info = probe_java(java_path)
    if info is None:
        raise DownloadError("下载的 Java 无法运行")
    if log:
        log(f"[Java] 安装完成：{info.path}（{info.version}）")
    return info
