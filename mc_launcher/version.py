"""版本 JSON 解析、inheritsFrom 合并、规则求值与依赖解析（HMCL 兼容）。"""

from __future__ import annotations

import copy
import json
import os
import platform
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

DEFAULT_LIBRARY_BASE = "https://libraries.minecraft.net/"

WINDOWS_OS_NAME = "windows"

# 愚人节版本（官方清单里多数标记为 snapshot，需要单独归类）
APRIL_FOOLS_IDS = {
    "2.0",
    "15w14a",
    "1.rv-pre1",
    "3d shareware v1.34",
    "20w14infinite",
    "22w13oneblockatatime",
    "23w13a_or_b",
    "24w14potato",
    "25w14craftmine",
}

CATEGORY_LABELS = {
    "release": "正式版",
    "snapshot": "快照",
    "old": "远古版本",
    "april": "愚人节版本",
}


def is_april_fools(version_id: str) -> bool:
    key = (version_id or "").strip().lower()
    return key in APRIL_FOOLS_IDS or key.startswith("3d shareware")


def version_category(version_id: str, version_type: str = "") -> str:
    """把版本清单条目归类为 release / snapshot / old / april。"""
    if is_april_fools(version_id):
        return "april"
    kind = (version_type or "").lower()
    if kind == "release":
        return "release"
    if kind == "snapshot":
        return "snapshot"
    return "old"


class VersionError(Exception):
    pass


def os_arch() -> str:
    if struct.calcsize("P") * 8 == 32:
        return "x86"
    machine = platform.machine().lower()
    if machine in ("arm64", "aarch64"):
        return "arm64"
    return "x86_64"


def default_features() -> dict[str, bool]:
    return {
        "is_demo_user": False,
        "has_custom_resolution": False,
        "has_quick_plays_support": False,
        "is_quick_play_singleplayer": False,
        "is_quick_play_multiplayer": False,
        "is_quick_play_realms": False,
    }


def rules_allow(
    rules: Iterable[dict[str, Any]] | None,
    features: dict[str, bool] | None = None,
    os_name: str = WINDOWS_OS_NAME,
    arch: str | None = None,
) -> bool:
    """Mojang 规则：按顺序匹配，最后匹配的 action 生效；没有匹配则拒绝。"""
    if not rules:
        return True
    features = features or default_features()
    arch = arch or os_arch()
    current = False
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        action = rule.get("action")
        matched = True
        rule_os = rule.get("os")
        if isinstance(rule_os, dict):
            if "name" in rule_os and rule_os["name"] != os_name:
                matched = False
            if matched and "arch" in rule_os and rule_os["arch"] != arch:
                matched = False
            if matched and "version" in rule_os:
                try:
                    if not re.match(str(rule_os["version"]), platform.version()):
                        matched = False
                except re.error:
                    matched = False
        if matched and isinstance(rule.get("features"), dict):
            for key, expected in rule["features"].items():
                if bool(features.get(key)) != bool(expected):
                    matched = False
                    break
        if matched:
            current = action == "allow"
    return current


def maven_path(name: str) -> str | None:
    """group:artifact:version[:classifier][@ext] -> 仓库内相对路径。"""
    if not name:
        return None
    ext = "jar"
    if "@" in name:
        name, ext = name.split("@", 1)
    parts = name.split(":")
    if len(parts) < 3:
        return None
    group, artifact, version = parts[0], parts[1], parts[2]
    classifier = parts[3] if len(parts) > 3 else ""
    filename = f"{artifact}-{version}"
    if classifier:
        filename += f"-{classifier}"
    filename += f".{ext}"
    return f"{group.replace('.', '/')}/{artifact}/{version}/{filename}"


@dataclass
class LibraryFile:
    key: str
    path: str
    url: str
    sha1: str = ""
    size: int = 0
    extract: bool = False
    exclude: list[str] = field(default_factory=list)
    label: str = ""

    @property
    def filename(self) -> str:
        return Path(self.path).name


def _download_entry(base: str, entry: dict[str, Any] | None, rel_path: str) -> tuple[str, str, str, int]:
    entry = entry or {}
    url = entry.get("url") or (base.rstrip("/") + "/" + rel_path)
    return rel_path, url, str(entry.get("sha1") or ""), int(entry.get("size") or 0)


def _name_classifier(name: str) -> str:
    parts = name.split(":")
    if len(parts) < 4:
        return ""
    return parts[3].split("@", 1)[0]


def _is_native_entry(name: str) -> bool:
    """1.19+ 把 natives 写成带 classifier 的普通库条目（如 lwjgl:3.3.1:natives-windows）。"""
    return _name_classifier(name).startswith("natives-")


