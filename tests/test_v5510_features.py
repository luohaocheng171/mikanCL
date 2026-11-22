"""v5.5.10：全面渲染（种子补齐黑边）、地下矿脉视角、区块编辑器的回归测试。

这些测试只用内存 / 临时目录里的合成存档，不依赖 PySide6 或网络。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mc_launcher import chunk_editor as ce  # noqa: E402
from mc_launcher import save_map as sm  # noqa: E402
from mc_launcher import underground_view as uv  # noqa: E402


class FullRenderTest(unittest.TestCase):
    """合成高度字节应当把「没生成」的像素也画成地形，而不是留黑。"""

    def test_view_with_synthetic_fills_every_pixel(self):
        from tests.test_v560_save_map import build_world

        with tempfile.TemporaryDirectory() as tmp:
            world = build_world(Path(tmp) / "world")
            session = sm.SaveMapSession(world)
            session.expand(9999)
            size = 64
            full = bytes((i * 4) % 256 for i in range(size * size))
            plain = session.view(0, 0, 2048, size, "height")
            filled = session.view(0, 0, 2048, size, "height",
                                  synthetic=full,
                                  synth_params={"min_y": -64, "max_y": 320})
            self.assertTrue(filled["full_render"])
            self.assertGreater(filled.get("synthetic_pixels", 0), 0)
            self.assertGreater(filled["covered"], plain["covered"])
            self.assertIn("-full", Path(filled["png"]).name)
            self.assertLessEqual(filled["covered"], 1.0)

    def test_view_without_synthetic_keeps_old_behavior(self):
        from tests.test_v560_save_map import build_world

        with tempfile.TemporaryDirectory() as tmp:
            world = build_world(Path(tmp) / "world")
            session = sm.SaveMapSession(world)
            session.expand(9999)
            view = session.view(0, 0, 2048, 64, "height")
            self.assertFalse(view["full_render"])
            self.assertEqual(view.get("synthetic_pixels", 0), 0)


class UndergroundViewTest(unittest.TestCase):
    def test_public_api_contract(self):
        self.assertEqual(uv.list_ores("x"), uv.list_ores("x"))
        self.assertIsInstance(uv.ORE_COLORS, dict)
        self.assertIn("diamond_ore", uv.SUPPORTED_ORES)

    def test_render_on_empty_world_is_safe(self):
        from tests.test_v560_save_map import build_world

        with tempfile.TemporaryDirectory() as tmp:
            world = build_world(Path(tmp) / "world")
            data = uv.render_underground(world, size=64, span=512, y=64, mode="ore")
            self.assertTrue(data.get("ok"), data)
            self.assertTrue(Path(data["png"]).is_file())


class ChunkEditorTest(unittest.TestCase):
    def test_copy_clipboard_and_backup_safety(self):
        from tests.test_v560_save_map import build_world

        with tempfile.TemporaryDirectory() as tmp:
            world = build_world(Path(tmp) / "world")
            editor = ce.ChunkEditor(world)
            listed = editor.list_chunks()
            self.assertTrue(listed.get("ok"), listed)
            self.assertGreater(listed["count"], 0)
            target = (listed["chunks"][0]["x"], listed["chunks"][0]["z"])
            copied = editor.copy_chunks([list(target)], slot="t")
            self.assertTrue(copied.get("ok"), copied)
            info = editor.clipboard_info("t")
            self.assertTrue(info.get("ok"), info)
            self.assertEqual(info["count"], 1)

            deleted = editor.delete_chunks([list(target)])
            self.assertTrue(deleted.get("ok"), deleted)
            self.assertTrue(Path(deleted["backup"]).is_dir())
            after = editor.list_chunks()
            self.assertNotIn(target, [(c["x"], c["z"]) for c in after["chunks"]])


if __name__ == "__main__":
    unittest.main()


class World3DTest(unittest.TestCase):
    def test_grid_payload_is_consistent(self):
        import base64
        import struct
        from tests.test_v560_save_map import build_world
        from mc_launcher.world_3d import build_grid

        with tempfile.TemporaryDirectory() as tmp:
            world = build_world(Path(tmp) / "world")
            g = build_grid(world, max_cells=64)
            self.assertTrue(g["ok"])
            n = g["nx"] * g["nz"]
            heights = struct.unpack("<%dh" % n, base64.b64decode(g["heights"]))
            colors = base64.b64decode(g["colors"])
            water = struct.unpack("<%dh" % n, base64.b64decode(g["water"]))
            self.assertEqual(len(heights), n)
            self.assertEqual(len(colors), n)
            self.assertEqual(len(water), n)
            self.assertTrue(g["palette"])
            self.assertGreaterEqual(g["step"], 1)


class VersionGroupingTest(unittest.TestCase):
    def test_save_list_has_version_and_grouping(self):
        import inspect
        from mc_launcher.ui_web.shell import WebApi

        src = inspect.getsource(WebApi.seed_saves)
        self.assertIn('"version": version', src)
        # HTML helper should group by <optgroup>
        js = open(ROOT / "mc_launcher/ui_web/web/app.js", encoding="utf-8").read()
        self.assertIn("<optgroup label=", js)
        self.assertIn("saveVersionField", js)
        # option values must be HTML-escaped, not URL-encoded
        self.assertIn("'<option value=\"' + esc(item.path)", js)

    def test_height_out_of_range_is_clamped_or_failed(self):
        from tests.test_v560_save_map import build_world
        from mc_launcher.save_map import SaveMapSession

        with tempfile.TemporaryDirectory() as tmp:
            world = build_world(Path(tmp) / "world")
            session = SaveMapSession(world)
            session.expand(99999)
            self.assertGreater(len(session.heights), 0)
            for maps in session.heights.values():
                for values in maps.values():
                    for value in values:
                        self.assertGreaterEqual(value, session.min_y)
                        self.assertLessEqual(value, session.max_y)


class Round3FixesTest(unittest.TestCase):
    def test_dependency_center_crud(self):
        import tempfile as _tmp
        from pathlib import Path as _Path
        from unittest import mock as _mock
        from mc_launcher import dependency_center as dc

        with _tmp.TemporaryDirectory() as tmp:
            store = _Path(tmp) / "deps.json"
            with _mock.patch.object(dc, "STORE", store):
                dc.add_item({"id": "test", "name": "测试依赖", "kind": "tool",
                             "repo": "a/b", "tags": ["x"]})
                rows = dc.list_items()["items"]
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["name"], "测试依赖")
                dc.set_enabled("test", False)
                self.assertFalse(dc.list_items()["items"][0]["enabled"])
                self.assertTrue(dc.remove_item("test")["ok"])

    def test_nbt_pro_formats(self):
        from mc_launcher.nbt_pro import (detect_encoding, get_path, load_any,
                                         parse_snbt, set_path, to_snbt,
                                         validate, write_any)

        root = parse_snbt('{a:1,b:{c:[1,2,3]},d:"hi"}')
        self.assertTrue(validate(root)["ok"])
        set_path(root, "/b/c[1]", 99)
        self.assertEqual(get_path(root, "/b/c[1]"), 99)
        self.assertIn('"a"', to_snbt(root))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.snbt"
            write_any(path, root, "snbt")
            self.assertIn(detect_encoding(path.read_bytes()), ("json", "snbt"))
            self.assertEqual(load_any(path)["root"]["a"], 1)

    def test_external_tool_version_selection(self):
        from mc_launcher.ui_web.shell import WebApi

        api = WebApi.__new__(WebApi)
        self.assertEqual(api._version_minor("1.8.9"), 8)
        self.assertEqual(api.external_tool_for_version("1.20.1")["key"], "mcaselector")
        self.assertEqual(api.external_tool_for_version("1.21.4")["key"], "mcsave")

    def test_last_launched_version_ordering(self):
        src = open(ROOT / "mc_launcher/ui_web/shell.py", encoding="utf-8").read()
        self.assertIn("last_launched_version", src)
        cfg = open(ROOT / "mc_launcher/config.py", encoding="utf-8").read()
        self.assertIn("last_launched_version: str", cfg)

    def test_path_normalization_and_no_dead_pages(self):
        shell = open(ROOT / "mc_launcher/ui_web/shell.py", encoding="utf-8").read()
        self.assertIn("def _clean_path", shell)
        js = open(ROOT / "mc_launcher/ui_web/web/app.js", encoding="utf-8").read()
        self.assertIn("['deps', '依赖中心', 'deps']", js)
        self.assertNotIn("['underworld', '地下世界'", js)
        self.assertNotIn("underworld_view", js)

    def test_full_generation_params(self):
        src = open(ROOT / "mc_launcher/seed_world.py", encoding="utf-8").read()
        self.assertIn("radius_chunks", src)
        self.assertIn("full_generation", src)
        self.assertIn("forceload add", src)
