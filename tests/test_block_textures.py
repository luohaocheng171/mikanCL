"""方块贴图：按 id 找贴图、灰度贴图染色、透明像素处理。

这三条是之前 3D 视图「整片灰」「纹理错位/错行」的直接原因，锁成测试防止回潮。
"""
from __future__ import annotations

import struct
import unittest
import zlib

from mc_launcher import block_textures as bt


def _png(width: int, height: int, rgba: bytes) -> bytes:
    """手搓一张 RGBA PNG（测试用，避免依赖 PIL）。"""
    raw = b"".join(b"\x00" + bytes(rgba[y * width * 4:(y + 1) * width * 4])
                   for y in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class DecodeTest(unittest.TestCase):
    def test_rgba_keeps_alpha(self):
        png = _png(2, 1, bytes([10, 20, 30, 255, 40, 50, 60, 0]))
        width, height, pixels = bt.decode_png(png, alpha=True)
        self.assertEqual((width, height), (2, 1))
        self.assertEqual(len(pixels), 8)
        self.assertEqual(pixels[3], 255)
        self.assertEqual(pixels[7], 0)

    def test_rgb_drops_alpha(self):
        png = _png(1, 1, bytes([10, 20, 30, 128]))
        width, height, pixels = bt.decode_png(png)
        self.assertEqual((width, height, len(pixels)), (1, 1, 3))
        self.assertEqual(tuple(pixels), (10, 20, 30))


class TextureFaceTest(unittest.TestCase):
    def test_special_blocks(self):
        self.assertEqual(bt.texture_faces("grass_block"),
                         ("grass_block_top", "grass_block_side", "dirt"))
        self.assertEqual(bt.texture_faces("water"),
                         ("water_still", "water_still", "water_still"))

    def test_log_uses_top_texture(self):
        self.assertEqual(bt.texture_faces("oak_log"),
                         ("oak_log_top", "oak_log", "oak_log_top"))
        self.assertEqual(bt.texture_faces("crimson_stem"),
                         ("crimson_stem_top", "crimson_stem", "crimson_stem_top"))

    def test_slab_uses_base_block(self):
        self.assertEqual(bt.texture_faces("stone_slab"), ("stone", "stone", "stone"))
        self.assertEqual(bt.texture_faces("cobblestone_wall"),
                         ("cobblestone", "cobblestone", "cobblestone"))
        self.assertEqual(bt.texture_faces("oak_stairs"),
                         ("oak_planks", "oak_planks", "oak_planks"))

    def test_plain_block_is_itself(self):
        self.assertEqual(bt.texture_faces("diamond_ore"),
                         ("diamond_ore", "diamond_ore", "diamond_ore"))


class TintTest(unittest.TestCase):
    def test_tint_keeps_brightness(self):
        tint = bt._tint_color((94, 152, 72))
        self.assertEqual(max(tint), 235)
        self.assertGreater(tint[1], tint[0])      # 绿 > 红
        self.assertGreater(tint[1], tint[2])

    def test_gray_block_stays_neutral(self):
        tint = bt._tint_color((126, 126, 126))
        self.assertEqual(len(set(tint)), 1)

    def test_grayscale_grass_becomes_green(self):
        """草方块顶面是灰度图，染色后必须变绿，而不是一片灰。"""
        rgba = bytes([150, 150, 150, 255]) * (16 * 16)
        rgb = bt._prepare(rgba, 16, 16, (94, 152, 72))
        r, g, b = rgb[:3]
        self.assertGreater(g, r)
        self.assertGreater(g, b)

    def test_transparent_pixels_take_block_color(self):
        """树叶/草的透明像素按方块颜色填，不再压成黑色麻点。"""
        rgba = bytes([0, 0, 0, 0]) + bytes([255, 255, 255, 255]) * (16 * 16 - 1)
        rgb = bt._prepare(rgba, 16, 16, (66, 122, 56))
        self.assertGreater(rgb[1], 40)


class AtlasLayoutTest(unittest.TestCase):
    """图集尺寸：WebGL1 只有 2 的幂纹理能开 mipmap，否则采样直接变黑。"""

    def test_png_height_is_power_of_two(self):
        for count in (1, 17, 33, 40, 49, 100):
            atlas = bt.Atlas()
            for index in range(count):
                atlas.tile_for(f"t{index}", lambda: b"\x10" * (bt.CELL * bt.CELL * 3))
            _raw, width, height = atlas.png_bytes()
            self.assertEqual(width & (width - 1), 0, f"width {width}")
            self.assertEqual(height & (height - 1), 0, f"height {height} count {count}")
            self.assertGreaterEqual(height, ((count + bt.COLS - 1) // bt.COLS) * bt.CELL)

    def test_build_atlas_rows_match_png(self):
        """rows 必须按补齐后的图片高度算，否则前端 ch=1/rows 会让 UV 整体错位。"""
        import tempfile
        import zipfile
        from pathlib import Path

        game = Path(tempfile.mkdtemp())
        version = "1.20.1"
        jar_path = game / "versions" / version / f"{version}.jar"
        jar_path.parent.mkdir(parents=True)
        with zipfile.ZipFile(jar_path, "w") as jar:
            jar.writestr("assets/minecraft/textures/block/stone.png",
                         _png(16, 16, bytes([126, 126, 126, 255]) * (16 * 16)))
        materials = [{"name": f"mod_block_{index}", "color": [100, 100, 100]}
                     for index in range(33)]
        materials.append({"name": "stone", "color": [126, 126, 126]})
        atlas = bt.build_atlas(version, str(game), materials)
        self.assertTrue(atlas["ok"], atlas.get("message"))
        width, height, _pixels = bt.decode_png(Path(atlas["png"]).read_bytes())
        self.assertEqual(width, atlas["cols"] * atlas["cell"])
        self.assertEqual(height, atlas["rows"] * atlas["cell"])
        self.assertEqual(height & (height - 1), 0)
        # 34 个材质 → 3 行 → 补到 4 行
        self.assertEqual(atlas["rows"], 4)

    def test_atlas_format_changes_cache_key(self):
        """图集格式（padding / UV 规则）改了必须换文件名，不能命中旧 PNG。"""
        import tempfile
        import zipfile
        from pathlib import Path

        game = Path(tempfile.mkdtemp())
        version = "1.20.1"
        jar_path = game / "versions" / version / f"{version}.jar"
        jar_path.parent.mkdir(parents=True)
        with zipfile.ZipFile(jar_path, "w") as jar:
            jar.writestr("assets/minecraft/textures/block/stone.png",
                         _png(16, 16, bytes([126, 126, 126, 255]) * (16 * 16)))
        materials = [{"name": "stone", "color": [126, 126, 126]}]
        first = bt.build_atlas(version, str(game), materials)
        original = bt.ATLAS_FORMAT
        try:
            bt.ATLAS_FORMAT = original + "-next"
            second = bt.build_atlas(version, str(game), materials)
        finally:
            bt.ATLAS_FORMAT = original
        self.assertTrue(first["ok"] and second["ok"])
        self.assertNotEqual(Path(first["png"]).name, Path(second["png"]).name)


if __name__ == "__main__":
    unittest.main()