def _foreign_arch_native(name: str) -> bool:
    """判断是否为其它 CPU 架构的 natives 包，避免不同架构的同名 DLL 互相覆盖。"""
    classifier = _name_classifier(name)
    if not classifier.startswith("natives-"):
        return False
    arch = os_arch()
    if classifier.endswith("-arm64"):
        return arch != "arm64"
    if classifier.endswith("-x86"):
        return arch != "x86"
    return arch != "x86_64"



def library_files(lib: dict[str, Any]) -> list[LibraryFile]:
    """解析单个库在 Windows 下需要下载的文件（含旧版 natives 解压包）。"""
    if not isinstance(lib, dict):
        return []
    name = str(lib.get("name") or "")
    downloads = lib.get("downloads") if isinstance(lib.get("downloads"), dict) else {}
    base = str(lib.get("url") or DEFAULT_LIBRARY_BASE)
    result: list[LibraryFile] = []

    artifact = downloads.get("artifact") if isinstance(downloads.get("artifact"), dict) else None
    natives = lib.get("natives")
    natives_only = isinstance(natives, dict) and not artifact
    if artifact and artifact.get("path"):
        rel, url, sha1, size = _download_entry(base, artifact, str(artifact["path"]))
        extract_info = lib.get("extract") if isinstance(lib.get("extract"), dict) else {}
        native = _is_native_entry(name)
        result.append(
            LibraryFile(
                key=name,
                path=rel,
                url=url,
                sha1=sha1,
                size=size,
                extract=native,
                exclude=[str(x) for x in (extract_info.get("exclude") or [])] if native else [],
                label=name,
            )
        )
    elif name and not natives_only:
        # 只有 natives 包、没有主 jar 的旧版库（如 jinput-platform）不下载主 jar
        rel = maven_path(name)
        if rel:
            rel, url, sha1, size = _download_entry(base, None, rel)
            result.append(LibraryFile(key=name, path=rel, url=url, sha1=sha1, size=size, label=name))

    if isinstance(natives, dict):
        classifier = natives.get("windows")
        if classifier is None:
            classifier = natives.get("windows-arm64") if os_arch() == "arm64" else None
        if classifier:
            classifier = str(classifier).replace("${arch}", "64" if os_arch() == "x86_64" else "32")
            classifiers = downloads.get("classifiers") if isinstance(downloads.get("classifiers"), dict) else {}
            entry = classifiers.get(classifier) if isinstance(classifiers, dict) else None
            if entry and entry.get("path"):
                rel, url, sha1, size = _download_entry(base, entry, str(entry["path"]))
            else:
                rel_name = f"{name}:{classifier}"
                rel = maven_path(rel_name)
                if not rel:
                    return result
                rel, url, sha1, size = _download_entry(base, None, rel)
            extract_info = lib.get("extract") if isinstance(lib.get("extract"), dict) else {}
            exclude = [str(x) for x in (extract_info.get("exclude") or [])]
            result.append(
                LibraryFile(
                    key=name + "::" + classifier,
                    path=rel,
                    url=url,
                    sha1=sha1,
                    size=size,
                    extract=True,
                    exclude=exclude,
                    label=f"{name} ({classifier})",
                )
            )
    return result


def resolve_libraries(
    version_json: dict[str, Any], features: dict[str, bool] | None = None
) -> list[LibraryFile]:
    """筛选、去重并解析所有 Windows 下需要的库文件。"""
    features = features or default_features()
    entries: list[tuple[str, LibraryFile]] = []
    for lib in version_json.get("libraries") or []:
        if not isinstance(lib, dict):
            continue
        if not rules_allow(lib.get("rules"), features):
            continue
        if _foreign_arch_native(str(lib.get("name") or "")):
            continue
        for file in library_files(lib):
            entries.append((file.key, file))
    # 子版本覆盖父版本：同 key 保留靠后的
    merged: dict[str, LibraryFile] = {}
    for key, file in entries:
        merged[key] = file
    # 同一路径只保留一个
    by_path: dict[str, LibraryFile] = {}
    for file in merged.values():
        if file.path not in by_path:
            by_path[file.path] = file
    return list(by_path.values())


# ---------------------------------------------------------------------------
# 版本合并
# ---------------------------------------------------------------------------
def _flatten_entries(
    entries: Any, features: dict[str, bool] | None = None
) -> list[str]:
    """把 arguments 中的字符串与带 rules 的对象展开为字符串列表。"""
    if not isinstance(entries, list):
        return []
    features = features or default_features()
    result: list[str] = []
    for entry in entries:
        if isinstance(entry, str):
            result.append(entry)
        elif isinstance(entry, dict):
            if rules_allow(entry.get("rules"), features):
                value = entry.get("value")
                if isinstance(value, str):
                    result.append(value)
                elif isinstance(value, list):
                    result.extend(str(v) for v in value)
    return result


