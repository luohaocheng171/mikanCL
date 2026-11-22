"""Alpha / Beta 适配回归测试。

覆盖：
- 远古目标版本识别（b1.7.3 / a1.2.6）；
- Anvil → Beta(McRegion) / Alpha(独立区块) 降级，含 128 格以上方块丢弃与
  扁平化存档拒绝；
- 1.6 以前版本 jar 的物品枚举（按 lang 文件，不猜贴图）；
- 远古版本的 Java 版本推断。
"""

from __future__ import annotations

import struct
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path

from mc_launcher import item_icons, nbt, world_convert as W
from mc_launcher.version import infer_java_major, version_category


def _write_anvil_world(root: Path, *, flattened: bool = False,
                       blocks: list[tuple[int, int, int, int, int]] | None = None) -> Path:
    """造一个 1.12.2 结构的 Anvil 世界（数字 ID，可选扁平化）。"""
    root.mkdir(parents=True, exist_ok=True)
    data = {
        "LevelName": (nbt.TAG_STRING, "ModernWorld"),
        "RandomSeed": (nbt.TAG_LONG, 777),
        "SpawnX": (nbt.TAG_INT, 8),
        "SpawnY": (nbt.TAG_INT, 70),
        "SpawnZ": (nbt.TAG_INT, 8),
        "DataVersion": (nbt.TAG_INT, 1343),
    }
    (root / "level.dat").write_bytes(
        nbt.write_nbt_typed("", (nbt.TAG_COMPOUND, {"Data": (nbt.TAG_COMPOUND, data)}))
    )

    sections: dict[int, bytearray] = {}
    for x, y, z, block_id, meta in (blocks or [(1, 3, 2, 1, 0)]):
        section_y = y // 16
        sec = sections.setdefault(section_y, bytearray(4096))
        index = ((y % 16) << 8) | (z << 4) | x
        sec[index] = block_id

    section_nodes = []
    for section_y in sorted(sections):
        build = {
            "Y": (nbt.TAG_BYTE, section_y),
            "Blocks": (nbt.TAG_BYTE_ARRAY, sections[section_y]),
        }
        if flattened:
            build.pop("Blocks")
            build["Palette"] = (nbt.TAG_LIST, (nbt.TAG_COMPOUND, [
                (nbt.TAG_COMPOUND, {"Name": (nbt.TAG_STRING, "minecraft:stone")}),
            ]))
            build["BlockStates"] = (nbt.TAG_LONG_ARRAY, [0] * 256)
        section_nodes.append((nbt.TAG_COMPOUND, build))

    level = {
        "xPos": (nbt.TAG_INT, 0),
        "zPos": (nbt.TAG_INT, 0),
        "Sections": (nbt.TAG_LIST, (nbt.TAG_COMPOUND, section_nodes)),
        "Entities": (nbt.TAG_LIST, (nbt.TAG_COMPOUND, [])),
        "TileEntities": (nbt.TAG_LIST, (nbt.TAG_COMPOUND, [
            (nbt.TAG_COMPOUND, {"id": (nbt.TAG_STRING, "Chest"),
                                "x": (nbt.TAG_INT, 1), "y": (nbt.TAG_INT, 3), "z": (nbt.TAG_INT, 2)}),
            (nbt.TAG_COMPOUND, {"id": (nbt.TAG_STRING, "Chest"),
                                "x": (nbt.TAG_INT, 1), "y": (nbt.TAG_INT, 200), "z": (nbt.TAG_INT, 2)}),
        ])),
    }
    raw = nbt.write_nbt_typed("", (nbt.TAG_COMPOUND, {"Level": (nbt.TAG_COMPOUND, level)}))
    compressed = zlib.compress(raw, 6)
    record = struct.pack(">I", len(compressed) + 1) + b"\x02" + compressed
    record += b"\x00" * ((-len(record)) % 4096)
    header = bytearray(8192)
    header[0:4] = struct.pack(">I", (2 << 8) | (len(record) // 4096))
    (root / "region").mkdir(exist_ok=True)
    (root / "region" / "r.0.0.mca").write_bytes(bytes(header) + record)
    return root


def _write_mcregion_world(root: Path) -> Path:
    """造一个 Beta 1.7.3 结构的 McRegion 世界（32768 字节 Blocks）。"""
    root.mkdir(parents=True, exist_ok=True)
    data = {
        "LevelName": (nbt.TAG_STRING, "BetaWorld"),
        "RandomSeed": (nbt.TAG_LONG, 42),
        "SpawnX": (nbt.TAG_INT, 0), "SpawnY": (nbt.TAG_INT, 64), "SpawnZ": (nbt.TAG_INT, 0),
    }
    (root / "level.dat").write_bytes(
        nbt.write_nbt_typed("", (nbt.TAG_COMPOUND, {"Data": (nbt.TAG_COMPOUND, data)}))
    )
    blocks = bytearray(32768)
    blocks[(2 << 11) | (3 << 7) | 5] = 1     # x=2 z=3 y=5 放石头
    level = {
        "xPos": (nbt.TAG_INT, 0), "zPos": (nbt.TAG_INT, 0),
        "Blocks": (nbt.TAG_BYTE_ARRAY, blocks),
        "Data": (nbt.TAG_BYTE_ARRAY, bytearray(16384)),
        "HeightMap": (nbt.TAG_BYTE_ARRAY, bytes(256)),
        "Entities": (nbt.TAG_LIST, (nbt.TAG_COMPOUND, [])),
        "TileEntities": (nbt.TAG_LIST, (nbt.TAG_COMPOUND, [])),
        "TerrainPopulated": (nbt.TAG_BYTE, 1),
    }
    raw = nbt.write_nbt_typed("", (nbt.TAG_COMPOUND, {"Level": (nbt.TAG_COMPOUND, level)}))
    compressed = zlib.compress(raw, 6)
    record = struct.pack(">I", len(compressed) + 1) + b"\x02" + compressed
    record += b"\x00" * ((-len(record)) % 4096)
    header = bytearray(8192)
    header[0:4] = struct.pack(">I", (2 << 8) | (len(record) // 4096))
    (root / "region").mkdir(exist_ok=True)
    (root / "region" / "r.0.0.mcr").write_bytes(bytes(header) + record)
    return root


class LegacyTargetTest(unittest.TestCase):
    """远古目标版本的配置识别。"""

    def test_beta_profile(self):
        profile = W.target_profile("b1.7.3")
        self.assertTrue(profile["legacy"])
        self.assertEqual(profile["legacy_era"], "mcregion")
        self.assertEqual(profile["height"], 128)
        self.assertEqual(profile["data_version"], 0)

    def test_alpha_profile(self):
        profile = W.target_profile("a1.2.6")
        self.assertTrue(profile["legacy"])
        self.assertEqual(profile["legacy_era"], "alpha")

    def test_unknown_old_prefix_still_accepted(self):
        # 表里没登记的远古版本按前缀推断，不应该直接报错
        self.assertEqual(W.target_profile("b1.9-pre5")["legacy_era"], "mcregion")
        self.assertEqual(W.target_profile("inf-20100618")["legacy_era"], "alpha")

    def test_legacy_targets_are_listed(self):
        ids = [entry["id"] for entry in W.LEGACY_TARGETS]
        self.assertIn("b1.7.3", ids)
        self.assertIn("a1.2.6", ids)

    def test_java_and_category(self):
        for version in ("b1.7.3", "a1.2.6", "inf-20100618", "c0.30_01c"):
            # 远古版本优先 Java 6/7（Java 8 只作为兜底，不再是「恰好匹配」）
            self.assertEqual(infer_java_major(version), 7, version)
            self.assertEqual(version_category(version, "old_beta"), "old", version)


class DowngradeTest(unittest.TestCase):
    """Anvil → Beta / Alpha 降级。"""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)

    def tearDown(self):
        self._temp.cleanup()

    def test_beta_outputs_mcr(self):
        world = _write_anvil_world(self.root / "Modern", blocks=[
            (1, 3, 2, 1, 0),        # y=3 石头，应保留
            (0, 130, 0, 41, 0),     # y=130 金块，超出 128 格应丢弃
        ])
        result = W.convert(world, "b1.7.3", output_dir=self.root / "out")
        out = Path(result["output"])
        self.assertTrue((out / "region" / "r.0.0.mcr").is_file())
        self.assertFalse((out / "region" / "r.0.0.mca").exists())
        self.assertEqual(result["stats"]["chunks"], 1)
        self.assertEqual(result["stats"]["dropped_blocks"], 1)

        chunks = W._read_region(out / "region" / "r.0.0.mcr")
        level = chunks[(0, 0)][1][1]["Level"][1]
        self.assertNotIn("Sections", level)
        blocks = level["Blocks"][1]
        self.assertEqual(len(blocks), 32768)
        self.assertEqual(blocks[(1 << 11) | (2 << 7) | 3], 1)
        self.assertEqual(len(level["HeightMap"][1]), 256)
        # 128 格以上的方块实体被过滤掉
        self.assertEqual(len(level["TileEntities"][1][1]), 1)

    def test_alpha_outputs_chunk_files(self):
        world = _write_anvil_world(self.root / "Modern")
        result = W.convert(world, "a1.2.6", output_dir=self.root / "out")
        out = Path(result["output"])
        self.assertTrue((out / "c.0.0.dat").is_file())
        _name, node = nbt.parse_nbt_typed((out / "c.0.0.dat").read_bytes())
        level = node[1]["Level"][1]
        self.assertEqual(level["Blocks"][1][(1 << 11) | (2 << 7) | 3], 1)
        # level.dat 不能带 DataVersion，否则旧版会当成未来存档
        _ln, lnode = nbt.load_nbt_typed_file(out / "level.dat")
        self.assertNotIn("DataVersion", lnode[1]["Data"][1])
        self.assertIn("Player", lnode[1]["Data"][1])

    def test_flattened_source_is_rejected(self):
        world = _write_anvil_world(self.root / "Flat", flattened=True)
        with self.assertRaises(W.WorldConvertError) as ctx:
            W.convert(world, "b1.7.3", output_dir=self.root / "out")
        self.assertIn("扁平化", str(ctx.exception))

    def test_mcregion_source_to_alpha(self):
        """Beta 1.7.3 的 McRegion 存档直接降级到 Alpha：不做索引转置，只重算高度图。"""
        world = _write_mcregion_world(self.root / "BetaWorld")
        result = W.convert(world, "a1.2.6", output_dir=self.root / "out")
        out = Path(result["output"])
        _name, node = nbt.parse_nbt_typed((out / "c.0.0.dat").read_bytes())
        level = node[1]["Level"][1]
        self.assertEqual(level["Blocks"][1][(2 << 11) | (3 << 7) | 5], 1)
        self.assertEqual(level["HeightMap"][1][(3 << 4) | 2], 6)
        self.assertEqual(result["stats"]["kept_blocks"], 1)

    def test_earlier_source_is_rejected(self):
        world = _write_anvil_world(self.root / "Modern")
        with self.assertRaises(W.WorldConvertError):
            W.convert(world, "b1.7.3", output_dir=self.root / "out", source_era="alpha")


class LegacyJarEnumerationTest(unittest.TestCase):
    """1.6 以前版本 jar 的物品枚举。"""

    def _make_jar(self, root: Path, lang: str | None) -> Path:
        jar = root / "b1.7.3.jar"
        with zipfile.ZipFile(jar, "w") as archive:
            archive.writestr("net/minecraft/client/Minecraft.class", b"\xca\xfe\xba\xbe")
            if lang is not None:
                archive.writestr("lang/en_US.lang", lang)
        return jar

    def test_lang_enumeration(self):
        with tempfile.TemporaryDirectory() as tmp:
            jar = self._make_jar(Path(tmp), (
                "tile.stone.name=Stone\ntile.stone.desc=Rock\n"
                "tile.grass.name=Grass\n"
                "item.apple.name=Apple\nitem.shovelIron.name=Iron Shovel\n"
                "gui.done=Done\n"
            ))
            result = item_icons.enumerate_items("b1.7.3", game_dir=jar)
            self.assertEqual(result["source"], "legacy-lang")
            ids = [row["id"] for row in result["items"]]
            self.assertEqual(ids, [
                "minecraft:stone", "minecraft:grass",
                "minecraft:apple", "minecraft:shovel_iron",
            ])
            names = {row["id"]: row["name"] for row in result["items"]}
            self.assertEqual(names["minecraft:stone"], "Stone")
            self.assertEqual(names["minecraft:shovel_iron"], "Iron Shovel")
            kinds = {row["id"]: row["kind"] for row in result["items"]}
            self.assertEqual(kinds["minecraft:stone"], "block")
            self.assertEqual(kinds["minecraft:apple"], "item")
            # 贴图索引无法从 jar 推导：不能谎报有贴图
            self.assertFalse(any(row["texture_available"] for row in result["items"]))
            # 数字 ID 由 lang 键经别名表翻译，Beta 的 "Emerald" 就是钻石
            by_key = {row["key"]: row for row in result["items"]}
            self.assertEqual(by_key["stone"]["legacy_id"], 1)
            self.assertEqual(by_key["grass"]["legacy_id"], 2)
            self.assertEqual(by_key["apple"]["legacy_id"], 260)
            self.assertEqual(by_key["shovelIron"]["legacy_id"], 256)
            self.assertEqual(by_key["shovelIron"]["legacy_damage"], 0)

    def test_damage_variants(self):
        with tempfile.TemporaryDirectory() as tmp:
            jar = self._make_jar(Path(tmp), (
                "tile.cloth.black.name=Black Wool\n"
                "tile.cloth.white.name=Wool\n"
                "tile.clay.name=Clay\n"
                "item.clay.name=Clay\n"
                "item.charcoal.name=Charcoal\n"
            ))
            rows = item_icons.enumerate_items("b1.7.3", game_dir=jar)["items"]
            by_key = {(row["kind"], row["key"]): row for row in rows}
            self.assertEqual(by_key[("block", "cloth.black")]["legacy_id"], 35)
            self.assertEqual(by_key[("block", "cloth.black")]["legacy_damage"], 15)
            self.assertEqual(by_key[("block", "cloth.white")]["legacy_damage"], 0)
            # 同名的方块与物品要分别翻译：黏土块 82 / 黏土球 337
            self.assertEqual(by_key[("block", "clay")]["legacy_id"], 82)
            self.assertEqual(by_key[("item", "clay")]["legacy_id"], 337)
            # 木炭是煤炭 + Damage 1
            self.assertEqual(by_key[("item", "charcoal")]["legacy_id"], 263)
            self.assertEqual(by_key[("item", "charcoal")]["legacy_damage"], 1)

    def test_missing_lang_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            jar = self._make_jar(Path(tmp), None)
            result = item_icons.enumerate_items("b1.7.3", game_dir=jar)
            self.assertEqual(result["count"], 0)
            self.assertEqual(result["source"], "none")

    def test_duplicate_keys_are_disambiguated(self):
        with tempfile.TemporaryDirectory() as tmp:
            jar = self._make_jar(Path(tmp), (
                "tile.leaves.name=Leaves\nitem.leaves.name=Leaves\n"
            ))
            result = item_icons.enumerate_items("b1.7.3", game_dir=jar)
            ids = [row["id"] for row in result["items"]]
            self.assertEqual(len(ids), len(set(ids)))
            self.assertIn("minecraft:leaves", ids)
            self.assertIn("minecraft:leaves_item", ids)


if __name__ == "__main__":
    unittest.main(verbosity=2)
