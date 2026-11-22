"""v5.6.0：存档地图会话（缩放 / 增量渲染 / 找目标）+ 版本目录的单元测试。

覆盖：
- 版本解析与「该版本支持哪些建筑 / 群系」的过滤；
- 会话索引：只读 region 头就能报出区块总数与范围；
- 增量渲染：expand 之后再 view，覆盖率上升、已解压区块复用；
- 视窗出图：中心 / 跨度 / 像素与 bounds 一致，图层切换出不同颜色；
- 群系连通块：相邻同群系区块合成一个圆形标记；
- 查找目标：找到 → 再查下一个 → 没有了就报 exhausted；单次上限报 capped；
- WebApi 桥：save_map_open / view / expand / find / catalog / discard 走通。
"""

from __future__ import annotations

import gzip
import inspect
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mc_launcher import save_map as sm  # noqa: E402
from mc_launcher import world_catalog as wc  # noqa: E402
from mc_launcher.world_render import EMPTY_RGB  # noqa: E402
from mc_launcher.nbt import (  # noqa: E402
    TAG_COMPOUND,
    TAG_INT,
    TAG_INT_ARRAY,
    TAG_LIST,
    TAG_LONG_ARRAY,
    TAG_STRING,
    write_nbt_typed,
)
from tests.creator_fixtures import make_region  # noqa: E402


def pack_long_stream(values, bits: int) -> list[int]:
    mask = (1 << bits) - 1
    total = (len(values) * bits + 63) // 64
    out = [0] * total
    for index, value in enumerate(values):
        offset = index * bits
        slot, shift = divmod(offset, 64)
        value &= mask
        out[slot] |= (value << shift) & 0xFFFFFFFFFFFFFFFF
        if shift + bits > 64:
            out[slot + 1] |= (value >> (64 - shift)) & mask
    return [value - (1 << 64) if value >= (1 << 63) else value for value in out]


def _c(**kwargs):
    return (TAG_COMPOUND, {name: node for name, node in kwargs.items()})


def _i(value):
    return (TAG_INT, int(value))


def _s(value):
    return (TAG_STRING, str(value))


def _list(element_tag, items):
    return (TAG_LIST, (element_tag, list(items)))


def chunk_bytes(chunk_x: int, chunk_z: int, heights: list[int], floors: list[int],
                biome_id: int = 1, structure: str = "") -> bytes:
    """1.14 风格区块：Level.Heightmaps + Level.Biomes + Level.Structures。"""
    starts = {}
    if structure:
        starts[structure] = _c(ChunkX=_i(chunk_x), ChunkZ=_i(chunk_z),
                               id=_s(structure), references=_i(0))
    level = _c(
        xPos=_i(chunk_x),
        zPos=_i(chunk_z),
        Status=_s("full"),
        Heightmaps=_c(
            MOTION_BLOCKING=(TAG_LONG_ARRAY, pack_long_stream(heights, 9)),
            OCEAN_FLOOR=(TAG_LONG_ARRAY, pack_long_stream(floors, 9)),
        ),
        Biomes=(TAG_INT_ARRAY, [int(biome_id)] * 256),
        Sections=_list(TAG_COMPOUND, [
            _c(Y=_i(4), Palette=_list(TAG_COMPOUND, [_c(Name=_s("minecraft:stone"))])),
        ]),
        Structures=_c(Starts=_c(**starts), References=_c()),
    )
    root = _c(Level=level, DataVersion=_i(1976))
    return zlib.compress(write_nbt_typed("", root))


def level_dat(seed: int = 114514, spawn=(8, 8)) -> bytes:
    data = _c(
        LevelName=_s("InteractiveTest"),
        seed=(TAG_INT, int(seed)),
        SpawnX=_i(spawn[0]),
        SpawnZ=_i(spawn[1]),
        Version=_c(Name=_s("1.14.4")),
        DataVersion=_i(1976),
    )
    return gzip.compress(write_nbt_typed("", _c(Data=data)))


def build_world(root: Path, chunks: dict | None = None, name: str = "InteractiveTest") -> Path:
    """造一个 4 区块（2×2）的存档：沙漠两列相邻，其中一格有村庄。"""
    world = root / name
    (world / "region").mkdir(parents=True)
    (world / "level.dat").write_bytes(level_dat())
    plains = [64] * 256
    desert = [70] * 256
    if chunks is None:
        chunks = {
            (0, 0): chunk_bytes(0, 0, plains, [63] * 256, biome_id=1),
            (1, 0): chunk_bytes(1, 0, desert, [69] * 256, biome_id=2, structure="Minecraft:village"),
            (0, 1): chunk_bytes(0, 1, plains, [63] * 256, biome_id=1),
            (1, 1): chunk_bytes(1, 1, desert, [69] * 256, biome_id=2),
        }
    make_region(world / "region" / "r.0.0.mca", chunks)
    return world


