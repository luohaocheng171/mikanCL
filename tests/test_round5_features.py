"""第五轮：地图铺满面板、第三方组件中心、增强数据包、内存工具的回归测试。

只依赖临时目录和合成数据，不碰网络、不需要 PySide6。
"""

from __future__ import annotations

import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mc_launcher import cheat_pack as cp  # noqa: E402
from mc_launcher import save_map as sm  # noqa: E402
from mc_launcher import thirdparty as tp  # noqa: E402


def png_size(path: Path) -> tuple[int, int]:
    data = Path(path).read_bytes()
    width, height = struct.unpack(">II", data[16:24])
    return width, height


class MapAspectTest(unittest.TestCase):
    """地图要按面板宽高比出图，不能永远是正方形。"""

    def test_view_fills_wide_panel(self):
        from tests.test_v560_save_map import build_world

        with tempfile.TemporaryDirectory() as tmp:
            world = build_world(Path(tmp) / "world")
            session = sm.SaveMapSession(world)
            session.expand(9999)
            view = session.view(0, 0, 1024, 384, "height", size_h=160)
            self.assertTrue(view["ok"])
            self.assertEqual(view["px"], 384)
            self.assertEqual(view["px_h"], 160)
            # 纵向跨度按像素比例缩小
            self.assertAlmostEqual(view["span"], 1024, delta=1)
            self.assertAlmostEqual(view["span_z"], 1024 * 160 / 384, delta=1)
            width, height = png_size(Path(view["png"]))
            self.assertEqual((width, height), (384, 160))
            x0, z0, x1, z1 = view["bounds"]
            self.assertGreater(x1 - x0, z1 - z0)

    def test_synthetic_still_fills_non_square(self):
        from tests.test_v560_save_map import build_world

        with tempfile.TemporaryDirectory() as tmp:
            world = build_world(Path(tmp) / "world")
            session = sm.SaveMapSession(world)
            size = 128
            noise = bytes((i * 3) % 256 for i in range(size * size))
            view = session.view(4096, 4096, 4096, 256, "height",
                                synthetic=noise,
                                synth_params={"min_y": -64, "max_y": 320},
                                size_h=128)
            self.assertGreater(view["synthetic_pixels"], 0)
            self.assertGreater(view["covered"], 0.9)


class CheatPackTest(unittest.TestCase):
    def test_write_read_remove(self):
        from tests.test_v560_save_map import build_world

        with tempfile.TemporaryDirectory() as tmp:
            world = build_world(Path(tmp) / "world")
            folder = cp.write_pack(world, "1.20.1", ["no_damage", "no_knockback", "noclip"])
            self.assertTrue((folder / "pack.mcmeta").is_file())
            # 1.20.1 用复数目录（functions/）
            tick = folder / "data/mikancl/functions/tick.mcfunction"
            self.assertTrue(tick.is_file())
            body = tick.read_text(encoding="utf-8")
            self.assertIn("minecraft:resistance", body)
            self.assertIn("knockback_resistance", body)
            self.assertIn("mikancl.noclip", body)
            state = cp.pack_state(world)
            self.assertTrue(state["installed"])
            self.assertEqual(set(state["options"]), {"no_damage", "no_knockback", "noclip"})
            self.assertTrue(cp.remove_pack(world))
            self.assertFalse(cp.pack_state(world)["installed"])

    def test_modern_layout_and_attribute_name(self):
        from tests.test_v560_save_map import build_world

        with tempfile.TemporaryDirectory() as tmp:
            world = build_world(Path(tmp) / "world")
            folder = cp.write_pack(world, "1.21.4", ["no_knockback"])
            tick = folder / "data/mikancl/function/tick.mcfunction"
            self.assertTrue(tick.is_file())
            body = tick.read_text(encoding="utf-8")
            # 1.21.2 起去掉了 generic. 前缀
            self.assertIn("minecraft:knockback_resistance", body)
            self.assertNotIn("generic.knockback_resistance", body)

    def test_enable_commands_keeps_level_dat_readable(self):
        """打开「允许作弊」后 level.dat 必须还是 gzip，否则游戏判定存档损坏。"""
        import gzip

        from mc_launcher import nbt_pro
        from mc_launcher.nbt import write_nbt

        with tempfile.TemporaryDirectory() as tmp:
            world = Path(tmp)
            level = world / "level.dat"
            level.write_bytes(gzip.compress(write_nbt("", {
                "Data": {"allowCommands": 0, "LevelName": "w"},
            })))
            self.assertTrue(cp.enable_commands(level))
            self.assertEqual(level.read_bytes()[:2], b"\x1f\x8b")
            loaded = nbt_pro.load_any(level)
            self.assertEqual(loaded["root"]["Data"]["allowCommands"], 1)
            self.assertTrue((world / "level.dat.bak").is_file(), "改之前要留备份")

    def test_datapack_version_gate(self):
        self.assertTrue(cp.supports_datapack("1.13"))
        self.assertTrue(cp.supports_datapack("1.21.4"))
        self.assertFalse(cp.supports_datapack("1.12.2"))
        self.assertFalse(cp.supports_datapack("1.8.9"))


