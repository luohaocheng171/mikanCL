"""v5.5.8：存档地图渲染 + 种子页面地图对齐的单元测试。

覆盖：
- 9 bit 连续位流解包（跨 long 边界）；
- 高度图 / 群系从真实区块结构里解码（1.14 二维群系、1.18 section 群系）；
- 结构 id → 中文名 / 颜色；
- 端到端：造一个最小存档 → 渲染 PNG → 读回像素确认画的是地形；
- WebApi 上新增接口存在（seed_world_map / seed_saves）。
"""

from __future__ import annotations

import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mc_launcher import world_render as wr  # noqa: E402
from mc_launcher.nbt import (  # noqa: E402
    TAG_COMPOUND,
    TAG_INT,
    TAG_INT_ARRAY,
    TAG_LIST,
    TAG_LONG_ARRAY,
    TAG_STRING,
    write_nbt_typed,
)
from mc_launcher.world_render import (  # noqa: E402
    EMPTY_RGB,
    biome_color,
    land_color,
    render_world_map,
    structure_kind,
    top_section_y,
    unpack_long_stream,
)
from tests.creator_fixtures import make_region  # noqa: E402


def pack_long_stream(values, bits: int) -> list[int]:
    """把数值按 Minecraft 的连续位流打包回 long 数组（测试用反向操作）。"""
    if not values:
        return []
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


def _i(value: int):
    return (TAG_INT, int(value))


def _s(value: str):
    return (TAG_STRING, str(value))


def _int_array(values):
    return (TAG_INT_ARRAY, [int(v) for v in values])


def _long_array(values):
    return (TAG_LONG_ARRAY, list(values))


def _list(element_tag: int, items):
    return (TAG_LIST, (element_tag, list(items)))


def build_chunk(heights: list[int], floors: list[int], biomes: list[int],
                section_y: int = 4, structure: str = "Minecraft:village") -> bytes:
    """造一个 1.14 风格的区块：Level + Heightmaps + Biomes + Sections + Structures。"""
    starts = {}
    if structure:
        starts[structure] = _c(
            ChunkX=_i(0), ChunkZ=_i(0), id=_s(structure), references=_i(0),
        )
    level = _c(
        xPos=_i(0),
        zPos=_i(0),
        Status=_s("full"),
        Heightmaps=_c(
            MOTION_BLOCKING=_long_array(pack_long_stream(heights, 9)),
            OCEAN_FLOOR=_long_array(pack_long_stream(floors, 9)),
        ),
        Biomes=_int_array(biomes),
        Sections=_list(TAG_COMPOUND, [
            _c(Y=_i(section_y), Palette=_list(TAG_COMPOUND, [_c(Name=_s("minecraft:stone"))])),
        ]),
        Structures=_c(Starts=_c(**starts), References=_c()),
    )
    root = _c(Level=level, DataVersion=_i(1976))
    return zlib.compress(write_nbt_typed("", root))


def build_level_dat(resolved_seed: int = 114514, spawn=(0, 0),
                    version_name: str = "1.14.4", data_version: int = 1976) -> bytes:
    import gzip

    data = _c(
        LevelName=_s("MapTest"),
        seed=(TAG_INT, int(resolved_seed)),
        SpawnX=_i(spawn[0]),
        SpawnZ=_i(spawn[1]),
        Version=_c(Name=_s(version_name)),
        DataVersion=_i(data_version),
    )
    return gzip.compress(write_nbt_typed("", _c(Data=data)))


def read_png_rgb(path: Path) -> tuple[int, int, list[bytearray]]:
    """读回本项目自己写的 PNG（只有 filter 0 的行），返回尺寸与像素行。"""
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
    raw = zlib.decompress(idat)
    stride = 1 + width * 3
    rows = []
    for row in range(height):
        line = raw[row * stride:(row + 1) * stride]
        assert line[0] == 0, "本项目写出的 PNG 每行都应该是 filter 0"
        rows.append(bytearray(line[1:]))
    return width, height, rows


