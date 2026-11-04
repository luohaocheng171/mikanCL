"""从 PCL2 / HMCL 的配置目录导入游戏版本与游戏设置。

只做读取与登记，不复制、不移动对方目录里的任何文件：
- 扫描对方 `.minecraft` 下已有的版本（含加载器与整合包版本）；
- 读取 PCL 的 `Setup.ini` / HMCL 的 `.hmcl.json`、`hmclversion.cfg` 中的设置；
- 为「本启动器没有、对方独有」的版本创建实例（实例直接指向对方的游戏目录），
  这样 mod、存档、资源包都沿用原目录，无需重复下载。
"""

from __future__ import annotations

import configparser
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config, Instance, VersionSettings


LOADER_LABELS = {
    "forge": "Forge",
    "neoforge": "NeoForge",
    "fabric": "Fabric",
    "quilt": "Quilt",
    "liteloader": "LiteLoader",
    "optifine": "OptiFine",
}


@dataclass
class ExternalVersion:
    version_id: str
    path: Path
    mc_version: str = ""
    loader: str = ""
    loader_version: str = ""
    description: str = ""
    memory_mb: int = 0
    java_path: str = ""
    isolation: str = ""
    window_title: str = ""
    extra_jvm_args: str = ""
    extra_game_args: str = ""
    imported: bool = False
    skip_reason: str = ""

    @property
    def label(self) -> str:
        parts = [self.version_id]
        if self.loader:
            parts.append(LOADER_LABELS.get(self.loader, self.loader))
        if self.mc_version and self.mc_version != self.version_id:
            parts.append(self.mc_version)
        return " · ".join(parts)


@dataclass
class ExternalProfile:
    kind: str
    root: Path
    game_dir: Path
    versions: list[ExternalVersion] = field(default_factory=list)
    settings: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _read_ini(path: Path) -> dict[str, str]:
    """读取 PCL 的 ini / HMCL 的 cfg（兼容无节名、BOM、Key:Value 与 Key=Value）。"""
    result: dict[str, str] = {}
    if path.suffix.lower() == ".json":
        try:
            raw = path.read_text(encoding="utf-8-sig", errors="replace")
            data = json.loads(raw)
            return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return result
    try:
        raw = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return result
    parser = configparser.ConfigParser(interpolation=None, strict=False, allow_no_value=True)
    try:
        parser.read_string(raw)
    except configparser.Error:
        # 没有节名的纯 key=value / key:value 文件（PCL 与 HMCL 都是这种）
        return _parse_flat(raw)
    for section in parser.sections():
        for key, value in parser.items(section, raw=True):
            result[key.strip()] = str(value or "").strip()
    if not result:
        result = _parse_flat(raw)
    return result


def _parse_flat(raw: str) -> dict[str, str]:
    """逐行解析无节名的 key=value / key:value 文本。"""
    result: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", ";")) or ":" not in line and "=" not in line:
            continue
        key, value = _split_pair(line)
        if key:
            result[key] = value
    return result


def _split_pair(line: str) -> tuple[str, str]:
    """按第一个 '=' 或第一个 ':' 切分 key/value（PCL 用冒号，HMCL 用等号）。"""
    colon = line.find(":")
    equal = line.find("=")
    positions = [pos for pos in (colon, equal) if pos >= 0]
    if not positions:
        return "", ""
    index = min(positions)
    return line[:index].strip(), line[index + 1:].strip()


def _bool(value: object) -> bool:
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on", "enable", "enabled"}


def _int(value: object, default: int = 0) -> int:
    try:
        return max(0, int(float(str(value).strip())))
    except (TypeError, ValueError):
        return default


def _guess_mc_version(version_id: str, data: dict) -> str:
    inherited = str(data.get("inheritsFrom") or "").strip()
    if inherited:
        return inherited
    match = re.search(r"(1\.\d+(?:\.\d+)?)", version_id)
    return match.group(1) if match else ""


def _libraries_text(data: dict) -> str:
    libraries = data.get("libraries")
    if not isinstance(libraries, list):
        return ""
    return " ".join(
        str(item.get("name") or "") for item in libraries if isinstance(item, dict)
    ).lower()


def _loader_info(version_id: str, data: dict) -> tuple[str, str]:
    text = version_id.lower()
    libs = _libraries_text(data)
    if "neoforge" in text or "neoforge" in libs:
        match = re.search(r"neoforge[-_]([0-9][\w.\-+]*)", text)
        return "neoforge", match.group(1) if match else ""
    if "quilt" in text or "quilt-loader" in libs:
        match = re.search(r"quilt-loader[-_]([0-9][\w.\-+]*)", libs) or re.search(
            r"quilt[-_]([0-9][\w.\-+]*)", text
        )
        return "quilt", match.group(1) if match else ""
    if "fabric" in text or "fabric-loader" in libs:
        match = re.search(r"fabric-loader[-_]([0-9][\w.\-+]*)", libs) or re.search(
            r"fabric-loader[-_]([0-9][\w.\-+]*)", text
        )
        if not match:
            match = re.search(r"loader[-_]([0-9][\w.\-+]*)", text)
        return "fabric", match.group(1) if match else ""
    if "liteloader" in text or "com.mumfrey:liteloader" in libs:
        match = re.search(r"liteloader[-_]([0-9][\w.\-+]*)", text)
        return "liteloader", match.group(1) if match else ""
    if "optifine" in text or "optifine:optifine" in libs:
        match = re.search(r"optifine[-_]([0-9][\w.\-+]*)", text)
        return "optifine", match.group(1) if match else ""
    if "forge" in text or "net.minecraftforge:forge" in libs:
        match = re.search(r"forge[-_]([0-9][\w.\-+]*)", text)
        return "forge", match.group(1) if match else ""
    return "", ""


