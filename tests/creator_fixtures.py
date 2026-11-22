"""创世神面板测试用的合成存档夹具。"""

from __future__ import annotations

import gzip
import json
import struct
from pathlib import Path

from mc_launcher.nbt import (
    TAG_BYTE,
    TAG_COMPOUND,
    TAG_DOUBLE,
    TAG_FLOAT,
    TAG_INT,
    TAG_LIST,
    TAG_LONG,
    TAG_SHORT,
    TAG_STRING,
    write_nbt_typed,
)


def _c(**kwargs):
    """把 {name: node} 组装成 Compound 节点。"""
    return (TAG_COMPOUND, kwargs)


def _list(element_tag: int, items):
    return (TAG_LIST, (element_tag, list(items)))


def build_level_dat(*, data_version: int = 3465, version_name: str = "1.20.1") -> bytes:
    """生成一个最小但结构完整的 level.dat（Anvil）。"""
    data = _c(
        DataVersion=(TAG_INT, int(data_version)),
        Version=_c(
            Name=(TAG_STRING, version_name),
            Snapshot=(TAG_BYTE, 0),
        ),
        LevelName=(TAG_STRING, "Test World"),
        GameType=(TAG_INT, 1),
        Difficulty=(TAG_BYTE, 2),
        hardcore=(TAG_BYTE, 0),
        allowCommands=(TAG_BYTE, 1),
        Time=(TAG_LONG, 12000),
        DayTime=(TAG_LONG, 6000),
        raining=(TAG_BYTE, 0),
        thundering=(TAG_BYTE, 0),
        rainTime=(TAG_INT, 12000),
        thunderTime=(TAG_INT, 6000),
        SpawnX=(TAG_INT, 0),
        SpawnY=(TAG_INT, 64),
        SpawnZ=(TAG_INT, 0),
        RandomSeed=(TAG_LONG, 12345),
        GameRules=_c(doFireTick=(TAG_STRING, "true"), randomTickSpeed=(TAG_STRING, "3")),
        WorldBorder=_c(
            CenterX=(TAG_DOUBLE, 0.0),
            CenterZ=(TAG_DOUBLE, 0.0),
            Size=(TAG_DOUBLE, 59999968.0),
            DamagePerBlock=(TAG_DOUBLE, 0.2),
            WarningBlocks=(TAG_INT, 5),
        ),
        Player=_c(
            Pos=_list(TAG_DOUBLE, [(TAG_DOUBLE, 0.0), (TAG_DOUBLE, 64.0), (TAG_DOUBLE, 0.0)]),
            Health=(TAG_FLOAT, 20.0),
            foodSaturationLevel=(TAG_FLOAT, 5.0),
            XpLevel=(TAG_INT, 0),
            playerGameType=(TAG_INT, 1),
            Dimension=(TAG_STRING, "minecraft:overworld"),
            Inventory=_list(TAG_COMPOUND, []),
            EnderItems=_list(TAG_COMPOUND, []),
            ActiveEffects=_list(TAG_COMPOUND, []),
            Attributes=_list(
                TAG_COMPOUND,
                [
                    (
                        TAG_COMPOUND,
                        {
                            "Name": (TAG_STRING, "generic.max_health"),
                            "Base": (TAG_DOUBLE, 20.0),
                        },
                    )
                ],
            ),
        ),
    )
    root = _c(Data=data)
    return gzip.compress(write_nbt_typed("", root))


def build_legacy_player(*, count: int = 1) -> bytes:
    """1.12 及以前的玩家结构：数字 ID、Count 为 Byte。"""
    root = _c(
        Health=(TAG_FLOAT, 20.0),
        XpLevel=(TAG_INT, 0),
        Inventory=_list(
            TAG_COMPOUND,
            [
                (
                    TAG_COMPOUND,
                    {
                        "id": (TAG_SHORT, 276),
                        "Slot": (TAG_BYTE, 0),
                        "Count": (TAG_BYTE, int(count)),
                        "Damage": (TAG_SHORT, 0),
                    },
                )
            ],
        ),
    )
    return gzip.compress(write_nbt_typed("", root))


def build_modern_player(*, count: int = 1, count_tag: int = TAG_INT) -> bytes:
    """1.20.5+ 玩家结构：命名空间 ID、小写 count。"""
    root = _c(
        Health=(TAG_FLOAT, 20.0),
        XpLevel=(TAG_INT, 0),
        Inventory=_list(
            TAG_COMPOUND,
            [
                (
                    TAG_COMPOUND,
                    {
                        "id": (TAG_STRING, "minecraft:diamond_sword"),
                        "Slot": (TAG_BYTE, 0),
                        "count": (count_tag, int(count)),
                    },
                )
            ],
        ),
    )
    return gzip.compress(write_nbt_typed("", root))


def make_world(root: Path, *, data_version: int = 3465, version_name: str = "1.20.1") -> Path:
    world = root / "saves" / "TestWorld"
    world.mkdir(parents=True)
    (world / "level.dat").write_bytes(
        build_level_dat(data_version=data_version, version_name=version_name)
    )
    (world / "session.lock").write_bytes(struct.pack(">q", 1234567890))
    (world / "playerdata").mkdir()
    return world


def make_region(path: Path, chunks: dict[tuple[int, int], bytes]) -> Path:
    """写出一个最小 region 文件；chunks 的值是已压缩的 chunk payload。"""
    header = bytearray(8192)
    body = bytearray()
    sector = 2
    for (cx, cz), payload in chunks.items():
        index = (cx & 31) + (cz & 31) * 32
        sectors = (len(payload) + 4095) // 4096
        offset = sector if sectors else 0
        header[index * 4 : index * 4 + 4] = struct.pack(">I", (offset << 8) | min(sectors, 255))
        header[4096 + index * 4 : 4096 + index * 4 + 4] = struct.pack(">I", 1)
        body.extend(struct.pack(">I", len(payload) + 1))
        body.extend(b"\x02")
        body.extend(payload)
        body.extend(b"\x00" * (sectors * 4096 - len(payload) - 5))
        sector += sectors
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(header) + bytes(body))
    return path


def write_ops(path: Path, entries) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = []
    for uuid, name, level, bypasses in entries:
        payload.append(
            {
                "uuid": uuid,
                "name": name,
                "level": level,
                "bypassesPlayerLimit": bypasses,
            }
        )
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
