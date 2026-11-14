"""Anvil region 读写：保留每个 slot 的原始 payload，只在必要时重写区块。

现有 ``world_convert._read_region`` 会跳过无法解析的记录，用它做全图替换
等于静默丢块。这里改为：
- 1024 个 slot 全部保留位置、时间戳、压缩类型与原始 payload；
- 未修改的区块原样写回，不重新压缩；
- 任何截断、重叠、未知压缩都整批失败。
"""

from __future__ import annotations

import gzip
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from .nbt import (
    TAG_BYTE,
    TAG_BYTE_ARRAY,
    TAG_COMPOUND,
    TAG_INT,
    TAG_LIST,
    TAG_LONG_ARRAY,
    TAG_STRING,
    parse_nbt_typed,
    write_nbt_typed,
)

SECTOR = 4096
SLOTS = 1024
AIR_NAMES = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}
COMPRESSION_GZIP = 1
COMPRESSION_ZLIB = 2
COMPRESSION_NONE = 3


class RegionError(Exception):
    """region 文件损坏或结构不受支持。"""


@dataclass
class Slot:
    x: int
    z: int
    timestamp: int
    compression: int
    payload: bytes
    dirty: bool = False

    @property
    def key(self) -> tuple[int, int]:
        return (self.x, self.z)


@dataclass
class RegionArchive:
    path: Path | None
    slots: list[Slot | None] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _decompress(compression: int, payload: bytes) -> bytes:
    if compression == COMPRESSION_GZIP:
        try:
            return gzip.decompress(payload)
        except (OSError, EOFError) as exc:
            raise RegionError(f"gzip 区块解压失败：{exc}") from exc
    if compression == COMPRESSION_ZLIB:
        try:
            return zlib.decompress(payload)
        except zlib.error as exc:
            raise RegionError(f"zlib 区块解压失败：{exc}") from exc
    if compression == COMPRESSION_NONE:
        return payload
    raise RegionError(f"未知的区块压缩类型：{compression}")


def _compress(compression: int, data: bytes) -> bytes:
    if compression == COMPRESSION_GZIP:
        return gzip.compress(data)
    if compression == COMPRESSION_ZLIB:
        return zlib.compress(data)
    if compression == COMPRESSION_NONE:
        return data
    raise RegionError(f"未知的区块压缩类型：{compression}")


def read_region(path) -> RegionArchive:
    target = Path(path)
    data = target.read_bytes()
    if len(data) < 2 * SECTOR:
        raise RegionError(f"{target.name} 不足 8KB，不是有效的 region 文件")
    slots: list[Slot | None] = [None] * SLOTS
    used: list[tuple[int, int]] = []
    for index in range(SLOTS):
        location = struct.unpack(">I", data[index * 4 : index * 4 + 4])[0]
        timestamp = struct.unpack(">I", data[SECTOR + index * 4 : SECTOR + index * 4 + 4])[0]
        if location == 0:
            continue
        offset = location >> 8
        sectors = location & 0xFF
        if sectors == 0 or offset < 2:
            raise RegionError(f"{target.name} 第 {index} 个 slot 的头部无效")
        start = offset * SECTOR
        end = start + sectors * SECTOR
        if start >= len(data) or end > len(data):
            raise RegionError(f"{target.name} 第 {index} 个 slot 超出文件范围（文件被截断）")
        for other_start, other_end in used:
            if start < other_end and other_start < end:
                raise RegionError(f"{target.name} 的 sector 区间重叠，文件可能已损坏")
        used.append((start, end))
        if sectors >= 255:
            raise RegionError(f"{target.name} 第 {index} 个 slot 超过 255 sector，无法安全编辑")
        length = struct.unpack(">I", data[start : start + 4])[0]
        if length < 1 or start + 4 + length > end:
            raise RegionError(f"{target.name} 第 {index} 个 slot 的长度字段无效")
        compression = data[start + 4]
        payload = data[start + 5 : start + 4 + length]
        cx, cz = index % 32, index // 32
        slots[index] = Slot(x=cx, z=cz, timestamp=timestamp, compression=compression, payload=payload)
    return RegionArchive(path=target, slots=slots)