_VERSION_KEY_HINTS = ("ram", "memory")
_JAVA_KEY_HINTS = ("java", "jvm")
_ISOLATION_KEY_HINTS = ("indie", "isolation", "isolate", "separat")


def _apply_settings(version: ExternalVersion, settings: dict, kind: str) -> None:
    """把 PCL / HMCL 的键值设置映射到本启动器的版本设置。"""
    for key, raw in settings.items():
        text = str(raw or "").strip()
        low = key.lower()
        if not text:
            continue
        if any(hint in low for hint in _VERSION_KEY_HINTS):
            number = _int(text)
            if 256 <= number <= 262144:
                version.memory_mb = number
            continue
        if any(hint in low for hint in _JAVA_KEY_HINTS):
            if text.lower().endswith(("java.exe", "javaw.exe")) or os.path.isdir(text):
                version.java_path = text
            continue
        if any(hint in low for hint in _ISOLATION_KEY_HINTS):
            if _bool(text):
                # PCL 的「版本隔离」等价于本启动器的全部隔离（mod/存档/资源全部独立）
                version.isolation = "all"
            continue
        if low == "info":
            version.description = text
            continue
        if (low in {"name", "description"} or low.endswith("vanillaname")) and not version.description:
            version.description = text
            continue
        if "jvm" in low or "javaarg" in low:
            version.extra_jvm_args = text
        elif "gamearg" in low:
            version.extra_game_args = text
        if "title" in low and not version.window_title:
            version.window_title = text


def _scan_versions(profile: ExternalProfile) -> None:
    versions_dir = profile.game_dir / "versions"
    if not versions_dir.is_dir():
        profile.warnings.append(f"目录中没有 versions 文件夹：{versions_dir}")
        return
    for folder in sorted(versions_dir.iterdir()):
        if not folder.is_dir():
            continue
        json_path = folder / f"{folder.name}.json"
        if not json_path.is_file():
            candidates = sorted(folder.glob("*.json"))
            if not candidates:
                continue
            json_path = candidates[0]
        data = _read_json(json_path)
        version_id = str(data.get("id") or json_path.stem or folder.name)
        mc_version = _guess_mc_version(version_id, data)
        loader, loader_version = _loader_info(version_id, data)
        item = ExternalVersion(
            version_id=version_id,
            path=json_path,
            mc_version=mc_version or version_id,
            loader=loader,
            loader_version=loader_version,
        )

        if profile.kind == "PCL":
            for candidate in (folder / "PCL" / "Setup.ini", folder / "PCL" / "config.json"):
                if candidate.is_file():
                    _apply_settings(item, _read_ini(candidate), "PCL")
            pcl_ini = folder / "PCL.ini"
            if pcl_ini.is_file():
                _apply_settings(item, _read_ini(pcl_ini), "PCL")
        else:
            for name in ("hmclversion.cfg", "instance.cfg", "PCL.ini"):
                candidate = folder / name
                if candidate.is_file():
                    _apply_settings(item, _read_ini(candidate), "HMCL")
        profile.versions.append(item)


def _resolve_game_dir(path: Path) -> tuple[Path | None, Path]:
    """从用户选择的路径推断 (游戏目录, 启动器根目录)。"""
    if path.is_file():
        # 允许直接选 .hmcl.json
        return path.parent / ".minecraft", path.parent
    if path.name.lower() == ".minecraft":
        return path, path.parent
    if path.name.lower() == "pcl":
        return path.parent / ".minecraft", path.parent
    if path.name.lower() == ".hmcl":
        return path.parent / ".minecraft", path.parent
    nested = path / ".minecraft"
    if nested.is_dir():
        return nested, path
    if (path / "versions").is_dir():
        return path, path.parent
    return None, path