def read_png(path: Path) -> tuple[int, int, bytes]:
    data = Path(path).read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos = 8
    width = height = 0
    idat = b""
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if tag == b"IHDR":
            width, height = struct.unpack(">II", body[:8])
        elif tag == b"IDAT":
            idat += body
    return width, height, zlib.decompress(idat)


class VersionCatalogTest(unittest.TestCase):
    def test_parse_version(self):
        self.assertEqual(wc.parse_version("1.20.1"), (1, 20, 1))
        self.assertEqual(wc.parse_version("1.7.10"), (1, 7, 10))
        self.assertEqual(wc.parse_version("b1.7.3"), (0, 1, 7))
        self.assertEqual(wc.parse_version("a1.2.6"), (0, 0, 2))
        # 解析不出来按最新版处理，宁可多给目标也不要藏起来
        self.assertEqual(wc.parse_version(""), (99, 0, 0))
        self.assertEqual(wc.parse_version("23w13a"), (99, 0, 0))

    def test_catalog_filters_by_version(self):
        old = wc.catalog("1.12.2")
        self.assertFalse(old["ok"] is False)
        self.assertNotIn("trial_chambers", old["available_structures"])
        self.assertNotIn("ancient_city", old["available_structures"])
        self.assertIn("village", old["available_structures"])
        self.assertIn("ocean_monument", old["available_structures"])
        self.assertNotIn("cherry_grove", old["available_biomes"])
        self.assertIn("plains", old["available_biomes"])

        new = wc.catalog("1.21.4")
        for kind in ("trial_chambers", "ancient_city", "trail_ruins", "bastion"):
            self.assertIn(kind, new["available_structures"])
        self.assertIn("cherry_grove", new["available_biomes"])
        self.assertIn("deep_dark", new["available_biomes"])

    def test_beta_only_has_early_structures(self):
        beta = wc.catalog("b1.8.1")
        self.assertIn("village", beta["available_structures"])
        self.assertNotIn("jungle_temple", beta["available_structures"])
        self.assertNotIn("pillager_outpost", beta["available_structures"])

    def test_catalog_rows_carry_labels(self):
        rows = wc.catalog("1.20.1")["structures"]
        village = [row for row in rows if row["kind"] == "village"][0]
        self.assertEqual(village["name"], "村庄")
        self.assertTrue(village["color"].startswith("#"))
        self.assertTrue(all("available" in row for row in rows))


