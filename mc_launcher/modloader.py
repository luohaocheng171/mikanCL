"""Mod 加载器安装：Forge / NeoForge / Fabric / Quilt / LiteLoader。

Fabric、Quilt 使用官方 meta 提供的 profile JSON，Forge / NeoForge 调用官方 installer，
LiteLoader 根据官方 versions.json 构造版本 JSON。
"""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Callable

from .config import CACHE_DIR, Config
from .net import Candidate, DownloadError, Http
from .version import infer_java_major

LOADER_LABELS = {
    "forge": "Forge",
    "neoforge": "NeoForge",
    "fabric": "Fabric",
    "quilt": "Quilt",
    "liteloader": "LiteLoader",
}

FABRIC_META = "https://meta.fabricmc.net/v2"
QUILT_META = "https://meta.quiltmc.org/v3"
FORGE_MAVEN_BASE = "https://maven.minecraftforge.net/net/minecraftforge/forge"
NEOFORGE_MAVEN_BASE = "https://maven.neoforged.net/releases/net/neoforged"
# BMCLAPI 的 maven 代理同时镜像 Forge / NeoForge 的产物，用于官方源超时时的回退
MAVEN_MIRROR_BASE = "https://bmclapi2.bangbang93.com/maven"
LITELOADER_VERSIONS_URL = "http://dl.liteloader.com/versions/versions.json"
LITELOADER_BASE = "http://dl.liteloader.com/versions"

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# Forge / NeoForge 安装器在无网络或弹出 GUI 时会无限阻塞，超过该时限直接终止
INSTALLER_TIMEOUT = 600


class LoaderError(Exception):
    pass


def _http() -> Http:
    return Http(timeout=40)


def _version_key(text: str) -> tuple:
    parts = re.split(r"[.\-+]", text)
    key = []
    for part in parts:
        key.append(int(part) if part.isdigit() else 0)
    return tuple(key)


def _latest(versions: list[str]) -> str:
    return sorted(versions, key=_version_key, reverse=True)[0] if versions else ""


def _parse_maven_versions(xml: str, prefix: str = "") -> list[str]:
    versions = re.findall(r"<version>([^<]+)</version>", xml)
    if prefix:
        versions = [v for v in versions if v.startswith(prefix)]
        versions = [v[len(prefix):].lstrip("-") for v in versions]
    return sorted(versions, key=_version_key, reverse=True)


def list_loader_versions(kind: str, mc_version: str) -> list[str]:
    """返回指定加载器可用的版本列表（新 → 旧）。"""
    http = _http()
    try:
        if kind == "fabric":
            data = http.get_json_url(f"{FABRIC_META}/versions/loader/{mc_version}")
            if not isinstance(data, list):
                return []
            stable = [d["loader"]["version"] for d in data if d.get("loader", {}).get("stable")]
            all_versions = [str(d.get("loader", {}).get("version")) for d in data if d.get("loader")]
            ordered = stable + [v for v in all_versions if v not in stable]
            return [v for v in ordered if v]
        if kind == "quilt":
            data = http.get_json_url(f"{QUILT_META}/versions/loader/{mc_version}")
            if not isinstance(data, list):
                return []
            return [
                str(d.get("loader", {}).get("version"))
                for d in data
                if isinstance(d, dict) and d.get("loader", {}).get("version")
            ]
        if kind == "forge":
            raw = http.request(f"{FORGE_MAVEN_BASE}/maven-metadata.xml").decode(
                "utf-8", errors="replace"
            )
            versions = []
            for item in re.findall(r"<version>([^<]+)</version>", raw):
                if item.startswith(mc_version + "-"):
                    stripped = item[len(mc_version) + 1:]
                    # 1.7.10 等旧版会附加一次 MC 版本后缀
                    if stripped.endswith("-" + mc_version):
                        stripped = stripped[: -len(mc_version) - 1]
                    versions.append(stripped)
            return sorted(set(versions), key=_version_key, reverse=True)
        if kind == "neoforge":
            return _neoforge_versions(mc_version)
        if kind == "liteloader":
            data = http.get_json_url(LITELOADER_VERSIONS_URL)
            info = _find_liteloader(data, mc_version)
            return [info["version"]] if info else []
    except DownloadError as exc:
        raise LoaderError(f"获取 {LOADER_LABELS.get(kind, kind)} 版本列表失败：{exc}") from exc
    return []