def build_region_bytes(archive: RegionArchive, *, timestamps: dict | None = None) -> bytes:
    """把 archive 渲染为完整的 region 字节（不落盘），供事务层使用。"""
    header = bytearray(2 * SECTOR)
    body = bytearray()
    sector = 2
    stamps = timestamps or {}
    for index, slot in enumerate(archive.slots):
        if slot is None:
            continue
        payload = slot.payload
        total = len(payload) + 5
        sectors = (total + SECTOR - 1) // SECTOR
        if sectors > 255:
            raise RegionError(f"第 {index} 个区块超过 255 sector，无法写入")
        header[index * 4 : index * 4 + 4] = struct.pack(">I", (sector << 8) | sectors)
        stamp = int(stamps.get(index, slot.timestamp))
        header[SECTOR + index * 4 : SECTOR + index * 4 + 4] = struct.pack(">I", stamp)
        chunk = struct.pack(">I", len(payload) + 1) + bytes([slot.compression]) + payload
        chunk += b"\x00" * (sectors * SECTOR - len(chunk))
        body.extend(chunk)
        sector += sectors
    return bytes(header) + bytes(body)


def write_region(path, archive: RegionArchive, *, timestamps: dict | None = None, changes: dict | None = None) -> Path:
    """按 slot 顺序重新写出 region，未修改的区块保持原 payload。

    ``changes`` 参数仅为接口兼容保留；实际修改通过 ``archive.slots`` 中的
    ``payload`` 完成，这样未触碰的区块不会被重新编码。
    """
    target = Path(path)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_bytes(build_region_bytes(archive, timestamps=timestamps))
    tmp.replace(target)
    return target


# ----------------------------------------------------------------------
# 区块结构遍历
# ----------------------------------------------------------------------
def _root(path: Path, slot: Slot) -> tuple[int, object]:
    raw = _decompress(slot.compression, slot.payload)
    try:
        _name, node = parse_nbt_typed(raw)
        return node
    except Exception as exc:  # noqa: BLE001 - NBT 损坏统一转成 RegionError
        raise RegionError(f"{path.name} 区块解析失败：{exc}") from exc


def _sections(root) -> list:
    fields = root[1]
    if "sections" in fields and fields["sections"][0] == TAG_LIST:
        return fields["sections"][1][1]
    level = fields.get("Level")
    if level and level[0] == TAG_COMPOUND:
        sections = level[1].get("Sections")
        if sections and sections[0] == TAG_LIST:
            return sections[1][1]
    return []


def _data_version(root) -> int:
    node = root[1].get("DataVersion")
    return int(node[1]) if node and node[0] == TAG_INT else 0


def _section_kind(fields: dict) -> str:
    if "block_states" in fields:
        return "block_states"
    if "Palette" in fields:
        return "palette"
    if "Blocks" in fields:
        return "legacy"
    return "none"


def _palette_entries(fields: dict) -> list[str]:
    if "block_states" in fields:
        states = fields["block_states"][1]
        palette = states.get("palette")
    else:
        palette = fields.get("Palette")
    if not palette or palette[0] != TAG_LIST:
        return []
    names = []
    for entry in palette[1][1]:
        node = entry[1].get("Name") if entry[0] == TAG_COMPOUND else None
        names.append(str(node[1]) if node else "minecraft:air")
    return names


def _data_array(fields: dict):
    if "block_states" in fields:
        return fields["block_states"][1].get("data")
    return fields.get("BlockStates")


def _bits_for(palette_size: int) -> int:
    return max(4, max(0, palette_size - 1).bit_length())


def _unpack(longs, bits: int, count: int, spanning: bool) -> list[int]:
    mask = (1 << bits) - 1
    values: list[int] = []
    if not spanning:
        per = 64 // bits
        for raw in longs:
            word = int(raw) & 0xFFFFFFFFFFFFFFFF
            for index in range(per):
                if len(values) >= count:
                    break
                values.append((word >> (index * bits)) & mask)
        return values
    bitpos = 0
    for _ in range(count):
        index = bitpos >> 6
        offset = bitpos & 63
        word = int(longs[index]) & 0xFFFFFFFFFFFFFFFF
        if offset + bits <= 64:
            values.append((word >> offset) & mask)
        else:
            high = int(longs[index + 1]) & 0xFFFFFFFFFFFFFFFF
            values.append(((word >> offset) | (high << (64 - offset))) & mask)
        bitpos += bits
    return values


