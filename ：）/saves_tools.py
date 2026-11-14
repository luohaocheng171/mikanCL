"""存档编辑器与版本转换器：直接读写 level.dat，并可按目标版本改写版本标记。

设计原则：
- 所有写入都先备份原始 level.dat（同目录 ``level.dat.<时间戳>.bak``，最多保留 5 份）；
- 只处理文档中明确列出的常用字段，未知字段原样保留；
- 转换只改写 ``DataVersion`` 与 ``Data.Version``，不会做区块级数据升级，
  跨大版本仍可能失败，界面上必须提示用户先整份备份。
"""

from __future__ import annotations

import os
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .nbt import NBTError, load_nbt_file, save_nbt_file
from .saves import _safe_name, saves_dir

GAME_MODE_LABELS = {
    0: "生存模式",
    1: "创造模式",
    2: "冒险模式",
    3: "旁观模式",
}
DIFFICULTY_LABELS = {
    0: "和平",
    1: "简单",
    2: "普通",
    3: "困难",
}
WEATHER_LABELS = {
    "clear": "晴天",
    "rain": "下雨",
    "thunder": "雷雨",
}

# 常见正式版 → (DataVersion, 协议号)。仅用于「按目标版本改写标记」，
# 数值取自 Minecraft Wiki 的版本表；未知版本可手动填写 DataVersion。
VERSION_TABLE: tuple[dict[str, Any], ...] = (
    {"name": "1.8.9", "data_version": 0, "protocol": 47},
    {"name": "1.9.4", "data_version": 184, "protocol": 110},
    {"name": "1.10.2", "data_version": 512, "protocol": 210},
    {"name": "1.11.2", "data_version": 922, "protocol": 316},
    {"name": "1.12.2", "data_version": 1343, "protocol": 340},
    {"name": "1.13.2", "data_version": 1631, "protocol": 404},
    {"name": "1.14.4", "data_version": 1976, "protocol": 498},
    {"name": "1.15.2", "data_version": 2230, "protocol": 578},
    {"name": "1.16.5", "data_version": 2586, "protocol": 754},
    {"name": "1.17.1", "data_version": 2730, "protocol": 756},
    {"name": "1.18.2", "data_version": 2975, "protocol": 758},
    {"name": "1.19.2", "data_version": 3120, "protocol": 760},
    {"name": "1.19.4", "data_version": 3337, "protocol": 762},
    {"name": "1.20.1", "data_version": 3465, "protocol": 763},
    {"name": "1.20.4", "data_version": 3700, "protocol": 765},
    {"name": "1.20.6", "data_version": 3839, "protocol": 766},
    {"name": "1.21", "data_version": 3953, "protocol": 767},
    {"name": "1.21.1", "data_version": 3955, "protocol": 767},
    {"name": "1.21.4", "data_version": 4189, "protocol": 769},
)

TARGET_BACKUP_KEEP = 5


class SaveToolError(Exception):
    """存档编辑 / 转换失败。"""


@dataclass
class WorldMeta:
    folder: str
    path: Path
    level_path: Path
    name: str = ""
    version_name: str = ""
    data_version: int = 0
    game_type: int = 0
    difficulty: int = 1
    hardcore: bool = False
    allow_commands: bool = False
    day_time: int = 0
    total_time: int = 0
    weather: str = "clear"
    spawn: tuple[int, int, int] = (0, 64, 0)
    game_rules: dict[str, str] = field(default_factory=dict)
    seed: int = 0

    @property
    def game_mode_text(self) -> str:
        return GAME_MODE_LABELS.get(self.game_type, f"模式 {self.game_type}")

    @property
    def difficulty_text(self) -> str:
        return DIFFICULTY_LABELS.get(self.difficulty, f"难度 {self.difficulty}")


def _data(payload: dict) -> dict:
    data = payload.get("Data")
    if not isinstance(data, dict):
        raise SaveToolError("level.dat 缺少 Data 标签，可能不是有效的存档")
    return data


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _weather_of(data: dict) -> str:
    if _to_int(data.get("thundering")):
        return "thunder"
    if _to_int(data.get("raining")):
        return "rain"
    return "clear"


def _version_name_of(data: dict) -> str:
    version = data.get("Version")
    if isinstance(version, dict):
        return str(version.get("Name") or "")
    return ""