def _sort_mc_versions(versions) -> list[str]:
    return sorted({str(v) for v in versions if v}, key=_version_key, reverse=True)


def list_loader_mc_versions(kind: str) -> list[str]:
    """返回指定加载器支持的全部 Minecraft 版本（新 → 旧）。

    单个数据源失败时返回空列表，不向界面抛异常。
    """
    try:
        http = _http()
        if kind in ("fabric", "quilt"):
            base = FABRIC_META if kind == "fabric" else QUILT_META
            data = http.get_json_url(f"{base}/versions/game")
            if not isinstance(data, list):
                return []
            stable: list[str] = []
            others: list[str] = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                version = str(item.get("version") or "")
                if not version:
                    continue
                (stable if item.get("stable") else others).append(version)
            stable_sorted = _sort_mc_versions(stable)
            return stable_sorted + [
                v for v in _sort_mc_versions(others) if v not in stable_sorted
            ]
        if kind == "forge":
            raw = http.request(f"{FORGE_MAVEN_BASE}/maven-metadata.xml").decode(
                "utf-8", errors="replace"
            )
            prefixes = []
            for item in re.findall(r"<version>([^<]+)</version>", raw):
                prefix = item.split("-", 1)[0].strip()
                # 1.21.1-52.0.1 / 1.7.10-10.13.4.1614-1.7.10 → 1.21.1 / 1.7.10
                if re.fullmatch(r"1\.\d+(?:\.\d+)?", prefix):
                    prefixes.append(prefix)
            return _sort_mc_versions(prefixes)
        if kind == "neoforge":
            return _neoforge_mc_versions()
        if kind == "liteloader":
            data = http.get_json_url(LITELOADER_VERSIONS_URL)
            node = data.get("versions") if isinstance(data, dict) else None
            if not isinstance(node, dict):
                return []
            return _sort_mc_versions(node.keys())
    except Exception:  # noqa: BLE001 - 单个源失败不应影响页面
        return []
    return []


def _fetch_race(candidates: list[tuple[str, int]]) -> str:
    """并发请求多个候选地址，返回最先成功的内容；全部失败时抛出 DownloadError。

    NeoForge 官方 maven 在国内常超时，BMCLAPI 镜像偶尔证书链异常，
    两边同时发起（官方给更长超时），避免串行等待导致界面报「获取失败」。
    """
    results: queue.Queue = queue.Queue()
    errors: list[str] = []
    lock = threading.Lock()

    def worker(url: str, timeout: int) -> None:
        try:
            text = Http(timeout=timeout).request(url).decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001 - 单个地址失败交给其余候选
            with lock:
                errors.append(f"{url}：{exc}")
            results.put(None)
        else:
            results.put(text)

    for url, timeout in candidates:
        threading.Thread(target=worker, args=(url, timeout), daemon=True).start()
    for _ in candidates:
        text = results.get()
        if text:
            return text
    raise DownloadError("；".join(errors))


def _fetch_neoforge_text(path: str) -> str:
    """NeoForge 官方 maven 与 BMCLAPI 镜像并发获取，取最先成功的结果。"""
    return _fetch_race(
        [
            (f"{NEOFORGE_MAVEN_BASE}/{path}", 30),
            (f"{MAVEN_MIRROR_BASE}/net/neoforged/{path}", 20),
        ]
    )