class LongStreamTest(unittest.TestCase):
    def test_roundtrip_cross_boundary(self):
        values = [((index * 37) % 512) for index in range(256)]
        longs = pack_long_stream(values, 9)
        self.assertEqual(len(longs), 36)
        self.assertEqual(unpack_long_stream(longs, 9, 256), values)

    def test_matches_minecraft_1_14_layout(self):
        # 1.14 的 256 列 9 bit 高度图正好占 36 个 long（最后 4 位空着）
        longs = pack_long_stream([63] * 256, 9)
        self.assertEqual(len(longs), 36)
        self.assertEqual(set(unpack_long_stream(longs, 9, 256)), {63})

    def test_zero_bits_is_safe(self):
        self.assertEqual(unpack_long_stream([0, 0], 0, 4), [0, 0, 0, 0])


class ColorTest(unittest.TestCase):
    def test_land_bands(self):
        sea = 63
        self.assertGreater(land_color(sea + 30, sea)[0], land_color(sea + 5, sea)[0])
        self.assertEqual(land_color(sea - 10, sea, beach=True), (223, 205, 145))
        # 贴着海平面的平地不应该是沙色（否则整片平原看起来像沙漠）
        self.assertNotEqual(land_color(sea, sea), (223, 205, 145))
        # 高山应该偏白
        self.assertGreater(min(land_color(sea + 90, sea)), 180)

    def test_biome_stems(self):
        self.assertEqual(biome_color("desert_hills"), biome_color("desert"))
        self.assertEqual(biome_color("modified_wooded_badlands_plateau"),
                         biome_color("wooded_badlands_plateau"))
        self.assertNotEqual(biome_color("some_modded_biome"), (0, 0, 0))
        self.assertEqual(biome_color("some_modded_biome"), biome_color("some_modded_biome"))

    def test_unknown_biome(self):
        self.assertEqual(biome_color(None), (74, 88, 78))
        self.assertEqual(biome_color("unknown"), (96, 104, 92))


class StructureTest(unittest.TestCase):
    def test_aliases(self):
        self.assertEqual(structure_kind("Minecraft:village_plains")[0], "village")
        self.assertEqual(structure_kind("village_taiga")[1], "村庄")
        self.assertEqual(structure_kind("Mineshaft")[0], "mineshaft")
        self.assertEqual(structure_kind("minecraft:ruined_portal")[0], "ruined_portal")
        self.assertEqual(structure_kind("minecraft:bastion_remnant")[0], "bastion")
        self.assertEqual(structure_kind("unknown:thing")[0], "unknown")

    def test_top_section_y_is_block_y(self):
        level = {"Sections": [
            {"Y": 3, "block_states": {"palette": [{"Name": "minecraft:air"}]}},
            {"Y": 4, "Section": {}, "Palette": [{"Name": "minecraft:stone"}]},
        ]}
        self.assertEqual(top_section_y(level), 64)
        self.assertIsNone(top_section_y({"Sections": []}))