class SessionTest(unittest.TestCase):
    def test_index_without_decoding(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = build_world(Path(tmp))
            session = sm.SaveMapSession(world)
            state = session.state()
            self.assertEqual(state["chunks_total"], 4)
            self.assertEqual(state["chunks_done"], 0)
            self.assertFalse(state["exhausted"])
            self.assertEqual(state["seed"], "114514")
            self.assertEqual(state["version"], "1.14.4")
            self.assertEqual(state["sea_level"], 63)
            # 出生点 (8, 8) 落在存档里，中心就该用它
            self.assertEqual(state["center"], [8.0, 8.0])

    def test_expand_is_incremental(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = build_world(Path(tmp))
            session = sm.SaveMapSession(world)
            first = session.expand(2)
            self.assertEqual(first["chunks_done"], 2)
            second = session.expand(2)
            self.assertEqual(second["chunks_done"], 4)
            self.assertTrue(second["exhausted"])
            # 再解压不会重复计数
            third = session.expand(2)
            self.assertEqual(third["chunks_done"], 4)
            self.assertEqual(third["added"], 0)

    def test_view_reports_bounds_and_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = build_world(Path(tmp))
            session = sm.SaveMapSession(world)
            session.expand(4)
            view = session.view(8, 8, 512, 256, "height")
            self.assertEqual(view["px"], 256)
            self.assertEqual(view["radius"], 256.0)
            self.assertEqual(view["bounds"], [-248.0, -248.0, 264.0, 264.0])
            self.assertGreater(view["chunks_in_view"], 0)
            self.assertGreater(view["covered"], 0.0)
            self.assertLess(view["covered"], 1.0)   # 4 个区块铺不满 512×512
            self.assertEqual(view["chunks_done"], 4)
            self.assertEqual(view["height"]["min"], 64)
            self.assertEqual(view["height"]["max"], 70)
            width, height, raw = read_png(Path(view["png"]))
            self.assertEqual((width, height), (256, 256))
            self.assertEqual(len(raw), 256 * (1 + 256 * 3))

    def test_pending_chunks_are_marked_separately(self):
        """只解压一半时，没解压的区块应该画成「待渲染」色，和「没生成」区分开。"""
        with tempfile.TemporaryDirectory() as tmp:
            world = build_world(Path(tmp))
            session = sm.SaveMapSession(world)
            session.expand(2)
            view = session.view(8, 8, 384, 128, "height")
            _w, _h, raw = read_png(Path(view["png"]))
            stride = 1 + 128 * 3
            colors = set()
            for row in range(128):
                line = raw[row * stride + 1:(row + 1) * stride]
                for col in range(0, len(line), 3):
                    colors.add(bytes(line[col:col + 3]))
            self.assertIn(bytes(sm.PENDING_RGB), colors)
            self.assertIn(bytes(EMPTY_RGB), colors)

    def test_view_is_deterministic_and_layer_aware(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = build_world(Path(tmp))
            session = sm.SaveMapSession(world)
            session.expand(4)
            first = session.view(8, 8, 384, 192, "height")
            payload_a = Path(first["png"]).read_bytes()
            second = session.view(8, 8, 384, 192, "height")
            self.assertEqual(payload_a, Path(second["png"]).read_bytes())
            biome = session.view(8, 8, 384, 192, "biome")
            self.assertNotEqual(payload_a, Path(biome["png"]).read_bytes())
            self.assertEqual(biome["layer"], "biome")

    def test_empty_region_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = Path(tmp) / "Empty"
            (world / "region").mkdir(parents=True)
            (world / "level.dat").write_bytes(level_dat())
            with self.assertRaises(ValueError):
                sm.SaveMapSession(world)
            missing = Path(tmp) / "NoLevel"
            missing.mkdir()
            with self.assertRaises(ValueError):
                sm.SaveMapSession(missing)

    def test_biome_patches_merge_neighbours(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = build_world(Path(tmp))
            session = sm.SaveMapSession(world)
            session.expand(4)
            patches = session.biome_patches()
            by_name = {row["name"]: row for row in patches}
            self.assertIn("desert", by_name)
            self.assertIn("plains", by_name)
            # 沙漠两格相邻 → 合成一块，共 2 个区块
            self.assertEqual(by_name["desert"]["chunks"], 2)
            self.assertEqual(by_name["plains"]["chunks"], 2)
            self.assertTrue(by_name["desert"]["color"].startswith("#"))

    def test_find_structure_then_next_then_exhausted(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = build_world(Path(tmp))
            session = sm.SaveMapSession(world)
            first = session.find("village", "structure", None, 64)
            self.assertTrue(first["found"])
            self.assertEqual(first["found"]["kind"], "village")
            self.assertEqual((first["found"]["x"], first["found"]["z"]), (24, 8))
            self.assertFalse(first["exhausted"])
            again = session.find("village", "structure",
                                (first["found"]["x"], first["found"]["z"]), 64)
            self.assertIsNone(again["found"])
            self.assertTrue(again["exhausted"])

    def test_find_biome_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = build_world(Path(tmp))
            session = sm.SaveMapSession(world)
            result = session.find("desert", "biome", None, 64)
            self.assertTrue(result["found"])
            self.assertEqual(result["found"]["kind"], "biome")
            self.assertEqual(result["found"]["chunks"], 2)

    def test_find_reports_capped_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = build_world(Path(tmp))
            session = sm.SaveMapSession(world)
            with mock.patch.object(sm, "DEFAULT_STEP", 1):
                result = session.find("trial_chambers", "structure", None, 1)
            self.assertIsNone(result["found"])
            self.assertFalse(result["exhausted"])
            self.assertTrue(result["capped"])

    def test_find_requires_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = build_world(Path(tmp))
            session = sm.SaveMapSession(world)
            with self.assertRaises(ValueError):
                session.find("", "structure")


class WebApiBridgeTest(unittest.TestCase):
    def _api(self, root: Path):
        from types import SimpleNamespace

        from mc_launcher.ui_web.shell import WebApi

        config = SimpleNamespace(
            game_path=root / "game", java_path="", selected_version_id="",
            player_name="Tester", language="zh_CN",
        )
        return WebApi(config)

    @staticmethod
    def _wait(api, job_id: str, timeout: float = 30.0) -> dict:
        import time

        from mc_launcher.ui_web import shell as sh

        started = time.time()
        while time.time() - started < timeout:
            job = sh._JOBS.get(job_id)
            if job is not None and job.state in ("ok", "failed", "cancelled"):
                return {"state": job.state, "result": job.result, "error": job.error,
                        "stage": job.stage}
            time.sleep(0.02)
        raise AssertionError("任务超时")

    def test_open_view_expand_find_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            world = build_world(root)
            api = self._api(root)

            opened = api.save_map_open(str(world), 256, 512, "height")
            self.assertTrue(opened["ok"])
            done = self._wait(api, opened["job"])
            self.assertEqual(done["state"], "ok")
            payload = done["result"]
            self.assertEqual(payload["source"], "save")
            self.assertTrue(payload["image_url"].startswith("data:image/png;base64,"))
            self.assertEqual(payload["session"]["chunks_total"], 4)
            self.assertEqual(payload["session"]["chunks_done"], 4)
            self.assertNotIn("png", payload)          # 本地路径不外泄
            self.assertEqual(len(payload["structures"]), 1)

            moved = api.save_map_view(str(world), 24, 8, 256, 192, "biome")
            moved_done = self._wait(api, moved["job"])
            self.assertEqual(moved_done["state"], "ok")
            self.assertEqual(moved_done["result"]["layer"], "biome")
            self.assertEqual(moved_done["result"]["bounds"], [-104.0, -120.0, 152.0, 136.0])

            grown = api.save_map_expand(str(world), 1, 8, 8, 256, 192, "height")
            grown_done = self._wait(api, grown["job"])
            self.assertEqual(grown_done["state"], "ok")
            self.assertEqual(grown_done["result"]["added"], 0)  # 已经全解压完
            self.assertTrue(grown_done["result"]["session"]["exhausted"])

            found = api.save_map_find(str(world), "village", "structure",
                                      0, 0, False, 512, 192, "height", 64)
            found_done = self._wait(api, found["job"])
            self.assertEqual(found_done["state"], "ok")
            self.assertTrue(found_done["result"]["hit"])
            self.assertEqual(found_done["result"]["found"]["kind"], "village")
            self.assertEqual(found_done["result"]["center"],
                             [found_done["result"]["found"]["x"],
                              found_done["result"]["found"]["z"]])

            missing = api.save_map_find(str(world), "trial_chambers", "structure",
                                        0, 0, False, 512, 192, "height", 64)
            missing_done = self._wait(api, missing["job"])
            self.assertFalse(missing_done["result"]["hit"])
            self.assertTrue(missing_done["result"]["exhausted"])

    def test_session_is_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            world = build_world(root)
            api = self._api(root)
            first = api._save_map_session(str(world))
            job = api.save_map_view(str(world), 8, 8, 256, 128, "height")
            self.assertEqual(self._wait(api, job["job"])["state"], "ok")
            second = api._save_map_session(str(world))
            self.assertIs(first, second)
            self.assertGreaterEqual(len(first.heights), 4)

    def test_catalog_rpc(self):
        with tempfile.TemporaryDirectory() as tmp:
            api = self._api(Path(tmp))
            data = api.save_map_catalog("1.14.4")
            self.assertTrue(data["ok"])
            self.assertIn("pillager_outpost", data["available_structures"])
            self.assertNotIn("trial_chambers", data["available_structures"])
            self.assertEqual(data["version"], "1.14.4")

    def test_discard_only_inside_seed_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            world = build_world(root)
            api = self._api(root)
            refused = api.save_map_discard(str(world))
            self.assertFalse(refused["ok"])
            self.assertIn("临时存档", refused["message"])

            from mc_launcher.config import DATA_DIR

            preview_root = Path(DATA_DIR) / "seed_preview"
            preview_root.mkdir(parents=True, exist_ok=True)
            target = preview_root / "unit-test-world"
            if target.exists():
                import shutil
                shutil.rmtree(target)
            target.mkdir()
            (target / "level.dat").write_bytes(level_dat())
            removed = api.save_map_discard(str(target))
            self.assertTrue(removed and removed["ok"])
            self.assertFalse(target.exists())

    def test_keep_world_plumbing(self):
        from mc_launcher.seed_world import generate_world
        from mc_launcher.ui_web.shell import WebApi

        self.assertIn("target_root", inspect.signature(generate_world).parameters)
        self.assertIn("keep_world", inspect.signature(WebApi.seed_world_generate).parameters)
        for name in ("save_map_open", "save_map_view", "save_map_expand", "save_map_find",
                     "save_map_catalog", "save_map_discard", "_save_view_payload"):
            self.assertTrue(hasattr(WebApi, name), f"WebApi 缺 {name}")

    def test_api_gateway_group(self):
        from mc_launcher.api_gateway import GROUPS, _group_of

        self.assertEqual(GROUPS.get("save_map"), "存档地图浏览")
        self.assertEqual(_group_of("save_map_find"), "存档地图浏览")
        # 不能误落到「存档修复 / 存档」组
        self.assertNotEqual(_group_of("save_map_view"), "存档修复 / 存档")


if __name__ == "__main__":
    unittest.main()