def _neoforge_mc_prefix(version: str) -> str:
    """把 NeoForge 版本号映射到 Minecraft 版本号。

    旧 scheme：21.1.172 → 1.21.1，20.2.88 → 1.20.2，21.0.x → 1.21；
    1.20.1-47.1.106 → 1.20.1（带 MC 前缀的旧产物）；
    新 scheme（年份版本）：26.1.2.124 → 26.1.2，26.3.0.99 → 26.3。
    """
    text = version.strip()
    if "-" in text and text.startswith("1."):
        return text.split("-", 1)[0]
    parts = re.split(r"[.\-+]", text)
    numbers: list[int] = []
    for part in parts:
        if not part.isdigit():
            break
        numbers.append(int(part))
    if len(numbers) < 2:
        return ""
    major, minor = numbers[0], numbers[1]
    patch = numbers[2] if len(numbers) >= 3 else 0
    if major >= 25:  # 年份式版本号（26.x），直接对应 MC 版本
        return f"{major}.{minor}" if patch == 0 else f"{major}.{minor}.{patch}"
    return f"1.{major}" if minor == 0 else f"1.{major}.{minor}"


def _neoforge_mc_versions() -> list[str]:
    """从 NeoForge maven 元数据反推支持的 Minecraft 版本。"""
    prefixes: list[str] = []
    try:
        raw = _fetch_neoforge_text("neoforge/maven-metadata.xml")
        for item in re.findall(r"<version>([^<]+)</version>", raw):
            prefix = _neoforge_mc_prefix(item)
            if prefix:
                prefixes.append(prefix)
    except DownloadError:
        pass
    # 1.20.1 的 NeoForge 产物位于 net/neoforged/forge 下
    try:
        raw = _fetch_neoforge_text("forge/maven-metadata.xml")
        for item in re.findall(r"<version>([^<]+)</version>", raw):
            prefix = item.split("-", 1)[0].strip()
            if re.fullmatch(r"1\.\d+(?:\.\d+)?", prefix):
                prefixes.append(prefix)
    except DownloadError:
        pass
    return _sort_mc_versions(prefixes)


def _neoforge_versions(mc_version: str) -> list[str]:
    parts = mc_version.split(".")
    # 年份式 MC 版本（26.x）的 NeoForge 产物直接以 MC 版本为前缀
    if len(parts) >= 2 and parts[0].isdigit() and int(parts[0]) >= 25:
        prefix = re.escape(mc_version)
        raw = _fetch_neoforge_text("neoforge/maven-metadata.xml")
        versions = [
            v
            for v in re.findall(r"<version>([^<]+)</version>", raw)
            if re.fullmatch(prefix + r"(?:\.0)?\.\d+", v)
        ]
        return sorted(set(versions), key=_version_key, reverse=True)
    if len(parts) < 3 or parts[0] != "1":
        return []
    minor, patch = int(parts[1]), int(parts[2])
    if minor == 20 and patch <= 1:
        raw = _fetch_neoforge_text("forge/maven-metadata.xml")
        return _parse_maven_versions(raw, mc_version + "-")
    prefix = f"{minor}.{patch}"
    raw = _fetch_neoforge_text("neoforge/maven-metadata.xml")
    versions = [
        v
        for v in re.findall(r"<version>([^<]+)</version>", raw)
        if re.fullmatch(re.escape(prefix) + r"\.\d+", v)
    ]
    return sorted(set(versions), key=_version_key, reverse=True)


