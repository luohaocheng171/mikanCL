"""创世神面板的写入安全层：进程锁、严格备份、事务提交与回滚。

这里不承诺多文件绝对原子或断电无损；保证的是：
- 同一时间只有一个进程能编辑同一个世界；
- 任一源文件读不到就不备份、不写入；
- 所有新内容先在内存与同目录 staging 中准备完毕；
- 替换失败时按 journal 回滚已替换的文件。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

_LOCK_NAME = "session.lock"


class LockError(Exception):
    """世界正被占用，或锁文件状态未知。"""


class WorldLock:
    """独占 ``session.lock``。

    Windows 使用 ``msvcrt.locking``（对应 LockFileEx 的排他锁），
    其它平台使用 ``fcntl.flock``；都是非阻塞锁，冲突立即失败。
    """

    def __init__(self, world_dir):
        self.world = Path(world_dir)
        self.path = self.world / _LOCK_NAME
        self._handle = None
        self._locked = False

    def acquire(self) -> "WorldLock":
        if self._locked:
            return self
        if not self.world.is_dir():
            raise LockError(f"世界目录不存在：{self.world}")
        try:
            self.path.touch(exist_ok=True)
            handle = open(self.path, "r+b")
        except OSError as exc:
            raise LockError(f"无法打开 session.lock：{exc}") from exc
        try:
            if handle.seek(0, os.SEEK_END) == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise LockError(
                "存档正被游戏或另一个编辑进程占用，请先完全关闭游戏再试"
            ) from exc
        self._handle = handle
        self._locked = True
        return self

    def release(self) -> None:
        handle, self._handle = self._handle, None
        if handle is None:
            return
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            try:
                handle.close()
            except OSError:
                pass
            self._locked = False

    def __enter__(self) -> "WorldLock":
        return self.acquire()

    def __exit__(self, *_exc) -> None:
        self.release()

    @property
    def held(self) -> bool:
        return self._locked


@dataclass
class BackupInfo:
    archive: Path
    hashes: dict[str, str] = field(default_factory=dict)
    files: int = 0
    created: float = 0.0


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def strict_backup(world, backup_root, version_id: str = "") -> BackupInfo:
    """把整个世界打包为 zip，任何文件读取失败都会中止。

    与 ``saves.backup_world_path`` 的宽松模式不同，这里不允许跳过文件：
    备份不完整就不能进入写入流程。
    """
    world = Path(world)
    if not world.is_dir():
        raise OSError(f"世界目录不存在：{world}")
    root = Path(backup_root) / _safe(version_id or "unknown")
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = root / f"{_safe(world.name)}-{stamp}-creator.zip"

    members: list[tuple[str, bytes]] = []
    for path in sorted(world.rglob("*")):
        if not path.is_file():
            continue
        if path.name.lower() == _LOCK_NAME:
            continue
        arcname = f"{world.name}/{path.relative_to(world).as_posix()}"
        members.append((arcname, path.read_bytes()))

    if not members:
        raise OSError("世界目录为空，无法备份")

    hashes = {name: _sha256(data) for name, data in members}
    tmp = archive.with_suffix(".zip.part")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for name, data in members:
            zf.writestr(name, data)
    with zipfile.ZipFile(tmp) as zf:
        bad = zf.testzip()
        if bad is not None:
            tmp.unlink(missing_ok=True)
            raise OSError(f"备份校验失败，损坏成员：{bad}")
        if set(zf.namelist()) != set(hashes):
            tmp.unlink(missing_ok=True)
            raise OSError("备份成员集合与源文件不一致")
    tmp.replace(archive)
    (archive.with_suffix(".zip.json")).write_text(
        json.dumps({"archive": archive.name, "hashes": hashes}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return BackupInfo(archive=archive, hashes=hashes, files=len(members), created=time.time())


def _safe(name: str) -> str:
    cleaned = "".join(ch for ch in str(name) if ch not in '<>:"/\\|?*').strip(" .")
    return cleaned or "world"


class FileTransaction:
    """同目录 staging → 逐文件替换 → 失败按 journal 回滚。"""

    def __init__(self, root, journal_dir=None):
        self.root = Path(root)
        self.journal_dir = Path(journal_dir) if journal_dir else self.root / ".mikancl-tx"
        self._entries: list[dict] = []

    def add(self, path, data: bytes) -> None:
        target = Path(path)
        self._entries.append(
            {
                "target": target,
                "data": bytes(data),
                "backup": target.with_name(target.name + ".creator-bak"),
                "staged": target.with_name(target.name + ".creator-new"),
                "existed": target.exists(),
                "hash": _sha256(bytes(data)),
            }
        )

    def commit(self) -> None:
        if not self._entries:
            return
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        journal = self.journal_dir / f"tx-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.json"
        payload = {
            "status": "pending",
            "started": time.time(),
            "entries": [
                {
                    "target": str(entry["target"]),
                    "backup": str(entry["backup"]),
                    "hash": entry["hash"],
                    "existed": entry["existed"],
                }
                for entry in self._entries
            ],
        }
        journal.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        replaced: list[dict] = []
        try:
            for entry in self._entries:
                target: Path = entry["target"]
                target.parent.mkdir(parents=True, exist_ok=True)
                if entry["existed"]:
                    shutil.copy2(target, entry["backup"])
                entry["staged"].write_bytes(entry["data"])
                with open(entry["staged"], "rb+") as handle:
                    os.fsync(handle.fileno())
            for entry in self._entries:
                os.replace(entry["staged"], entry["target"])
                replaced.append(entry)
        except OSError:
            rolled_back = True
            for entry in reversed(replaced):
                try:
                    if entry["existed"]:
                        os.replace(entry["backup"], entry["target"])
                    else:
                        entry["target"].unlink(missing_ok=True)
                except OSError:
                    rolled_back = False
            for entry in self._entries:
                if entry not in replaced:
                    try:
                        entry["staged"].unlink(missing_ok=True)
                    except OSError:
                        pass
            payload["status"] = "failed"
            payload["rolled_back"] = rolled_back
            payload["finished"] = time.time()
            journal.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            raise

        for entry in self._entries:
            try:
                entry["backup"].unlink(missing_ok=True)
            except OSError:
                pass
        journal.unlink(missing_ok=True)
        _rmdir_quiet(self.journal_dir)


def _rmdir_quiet(path: Path) -> None:
    try:
        path.rmdir()
    except OSError:
        pass


def pending_transactions(world) -> list[Path]:
    """列出未完成事务，供下次打开时提示恢复。"""
    folder = Path(world) / ".mikancl-tx"
    if not folder.is_dir():
        return []
    return sorted(folder.glob("tx-*.json"))


def increase_file_lock(path) -> None:
    """兼容旧实现：把 session.lock 视为被占用时抛出 LockError。"""
    world = Path(path).parent if Path(path).name == _LOCK_NAME else Path(path)
    WorldLock(world).acquire().release()


def open_in_explorer(path) -> None:
    """在文件管理器中定位备份文件（仅 Windows 有实际行为）。"""
    target = Path(path)
    if os.name != "nt" or not target.exists():
        return
    try:
        subprocess.Popen(["explorer", "/select,", str(target)])
    except OSError:
        pass