def _pack(values: list[int], bits: int, spanning: bool) -> list[int]:
    mask = (1 << bits) - 1
    if not spanning:
        per = 64 // bits
        result = []
        for start in range(0, len(values), per):
            word = 0
            for offset, value in enumerate(values[start : start + per]):
                word |= (int(value) & mask) << (offset * bits)
            if word >= 1 << 63:
                word -= 1 << 64
            result.append(word)
        return result
    total_bits = len(values) * bits
    count = (total_bits + 63) // 64
    words = [0] * count
    bitpos = 0
    for value in values:
        index = bitpos >> 6
        offset = bitpos & 63
        words[index] |= (int(value) & mask) << offset
        if offset + bits > 64:
            words[index + 1] |= (int(value) & mask) >> (64 - offset)
        bitpos += bits
    return [word - (1 << 64) if word >= 1 << 63 else word for word in words]


def _section_y(fields: dict) -> int:
    node = fields.get("Y")
    if node and node[0] == TAG_BYTE:
        return int(node[1])
    return 0


def _block_index(x: int, y: int, z: int) -> int:
    return (y * 16 + z) * 16 + x


def _iter_blocks(root, data_version: int):
    """生成 (section_fields, kind, 索引, 方块标识) 序列。"""
    for section in _sections(root):
        if section[0] != TAG_COMPOUND:
            continue
        fields = section[1]
        kind = _section_kind(fields)
        if kind == "none":
            continue
        if kind == "legacy":
            blocks = fields["Blocks"][1]
            base_y = _section_y(fields)
            for index in range(4096):
                value = int(blocks[index]) if index < len(blocks) else 0
                yield fields, kind, index, base_y, value
            continue
        names = _palette_entries(fields)
        data_node = _data_array(fields)
        spanning = data_version < 2566
        bits = _bits_for(max(1, len(names)))
        if data_node and data_node[0] == TAG_LONG_ARRAY and data_node[1]:
            indices = _unpack(data_node[1], bits, 4096, spanning)
        else:
            indices = [0] * 4096
        base_y = _section_y(fields)
        for index, palette_index in enumerate(indices):
            name = names[palette_index] if palette_index < len(names) else "minecraft:air"
            yield fields, kind, index, base_y, name


def _legacy_block_value(value) -> int:
    """旧版方块 ID 既接受数字，也接受内置表里的方块名。"""
    text = str(value).strip()
    try:
        return int(text)
    except ValueError:
        pass
    from .creator_schema import LEGACY_ITEM_IDS

    key = text.lower()
    if ":" not in key:
        key = f"minecraft:{key}"
    if key in LEGACY_ITEM_IDS:
        return LEGACY_ITEM_IDS[key]
    raise RegionError(
        f"1.13 前存档不认识方块「{text}」，请填数字 ID，或使用内置表里的方块名"
    )


def replace_blocks(archive: RegionArchive, old_id, new_id, *, era: str) -> dict:
    """把 region 内所有 ``old_id`` 替换为 ``new_id``，返回统计。"""
    replaced = 0
    chunks = 0
    legacy = era == "legacy"
    if legacy:
        old_value = _legacy_block_value(old_id)
        new_value = _legacy_block_value(new_id)
        if not 0 <= old_value <= 255 or not 0 <= new_value <= 255:
            raise RegionError("旧版方块数字 ID 必须在 0 - 255 之间")
    for index, slot in enumerate(archive.slots):
        if slot is None:
            continue
        root = _root(archive.path or Path("<region>"), slot)
        data_version = _data_version(root)
        changed = False
        for fields, kind, block_index, base_y, value in _iter_blocks(root, data_version):
            if legacy:
                if kind != "legacy" or value != old_value:
                    continue
                fields["Blocks"][1][block_index] = new_value
                replaced += 1
                changed = True
            else:
                if kind == "legacy" or value != old_id:
                    continue
                _remap_palette(fields, old_id, new_id, data_version)
                replaced += 4096
                changed = True
                break
        if changed:
            raw = write_nbt_typed("", root)
            slot.payload = _compress(slot.compression, raw)
            slot.dirty = True
            chunks += 1
    return {"replaced": replaced, "chunks": chunks}