def _find_liteloader(data, mc_version: str) -> dict:
    versions = data.get("versions") if isinstance(data, dict) else None
    if not isinstance(versions, dict):
        return {}
    node = versions.get(mc_version)
    if not isinstance(node, dict):
        return {}
    for section in ("artefacts", "snapshots", "repo"):
        block = node.get(section)
        if not isinstance(block, dict):
            continue
        artefacts = block.get("com.mumfrey:liteloader")
        if not isinstance(artefacts, dict):
            continue
        entries = [
            value
            for value in artefacts.values()
            if isinstance(value, dict) and value.get("version")
        ]
        if not entries:
            continue
        entries.sort(
            key=lambda v: (
                int(v.get("lastSuccessfulBuild") or 0),
                str(v.get("timestamp") or ""),
            ),
            reverse=True,
        )
        best = entries[0]
        version = str(best["version"])
        file_name = str(best.get("file") or f"liteloader-{version}.jar")
        return {
            "version": version,
            "url": f"{LITELOADER_BASE}/com/mumfrey/liteloader/{version}/{file_name}",
            "tweakClass": str(
                best.get("tweakClass") or "com.mumfrey.liteloader.launch.LiteLoaderTweaker"
            ),
        }
    return {}


# ---------------------------------------------------------------------------
def _write_version_json(game_dir: Path, version_id: str, data: dict) -> Path:
    version_dir = game_dir / "versions" / version_id
    version_dir.mkdir(parents=True, exist_ok=True)
    path = version_dir / f"{version_id}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def install_loader(
    installer,
    kind: str,
    mc_version: str,
    loader_version: str = "",
    java_path: str = "",
    log: Callable[[str], None] | None = None,
    cancel: threading.Event | None = None,
) -> str:
    """安装指定加载器，返回安装后的版本 ID。"""
    if kind not in LOADER_LABELS:
        raise LoaderError(f"未知的加载器：{kind}")
    version_dir = installer.config.game_path / "versions"
    version_dir.mkdir(parents=True, exist_ok=True)
    before = {p.name for p in version_dir.iterdir() if p.is_dir()}
    if not loader_version and kind != "liteloader":
        available = list_loader_versions(kind, mc_version)
        loader_version = available[0] if available else ""
    if not loader_version and kind != "liteloader":
        raise LoaderError("没有可用的加载器版本。")

    if kind in ("fabric", "quilt"):
        return _install_profile(installer, kind, mc_version, loader_version, log, cancel)
    if kind in ("forge", "neoforge"):
        return _install_installer(
            installer, kind, mc_version, loader_version, java_path, before, log, cancel
        )
    return _install_liteloader(installer, mc_version, log, cancel)


def _install_profile(
    installer,
    kind: str,
    mc_version: str,
    loader_version: str,
    log: Callable[[str], None] | None,
    cancel: threading.Event | None,
) -> str:
    http = _http()
    base = FABRIC_META if kind == "fabric" else QUILT_META
    url = f"{base}/versions/loader/{mc_version}/{loader_version}/profile/json"
    if log:
        log(f"[加载器] 获取 {LOADER_LABELS[kind]} {loader_version} profile…")
    try:
        profile = http.get_json_url(url)
    except DownloadError as exc:
        raise LoaderError(f"获取 {LOADER_LABELS[kind]} profile 失败：{exc}") from exc
    if not isinstance(profile, dict):
        raise LoaderError(f"{LOADER_LABELS[kind]} profile 数据异常。")
    version_id = str(profile.get("id") or f"{kind}-loader-{loader_version}-{mc_version}")
    profile["id"] = version_id
    profile.setdefault("inheritsFrom", mc_version)
    _write_version_json(installer.config.game_path, version_id, profile)
    if log:
        log(f"[加载器] 已写入版本 {version_id}，开始补全依赖库…")
    installer.ensure_version(version_id)
    return version_id


def _ensure_launcher_profiles(game_dir: Path) -> None:
    """Forge/NeoForge 安装器要求目录里存在启动器档案，缺失时会直接退出。"""
    profiles = game_dir / "launcher_profiles.json"
    if not profiles.is_file():
        payload = {"profiles": {}, "settings": {"language": "zh_cn"}, "version": 3}
        profiles.write_text(json.dumps(payload), encoding="utf-8")
    store = game_dir / "launcher_profiles_microsoft_store.json"
    if not store.is_file():
        store.write_text(json.dumps({"profiles": {}}), encoding="utf-8")


