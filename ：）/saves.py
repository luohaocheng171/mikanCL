"""存档管理：列出世界、打包备份、恢复与启动前自动备份。

备份目录结构：<backup_root>/<版本 ID>/<世界名>-<时间戳>.zip，
zip 内保持 <世界名>/... 层级，恢复时可整体解压到任意版本的 saves 目录。
"""

from __future__ import annotations

import os
import re
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .nbt import load_nbt_file

GAME_MODES = {
    0: "生存模式",
    1: "创造模式",
    2: "冒险模式",
    3: "旁观模式",
}


@dataclass
class SaveInfo:
    folder: str
    name: str
    last_played: float
    size: int
    game_mode: str
    version_name: str
    path: Path


@dataclass
class BackupInfo:
    path: Path
    world: str
    created: float
    size: int
    auto: bool


def saves_dir(game_dir) -> Path:
    return Path(game_dir) / "saves"


def _dir_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                continue
    return total


def _safe_name(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", name).strip(" .")
    return cleaned or "world"


def list_saves(game_dir) -> list[SaveInfo]:
    """列出 saves/ 下的世界，读取 level.dat 的显示名称、模式与最后游玩时间。"""
    root = saves_dir(game_dir)
    if not root.is_dir():
        return []
    result: list[SaveInfo] = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        level = entry / "level.dat"
        if not entry.is_dir() or not level.is_file():
            continue
        name = entry.name
        last_played = level.stat().st_mtime
        game_type = 0
        version_name = ""
        try:
            _root_name, data = load_nbt_file(level)
            payload = data.get("Data", {}) if isinstance(data, dict) else {}
            if isinstance(payload, dict):
                name = str(payload.get("LevelName") or name)
                played = payload.get("LastPlayed")
                if isinstance(played, (int, float)) and played > 0:
                    last_played = float(played) / 1000.0
                game_type = int(payload.get("GameType") or 0)
                version = payload.get("Version")
                if isinstance(version, dict):
                    version_name = str(version.get("Name") or "")
        except Exception:  # noqa: BLE001 - 单个存档损坏不影响整个列表
            pass
        result.append(
            SaveInfo(
                folder=entry.name,
                name=name,
                last_played=last_played,
                size=_dir_size(entry),
                game_mode=GAME_MODES.get(game_type, f"模式 {game_type}"),
                version_name=version_name,
                path=entry,
            )
        )
    return result


def backup_dir_for(backup_root, version_id: str) -> Path:
    path = Path(backup_root) / _safe_name(version_id or "unknown")
    path.mkdir(parents=True, exist_ok=True)
    return path


def backup_save(
    game_dir,
    folder: str,
    backup_root,
    version_id: str,
    *,
    auto: bool = False,
    log: Callable[[str], None] | None = None,
) -> Path | None:
    """把单个世界打包为 zip，返回备份文件路径；世界不存在时返回 None。"""
    return backup_world_path(
        saves_dir(game_dir) / folder,
        backup_root,
        version_id,
        auto=auto,
        log=log,
    )


def backup_world_path(
    world,
    backup_root,
    version_id: str,
    *,
    auto: bool = False,
    log: Callable[[str], None] | None = None,
) -> Path | None:
    """按完整路径备份任意世界（目录、Classic 单文件、server_level.dat）。"""
    world = Path(world)
    single = world.is_file()
    if single:
        folder = world.stem or "world"
    else:
        if not (
            (world / "level.dat").is_file()
            or (world / "server_level.dat").is_file()
            or any(world.glob("*.mine"))
        ):
            return None
        folder = world.name or "world"
    target_dir = backup_dir_for(backup_root, version_id)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    prefix = "auto-" if auto else ""
    target = target_dir / f"{prefix}{_safe_name(folder)}-{stamp}.zip"
    written = False
    try:
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            if single:
                zf.write(world, f"{_safe_name(folder)}/level.dat")
                written = True
            else:
                for root, _dirs, files in os.walk(world):
                    for name in files:
                        if name.lower() == "session.lock":
                            continue  # 游戏运行时无法读取的锁文件，不打包
                        file_path = Path(root) / name
                        try:
                            arcname = Path(folder) / file_path.relative_to(world)
                            zf.write(file_path, arcname.as_posix())
                            written = True
                        except OSError:
                            continue
    except OSError as exc:
        if log:
            log(f"[备份] 打包存档失败：{exc}")
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        return None
    if not written:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        return None
    if log:
        log(f"[备份] 已备份存档「{folder}」→ {target}")
    return target


def backup_all_saves(
    game_dir,
    backup_root,
    version_id: str,
    *,
    log: Callable[[str], None] | None = None,
) -> list[Path]:
    saved: list[Path] = []
    for info in list_saves(game_dir):
        path = backup_save(
            game_dir, info.folder, backup_root, version_id, log=log
        )
        if path is not None:
            saved.append(path)
    return saved


def _prune_auto(version_dir: Path, keep: int = 20) -> None:
    if keep <= 0:
        return
    items = sorted(
        (p for p in version_dir.glob("auto-*.zip") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in items[keep:]:
        try:
            old.unlink()
        except OSError:
            pass


def auto_backup_saves(
    game_dir,
    backup_root,
    version_id: str,
    *,
    keep: int = 20,
    log: Callable[[str], None] | None = None,
) -> list[Path]:
    """启动前自动备份全部存档；只保留最近 keep 份自动备份。"""
    worlds = list_saves(game_dir)
    if not worlds:
        return []
    saved: list[Path] = []
    for info in worlds:
        # 同一世界一分钟内只自动备份一次，避免连续启动刷屏
        version_dir = backup_dir_for(backup_root, version_id)
        recent = sorted(version_dir.glob(f"auto-{_safe_name(info.folder)}-*.zip"))
        if recent and time.time() - recent[-1].stat().st_mtime < 60:
            continue
        path = backup_save(
            game_dir, info.folder, backup_root, version_id, auto=True, log=log
        )
        if path is not None:
            saved.append(path)
    _prune_auto(backup_dir_for(backup_root, version_id), keep)
    if log and saved:
        log(f"[备份] 启动前自动备份完成，共 {len(saved)} 个存档。")
    return saved


def list_backups(backup_root, version_id: str = "") -> list[BackupInfo]:
    """列出备份（可按版本过滤），按时间倒序。"""
    root = Path(backup_root)
    if not root.is_dir():
        return []
    folders = [root / _safe_name(version_id)] if version_id else [
        p for p in root.iterdir() if p.is_dir()
    ]
    result: list[BackupInfo] = []
    for folder in folders:
        if not folder.is_dir():
            continue
        for path in folder.glob("*.zip"):
            if not path.is_file():
                continue
            name = path.stem
            auto = name.startswith("auto-")
            if auto:
                name = name[5:]
            world = re.sub(r"-\d{8}-\d{6}$", "", name)
            try:
                created = path.stat().st_mtime
                size = path.stat().st_size
            except OSError:
                continue
            result.append(BackupInfo(path, world, created, size, auto))
    result.sort(key=lambda item: item.created, reverse=True)
    return result


def _zip_roots(zf: zipfile.ZipFile) -> list[str]:
    roots = set()
    for name in zf.namelist():
        head = name.split("/", 1)[0]
        if head and not head.startswith("__MACOSX"):
            roots.add(head)
    return sorted(roots)


def restore_backup(
    backup_path,
    game_dir,
    *,
    overwrite: bool = True,
    log: Callable[[str], None] | None = None,
) -> str:
    """把备份恢复到指定版本的 saves 目录，返回恢复的世界文件夹名。"""
    backup_path = Path(backup_path)
    if not backup_path.is_file():
        raise FileNotFoundError(backup_path)
    target_root = saves_dir(game_dir)
    target_root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(backup_path, "r") as zf:
        roots = _zip_roots(zf)
        if not roots:
            raise ValueError("备份压缩包为空")
        world = _safe_name(roots[0])
        target = target_root / world
        if target.exists():
            if not overwrite:
                raise FileExistsError(target)
            import shutil

            shutil.rmtree(target, ignore_errors=True)
        for member in zf.infolist():
            name = member.filename
            if name.lower().endswith("session.lock"):
                continue
            parts = Path(name).parts
            if not parts or parts[0] != roots[0]:
                continue  # 只恢复第一层世界目录，忽略多余的包装目录
            relative = Path(*parts[1:]) if len(parts) > 1 else Path()
            if relative.parts and (relative.parts[0] in ("..",) or ":" in relative.parts[0]):
                continue
            destination = target / relative if relative.parts else target
            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member, "r") as src, open(destination, "wb") as dst:
                dst.write(src.read())
    if log:
        log(f"[备份] 已恢复存档「{world}」到 {target_root}")
    return world


def delete_world(game_dir, folder: str) -> bool:
    """删除一个世界（用于损坏存档清理）。"""
    import shutil

    target = saves_dir(game_dir) / folder
    if not target.is_dir():
        return False
    shutil.rmtree(target, ignore_errors=True)
    return True