def read_meta(world_dir) -> WorldMeta:
    """读取世界元信息；世界或 level.dat 无效时抛出 SaveToolError。"""
    world = Path(world_dir)
    level = world / "level.dat"
    if not level.is_file():
        raise SaveToolError(f"找不到 {level}，请确认这是有效的世界目录")
    try:
        _root_name, payload = load_nbt_file(level)
    except (NBTError, OSError) as exc:
        raise SaveToolError(f"读取 level.dat 失败：{exc}") from exc
    data = _data(payload)
    rules = data.get("GameRules")
    game_rules = (
        {str(k): str(v) for k, v in rules.items()} if isinstance(rules, dict) else {}
    )
    spawn = (
        _to_int(data.get("SpawnX")),
        _to_int(data.get("SpawnY")),
        _to_int(data.get("SpawnZ")),
    )
    return WorldMeta(
        folder=world.name,
        path=world,
        level_path=level,
        name=str(data.get("LevelName") or world.name),
        version_name=_version_name_of(data),
        data_version=_to_int(data.get("DataVersion")),
        game_type=_to_int(data.get("GameType")),
        difficulty=_to_int(data.get("Difficulty")),
        hardcore=bool(_to_int(data.get("hardcore"))),
        allow_commands=bool(_to_int(data.get("allowCommands"))),
        day_time=_to_int(data.get("DayTime")),
        total_time=_to_int(data.get("Time")),
        weather=_weather_of(data),
        spawn=spawn,
        game_rules=game_rules,
        seed=_to_int(data.get("RandomSeed")),
    )


def _backup_level(level: Path) -> Path | None:
    """备份 level.dat 到同目录 level.dat.<时间戳>.bak，并清理过旧备份。"""
    if not level.is_file():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = level.with_name(f"{level.name}.{stamp}.bak")
    try:
        shutil.copy2(level, target)
    except OSError as exc:
        raise SaveToolError(f"备份 level.dat 失败：{exc}") from exc
    backups = sorted(
        level.parent.glob(f"{level.name}.*.bak"),
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
        reverse=True,
    )
    for old in backups[TARGET_BACKUP_KEEP:]:
        try:
            old.unlink()
        except OSError:
            pass
    return target


def apply_edits(world_dir, changes: dict[str, Any]) -> WorldMeta:
    """按 changes 修改 level.dat 并写回，返回修改后的元信息。

    支持的键：name / game_type / difficulty / hardcore / allow_commands /
    day_time / time / weather / spawn / game_rules。
    未提供的键保持不变。
    """
    world = Path(world_dir)
    level = world / "level.dat"
    if not level.is_file():
        raise SaveToolError(f"找不到 {level}")
    try:
        root_name, payload = load_nbt_file(level)
    except (NBTError, OSError) as exc:
        raise SaveToolError(f"读取 level.dat 失败：{exc}") from exc
    data = _data(payload)

    if "name" in changes:
        name = str(changes.get("name") or "").strip()
        if not name:
            raise SaveToolError("世界名称不能为空")
        data["LevelName"] = name[:64]
    if "game_type" in changes:
        mode = _to_int(changes.get("game_type"))
        if mode not in GAME_MODE_LABELS:
            raise SaveToolError("游戏模式只能是 0-3")
        data["GameType"] = mode
        data["playerGameType"] = mode
    if "difficulty" in changes:
        difficulty = _to_int(changes.get("difficulty"))
        if difficulty not in DIFFICULTY_LABELS:
            raise SaveToolError("难度只能是 0-3")
        data["Difficulty"] = difficulty
    if "hardcore" in changes:
        data["hardcore"] = 1 if changes.get("hardcore") else 0
    if "allow_commands" in changes:
        data["allowCommands"] = 1 if changes.get("allow_commands") else 0
    if "day_time" in changes:
        data["DayTime"] = max(0, _to_int(changes.get("day_time")))
    if "time" in changes:
        data["Time"] = max(0, _to_int(changes.get("time")))
    if "weather" in changes:
        weather = str(changes.get("weather") or "clear")
        if weather not in WEATHER_LABELS:
            raise SaveToolError("天气只能是 clear / rain / thunder")
        data["raining"] = 0 if weather == "clear" else 1
        data["thundering"] = 1 if weather == "thunder" else 0
        if weather == "clear":
            data["rainTime"] = 6000
            data["thunderTime"] = 12000
    if "spawn" in changes:
        spawn = changes.get("spawn") or ()
        if len(spawn) != 3:
            raise SaveToolError("出生点需要 3 个坐标")
        data["SpawnX"] = _to_int(spawn[0])
        data["SpawnY"] = _to_int(spawn[1])
        data["SpawnZ"] = _to_int(spawn[2])
    if "game_rules" in changes:
        rules = data.get("GameRules")
        if not isinstance(rules, dict):
            rules = {}
            data["GameRules"] = rules
        for key, value in dict(changes.get("game_rules") or {}).items():
            rules[str(key)] = str(value)

    backup = _backup_level(level)
    try:
        save_nbt_file(level, root_name, payload)
    except (NBTError, OSError) as exc:
        if backup is not None and backup.is_file():
            try:
                shutil.copy2(backup, level)
            except OSError:
                pass
        raise SaveToolError(f"写入 level.dat 失败：{exc}") from exc
    return read_meta(world)