def _install_installer(
    installer,
    kind: str,
    mc_version: str,
    loader_version: str,
    java_path: str,
    before: set[str],
    log: Callable[[str], None] | None,
    cancel: threading.Event | None,
) -> str:
    cache = CACHE_DIR / "loaders"
    cache.mkdir(parents=True, exist_ok=True)
    if kind == "forge":
        file_name = f"forge-{mc_version}-{loader_version}-installer.jar"
        url = (
            f"{FORGE_MAVEN_BASE}/{mc_version}-{loader_version}/"
            f"forge-{mc_version}-{loader_version}-installer.jar"
        )
        mirror_url = (
            f"{MAVEN_MIRROR_BASE}/net/minecraftforge/forge/{mc_version}-{loader_version}/"
            f"forge-{mc_version}-{loader_version}-installer.jar"
        )
    else:
        parts = mc_version.split(".")
        if len(parts) >= 3 and int(parts[1]) == 20 and int(parts[2]) <= 1:
            file_name = f"forge-{mc_version}-{loader_version}-installer.jar"
            url = (
                f"{NEOFORGE_MAVEN_BASE}/forge/{mc_version}-{loader_version}/"
                f"forge-{mc_version}-{loader_version}-installer.jar"
            )
            mirror_url = (
                f"{MAVEN_MIRROR_BASE}/net/neoforged/forge/{mc_version}-{loader_version}/"
                f"forge-{mc_version}-{loader_version}-installer.jar"
            )
        else:
            file_name = f"neoforge-{loader_version}-installer.jar"
            url = (
                f"{NEOFORGE_MAVEN_BASE}/neoforge/{loader_version}/"
                f"neoforge-{loader_version}-installer.jar"
            )
            mirror_url = (
                f"{MAVEN_MIRROR_BASE}/net/neoforged/neoforge/{loader_version}/"
                f"neoforge-{loader_version}-installer.jar"
            )
    jar = cache / file_name
    if not (jar.exists() and jar.stat().st_size > 1024):
        if log:
            log(f"[加载器] 下载 {LOADER_LABELS[kind]} 安装器 {file_name}…")
        try:
            _http().download(
                [
                    Candidate(url, {}, "official", "官方"),
                    Candidate(mirror_url, {}, "bmclapi", "BMCLAPI 镜像"),
                ],
                jar,
                size=None,
                sha1=None,
                cancel=cancel,
            )
        except DownloadError as exc:
            raise LoaderError(f"下载安装器失败：{exc}") from exc

    java = java_path
    if not java:
        raise LoaderError("未找到可用的 Java，无法运行安装器。请在设置中选择 Java。")
    game_dir = installer.config.game_path
    game_dir.mkdir(parents=True, exist_ok=True)
    _ensure_launcher_profiles(game_dir)
    command = [java, "-jar", str(jar), "--installClient", str(game_dir)]
    if log:
        log("[加载器] 执行：" + " ".join(command))
    process = subprocess.Popen(
        command,
        cwd=str(game_dir),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=CREATE_NO_WINDOW,
    )
    assert process.stdout is not None
    # Windows 的管道不支持 select，用独立读线程 + 队列，主线程定期检查取消与超时
    lines: queue.Queue[bytes | None] = queue.Queue()

    def _reader() -> None:
        try:
            for raw in iter(process.stdout.readline, b""):
                lines.put(raw)
        except Exception:  # noqa: BLE001 - 进程退出时管道可能已关闭
            pass
        finally:
            lines.put(None)

    threading.Thread(target=_reader, name="installer-stdout", daemon=True).start()
    deadline = time.time() + INSTALLER_TIMEOUT
    while True:
        if cancel is not None and cancel.is_set():
            process.terminate()
            raise LoaderError("安装已取消。")
        if time.time() > deadline:
            process.kill()
            raise LoaderError(
                f"安装器运行超过 {INSTALLER_TIMEOUT} 秒仍无响应，已强制终止。"
                "请检查网络后重试，或手动运行安装器。"
            )
        try:
            raw = lines.get(timeout=0.3)
        except queue.Empty:
            continue
        if raw is None:
            break
        line = raw.decode("utf-8", errors="replace").rstrip()
        if line and log:
            log(f"[安装器] {line}")
    try:
        code = process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        process.kill()
        code = -1
    # 安装器可能因为版本已存在而返回非零，最终以生成的文件为准
    after = {p.name for p in (game_dir / "versions").iterdir() if p.is_dir()}
    candidates = sorted(after - before)
    preferred = (
        f"{mc_version}-forge-{loader_version}"
        if kind == "forge"
        else f"neoforge-{loader_version}"
    )
    version_id = ""
    if preferred in after:
        version_id = preferred
    elif candidates:
        version_id = candidates[-1]
    if code != 0 and not version_id:
        raise LoaderError(f"安装器退出码 {code}，未生成版本文件。请查看日志。")
    if not version_id:
        raise LoaderError("安装器运行结束，但未找到生成的版本文件。")
    if not (game_dir / "versions" / version_id / f"{version_id}.json").exists():
        raise LoaderError(f"安装器没有生成 {version_id}.json（退出码 {code}）。")
    if log:
        log(f"[加载器] {LOADER_LABELS[kind]} 安装完成：{version_id}")
    try:
        installer.ensure_version(version_id)
    except Exception as exc:  # noqa: BLE001 - 安装器通常已完成，补全失败仅提示
        if log:
            log(f"[加载器] 依赖补全提示：{exc}")
    return version_id


