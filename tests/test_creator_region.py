"""creator_region：Anvil region 记录保留式读写与方块替换。"""

from __future__ import annotations

import gzip
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from mc_launcher import nbt
from mc_launcher.creator_region import (
    RegionError,
    read_region,
    remove_entities,
    replace_blocks,
    set_blocks,
    spawn_entities,
    surface_y,
    write_region,
)
from tests.creator_fixtures import make_region

TAG = nbt


def _modern_chunk(data_version: int, palette: list[str], fill: int = 0, root_sections: bool = False) -> bytes:
    """构造一个全为 palette[fill] 的区块（每格都相同，data 可省略）。"""
    section = {
        "Y": (TAG.TAG_BYTE, 0),
        "block_states": (
            TAG.TAG_COMPOUND,
            {
                "palette": (
                    TAG.TAG_LIST,
                    (TAG.TAG_COMPOUND, [(TAG.TAG_COMPOUND, {"Name": (TAG.TAG_STRING, name)}) for name in palette]),
                ),
            },
        ),
        "biomes": (TAG.TAG_COMPOUND, {"palette": (TAG.TAG_LIST, (TAG.TAG_STRING, [(TAG.TAG_STRING, "minecraft:plains")]))}),
    }
    if not root_sections:
        payload = {
            "DataVersion": (TAG.TAG_INT, data_version),
            "Level": (
                TAG.TAG_COMPOUND,
                {"Sections": (TAG.TAG_LIST, (TAG.TAG_COMPOUND, [(TAG.TAG_COMPOUND, section)]))},
            ),
        }
    else:
        payload = {
            "DataVersion": (TAG.TAG_INT, data_version),
            "sections": (TAG.TAG_LIST, (TAG.TAG_COMPOUND, [(TAG.TAG_COMPOUND, section)])),
        }
    return zlib.compress(nbt.write_nbt_typed("", (TAG.TAG_COMPOUND, payload)))


def _legacy_chunk(block_id: int, damage: int = 0) -> bytes:
    blocks = bytearray(4096)
    for index in range(4096):
        blocks[index] = block_id
    meta = bytearray(2048)
    if damage:
        for index in range(2048):
            meta[index] = damage | (damage << 4)
    payload = {
        "DataVersion": (TAG.TAG_INT, 1343),
        "Level": (
            TAG.TAG_COMPOUND,
            {
                "Sections": (
                    TAG.TAG_LIST,
                    (
                        TAG.TAG_COMPOUND,
                        [
                            (
                                TAG.TAG_COMPOUND,
                                {
                                    "Y": (TAG.TAG_BYTE, 0),
                                    "Blocks": (TAG.TAG_BYTE_ARRAY, blocks),
                                    "Data": (TAG.TAG_BYTE_ARRAY, meta),
                                },
                            )
                        ],
                    ),
                )
            },
        ),
    }
    return zlib.compress(nbt.write_nbt_typed("", (TAG.TAG_COMPOUND, payload)))