def merge_argument_lists(parent: list[Any], child: list[Any]) -> list[Any]:
    """合并父/子 arguments 原始条目（子项按选项名覆盖父项）。"""
    if not parent:
        return list(child or [])
    if not child:
        return list(parent or [])
    return list(parent) + list(child)


def _merge_version_json(parent: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(parent)
    for key, value in child.items():
        if key == "libraries":
            merged[key] = list(parent.get(key) or []) + list(value or [])
        elif key == "arguments":
            p_args = parent.get("arguments") if isinstance(parent.get("arguments"), dict) else {}
            c_args = value if isinstance(value, dict) else {}
            merged[key] = {
                "game": merge_argument_lists(p_args.get("game") or [], c_args.get("game") or []),
                "jvm": merge_argument_lists(p_args.get("jvm") or [], c_args.get("jvm") or []),
            }
        elif key == "downloads":
            downloads = dict(parent.get("downloads") or {})
            if isinstance(value, dict):
                downloads.update(value)
            merged["downloads"] = downloads
        elif key in ("logging", "assetIndex", "javaVersion", "clientVersion"):
            if value:
                merged[key] = value
        elif key == "minecraftArguments":
            if value:
                merged[key] = value
        else:
            merged[key] = value
    merged["id"] = str(child.get("id") or merged.get("id") or "")
    return merged


def _read_version_tree(
    versions_dir: Path, version_id: str, stack: tuple[str, ...] = ()
) -> dict[str, Any]:
    if version_id in stack:
        raise VersionError(f"版本继承出现循环：{' -> '.join(stack + (version_id,))}")
    path = versions_dir / version_id / f"{version_id}.json"
    if not path.exists():
        raise VersionError(f"缺少版本文件：{path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise VersionError(f"版本 JSON 无法解析：{path}\n{exc}") from exc
    if not isinstance(data, dict):
        raise VersionError(f"版本 JSON 格式错误：{path}")

    parent_id = data.get("inheritsFrom")
    if parent_id:
        parent = _read_version_tree(versions_dir, str(parent_id), stack + (version_id,))
        merged = _merge_version_json(parent, data)
        merged["__jar_id"] = data.get("jar") or parent.get("__jar_id") or str(parent_id)
    else:
        merged = copy.deepcopy(data)
        merged["__jar_id"] = data.get("jar") or version_id
    merged["__source_id"] = version_id
    return merged


@dataclass
class MergedVersion:
    id: str
    json: dict[str, Any]
    path: Path
    type: str
    main_class: str
    jar_id: str
    assets_id: str
    asset_index: dict[str, Any] | None
    client_download: dict[str, Any] | None
    logging: dict[str, Any] | None
    libraries: list[LibraryFile]
    raw_game_args: list[Any]
    raw_jvm_args: list[Any]
    minecraft_arguments: str
    release_time: str
    java_major: int | None
    inherits_from: str

    def game_args(self, features: dict[str, bool] | None = None) -> list[str]:
        if self.minecraft_arguments:
            return self.minecraft_arguments.split()
        return _dedupe_options(_flatten_entries(self.raw_game_args, features))

    def jvm_args(self, features: dict[str, bool] | None = None) -> list[str]:
        return _dedupe_options(_flatten_entries(self.raw_jvm_args, features))


def _dedupe_options(args: list[str]) -> list[str]:
    """同一个启动选项重复出现时保留最后一个（子版本覆盖父版本）。"""
    groups: list[list[str]] = []
    for token in args:
        if token.startswith("-"):
            groups.append([token])
        elif groups:
            groups[-1].append(token)
        else:
            groups.append([token])
    result: list[list[str]] = []
    index_by_key: dict[str, int] = {}
    for group in groups:
        head = group[0]
        if head.startswith("-"):
            key = head.split("=", 1)[0]
            if key in index_by_key:
                result[index_by_key[key]] = group
                continue
            index_by_key[key] = len(result)
        result.append(group)
    return [token for group in result for token in group]


def infer_java_major(version_id: str) -> int:
    match = re.match(r"^1\.(\d+)(?:\.(\d+))?", version_id)
    if match:
        minor = int(match.group(1))
        patch = int(match.group(2) or 0)
        if minor < 17:
            return 8
        if minor == 17:
            return 17
        if minor < 20 or (minor == 20 and patch < 5):
            return 17
        return 21
    return 21


def load_version(game_dir: Path, version_id: str) -> MergedVersion:
    versions_dir = game_dir / "versions"
    raw = _read_version_tree(versions_dir, version_id)
    java_version = raw.get("javaVersion") if isinstance(raw.get("javaVersion"), dict) else {}
    major = None
    try:
        if java_version.get("majorVersion") is not None:
            major = int(java_version["majorVersion"])
    except (TypeError, ValueError):
        major = None
    raw_game = (raw.get("arguments") or {}).get("game") if isinstance(raw.get("arguments"), dict) else []
    raw_jvm = (raw.get("arguments") or {}).get("jvm") if isinstance(raw.get("arguments"), dict) else []
    client = (raw.get("downloads") or {}).get("client") if isinstance(raw.get("downloads"), dict) else None
    logging = raw.get("logging", {}).get("client") if isinstance(raw.get("logging"), dict) else None
    return MergedVersion(
        id=version_id,
        json=raw,
        path=versions_dir / version_id / f"{version_id}.json",
        type=str(raw.get("type") or "unknown"),
        main_class=str(raw.get("mainClass") or "net.minecraft.client.main.Main"),
        jar_id=str(raw.get("__jar_id") or version_id),
        assets_id=str(raw.get("assets") or "legacy"),
        asset_index=raw.get("assetIndex") if isinstance(raw.get("assetIndex"), dict) else None,
        client_download=client if isinstance(client, dict) else None,
        logging=logging if isinstance(logging, dict) else None,
        libraries=resolve_libraries(raw),
        raw_game_args=list(raw_game or []),
        raw_jvm_args=list(raw_jvm or []),
        minecraft_arguments=str(raw.get("minecraftArguments") or ""),
        release_time=str(raw.get("releaseTime") or ""),
        java_major=major or infer_java_major(version_id),
        inherits_from=str(raw.get("inheritsFrom") or ""),
    )


@dataclass
class InstalledVersion:
    id: str
    path: Path
    type: str
    loader: str
    base_version: str
    modified: float
    error: str = ""

    @property
    def display_type(self) -> str:
        mapping = {
            "release": "正式版",
            "snapshot": "快照",
            "old_beta": "Beta",
            "old_alpha": "Alpha",
        }
        return mapping.get(self.type, self.type or "未知")


_LOADER_LABELS = [
    ("neoforge", "NeoForge"),
    ("forge", "Forge"),
    ("fabric", "Fabric"),
    ("quilt", "Quilt"),
    ("optifine", "OptiFine"),
    ("liteloader", "LiteLoader"),
]


def detect_loader(version_id: str, data: dict[str, Any]) -> str:
    haystack_parts = [version_id.lower(), str(data.get("mainClass") or "").lower()]
    libraries = data.get("libraries") or []
    for lib in libraries:
        if isinstance(lib, dict):
            haystack_parts.append(str(lib.get("name") or "").lower())
    haystack = " ".join(haystack_parts)
    for key, label in _LOADER_LABELS:
        if key in haystack:
            return label
    return "原版"


def scan_installed_versions(game_dir: Path) -> list[InstalledVersion]:
    versions_dir = game_dir / "versions"
    result: list[InstalledVersion] = []
    if not versions_dir.is_dir():
        return result
    for entry in versions_dir.iterdir():
        if not entry.is_dir():
            continue
        json_path = entry / f"{entry.name}.json"
        if not json_path.exists():
            continue
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("不是 JSON 对象")
            result.append(
                InstalledVersion(
                    id=entry.name,
                    path=json_path,
                    type=str(data.get("type") or "custom"),
                    loader=detect_loader(entry.name, data),
                    base_version=str(data.get("inheritsFrom") or ""),
                    modified=json_path.stat().st_mtime,
                )
            )
        except (OSError, ValueError) as exc:
            result.append(
                InstalledVersion(
                    id=entry.name,
                    path=json_path,
                    type="broken",
                    loader="损坏",
                    base_version="",
                    modified=json_path.stat().st_mtime if json_path.exists() else 0,
                    error=str(exc),
                )
            )
    result.sort(key=lambda v: v.modified, reverse=True)
    return result


def client_jar_path(game_dir: Path, jar_id: str) -> Path:
    return game_dir / "versions" / jar_id / f"{jar_id}.jar"


def logging_file_path(game_dir: Path, logging: dict[str, Any] | None) -> Path:
    file_info = (logging or {}).get("file")
    if not isinstance(file_info, dict):
        file_info = {}
    file_id = str(file_info.get("id") or "client-log.xml")
    return game_dir / "assets" / "log_configs" / Path(file_id).name