def scan_profile(path: str | Path) -> ExternalProfile | None:
    """扫描一个 PCL / HMCL 配置目录，返回可导入的版本与设置。"""
    root = Path(os.path.expandvars(str(path))).expanduser()
    if not root.exists():
        return None
    game_dir, launcher_root = _resolve_game_dir(root)
    if game_dir is None or not game_dir.is_dir():
        return None

    versions_root = game_dir / "versions"
    has_hmcl_instance = False
    if versions_root.is_dir():
        try:
            has_hmcl_instance = any(
                (folder / "hmclversion.cfg").is_file()
                for folder in versions_root.iterdir()
                if folder.is_dir()
            )
        except OSError:
            has_hmcl_instance = False
    kind = "HMCL" if (
        root.name.lower() == ".hmcl"
        or root.name.lower().endswith(".hmcl.json")
        or (launcher_root / ".hmcl.json").is_file()
        or (launcher_root / ".hmcl").is_dir()
        or has_hmcl_instance
    ) else "PCL"
    profile = ExternalProfile(kind=kind, root=launcher_root, game_dir=game_dir)

    settings: dict[str, str] = {}
    if kind == "PCL":
        for candidate in (
            launcher_root / "PCL" / "Setup.ini",
            game_dir / "PCL.ini",
            game_dir / "PCL" / "Setup.ini",
        ):
            if candidate.is_file():
                settings.update(_read_ini(candidate))
    else:
        for candidate in (
            launcher_root / ".hmcl.json",
            root if root.is_file() else launcher_root / ".hmcl.json",
        ):
            if candidate.is_file():
                settings.update(_read_ini(candidate))
        hmcl_cfg = launcher_root / ".hmcl" / "config.json"
        if hmcl_cfg.is_file():
            settings.update(_read_ini(hmcl_cfg))
    profile.settings = settings

    _scan_versions(profile)
    if not profile.versions:
        profile.warnings.append("没有找到可导入的版本（versions 目录为空）。")
    return profile


def _norm(path: str | Path) -> str:
    """规范化路径用于比较：展开环境变量、消解 .. / 尾斜杠，再统一大小写。"""
    text = os.path.expandvars(str(path or "")).strip().strip('"')
    try:
        resolved = Path(text).expanduser().resolve()
    except OSError:
        resolved = Path(text).expanduser().absolute()
    return os.path.normcase(str(resolved))


def _instance_identity(game_dir: str | Path, version_id: str) -> str:
    digest = hashlib.sha1(
        (_norm(game_dir) + "|" + version_id).encode("utf-8")
    ).hexdigest()
    return f"imported_{digest[:10]}"


def _local_version_ids(config: Config) -> set[str]:
    ids: set[str] = set()
    for game_dir in config.game_dirs:
        versions = Path(os.path.expandvars(game_dir.path)).expanduser() / "versions"
        if not versions.is_dir():
            continue
        try:
            ids.update(folder.name for folder in versions.iterdir() if folder.is_dir())
        except OSError:
            continue
    return ids


def import_profile(
    config: Config,
    profile: ExternalProfile,
    version_ids: list[str] | None = None,
    import_settings: bool = True,
    import_global: bool = False,
) -> dict:
    """把选定版本登记为实例；返回导入统计。"""
    selected = set(version_ids) if version_ids else {v.version_id for v in profile.versions}
    local_ids = _local_version_ids(config)
    existing = {_instance_identity(i.game_dir, i.version_id) for i in config.instances}

    imported: list[str] = []
    skipped: list[str] = []
    for item in profile.versions:
        if item.version_id not in selected:
            continue
        if item.version_id in local_ids:
            item.skip_reason = "本启动器已有同版本，无需重复导入"
            skipped.append(item.version_id)
            continue
        identity = _instance_identity(profile.game_dir, item.version_id)
        if identity in existing:
            item.skip_reason = "已导入过该版本"
            skipped.append(item.version_id)
            continue
        config.instances.append(
            Instance(
                id=identity,
                name=item.description or item.version_id,
                game_dir=str(profile.game_dir.resolve()),
                version_id=item.version_id,
                loader=item.loader,
                mc_version=item.mc_version,
                loader_version=item.loader_version,
                memory_mb=item.memory_mb,
                window_title=item.window_title,
                extra_jvm_args=item.extra_jvm_args,
            )
        )
        item.imported = True
        imported.append(item.version_id)
        if import_settings:
            settings = config.version_settings.get(item.version_id) or VersionSettings()
            if item.isolation:
                settings.isolation = item.isolation
            if item.extra_jvm_args:
                settings.extra_jvm_args = item.extra_jvm_args
            if item.extra_game_args:
                settings.extra_game_args = item.extra_game_args
            if item.window_title:
                settings.window_title = item.window_title
            if item.memory_mb:
                settings.memory_mb = item.memory_mb
            config.version_settings[item.version_id] = settings

    if import_global:
        for key, raw in profile.settings.items():
            low = key.lower()
            text = str(raw or "").strip()
            if not text:
                continue
            if any(hint in low for hint in _JAVA_KEY_HINTS) and text.lower().endswith(
                ("java.exe", "javaw.exe")
            ):
                config.java_path = text
            elif any(hint in low for hint in _VERSION_KEY_HINTS):
                number = _int(text)
                if 256 <= number <= 262144:
                    config.memory_mb = number

    config.save()
    return {
        "imported": imported,
        "skipped": skipped,
        "settings": sum(1 for item in profile.versions if item.imported),
    }