class RegionReadTest(unittest.TestCase):
    def test_read_preserves_all_slots(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_region(Path(tmp) / "r.0.0.mca", {(0, 0): _modern_chunk(3465, ["minecraft:stone"])})
            archive = read_region(path)
            self.assertEqual(len(archive.slots), 1024)
            self.assertIsNotNone(archive.slots[0])
            self.assertIsNone(archive.slots[1])

    def test_unknown_compression_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.0.0.mca"
            header = bytearray(8192)
            header[0:4] = struct.pack(">I", (2 << 8) | 1)
            body = struct.pack(">I", 4) + b"\x09" + b"abc"
            path.write_bytes(bytes(header) + body)
            with self.assertRaises(RegionError):
                read_region(path)

    def test_truncated_region_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.0.0.mca"
            header = bytearray(8192)
            header[0:4] = struct.pack(">I", (2 << 8) | 1)
            path.write_bytes(bytes(header) + b"\x00\x00")
            with self.assertRaises(RegionError):
                read_region(path)

    def test_roundtrip_keeps_unmodified_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_region(Path(tmp) / "r.0.0.mca", {(0, 0): _modern_chunk(3465, ["minecraft:stone"])})
            original = read_region(path).slots[0].payload
            archive = read_region(path)
            out = Path(tmp) / "copy.0.0.mca"
            write_region(out, archive, changes={})
            copied = read_region(out).slots[0]
            self.assertEqual(copied.payload, original)


class ReplaceTest(unittest.TestCase):
    def test_legacy_numeric_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_region(Path(tmp) / "r.0.0.mca", {(0, 0): _legacy_chunk(1)})
            archive = read_region(path)
            stats = replace_blocks(archive, 1, 57, era="legacy")
            self.assertEqual(stats["replaced"], 4096)
            payload = zlib.decompress(archive.slots[0].payload)
            _name, root = nbt.parse_nbt_typed(payload)
            blocks = root[1]["Level"][1]["Sections"][1][1][0][1]["Blocks"][1]
            self.assertEqual(set(blocks), {57})

    def test_legacy_replacement_accepts_builtin_block_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_region(Path(tmp) / "r.0.0.mca", {(0, 0): _legacy_chunk(1)})
            archive = read_region(path)
            stats = replace_blocks(archive, "minecraft:stone", "minecraft:diamond_block", era="legacy")
            self.assertEqual(stats["replaced"], 4096)
            payload = zlib.decompress(archive.slots[0].payload)
            _name, root = nbt.parse_nbt_typed(payload)
            blocks = root[1]["Level"][1]["Sections"][1][1][0][1]["Blocks"][1]
            self.assertEqual(set(blocks), {57})

    def test_legacy_unknown_block_name_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_region(Path(tmp) / "r.0.0.mca", {(0, 0): _legacy_chunk(1)})
            archive = read_region(path)
            with self.assertRaises(RegionError):
                replace_blocks(archive, "minecraft:cherry_leaves", "minecraft:diamond_block", era="legacy")

    def test_modern_palette_replacement_adds_new_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_region(Path(tmp) / "r.0.0.mca", {(0, 0): _modern_chunk(3465, ["minecraft:stone"])})
            archive = read_region(path)
            stats = replace_blocks(archive, "minecraft:stone", "minecraft:diamond_block", era="flattened")
            self.assertGreater(stats["replaced"], 0)
            payload = zlib.decompress(archive.slots[0].payload)
            _name, root = nbt.parse_nbt_typed(payload)
            section = root[1]["Level"][1]["Sections"][1][1][0][1]
            names = [entry[1]["Name"][1] for entry in section["block_states"][1]["palette"][1][1]]
            self.assertIn("minecraft:diamond_block", names)

    def test_no_match_changes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_region(Path(tmp) / "r.0.0.mca", {(0, 0): _modern_chunk(3465, ["minecraft:stone"])})
            archive = read_region(path)
            before = archive.slots[0].payload
            stats = replace_blocks(archive, "minecraft:bedrock", "minecraft:stone", era="flattened")
            self.assertEqual(stats["replaced"], 0)
            self.assertEqual(archive.slots[0].payload, before)


class SurfaceTest(unittest.TestCase):
    def test_surface_finds_top_solid_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_region(Path(tmp) / "r.0.0.mca", {(0, 0): _modern_chunk(3465, ["minecraft:stone"])})
            archive = read_region(path)
            self.assertEqual(surface_y(archive, 0, 0), 15)

    def test_surface_skips_air_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_region(Path(tmp) / "r.0.0.mca", {(0, 0): _modern_chunk(3465, ["minecraft:air"])})
            archive = read_region(path)
            self.assertIsNone(surface_y(archive, 0, 0))


class SetBlockTest(unittest.TestCase):
    def _section(self, archive):
        payload = zlib.decompress(archive.slots[0].payload)
        _name, root = nbt.parse_nbt_typed(payload)
        return root[1]["Level"][1]["Sections"][1][1][0][1]

    def test_set_single_block_adds_palette_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_region(Path(tmp) / "r.0.0.mca", {(0, 0): _modern_chunk(3465, ["minecraft:stone"])})
            archive = read_region(path)
            stats = set_blocks(archive, [(3, 5, 7)], "minecraft:diamond_block", era="flattened")
            self.assertEqual(stats["blocks"], 1)
            section = self._section(archive)
            names = [entry[1]["Name"][1] for entry in section["block_states"][1]["palette"][1][1]]
            self.assertEqual(names, ["minecraft:stone", "minecraft:diamond_block"])
            from mc_launcher.creator_region import _unpack

            data = section["block_states"][1]["data"][1]
            values = _unpack(data, 4, 4096, False)
            self.assertEqual(values[5 * 256 + 7 * 16 + 3], 1)
            self.assertEqual(values[0], 0)

    def test_set_block_creates_missing_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_region(Path(tmp) / "r.0.0.mca", {(0, 0): _modern_chunk(3465, ["minecraft:stone"])})
            archive = read_region(path)
            stats = set_blocks(archive, [(0, 40, 0)], "minecraft:gold_block", era="flattened")
            self.assertEqual(stats["sections_created"], 1)
            payload = zlib.decompress(archive.slots[0].payload)
            _name, root = nbt.parse_nbt_typed(payload)
            sections = root[1]["Level"][1]["Sections"][1][1]
            ys = sorted(section[1]["Y"][1] for section in sections)
            self.assertEqual(ys, [0, 2])

    def test_set_block_with_properties_writes_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_region(Path(tmp) / "r.0.0.mca", {(0, 0): _modern_chunk(3465, ["minecraft:air"])})
            archive = read_region(path)
            set_blocks(
                archive,
                [(0, 1, 0)],
                "minecraft:oak_stairs",
                properties={"facing": "north", "half": "top"},
                era="flattened",
            )
            section = self._section(archive)
            entry = section["block_states"][1]["palette"][1][1][-1][1]
            self.assertEqual(entry["Name"][1], "minecraft:oak_stairs")
            self.assertEqual(entry["Properties"][1]["facing"][1], "north")
            self.assertEqual(entry["Properties"][1]["half"][1], "top")

    def test_legacy_set_block_by_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_region(Path(tmp) / "r.0.0.mca", {(0, 0): _legacy_chunk(1)})
            archive = read_region(path)
            set_blocks(archive, [(1, 1, 1)], "minecraft:diamond_block", era="legacy")
            payload = zlib.decompress(archive.slots[0].payload)
            _name, root = nbt.parse_nbt_typed(payload)
            blocks = root[1]["Level"][1]["Sections"][1][1][0][1]["Blocks"][1]
            self.assertEqual(blocks[1 * 256 + 1 * 16 + 1], 57)

    def test_legacy_y_out_of_range_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_region(Path(tmp) / "r.0.0.mca", {(0, 0): _legacy_chunk(1)})
            archive = read_region(path)
            with self.assertRaises(RegionError):
                set_blocks(archive, [(0, 300, 0)], "minecraft:stone", era="legacy")

    def test_new_section_uses_palette_before_1_18(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_region(Path(tmp) / "r.0.0.mca", {(0, 0): _modern_chunk(2586, ["minecraft:stone"])})
            archive = read_region(path)
            set_blocks(archive, [(0, 20, 0)], "minecraft:glass", era="flattened")
            payload = zlib.decompress(archive.slots[0].payload)
            _name, root = nbt.parse_nbt_typed(payload)
            sections = root[1]["Level"][1]["Sections"][1][1]
            new_section = next(
                section[1] for section in sections if section[1]["Y"][1] == 1
            )
            self.assertIn("Palette", new_section)
            self.assertNotIn("block_states", new_section)

    def test_out_of_range_y_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_region(Path(tmp) / "r.0.0.mca", {(0, 0): _modern_chunk(2586, ["minecraft:stone"])})
            archive = read_region(path)
            with self.assertRaises(RegionError):
                set_blocks(archive, [(0, 300, 0)], "minecraft:stone", era="flattened")

    def test_missing_chunk_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_region(Path(tmp) / "r.0.0.mca", {(0, 0): _modern_chunk(3465, ["minecraft:stone"])})
            archive = read_region(path)
            with self.assertRaises(RegionError):
                set_blocks(archive, [(400, 5, 0)], "minecraft:stone", era="flattened")

    def test_fill_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_region(Path(tmp) / "r.0.0.mca", {(0, 0): _modern_chunk(3465, ["minecraft:air"])})
            archive = read_region(path)
            positions = [
                (x, y, z)
                for x in range(2, 5)
                for y in range(3, 5)
                for z in range(0, 3)
            ]
            stats = set_blocks(archive, positions, "minecraft:glass", era="flattened")
            self.assertEqual(stats["blocks"], 18)


class SpawnEntityTest(unittest.TestCase):
    def test_spawn_in_legacy_chunk(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_region(Path(tmp) / "r.0.0.mca", {(0, 0): _legacy_chunk(1)})
            stats = spawn_entities(
                Path(tmp), [(0.5, 64.0, 0.5)], "minecraft:zombie", split_entities=False
            )
            self.assertEqual(stats["entities"], 1)
            write_region(path, stats["archives"][str(path)])
            archive = read_region(path)
            payload = zlib.decompress(archive.slots[0].payload)
            _name, root = nbt.parse_nbt_typed(payload)
            entities = root[1]["Level"][1]["Entities"][1][1]
            self.assertEqual(entities[0][1]["id"][1], "minecraft:zombie")
            self.assertAlmostEqual(entities[0][1]["Pos"][1][1][0][1], 0.5)

    def test_spawn_creates_split_entities_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "region").mkdir()
            stats = spawn_entities(
                root / "region",
                [(0.5, 64.0, 0.5)],
                "minecraft:cow",
                split_entities=True,
                entities_dir=root / "entities",
                data_version=3953,
            )
            self.assertEqual(stats["entities"], 1)
            self.assertEqual(stats["created_files"], 1)
            entity_path = root / "entities" / "r.0.0.mca"
            entity_path.parent.mkdir(parents=True, exist_ok=True)
            write_region(entity_path, stats["archives"][str(entity_path)])
            self.assertTrue(entity_path.is_file())
            archive = read_region(entity_path)
            payload = zlib.decompress(archive.slots[0].payload)
            _name, chunk = nbt.parse_nbt_typed(payload)
            self.assertEqual(chunk[1]["DataVersion"][1], 3953)
            self.assertEqual(chunk[1]["Entities"][1][1][0][1]["id"][1], "minecraft:cow")

    def test_spawn_requires_existing_chunk_for_legacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "r.0.0.mca").parent.mkdir(parents=True, exist_ok=True)
            make_region(Path(tmp) / "r.0.0.mca", {(0, 0): _legacy_chunk(1)})
            with self.assertRaises(RegionError):
                spawn_entities(
                    Path(tmp), [(400.5, 64.0, 0.5)], "minecraft:zombie", split_entities=False
                )

    def test_remove_entities_inside_box(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_region(Path(tmp) / "r.0.0.mca", {(0, 0): _legacy_chunk(1)})
            spawned = spawn_entities(
                Path(tmp),
                [(0.5, 64.0, 0.5), (10.5, 64.0, 0.5)],
                "minecraft:zombie",
                split_entities=False,
            )
            write_region(path, spawned["archives"][str(path)])
            result = remove_entities(
                Path(tmp), ((0.0, 60.0, 0.0), (2.0, 70.0, 2.0)), split_entities=False
            )
            self.assertEqual(result["removed"], 1)
            write_region(path, result["archives"][str(path)])
            archive = read_region(path)
            payload = zlib.decompress(archive.slots[0].payload)
            _name, root = nbt.parse_nbt_typed(payload)
            entities = root[1]["Level"][1]["Entities"][1][1]
            self.assertEqual(len(entities), 1)
            self.assertAlmostEqual(
                entities[0][1]["Pos"][1][1][0][1], 10.5
            )

    def test_remove_entities_can_filter_by_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_region(Path(tmp) / "r.0.0.mca", {(0, 0): _legacy_chunk(1)})
            spawned = spawn_entities(
                Path(tmp),
                [(0.5, 64.0, 0.5), (1.5, 64.0, 0.5)],
                "minecraft:zombie",
                split_entities=False,
            )
            write_region(path, spawned["archives"][str(path)])
            cows = spawn_entities(
                Path(tmp),
                [(2.5, 64.0, 0.5)],
                "minecraft:cow",
                split_entities=False,
            )
            write_region(path, cows["archives"][str(path)])
            result = remove_entities(
                Path(tmp),
                ((0.0, 60.0, 0.0), (3.0, 70.0, 3.0)),
                split_entities=False,
                entity_id="minecraft:cow",
            )
            self.assertEqual(result["removed"], 1)
            write_region(path, result["archives"][str(path)])
            archive = read_region(path)
            _name, root = nbt.parse_nbt_typed(zlib.decompress(archive.slots[0].payload))
            entities = root[1]["Level"][1]["Entities"][1][1]
            self.assertEqual(len(entities), 2)
            self.assertTrue(all(entry[1]["id"][1] == "minecraft:zombie" for entry in entities))


if __name__ == "__main__":
    unittest.main()