def resolve_target(target: str) -> dict[str, Any]:
    """把版本号（如 1.20.1-forge-47.2.0）解析为版本表条目。"""
    text = str(target or "").strip()
    match = re.match(r"(\d+\.\d+(?:\.\d+)?)", text)
    if not match:
        return {}
    version = match.group(1)
    exact = next((item for item in VERSION_TABLE if item["name"] == version), None)
    if exact is not None:
        return dict(exact)
    prefix = version.rsplit(".", 1)[0] if version.count(".") >= 2 else version
    candidates = [
        item
        for item in VERSION_TABLE
        if item["name"] == prefix or item["name"].startswith(prefix + ".")
    ]
    return dict(candidates[-1]) if candidates else {"name": version}


def convert_world(
    world_dir,
    target_version: str,
    *,
    data_version: int | None = None,
    protocol: int | None = None,
    snapshot: bool = False,
) -> dict[str, Any]:
    """把存档的版本标记改写为目标版本，返回 {backup, world, before, after}。

    ``data_version=None`` 表示按目标版本自动查找；显式传 0 表示清除
    DataVersion（仅适用于 1.9 以前的旧格式）。
    """
    world = Path(world_dir)
    level = world / "level.dat"
    if not level.is_file():
        raise SaveToolError(f"找不到 {level}")
    info = resolve_target(target_version)
    if data_version is None:
        resolved = int(info.get("data_version") or 0)
        if resolved <= 0:
            raise SaveToolError(
                "无法自动确定目标版本的 DataVersion，请手动填写（例如 1.20.1 为 3465）"
            )
        target_dv = resolved
    else:
        target_dv = int(data_version)
    target_protocol = int(protocol if protocol is not None else info.get("protocol", 0) or 0)
    target_name = str(info.get("name") or target_version or "").strip()
    if not target_name:
        raise SaveToolError("请填写目标版本号，例如 1.20.1")
    if target_dv < 0:
        raise SaveToolError("DataVersion 不能为负数")

    try:
        root_name, payload = load_nbt_file(level)
    except (NBTError, OSError) as exc:
        raise SaveToolError(f"读取 level.dat 失败：{exc}") from exc
    data = _data(payload)
    before = {
        "version_name": _version_name_of(data),
        "data_version": _to_int(data.get("DataVersion")),
    }
    if target_dv > 0:
        data["DataVersion"] = target_dv
        version = data.get("Version")
        if not isinstance(version, dict):
            version = {}
            data["Version"] = version
        version["Name"] = target_name
        version["Snapshot"] = 1 if snapshot else 0
        version["Series"] = "main"
        if target_protocol > 0:
            version["Id"] = target_protocol
        elif "Id" not in version:
            version["Id"] = 0
    else:
        # 1.9 之前没有 DataVersion / Version 标签
        data.pop("DataVersion", None)
        data.pop("Version", None)

    backup = _backup_level(level)
    try:
        save_nbt_file(level, root_name, payload)
    except (NBTError, OSError) as exc:
        if backup is not None and backup.is_file():
            try:
                shutil.copy2(backup, level)
            except OSError:
                pass
        raise SaveToolError(f"写入 level.dat 失败：{exc}") from exc
    return {
        "world": world,
        "backup": backup,
        "before": before,
        "after": {"version_name": target_name, "data_version": target_dv},
    }