def _remap_palette(fields: dict, old_id: str, new_id: str, data_version: int) -> None:
    """在 palette 中把 old_id 全部映射到 new_id，必要时扩容并重建 data。"""
    names = _palette_entries(fields)
    if old_id not in names:
        raise RegionError(f"palette 中不存在方块 {old_id}")
    old_index = names.index(old_id)
    if new_id in names:
        new_index = names.index(new_id)
        names_changed = False
    else:
        new_index = len(names)
        names_changed = True

    data_node = _data_array(fields)
    spanning = data_version < 2566
    bits = _bits_for(max(1, len(names) + (1 if names_changed else 0)))
    if data_node and data_node[0] == TAG_LONG_ARRAY and data_node[1]:
        indices = _unpack(data_node[1], _bits_for(max(1, len(names))), 4096, spanning)
    else:
        indices = [0] * 4096
    indices = [new_index if value == old_index else value for value in indices]

    if names_changed:
        if "block_states" in fields:
            states = fields["block_states"][1]
            palette = states["palette"]
            palette[1][1].append(
                (TAG_COMPOUND, {"Name": (TAG_STRING, str(new_id))})
            )
            states["data"] = (TAG_LONG_ARRAY, _pack(indices, bits, spanning))
        else:
            palette = fields["Palette"]
            palette[1][1].append((TAG_COMPOUND, {"Name": (TAG_STRING, str(new_id))}))
            fields["BlockStates"] = (TAG_LONG_ARRAY, _pack(indices, bits, spanning))
    else:
        if "block_states" in fields:
            fields["block_states"][1]["data"] = (TAG_LONG_ARRAY, _pack(indices, bits, spanning))
        else:
            fields["BlockStates"] = (TAG_LONG_ARRAY, _pack(indices, bits, spanning))


def _is_air(value) -> bool:
    if isinstance(value, str):
        return value in AIR_NAMES
    return int(value) == 0


def surface_y(archive: RegionArchive, block_x: int, block_z: int) -> int | None:
    """查询某个方块列最高非空气方块的世界 Y；区块未加载则返回 None。"""
    chunk_x, chunk_z = block_x >> 4, block_z >> 4
    local_x, local_z = block_x & 15, block_z & 15
    slot = None
    for candidate in archive.slots:
        if candidate is not None and candidate.x == chunk_x and candidate.z == chunk_z:
            slot = candidate
            break
    if slot is None:
        return None
    root = _root(archive.path or Path("<region>"), slot)
    data_version = _data_version(root)
    best: int | None = None
    for fields, kind, block_index, base_y, value in _iter_blocks(root, data_version):
        y = block_index // 256
        z = (block_index // 16) % 16
        x = block_index % 16
        if (x, z) != (local_x, local_z):
            continue
        if _is_air(value):
            continue
        world_y = base_y * 16 + y
        if best is None or world_y > best:
            best = world_y
    return best


def region_files(world) -> list[Path]:
    """列出世界内需要扫描的 region 文件（主世界、DIM*、dimensions）。"""
    root = Path(world)
    result: list[Path] = []
    main = root / "region"
    if main.is_dir():
        result.extend(sorted(main.glob("*.mca")))
    for folder in root.glob("DIM*"):
        region = folder / "region"
        if region.is_dir():
            result.extend(sorted(region.glob("*.mca")))
    dimensions = root / "dimensions"
    if dimensions.is_dir():
        for namespace in dimensions.iterdir():
            if not namespace.is_dir():
                continue
            for dimension in namespace.iterdir():
                region = dimension / "region"
                if region.is_dir():
                    result.extend(sorted(region.glob("*.mca")))
    return result
