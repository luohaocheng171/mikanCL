"""Java 运行时探测与版本匹配。"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import USER_AGENT
from .config import DATA_DIR
from .net import Candidate, DownloadError, Http, open_with_ssl_fallback, proxy_opener

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


def java_key(path: str) -> str:
    """用于去重的 Java 路径键：统一大小写与 javaw.exe。"""
    return os.path.normcase(os.path.normpath(path or "")).replace("javaw.exe", "java.exe")


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
    # 启动器自身安装的运行时
    dirs.append(DATA_DIR / "runtime")
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
                key = java_key(info.path)
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


# ---------------------------------------------------------------------------
# 多发行版版本查询：全部走各家官方 API / 官方下载页，单个源失败自动降级
# ---------------------------------------------------------------------------
JAVA_DISTRIBUTIONS: tuple[dict, ...] = (
    {
        "id": "temurin",
        "name": "Eclipse Temurin",
        "vendor": "Adoptium",
        "homepage": "https://adoptium.net/",
        "description": "Eclipse 基金会维护的 OpenJDK 构建，社区使用最广。",
        "majors": (8, 11, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27),
        "channel": "Adoptium 官方 API",
    },
    {
        "id": "microsoft",
        "name": "Microsoft OpenJDK",
        "vendor": "Microsoft",
        "homepage": "https://learn.microsoft.com/java/openjdk/download",
        "description": "微软构建的 OpenJDK，Windows 平台优化较好。",
        "majors": (11, 17, 21, 25),
        "channel": "aka.ms 官方稳定链接",
    },
    {
        "id": "azul",
        "name": "Azul Zulu",
        "vendor": "Azul",
        "homepage": "https://www.azul.com/downloads/",
        "description": "Azul 提供的 Zulu OpenJDK，版本覆盖 8 到最新。",
        "majors": (8, 11, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25),
        "channel": "Azul 元数据 API",
    },
    {
        "id": "corretto",
        "name": "Amazon Corretto",
        "vendor": "Amazon",
        "homepage": "https://aws.amazon.com/corretto/",
        "description": "亚马逊长期免费支持的 OpenJDK 发行版。",
        "majors": (8, 11, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26),
        "channel": "GitHub Releases + 官方下载地址",
    },
    {
        "id": "dragonwell",
        "name": "Alibaba Dragonwell",
        "vendor": "Alibaba",
        "homepage": "https://dragonwell-jdk.io/",
        "description": "阿里巴巴面向云场景优化的 OpenJDK。",
        "majors": (8, 11, 17, 21, 25),
        "channel": "GitHub Releases",
    },
    {
        "id": "kona",
        "name": "Tencent Kona",
        "vendor": "Tencent",
        "homepage": "https://github.com/Tencent/TencentKona-21",
        "description": "腾讯开源的 OpenJDK 发行版。",
        "majors": (8, 11, 17, 21, 25),
        "channel": "GitHub Releases",
    },
    {
        "id": "liberica",
        "name": "BellSoft Liberica",
        "vendor": "BellSoft",
        "homepage": "https://bell-sw.com/libericajdk/",
        "description": "BellSoft 维护的 Liberica JDK，覆盖 8 到最新版本。",
        "majors": (8, 11, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27),
        "channel": "BellSoft 官方 API",
    },
    {
        "id": "semeru",
        "name": "IBM Semeru",
        "vendor": "IBM",
        "homepage": "https://developer.ibm.com/languages/java/semeru-runtimes/",
        "description": "IBM 基于 OpenJ9 的 OpenJDK 发行版，内存占用较低。",
        "majors": (8, 11, 17, 21, 25, 26),
        "channel": "IBM GitHub Releases",
    },
    {
        "id": "sapmachine",
        "name": "SAP SapMachine",
        "vendor": "SAP",
        "homepage": "https://sap.github.io/SapMachine/",
        "description": "SAP 维护的 OpenJDK 构建，长期同步上游更新。",
        "majors": (11, 17, 21, 25, 26),
        "channel": "SAP GitHub Releases",
    },
    {
        "id": "graalvm",
        "name": "GraalVM Community",
        "vendor": "Oracle / GraalVM",
        "homepage": "https://www.graalvm.org/",
        "description": "GraalVM 社区版，包含高性能 JIT 与原生镜像工具。",
        "majors": (17, 20, 21, 22, 23, 24, 25),
        "channel": "GraalVM GitHub Releases",
    },
)

_DISTRIBUTIONS_BY_ID = {item["id"]: item for item in JAVA_DISTRIBUTIONS}

_VERSION_CACHE: dict[tuple[str, int], tuple[float, list[dict]]] = {}
_ATOM_CACHE: dict[str, tuple[float, list[str]]] = {}
_ASSET_CACHE: dict[tuple[str, str], tuple[float, list[tuple[str, str]]]] = {}
_VERSION_CACHE_LOCK = threading.Lock()
_VERSION_CACHE_TTL = 600
_GITHUB_HEADERS = {"Accept": "application/vnd.github+json"}


def list_java_distributions() -> list[dict]:
    """返回支持的 Java 发行版元信息（id / 名称 / 主页 / 说明 / 可选主版本）。"""
    result: list[dict] = []
    for item in JAVA_DISTRIBUTIONS:
        entry = dict(item)
        entry["majors"] = list(item["majors"])
        result.append(entry)
    return result


def java_runtime_name(major: int, dist_id: str = "", version: str = "") -> str:
    """本地运行时目录名：未指定发行版时沿用 jre-<major>，否则 jre-<major>-<dist>-<version>。"""
    if dist_id and version:
        safe = re.sub(r"[^0-9A-Za-z._-]+", "_", f"{dist_id}-{version}").strip("_")
        return f"jre-{int(major)}-{safe}"
    return f"jre-{int(major)}"


def _version_key(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", str(text)))


def _head_url(url: str, timeout: int = 15) -> tuple[str, int]:
    """HEAD 探测链接，返回 (重定向后的最终 URL, 文件大小)；失败返回 ("", 0)。"""
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"}, method="HEAD"
    )
    try:
        with open_with_ssl_fallback(request, timeout) as response:
            final = response.geturl() or url
            length = response.headers.get("Content-Length")
            size = int(length) if length and str(length).isdigit() else 0
            return final, size
    except Exception:  # noqa: BLE001 - 单个链接探测失败不应影响整个版本列表
        return "", 0


def _version_entry(
    dist_id: str,
    major: int,
    version: str,
    url: str,
    name: str = "",
    size: int = 0,
    checksum: str = "",
    note: str = "",
    latest: bool = False,
    fallback: bool = False,
) -> dict:
    dist = _DISTRIBUTIONS_BY_ID.get(dist_id, {})
    return {
        "id": dist_id,
        "dist_name": dist.get("name", dist_id),
        "vendor": dist.get("vendor", ""),
        "channel": dist.get("channel", ""),
        "major": int(major),
        "version": str(version),
        "url": str(url),
        "name": name or str(url).rsplit("/", 1)[-1],
        "size": int(size or 0),
        "checksum": checksum,
        "note": note,
        "latest": bool(latest),
        "fallback": bool(fallback),
    }


def _fetch_adoptium_versions(major: int, timeout: int, limit: int) -> list[dict]:
    url = (
        "https://api.adoptium.net/v3/assets/feature_releases/"
        f"{int(major)}/ga?architecture=x64&heap_size=normal&image_type=jdk"
        "&jvm_impl=hotspot&os=windows&page=0&page_size={limit}&project=jdk"
        "&sort_method=DEFAULT&sort_order=DESC&vendor=eclipse"
    ).format(limit=max(1, limit))
    data = Http(timeout=timeout).get_json_url(url)
    rows: list[dict] = []
    for release in data if isinstance(data, list) else []:
        if not isinstance(release, dict):
            continue
        release_name = str(release.get("release_name") or "").strip()
        version = release_name[4:] if release_name.startswith("jdk-") else release_name
        if version.startswith("jdk8u"):
            version = version[3:]
        for binary in release.get("binaries") or []:
            if not isinstance(binary, dict):
                continue
            package = binary.get("package") or {}
            link = str(package.get("link") or "")
            if not link.lower().endswith(".zip"):
                continue
            rows.append(
                _version_entry(
                    "temurin",
                    major,
                    version or str(release.get("id") or ""),
                    link,
                    name=str(package.get("name") or ""),
                    size=int(package.get("size") or 0),
                    checksum=str(package.get("checksum") or ""),
                    note=f"Adoptium 官方 API · {release_name}",
                )
            )
            break
        if len(rows) >= limit:
            break
    return rows


def _fallback_adoptium(major: int, timeout: int) -> list[dict]:
    url = (
        ADOPTIUM_LATEST.format(major=int(major))
        + "?os=windows&architecture=x64&image_type=jdk"
    )
    data = Http(timeout=timeout).get_json_url(url)
    if not isinstance(data, list) or not data:
        return []
    package = ((data[0].get("binary") or {}).get("package") or {}) if isinstance(data[0], dict) else {}
    link = str(package.get("link") or "")
    if not link:
        return []
    return [
        _version_entry(
            "temurin",
            major,
            f"{major}.x（最新）",
            link,
            name=str(package.get("name") or ""),
            size=int(package.get("size") or 0),
            checksum=str(package.get("checksum") or ""),
            note="Adoptium 官方 latest 稳定链接",
            latest=True,
            fallback=True,
        )
    ]


def _fetch_microsoft_versions(major: int, timeout: int, limit: int) -> list[dict]:
    template = (
        f"https://aka.ms/download-jdk/microsoft-jdk-{int(major)}-windows-x64.zip"
    )
    final, size = _head_url(template, timeout=timeout)
    if not final:
        raise DownloadError(f"Microsoft OpenJDK {major} 稳定链接不可用")
    match = re.search(r"microsoft-jdk-([\d.]+)-windows-x64", final)
    version = match.group(1).rstrip(".") if match else f"{major}.x"
    return [
        _version_entry(
            "microsoft",
            major,
            version,
            template,
            name=final.rsplit("/", 1)[-1],
            size=size,
            note="Microsoft 官方 aka.ms 稳定链接，版本号由重定向解析",
            latest=True,
        )
    ]


def _fallback_microsoft(major: int, timeout: int) -> list[dict]:
    return _fetch_microsoft_versions(major, timeout, 1)


def _fetch_azul_versions(major: int, timeout: int, limit: int) -> list[dict]:
    url = (
        "https://api.azul.com/metadata/v1/zulu/packages/"
        f"?java_version={int(major)}&os=windows&arch=x64&java_package_type=jdk"
        "&archive_type=zip&availability_types=CA&page=1&page_size=40"
    )
    data = Http(timeout=timeout).get_json_url(url)
    candidates: list[dict] = []
    for row in data if isinstance(data, list) else []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "")
        if "-ca-jdk" not in name:  # 排除 crac / fx 等特殊包
            continue
        link = str(row.get("download_url") or "")
        if not link.lower().endswith(".zip"):
            continue
        version = ".".join(str(part) for part in (row.get("java_version") or []))
        if not version:
            continue
        candidates.append(
            _version_entry(
                "azul",
                major,
                version,
                link,
                name=name,
                note=f"Azul 元数据 API · Zulu {'.'.join(str(p) for p in row.get('distro_version') or [])}".strip(),
            )
        )
    candidates.sort(key=lambda item: _version_key(item["version"]), reverse=True)
    selected = candidates[: max(1, limit)]

    def probe_size(item: dict) -> None:
        _, size = _head_url(item["url"], timeout=min(timeout, 10))
        item["size"] = size

    # HEAD 探测并发执行，避免逐个等待拖慢页面
    if selected:
        with ThreadPoolExecutor(max_workers=min(6, len(selected))) as pool:
            list(pool.map(probe_size, selected))
    return selected


def _fallback_azul(major: int, timeout: int) -> list[dict]:
    url = (
        "https://api.azul.com/metadata/v1/zulu/packages/"
        f"?java_version={int(major)}&os=windows&arch=x64&java_package_type=jdk"
        "&archive_type=zip&latest=true&availability_types=CA"
    )
    data = Http(timeout=timeout).get_json_url(url)
    for row in data if isinstance(data, list) else []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "")
        link = str(row.get("download_url") or "")
        if "-ca-jdk" not in name or not link.lower().endswith(".zip"):
            continue
        version = ".".join(str(part) for part in (row.get("java_version") or []))
        _, size = _head_url(link, timeout=min(timeout, 12))
        return [
            _version_entry(
                "azul",
                major,
                f"{version or f'{major}.x'}（最新）",
                link,
                name=name,
                size=size,
                note="Azul 官方 latest 稳定链接",
                latest=True,
                fallback=True,
            )
        ]
    return []


def _corretto_url(tag: str) -> str:
    return (
        f"https://corretto.aws/downloads/resources/{tag}/"
        f"amazon-corretto-{tag}-windows-x64-jdk.zip"
    )


def _fetch_corretto_versions(major: int, timeout: int, limit: int) -> list[dict]:
    data = Http(timeout=timeout).get_json_url(
        f"https://api.github.com/repos/corretto/corretto-{int(major)}/releases"
        f"?per_page={max(2, limit + 2)}",
        headers=_GITHUB_HEADERS,
    )
    rows: list[dict] = []
    for release in data if isinstance(data, list) else []:
        if not isinstance(release, dict):
            continue
        tag = str(release.get("tag_name") or "")
        if not re.fullmatch(r"\d+(\.\d+)+", tag):
            continue
        link = _corretto_url(tag)
        _, size = _head_url(link, timeout=min(timeout, 12))
        if not size:  # 旧版本资源可能已下线
            continue
        rows.append(
            _version_entry(
                "corretto",
                major,
                tag,
                link,
                name=f"amazon-corretto-{tag}-windows-x64-jdk.zip",
                size=size,
                note=f"Amazon Corretto {tag}（版本特定下载地址）",
            )
        )
        if len(rows) >= limit:
            break
    return rows


def _fallback_corretto(major: int, timeout: int) -> list[dict]:
    template = (
        f"https://corretto.aws/downloads/latest/"
        f"amazon-corretto-{int(major)}-x64-windows-jdk.zip"
    )
    final, size = _head_url(template, timeout=timeout)
    if not final:
        return []
    match = re.search(r"amazon-corretto-([\d.]+)-windows-x64-jdk", final)
    version = match.group(1).rstrip(".") if match else f"{major}.x"
    return [
        _version_entry(
            "corretto",
            major,
            f"{version}（最新）",
            template,
            name=final.rsplit("/", 1)[-1],
            size=size,
            note="Amazon Corretto 官方 latest 稳定链接",
            latest=True,
            fallback=True,
        )
    ]


def _github_windows_zip(releases: list, dist_id: str, major: int) -> list[dict]:
    rows: list[dict] = []
    for release in releases:
        if not isinstance(release, dict):
            continue
        tag_low = str(release.get("tag_name") or "").lower()
        if dist_id == "dragonwell" and "extended" in tag_low:
            continue  # Dragonwell Extended 与 Standard 同版本，优先 Standard
        for asset in release.get("assets") or []:
            if not isinstance(asset, dict):
                continue
            name = str(asset.get("name") or "")
            low = name.lower()
            if not low.endswith(".zip") or "windows" not in low:
                continue
            if "x64" not in low and "x86_64" not in low:
                continue
            if any(skip in low for skip in ("debug", "sbom", "fix", "signature")):
                continue
            link = str(asset.get("browser_download_url") or "")
            if not link:
                continue
            if dist_id == "dragonwell":
                match = re.search(r"_(?:standard|extended)_([^_]+)_x64_windows", low)
                version = match.group(1).replace("_", ".") if match else ""
                note = "Alibaba Dragonwell GitHub Releases"
            else:
                match = re.search(r"tencentkona-?([\d.]+)", low)
                version = match.group(1).rstrip(".") if match else ""
                note = "Tencent Kona GitHub Releases"
            if not version:
                version = str(release.get("tag_name") or "").strip()
            rows.append(
                _version_entry(
                    dist_id,
                    major,
                    version,
                    link,
                    name=name,
                    size=int(asset.get("size") or 0),
                    checksum=str(asset.get("digest") or ""),
                    note=str(release.get("name") or note),
                )
            )
            break
    return rows


def _fetch_dragonwell_versions(major: int, timeout: int, limit: int) -> list[dict]:
    data = Http(timeout=timeout).get_json_url(
        f"https://api.github.com/repos/dragonwell-project/dragonwell{int(major)}"
        f"/releases?per_page={max(2, limit)}",
        headers=_GITHUB_HEADERS,
    )
    rows = _github_windows_zip(data if isinstance(data, list) else [], "dragonwell", major)
    return rows[: max(1, limit)]


def _fallback_dragonwell(major: int, timeout: int) -> list[dict]:
    return _atom_fallback(
        "dragonwell", f"dragonwell-project/dragonwell{int(major)}", major, timeout
    )


def _fetch_kona_versions(major: int, timeout: int, limit: int) -> list[dict]:
    data = Http(timeout=timeout).get_json_url(
        f"https://api.github.com/repos/Tencent/TencentKona-{int(major)}"
        f"/releases?per_page={max(2, limit)}",
        headers=_GITHUB_HEADERS,
    )
    rows = _github_windows_zip(data if isinstance(data, list) else [], "kona", major)
    return rows[: max(1, limit)]


def _fallback_kona(major: int, timeout: int) -> list[dict]:
    return _atom_fallback("kona", f"Tencent/TencentKona-{int(major)}", major, timeout)


def _github_atom_tags(repo: str, timeout: int = 20, limit: int = 12) -> list[str]:
    """通过 GitHub 的 releases.atom 取 tag 列表。

    api.github.com 对未认证请求限流很紧（60 次/小时），Atom 订阅源不走该限额，
    作为速率受限时的兜底渠道。
    """
    now = time.time()
    with _VERSION_CACHE_LOCK:
        cached = _ATOM_CACHE.get(repo)
    if cached and now - cached[0] < _VERSION_CACHE_TTL:
        return list(cached[1])
    try:
        raw = Http(timeout=timeout).request(f"https://github.com/{repo}/releases.atom").decode(
            "utf-8", errors="replace"
        )
    except Exception:  # noqa: BLE001 - 兜底渠道失败时按无数据处理
        return []
    tags = re.findall(r"<id>tag:github\.com,2008:Repository/\d+/([^<]+)</id>", raw)
    tags = [tag.strip() for tag in tags if tag.strip()][:limit]
    if tags:
        with _VERSION_CACHE_LOCK:
            _ATOM_CACHE[repo] = (now, tags)
    return tags


def _github_release_assets(repo: str, tag: str, timeout: int = 20) -> list[tuple[str, str]]:
    """从 GitHub 的 expanded_assets 片段解析真实资源名与下载链接（不受 API 限流影响）。"""
    key = (repo, tag)
    now = time.time()
    with _VERSION_CACHE_LOCK:
        cached = _ASSET_CACHE.get(key)
    if cached and now - cached[0] < _VERSION_CACHE_TTL:
        return list(cached[1])
    page = f"https://github.com/{repo}/releases/expanded_assets/{urllib.parse.quote(tag)}"
    try:
        html = Http(timeout=timeout).request(page).decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - 兜底渠道失败时按无数据处理
        return []
    items: list[tuple[str, str]] = []
    for href in re.findall(r'href="(/[^"]*/releases/download/[^"]+)"', html):
        name = urllib.parse.unquote(href.rsplit("/", 1)[-1])
        if name:
            items.append((name, href))
    if items:
        with _VERSION_CACHE_LOCK:
            _ASSET_CACHE[key] = (now, items)
    return items


def _atom_fallback(dist_id: str, repo: str, major: int, timeout: int, max_tags: int = 4) -> list[dict]:
    """GitHub API 被限流时：Atom 取 tag，再从资源片段取真实文件名，复用同一套解析逻辑。"""
    releases: list[dict] = []
    for tag in _github_atom_tags(repo, timeout, limit=max_tags * 3):
        assets = _github_release_assets(repo, tag, timeout)
        if not assets:
            continue
        releases.append(
            {
                "tag_name": tag,
                "name": tag,
                "assets": [
                    {
                        "name": name,
                        "browser_download_url": "https://github.com" + href,
                        "size": 0,
                    }
                    for name, href in assets
                ],
            }
        )
        if len(releases) >= max_tags:
            break
    if not releases:
        return []
    if dist_id in ("dragonwell", "kona"):
        rows = _github_windows_zip(releases, dist_id, major)
    elif dist_id == "semeru":
        rows = _semeru_rows(releases, major)
    elif dist_id == "sapmachine":
        rows = _sapmachine_rows(releases, major)
    else:
        rows = _graalvm_rows(releases, major)
    rows = [row for row in rows if str(row.get("url") or "")]
    for index, item in enumerate(rows):
        item["latest"] = index == 0
        item["fallback"] = True
    return rows[:4]


def _fetch_liberica_versions(major: int, timeout: int, limit: int) -> list[dict]:
    """BellSoft Liberica：官方 releases API 直接给出 zip 下载地址、大小与 sha1。"""
    url = (
        "https://api.bell-sw.com/v1/liberica/releases?"
        f"version-feature={int(major)}&os=windows&arch=x86&bitness=64&output=json"
    )
    data = Http(timeout=timeout).get_json_url(url)
    rows: list[dict] = []
    for row in data if isinstance(data, list) else []:
        if not isinstance(row, dict):
            continue
        link = str(row.get("downloadUrl") or "")
        if not link.lower().endswith(".zip"):
            continue
        if str(row.get("bundleType") or "") != "jdk":
            continue  # 只要标准 JDK，排除 jdk-full / lite 等变体
        rows.append(
            _version_entry(
                "liberica",
                major,
                str(row.get("version") or ""),
                link,
                name=str(row.get("filename") or ""),
                size=int(row.get("size") or 0),
                checksum=str(row.get("sha1") or ""),
                note="BellSoft Liberica 官方 API",
                latest=bool(row.get("latest")),
            )
        )
    rows.sort(key=lambda item: _version_key(item["version"]), reverse=True)
    return rows[: max(1, limit)]


def _fallback_liberica(major: int, timeout: int) -> list[dict]:
    rows = _fetch_liberica_versions(major, timeout, 1)
    for item in rows:
        item["latest"] = True
        item["fallback"] = True
        item["note"] = "BellSoft Liberica 官方最新版"
    return rows


def _semeru_rows(releases: list, major: int) -> list[dict]:
    rows: list[dict] = []
    for release in releases:
        if not isinstance(release, dict):
            continue
        for asset in release.get("assets") or []:
            if not isinstance(asset, dict):
                continue
            name = str(asset.get("name") or "")
            low = name.lower()
            if not low.endswith(".zip") or "windows" not in low:
                continue
            if "jdk" not in low or "x64" not in low:
                continue
            if any(skip in low for skip in ("debugimage", "testimage", "jre", "sources")):
                continue
            match = re.search(r"windows_([\d.]+(?:-m\d+)?)\.zip$", low)
            version = match.group(1) if match else str(release.get("tag_name") or "")
            rows.append(
                _version_entry(
                    "semeru",
                    major,
                    version,
                    str(asset.get("browser_download_url") or ""),
                    name=name,
                    size=int(asset.get("size") or 0),
                    checksum=str(asset.get("digest") or ""),
                    note=f"IBM Semeru {release.get('tag_name') or ''}".strip(),
                )
            )
            break
    return rows


def _fetch_semeru_versions(major: int, timeout: int, limit: int) -> list[dict]:
    data = Http(timeout=timeout).get_json_url(
        f"https://api.github.com/repos/ibmruntimes/semeru{int(major)}-binaries"
        f"/releases?per_page={max(2, limit)}",
        headers=_GITHUB_HEADERS,
    )
    rows = _semeru_rows(data if isinstance(data, list) else [], major)
    return rows[: max(1, limit)]


def _fallback_semeru(major: int, timeout: int) -> list[dict]:
    return _atom_fallback(
        "semeru", f"ibmruntimes/semeru{int(major)}-binaries", major, timeout
    )


def _sapmachine_rows(releases: list, major: int) -> list[dict]:
    rows: list[dict] = []
    prefix = re.compile(rf"^sapmachine-{int(major)}(?:\.|\+|$)")
    for release in releases:
        if not isinstance(release, dict):
            continue
        tag = str(release.get("tag_name") or "")
        if not prefix.match(tag):
            continue
        for asset in release.get("assets") or []:
            if not isinstance(asset, dict):
                continue
            name = str(asset.get("name") or "")
            low = name.lower()
            if not low.endswith("_windows-x64_bin.zip"):
                continue
            version = tag.split("-", 1)[-1]
            if low.startswith("sapmachine-jdk-"):
                version = name[len("sapmachine-jdk-"):].split("_windows")[0]
            rows.append(
                _version_entry(
                    "sapmachine",
                    major,
                    version,
                    str(asset.get("browser_download_url") or ""),
                    name=name,
                    size=int(asset.get("size") or 0),
                    checksum=str(asset.get("digest") or ""),
                    note=f"SAP SapMachine {tag}",
                )
            )
            break
    return rows


def _fetch_sapmachine_versions(major: int, timeout: int, limit: int) -> list[dict]:
    # SapMachine 的 release 列表跨多个 Java 版本，需要多取一些再按主版本过滤
    data = Http(timeout=timeout).get_json_url(
        f"https://api.github.com/repos/SAP/SapMachine/releases?per_page={max(10, limit * 6)}",
        headers=_GITHUB_HEADERS,
    )
    rows = _sapmachine_rows(data if isinstance(data, list) else [], major)
    return rows[: max(1, limit)]


def _fallback_sapmachine(major: int, timeout: int) -> list[dict]:
    return _atom_fallback("sapmachine", "SAP/SapMachine", major, timeout)


def _graalvm_rows(releases: list, major: int) -> list[dict]:
    rows: list[dict] = []
    for release in releases:
        if not isinstance(release, dict):
            continue
        tag = str(release.get("tag_name") or "")
        match = re.match(r"(?:jdk|graal)-(\d+)", tag)
        if not match or int(match.group(1)) != int(major):
            continue
        for asset in release.get("assets") or []:
            if not isinstance(asset, dict):
                continue
            name = str(asset.get("name") or "")
            low = name.lower()
            if not low.endswith("_windows-x64_bin.zip"):
                continue
            if not low.startswith("graalvm-community-jdk-"):
                continue
            version = name[len("graalvm-community-jdk-"):].split("_windows")[0]
            rows.append(
                _version_entry(
                    "graalvm",
                    major,
                    version,
                    str(asset.get("browser_download_url") or ""),
                    name=name,
                    size=int(asset.get("size") or 0),
                    checksum=str(asset.get("digest") or ""),
                    note=f"GraalVM Community {tag}",
                )
            )
            break
    return rows


def _fetch_graalvm_versions(major: int, timeout: int, limit: int) -> list[dict]:
    # 同一个 release 列表里混有多个 JDK 主版本，多取一些再过滤
    data = Http(timeout=timeout).get_json_url(
        "https://api.github.com/repos/graalvm/graalvm-ce-builds/releases?per_page=80",
        headers=_GITHUB_HEADERS,
    )
    rows = _graalvm_rows(data if isinstance(data, list) else [], major)
    return rows[: max(1, limit)]


def _fallback_graalvm(major: int, timeout: int) -> list[dict]:
    return _atom_fallback(
        "graalvm", "graalvm/graalvm-ce-builds", major, timeout, max_tags=6
    )


_FETCHERS: dict[str, Callable[[int, int, int], list[dict]]] = {
    "temurin": _fetch_adoptium_versions,
    "microsoft": _fetch_microsoft_versions,
    "azul": _fetch_azul_versions,
    "corretto": _fetch_corretto_versions,
    "dragonwell": _fetch_dragonwell_versions,
    "kona": _fetch_kona_versions,
    "liberica": _fetch_liberica_versions,
    "semeru": _fetch_semeru_versions,
    "sapmachine": _fetch_sapmachine_versions,
    "graalvm": _fetch_graalvm_versions,
}

_FALLBACK_FETCHERS: dict[str, Callable[[int, int], list[dict]]] = {
    "temurin": _fallback_adoptium,
    "microsoft": _fallback_microsoft,
    "azul": _fallback_azul,
    "corretto": _fallback_corretto,
    "dragonwell": _fallback_dragonwell,
    "kona": _fallback_kona,
    "liberica": _fallback_liberica,
    "semeru": _fallback_semeru,
    "sapmachine": _fallback_sapmachine,
    "graalvm": _fallback_graalvm,
}


def fetch_distribution_versions(
    dist_id: str,
    major: int,
    limit: int = 8,
    timeout: int = 20,
    force: bool = False,
) -> list[dict]:
    """查询某发行版某主版本的可用版本列表。

    返回 dict 列表（version / url / size / name / checksum / note / latest / fallback 等）。
    任何一个源失败都会尝试官方 latest 稳定链接降级；仍然失败则返回空列表，不抛异常。
    """
    key_dist = str(dist_id or "").strip().lower()
    try:
        key_major = int(major)
    except (TypeError, ValueError):
        return []
    key = (key_dist, key_major)
    if not force:
        with _VERSION_CACHE_LOCK:
            hit = _VERSION_CACHE.get(key)
        if hit and time.time() - hit[0] < _VERSION_CACHE_TTL:
            return [dict(item) for item in hit[1]]

    fetcher = _FETCHERS.get(key_dist)
    if fetcher is None:
        return []
    rows: list[dict] = []
    try:
        rows = list(fetcher(key_major, timeout, limit) or [])
    except Exception:  # noqa: BLE001 - 单个源异常时降级到 latest 链接
        rows = []
    rows = [row for row in rows if isinstance(row, dict) and str(row.get("url") or "")]
    if not rows:
        fallback = _FALLBACK_FETCHERS.get(key_dist)
        if fallback is not None:
            try:
                rows = list(fallback(key_major, timeout) or [])
            except Exception:  # noqa: BLE001 - 降级也失败时返回空列表
                rows = []
    unique: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        url = str(row.get("url") or "")
        if not url or url in seen:
            continue
        seen.add(url)
        unique.append(row)
    if unique:
        with _VERSION_CACHE_LOCK:
            _VERSION_CACHE[key] = (time.time(), unique)
    return [dict(item) for item in unique]


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
    cancel: threading.Event | None = None,
    pause: threading.Event | None = None,
    on_total: Callable[[int], None] | None = None,
    url: str = "",
    target_name: str = "",
    size: int = 0,
) -> JavaInfo:
    """下载并解压 JDK/JRE 到 <dest_root>/<target_name>（默认 jre-<major>）。

    url 为空时走 Adoptium API 自动解析；非空则直接下载该链接（用于其他发行版），
    size 为可选的总字节数（用于下载中心显示进度）。
    target_name 为空时沿用旧的 jre-<major> 目录，供 Java 中心按版本分目录安装。
    cancel / pause 透传给 Http.download；on_total 在拿到总大小后回调。
    """
    root = Path(dest_root)
    target = root / (target_name or f"jre-{major}")
    existing = find_java_in(target)
    if existing:
        info = probe_java(existing)
        if info is not None and info.major == int(major):
            return info

    if url:
        asset = {
            "url": url,
            "name": f"{target.name}.zip",
            "size": int(size) or None,
            "major": int(major),
        }
    else:
        asset = adoptium_asset(major)
    if on_total:
        on_total(int(asset.get("size") or 0))
    if log:
        log(f"[Java] 正在下载 Java {major}：{asset['name']}")
    archive = root / f"{target.name}.zip"
    root.mkdir(parents=True, exist_ok=True)
    Http(timeout=60).download(
        [Candidate(asset["url"], source_name="Adoptium" if not url else "Java")],
        archive,
        size=asset.get("size"),
        on_bytes=on_bytes,
        cancel=cancel,
        pause=pause,
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