class RenderTest(unittest.TestCase):
    def _world(self, folder: Path) -> Path:
        world = folder / "saves" / "MapTest"
        (world / "region").mkdir(parents=True)
        (world / "level.dat").write_bytes(build_level_dat())
        return world

    def test_render_synthetic_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = self._world(Path(tmp))
            heights = [64] * 256
            floors = [62] * 256
            heights[0] = 80  # 一个山包，用来确认高度真的被读出来
            biomes = [1] * 256  # plains
            chunk = build_chunk(heights, floors, biomes)
            make_region(world / "region" / "r.0.0.mca", {(0, 0): chunk, (1, 0): chunk})

            result = render_world_map(world, 128)
            self.assertEqual(result["chunks"], 2)
            self.assertEqual(result["source"], "save")
            self.assertEqual(result["seed"], "114514")
            self.assertEqual(result["version"], "1.14.4")
            self.assertEqual(result["height"]["min"], 64)
            self.assertEqual(result["height"]["max"], 80)
            self.assertEqual([item["kind"] for item in result["structures"]], ["village"])

            width, height, rows = read_png_rgb(Path(result["height_png"]))
            self.assertEqual((width, height), (128, 128))
            # 地图中心一定是己方区块的地形，不可能是「未生成」深灰
            center = rows[64][64 * 3:64 * 3 + 3]
            self.assertNotEqual(bytes(center), bytes(EMPTY_RGB))
            # 图片左下角（区块范围外）应该是深灰
            corner = rows[126][3:6]
            self.assertEqual(bytes(corner), bytes(EMPTY_RGB))
            self.assertTrue(Path(result["biome_png"]).is_file())

    def test_render_relative_heightmap(self):
        """1.18+ 的高度图若存相对值，必须加上 min_y 对齐到真实 Y。"""
        with tempfile.TemporaryDirectory() as tmp:
            world = Path(tmp) / "saves" / "Modern"
            (world / "region").mkdir(parents=True)
            (world / "level.dat").write_bytes(
                build_level_dat(version_name="1.18.2", data_version=2865))
            # 段序号 4 = 方块 Y 64..79；相对值 130 → 真实 Y 66
            raw = [130] * 256
            level = _c(
                sections=_list(TAG_COMPOUND, [
                    _c(Y=_i(4),
                       block_states=_c(palette=_list(TAG_COMPOUND, [_c(Name=_s("minecraft:stone"))])),
                       biomes=_c(palette=_list(TAG_STRING, [_s("minecraft:plains")]), data=_long_array([]))),
                ]),
                Heightmaps=_c(
                    MOTION_BLOCKING=_long_array(pack_long_stream(raw, 9)),
                    OCEAN_FLOOR=_long_array(pack_long_stream(raw, 9)),
                ),
                Biomes=_int_array([1] * 256),
                structures=_c(starts=_c()),
            )
            make_region(world / "region" / "r.0.0.mca",
                        {(0, 0): zlib.compress(write_nbt_typed("", level))})
            result = render_world_map(world, 64)
            self.assertEqual(result["height"]["min"], 66)
            self.assertEqual(result["height"]["max"], 66)
            # 群系必须按「换算后的绝对 Y」定位 section，否则整片会是 None
            self.assertEqual([row["name"] for row in result["biomes"]], ["plains"])

    def test_missing_level_dat(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                render_world_map(Path(tmp) / "nope", 64)

    def test_empty_region_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = Path(tmp) / "saves" / "Empty"
            world.mkdir(parents=True)
            (world / "level.dat").write_bytes(build_level_dat())
            (world / "region").mkdir()
            with self.assertRaises(ValueError):
                render_world_map(world, 64)


class ApiSurfaceTest(unittest.TestCase):
    def test_new_methods_exist(self):
        from mc_launcher.ui_web.shell import WebApi

        for name in ("seed_world_map", "seed_saves", "_save_map_payload"):
            self.assertTrue(hasattr(WebApi, name), f"WebApi 缺 {name}")
        # 公开方法才能被 http / electron 网关反射到
        self.assertFalse("seed_world_map".startswith("_"))

    def test_map_dir_under_data(self):
        self.assertTrue(str(wr.MAP_DIR).endswith("world-maps"))

    def test_bridge_payload_and_listing(self):
        """WebApi 层：预览图转 data URL、存档列表能列出刚造的存档。"""
        from types import SimpleNamespace

        from mc_launcher.ui_web.shell import WebApi

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            world = root / "game" / "saves" / "BridgeTest"
            (world / "region").mkdir(parents=True)
            (world / "level.dat").write_bytes(build_level_dat())
            heights = [64] * 256
            make_region(world / "region" / "r.0.0.mca",
                        {(0, 0): build_chunk(heights, [63] * 256, [1] * 256)})

            config = SimpleNamespace(
                game_path=root / "game",
                backup_root=root / "backups",
                selected_instance=lambda: SimpleNamespace(version_id="1.14.4"),
            )
            api = WebApi(config)
            payload = api._save_map_payload(str(world), 64)
            self.assertTrue(payload["height_url"].startswith("data:image/png;base64,"))
            self.assertTrue(payload["biome_url"].startswith("data:image/png;base64,"))
            self.assertEqual(payload["label"], "游戏本体存档")
            self.assertNotIn("height_png", payload)  # 本地路径不外泄给前端

            listing = api.seed_saves()
            names = [item["name"] for item in listing["items"]]
            self.assertIn("BridgeTest", names)
            self.assertTrue(listing["items"][0]["regions"] >= 1)


if __name__ == "__main__":
    unittest.main()
