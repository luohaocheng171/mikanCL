"""矿石分类：以游戏自带的 block tag 为准，内置表兜底。"""
from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from mc_launcher import ore_tags


def _jar(root: Path, version: str, tags: dict[str, list[str]],
         folder: str = "blocks") -> Path:
    """造一个只含 block tag 的假 jar，模拟版本 jar 里的 data/minecraft/tags。"""
    path = root / "versions" / version / f"{version}.jar"
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as jar:
        for name, values in tags.items():
            payload = json.dumps({"replace": False, "values": values}).encode("utf-8")
            jar.writestr(f"data/minecraft/tags/{folder}/{name}.json", payload)
        # 随便塞点别的文件，确保我们只挑 *_ores.json
        jar.writestr("data/minecraft/tags/blocks/mineable_pickaxe.json",
                     b'{"values":["minecraft:stone"]}')
    return path


class BuiltinFallbackTest(unittest.TestCase):
    def test_no_jar_uses_builtin(self):
        tmp = Path(tempfile.mkdtemp())
        rows = ore_tags.groups("1.12.2", tmp)
        self.assertTrue(rows)
        self.assertTrue(all(row["source"] == "builtin" for row in rows))
        slugs = [row["id"] for row in rows]
        self.assertIn("diamond", slugs)
        self.assertIn("quartz", slugs)      # 只在色表里、原版没有 tag 的也要在

    def test_builtin_covers_deepslate_variants(self):
        tmp = Path(tempfile.mkdtemp())
        rows = {row["id"]: row for row in ore_tags.groups("1.12.2", tmp)}
        self.assertIn("deepslate_iron_ore", rows["iron"]["blocks"])
        self.assertIn("iron_ore", rows["iron"]["blocks"])

    def test_labels_and_order(self):
        tmp = Path(tempfile.mkdtemp())
        rows = ore_tags.groups("1.12.2", tmp)
        self.assertEqual(rows[0]["id"], "coal")
        self.assertEqual(rows[0]["label"], "煤矿")
        self.assertTrue(all(len(row["color"]) == 3 for row in rows))


class GameTagTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_reads_version_jar_tags(self):
        _jar(self.tmp, "1.20.1", {
            "diamond_ores": ["minecraft:diamond_ore", "minecraft:deepslate_diamond_ore"],
            "copper_ores": ["minecraft:copper_ore", "minecraft:deepslate_copper_ore"],
        })
        rows = {row["id"]: row for row in ore_tags.groups("1.20.1", self.tmp)}
        self.assertEqual(rows["diamond"]["source"], "both")
        self.assertIn("deepslate_diamond_ore", rows["diamond"]["blocks"])
        self.assertIn("copper_ore", rows["copper"]["blocks"])

    def test_singular_tag_folder_for_new_versions(self):
        """1.20.5+ 把 tags/blocks 改成了 tags/block，两种都要认。"""
        _jar(self.tmp, "1.21.8", {"emerald_ores": ["minecraft:emerald_ore"]}, folder="block")
        rows = {row["id"]: row for row in ore_tags.groups("1.21.8", self.tmp)}
        self.assertIn("emerald_ore", rows["emerald"]["blocks"])
        self.assertIn(rows["emerald"]["source"], ("tag", "both"))

    def test_nested_tag_reference(self):
        _jar(self.tmp, "1.20.1", {
            "diamond_ores": ["minecraft:diamond_ore"],
            "gem_ores": ["#minecraft:diamond_ores", "minecraft:emerald_ore"],
        })
        rows = {row["id"]: row for row in ore_tags.groups("1.20.1", self.tmp)}
        self.assertIn("gem", rows)
        self.assertIn("diamond_ore", rows["gem"]["blocks"])
        self.assertIn("emerald_ore", rows["gem"]["blocks"])

    def test_datapack_adds_mod_ore(self):
        _jar(self.tmp, "1.20.1", {"diamond_ores": ["minecraft:diamond_ore"]})
        world = self.tmp / "world"
        pack = world / "datapacks" / "more_ores" / "data" / "minecraft" / "tags" / "blocks"
        pack.mkdir(parents=True)
        (pack / "zinc_ores.json").write_text(
            json.dumps({"values": ["mod:zinc_ore"]}), encoding="utf-8")
        rows = {row["id"]: row for row in ore_tags.groups("1.20.1", self.tmp, world)}
        self.assertIn("zinc", rows)
        self.assertIn("zinc_ore", rows["zinc"]["blocks"])

    def test_broken_jar_falls_back(self):
        bad = self.tmp / "versions" / "1.20.1" / "1.20.1.jar"
        bad.parent.mkdir(parents=True)
        bad.write_bytes(b"not a zip")
        rows = ore_tags.groups("1.20.1", self.tmp)
        self.assertTrue(rows)
        self.assertTrue(all(row["source"] == "builtin" for row in rows))

    def test_all_ore_blocks_union(self):
        _jar(self.tmp, "1.20.1", {"diamond_ores": ["minecraft:diamond_ore"]})
        blocks = ore_tags.all_ore_blocks("1.20.1", self.tmp)
        self.assertIn("diamond_ore", blocks)
        self.assertIn("ancient_debris", blocks)       # 内置表兜底的那些也要在


class PayloadTest(unittest.TestCase):
    def test_voxel_payload_has_ore_groups(self):
        from tests.creator_fixtures import build_level_dat
        from mc_launcher.voxel_view import build_voxel

        tmp = Path(tempfile.mkdtemp())
        _jar(tmp, "1.20.1", {"diamond_ores": ["minecraft:diamond_ore"]})
        world = tmp / "world"
        (world / "region").mkdir(parents=True)
        (world / "level.dat").write_bytes(build_level_dat(version_name="1.20.1"))
        # 已换回旧版体素：矿透走内置矿物表，不接 game_dir / ore_groups
        result = build_voxel(world, cx=0, cz=0, span=32, mode="ores")
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("mode"), "ores")
        # 瓦片网格必须落在 16 的整数倍上，前端才能对齐拼接
        self.assertEqual(result["origin"][0] % 16, 0)
        self.assertEqual(result["origin"][2] % 16, 0)
        self.assertEqual(result["span"], 32)


if __name__ == "__main__":
    unittest.main()


class AtlasSizeTest(unittest.TestCase):
    def test_atlas_height_is_power_of_two(self):
        """WebGL1 只有 2 的幂纹理能开 mipmap；行数必须补齐，否则整块贴图变黑。"""
        from mc_launcher.block_textures import Atlas, CELL

        for count in (1, 17, 33, 40, 49, 100):
            atlas = Atlas()
            for index in range(count):
                atlas.tile_for(f"t{index}", lambda: b"\x10" * (CELL * CELL * 3))
            _raw, width, height = atlas.png_bytes()
            self.assertEqual(width & (width - 1), 0, f"width {width}")
            self.assertEqual(height & (height - 1), 0, f"height {height} count {count}")
            self.assertGreaterEqual(height, ((count + 15) // 16) * CELL)