def _install_liteloader(
    installer,
    mc_version: str,
    log: Callable[[str], None] | None,
    cancel: threading.Event | None,
) -> str:
    http = _http()
    try:
        data = http.get_json_url(LITELOADER_VERSIONS_URL)
    except DownloadError as exc:
        raise LoaderError(f"获取 LiteLoader 版本列表失败：{exc}") from exc
    info = _find_liteloader(data, mc_version)
    if not info or not info.get("url"):
        raise LoaderError(
            f"LiteLoader 不支持 Minecraft {mc_version}（官方仅提供到 1.12.2）。"
        )
    version = info["version"]
    version_id = f"{mc_version}-liteloader-{version}"
    jar_rel = f"com/mumfrey/liteloader/{version}/liteloader-{version}.jar"
    payload = {
        "id": version_id,
        "inheritsFrom": mc_version,
        "type": "release",
        "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "releaseTime": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mainClass": "net.minecraft.launchwrapper.Launch",
        "minecraftArguments": (
            "--username ${auth_player_name} --version ${version_name} "
            "--gameDir ${game_directory} --assetsDir ${assets_root} "
            "--assetIndex ${assets_index_name} --uuid ${auth_uuid} "
            "--accessToken ${auth_access_token} --userType ${user_type} "
            "--tweakClass com.mumfrey.liteloader.launch.LiteLoaderTweaker"
        ),
        "libraries": [
            {
                "name": f"com.mumfrey:liteloader:{version}",
                "downloads": {
                    "artifact": {
                        "url": info["url"],
                        "path": jar_rel,
                        "size": 0,
                    }
                },
            },
            {"name": "net.minecraft:launchwrapper:1.12", "url": "https://libraries.minecraft.net/"},
            {"name": "org.ow2.asm:asm-all:5.2", "url": "https://maven.minecraftforge.net/"},
        ],
    }
    if log:
        log(f"[加载器] 生成 LiteLoader 版本 {version_id}")
    _write_version_json(installer.config.game_path, version_id, payload)
    installer.ensure_version(version_id)
    return version_id


def java_for_mc(mc_version: str) -> int:
    return infer_java_major(mc_version)