# ---------------------------------------------------------------------------
# 存档导入 / 导出
# ---------------------------------------------------------------------------
def import_world_zip(archive, game_dir, *, overwrite: bool = False) -> str:
    """把世界 zip 导入到指定版本的 saves 目录，返回世界文件夹名。"""
    source = Path(archive)
    if not source.is_file():
        raise SaveToolError(f"找不到压缩包：{source}")
    target_root = saves_dir(game_dir)
    target_root.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(source, "r") as zf:
            roots = {
                name.split("/", 1)[0]
                for name in zf.namelist()
                if name and not name.startswith("__MACOSX")
            }
            world_root = ""
            if len(roots) == 1:
                candidate = next(iter(roots))
                if candidate.endswith("level.dat"):
                    world_root = ""
                else:
                    world_root = candidate
            member_names = zf.namelist()
            if world_root:
                has_level = f"{world_root}/level.dat" in member_names
            else:
                has_level = "level.dat" in member_names
            if not has_level:
                raise SaveToolError("压缩包里没有找到 level.dat，不是有效的世界存档")
            folder = _safe_name(world_root or source.stem)
            target = target_root / folder
            if target.exists():
                if not overwrite:
                    raise SaveToolError(f"目标世界里已存在同名存档「{folder}」")
                shutil.rmtree(target, ignore_errors=True)
            target.mkdir(parents=True, exist_ok=True)
            prefix = f"{world_root}/" if world_root else ""
            for member in zf.infolist():
                name = member.filename
                if not name.startswith(prefix):
                    continue
                relative = name[len(prefix):]
                if not relative or relative.endswith("/"):
                    continue
                parts = Path(relative).parts
                if not parts or ".." in parts or ":" in parts[0]:
                    continue
                if parts[-1].lower() == "session.lock":
                    continue
                destination = target.joinpath(*parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member, "r") as src, open(destination, "wb") as dst:
                    dst.write(src.read())
    except zipfile.BadZipFile as exc:
        raise SaveToolError(f"压缩包损坏：{exc}") from exc
    except OSError as exc:
        raise SaveToolError(f"导入失败：{exc}") from exc
    return folder


def export_world_zip(world_dir, destination) -> Path:
    """把世界目录打包为 zip（跳过 session.lock）。"""
    world = Path(world_dir)
    if not world.is_dir():
        raise SaveToolError(f"找不到世界目录：{world}")
    target = Path(destination)
    if target.suffix.lower() != ".zip":
        target = target.with_suffix(".zip")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for root, _dirs, files in os.walk(world):
                for name in files:
                    if name.lower() == "session.lock":
                        continue
                    file_path = Path(root) / name
                    try:
                        arcname = Path(world.name) / file_path.relative_to(world)
                        zf.write(file_path, arcname.as_posix())
                    except OSError:
                        continue
    except OSError as exc:
        raise SaveToolError(f"导出失败：{exc}") from exc
    return target


def copy_world(world_dir, new_name: str = "") -> Path:
    """复制一个世界目录（跳过 session.lock），自动避开重名。"""
    source = Path(world_dir)
    if not (source / "level.dat").is_file():
        raise SaveToolError(f"找不到世界存档：{source}")
    base = _safe_name(new_name or f"{source.name} 副本")
    target = source.parent / base
    index = 2
    while target.exists():
        target = source.parent / f"{base} ({index})"
        index += 1
    try:
        shutil.copytree(source, target, ignore=shutil.ignore_patterns("session.lock"))
    except OSError as exc:
        raise SaveToolError(f"复制存档失败：{exc}") from exc
    return target


def list_worlds(game_dir) -> list[WorldMeta]:
    """列出某个游戏目录下的全部世界（损坏的存档会被跳过）。"""
    root = saves_dir(game_dir)
    if not root.is_dir():
        return []
    worlds: list[WorldMeta] = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_dir() or not (entry / "level.dat").is_file():
            continue
        try:
            worlds.append(read_meta(entry))
        except SaveToolError:
            continue
    return worlds


def prune_backups(world_dir, keep: int = TARGET_BACKUP_KEEP) -> None:
    """手动清理某个世界目录里的 level.dat 备份。"""
    world = Path(world_dir)
    backups = sorted(
        world.glob("level.dat.*.bak"),
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
        reverse=True,
    )
    for old in backups[max(1, int(keep)):]:
        try:
            old.unlink()
        except OSError:
            pass
