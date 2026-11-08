"""皮肤库：记录用户导入过的皮肤，支持在侧栏快速切换。

原实现每次导入都覆盖 ``data/skins/<玩家名>.png``，旧皮肤顺手就丢了。
这里把每份皮肤另存一份到 ``data/skins/library/``，用 ``library.json``
记录名称、手臂模型与最近使用时间；内容相同的文件只保留一条记录。
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import DATA_DIR

SKIN_DIR = DATA_DIR / "skins"
LIBRARY_DIR = SKIN_DIR / "library"
INDEX_FILE = SKIN_DIR / "library.json"

# 皮肤库上限：只留最近使用的若干份，避免长期使用后无限增长
MAX_ENTRIES = 60


@dataclass
class SkinEntry:
    path: str
    name: str = ""
    model: str = "classic"
    digest: str = ""
    added: float = 0.0
    used: float = 0.0


def _load() -> list[SkinEntry]:
    try:
        data = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    entries: list[SkinEntry] = []
    if not isinstance(data, list):
        return entries
    for item in data:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "")
        if not path:
            continue
        entries.append(
            SkinEntry(
                path=path,
                name=str(item.get("name") or ""),
                model=str(item.get("model") or "classic"),
                digest=str(item.get("digest") or ""),
                added=float(item.get("added") or 0.0),
                used=float(item.get("used") or 0.0),
            )
        )
    return entries


def _save(entries: list[SkinEntry]) -> None:
    try:
        SKIN_DIR.mkdir(parents=True, exist_ok=True)
        tmp = INDEX_FILE.with_suffix(".tmp")
        tmp.write_text(
            json.dumps([asdict(entry) for entry in entries], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(INDEX_FILE)
    except OSError:
        pass


def _digest(path: Path) -> str:
    try:
        return hashlib.sha1(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def entries(limit: int = 0) -> list[SkinEntry]:
    """按最近使用时间倒序返回仍然存在的皮肤。"""
    items = [entry for entry in _load() if Path(entry.path).exists()]
    items.sort(key=lambda entry: entry.used or entry.added, reverse=True)
    return items[:limit] if limit > 0 else items


def remember(source: str | Path, model: str = "classic", name: str = "") -> SkinEntry:
    """把皮肤复制进皮肤库；内容相同则复用已有记录。"""
    src = Path(source)
    digest = _digest(src)
    items = _load()
    if digest:
        for entry in items:
            if entry.digest == digest and Path(entry.path).exists():
                entry.used = time.time()
                entry.model = model or entry.model
                _save(items)
                return entry
    try:
        LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
        target = LIBRARY_DIR / f"{int(time.time() * 1000)}_{src.name}"
        shutil.copy2(src, target)
    except OSError:
        # 复制失败时不阻断导入，至少让当前会话能用原始路径
        return SkinEntry(
            path=str(src),
            name=name or src.stem,
            model=model,
            added=time.time(),
            used=time.time(),
        )
    entry = SkinEntry(
        path=str(target),
        name=name or src.stem,
        model=model,
        digest=digest,
        added=time.time(),
        used=time.time(),
    )
    items.append(entry)
    if len(items) > MAX_ENTRIES:
        keep = sorted(items, key=lambda item: item.used or item.added, reverse=True)[
            :MAX_ENTRIES
        ]
        removed = [item for item in items if item not in keep]
        for item in removed:
            try:
                Path(item.path).unlink()
            except OSError:
                pass
        items = keep
    _save(items)
    return entry


def touch(entry: SkinEntry) -> None:
    """标记为最近使用。"""
    items = _load()
    for item in items:
        if item.path == entry.path:
            item.used = time.time()
            break
    else:
        return
    _save(items)