class ThirdPartyTest(unittest.TestCase):
    def test_catalog_has_groups_and_core_projects(self):
        status = tp.status()
        self.assertTrue(status["ok"])
        names = [item["name"] for item in status["items"]]
        self.assertTrue(any("陶瓦联机" in name for name in names))
        self.assertTrue(any("MCA Selector" == name for name in names))
        self.assertTrue(any("NBT Studio" in name for name in names))
        groups = [group["name"] for group in status["groups"]]
        self.assertIn("联机", groups)
        self.assertIn("NBT 工具", groups)

    def test_asset_pick_prefers_64bit_windows(self):
        assets = [
            {"name": "tool-linux-x86_64.tar.gz", "size": 1},
            {"name": "tool-windows-i686.zip", "size": 1},
            {"name": "tool-windows-x86_64.zip", "size": 1},
        ]
        picked = tp._pick_asset(assets, {"ext": ".zip", "hints": ["windows"]})
        self.assertIsNotNone(picked)
        self.assertEqual(picked["name"], "tool-windows-x86_64.zip")

    def test_launcher_lookup_uses_expected_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "sub").mkdir()
            exe = folder / "sub" / "NbtStudio.exe"
            exe.write_bytes(b"MZ" + b"\x00" * 4096)
            found = tp._find_launcher(folder, "NbtStudio.exe")
            self.assertIsNotNone(found)
            self.assertEqual(found.name, "NbtStudio.exe")


class TrainerTest(unittest.TestCase):
    def test_status_shape(self):
        from mc_launcher import game_trainer

        session = game_trainer.session()
        status = session.status()
        self.assertIn("available", status)
        self.assertIn("processes", status)
        self.assertIn("frozen", status)
        self.assertIsInstance(status["frozen"], list)

    def test_kind_tables_consistent(self):
        from mc_launcher import game_trainer

        for kind, size in game_trainer.KIND_SIZE.items():
            self.assertEqual(size, struct.calcsize(game_trainer.KIND_FMT[kind]))


class NbtProCompressionTest(unittest.TestCase):
    """level.dat 是 gzip 的，读要能解压、写要按原压缩方式写回。"""

    def _make_level_dat(self, tmp: Path) -> Path:
        import gzip

        from mc_launcher.nbt import write_nbt

        root = {
            "Data": {
                "LevelName": "测试世界",
                "allowCommands": 1,
                "version": 19133,
                "SpawnX": 0,
                "raining": False,
            }
        }
        path = tmp / "level.dat"
        path.write_bytes(gzip.compress(write_nbt("", root)))
        return path

    def test_loads_gzip_dat(self):
        from mc_launcher import nbt_pro

        with tempfile.TemporaryDirectory() as tmp:
            path = self._make_level_dat(Path(tmp))
            loaded = nbt_pro.load_any(path)
            self.assertEqual(loaded["compression"], "gzip")
            self.assertEqual(loaded["encoding"], "java")
            self.assertEqual(loaded["root"]["Data"]["LevelName"], "测试世界")

    def test_write_keeps_gzip(self):
        import gzip

        from mc_launcher import nbt_pro

        with tempfile.TemporaryDirectory() as tmp:
            path = self._make_level_dat(Path(tmp))
            loaded = nbt_pro.load_any(path)
            loaded["root"]["Data"]["allowCommands"] = 0
            nbt_pro.write_any(path, loaded["root"], "java")
            raw = path.read_bytes()
            self.assertEqual(raw[:2], b"\x1f\x8b", "写回后必须还是 gzip")
            self.assertEqual(nbt_pro.compression_of(raw), "gzip")
            again = nbt_pro.load_any(path)
            self.assertEqual(again["root"]["Data"]["allowCommands"], 0)
            # 内容仍是合法 gzip，能被标准库解开
            self.assertIn(b"allowCommands", gzip.decompress(raw))

    def test_plain_nbt_stays_plain(self):
        from mc_launcher import nbt_pro
        from mc_launcher.nbt import write_nbt

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plain.nbt"
            path.write_bytes(write_nbt("", {"value": 7}))
            loaded = nbt_pro.load_any(path)
            self.assertEqual(loaded["compression"], "none")
            nbt_pro.write_any(path, loaded["root"], "java")
            self.assertEqual(nbt_pro.compression_of(path.read_bytes()), "none")


class DynamicLoadTest(unittest.TestCase):
    """动态加载：未解压的区块要先报出来，前端才知道还要继续补。"""

    def test_pending_reported_before_expand(self):
        from tests.test_v560_save_map import build_world

        with tempfile.TemporaryDirectory() as tmp:
            world = build_world(Path(tmp) / "world")
            session = sm.SaveMapSession(world)
            view = session.view(0, 0, 1024, 256, "height", size_h=128)
            self.assertGreater(view["pending_chunks"], 0)
            self.assertGreater(view["pending_pixels"], 0)
            session.expand(9999)
            done = session.view(0, 0, 1024, 256, "height", size_h=128)
            self.assertEqual(done["pending_chunks"], 0)
            self.assertEqual(done["pending_pixels"], 0)


class TrainerCommandTest(unittest.TestCase):
    """无碰撞飞行走 tp，不改游戏模式。"""

    def test_tpfly_pack_uses_trigger_and_tp(self):
        from tests.test_v560_save_map import build_world

        with tempfile.TemporaryDirectory() as tmp:
            world = build_world(Path(tmp) / "world")
            folder = cp.write_pack(world, "1.20.1", ["tpfly"])
            body = (folder / "data/mikancl/functions/tick.mcfunction").read_text(encoding="utf-8")
            self.assertIn("mikancl.flytrig", body)
            self.assertIn("tp @s ^ ^ ^0.45", body)
            # 不能靠切游戏模式
            self.assertNotIn("gamemode", body)
            self.assertIn("tpfly", cp.pack_state(world)["options"])


class PlayerDataTest(unittest.TestCase):
    """玩家数据：读得出来、写得回去、写前留备份。"""

    def _world(self, tmp):
        import gzip

        from mc_launcher.nbt import write_nbt

        world = Path(tmp) / "world"
        (world / "playerdata").mkdir(parents=True)
        root = {
            "Health": 20.0,
            "foodLevel": 20,
            "XpLevel": 5,
            "Inventory": [{"Slot": 0, "id": "minecraft:stone", "Count": 3}],
            "Pos": [1.5, 64.0, 2.5],
            "Dimension": "minecraft:overworld",
        }
        (world / "playerdata" / "abc.dat").write_bytes(gzip.compress(write_nbt("", root)))
        return world

    def test_read_and_write(self):
        from mc_launcher import player_data as pd

        with tempfile.TemporaryDirectory() as tmp:
            world = self._world(tmp)
            listing = pd.list_players(world)
            self.assertEqual(len(listing["items"]), 1)
            info = pd.read_player(world, "abc.dat")
            self.assertTrue(info["ok"])
            self.assertEqual(info["values"]["foodLevel"], 20)
            self.assertEqual(info["values"]["Inventory"], 1)
            result = pd.write_player(world, "abc.dat", {"Health": 6, "foodLevel": 3, "XpLevel": 30})
            self.assertTrue(result["ok"], result.get("message"))
            again = pd.read_player(world, "abc.dat")
            self.assertAlmostEqual(float(again["values"]["Health"]), 6.0, places=3)
            self.assertEqual(again["values"]["foodLevel"], 3)
            self.assertEqual(again["values"]["XpLevel"], 30)
            self.assertTrue((world / "playerdata" / "abc.dat.bak").is_file())
            # 背包 / 坐标没被写丢
            self.assertEqual(again["values"]["Inventory"], 1)

    def test_rejects_unknown_fields(self):
        from mc_launcher import player_data as pd

        with tempfile.TemporaryDirectory() as tmp:
            world = self._world(tmp)
            result = pd.write_player(world, "abc.dat", {"Inventory": []})
            self.assertFalse(result["ok"])


class ThirdPartyLaunchTest(unittest.TestCase):
    def test_status_reports_running(self):
        status = tp.status()
        for row in status["items"]:
            self.assertIn("running", row)
            self.assertIn("pid", row)
        self.assertFalse(tp.stop("not-installed")["ok"])


class HeightmapPackingTest(unittest.TestCase):
    """1.16+ 的高度图是「每 long 7 个 9bit 值、不跨 long」，解错就是满屏条纹。"""

    def _pack_flat(self, values, bits=9, per=7):
        longs = []
        for start in range(0, len(values), per):
            chunk = values[start:start + per]
            word = 0
            for index, item in enumerate(chunk):
                word |= (int(item) & ((1 << bits) - 1)) << (bits * index)
            if word >= (1 << 63):
                word -= 1 << 64
            longs.append(word)
        return longs

    def test_flat_layout_roundtrip(self):
        from mc_launcher.world_render import unpack_heightmap

        values = []
        for z in range(16):
            for x in range(16):
                values.append(64 + (z // 5))
        longs = self._pack_flat(values)
        # 37 个 long（256 个 9bit 值按 7/long 装）
        self.assertEqual(len(longs), 37)
        out = unpack_heightmap(longs, 256)
        self.assertEqual(out[:16], values[:16])
        self.assertEqual(max(out), max(values))

    def test_prefers_smooth_layout(self):
        from mc_launcher.world_render import _roughness, unpack_heightmap

        smooth = [63 + (i % 3) for i in range(256)]
        out = unpack_heightmap(self._pack_flat(smooth), 256)
        self.assertLessEqual(_roughness(out), _roughness(smooth) + 1)


if __name__ == "__main__":
    unittest.main()
