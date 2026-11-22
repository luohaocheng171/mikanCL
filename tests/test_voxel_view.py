"""逐方块体素视图：解码、上色、只显示矿石。

用内存里构造的 section 直接跑，不依赖真实存档文件；只把 region 索引与 NBT 读取
换成桩，验证的是「调色板 → 方块 → 面片」这条链路本身。
"""

from __future__ import annotations

import base64
import struct
from pathlib import Path
from unittest import mock

from mc_launcher import voxel_view as vv

STONE, AIR, DIAMOND, DEEPSLATE = 0, 1, 2, 3
PALETTE = [
    {"Name": "minecraft:stone"},
    {"Name": "minecraft:air"},
    {"Name": "minecraft:diamond_ore"},
    {"Name": "minecraft:deepslate"},
]


def _pack_nibbles(values: list[int]) -> list[int]:
    """1.16+ 的紧凑布局：每个 long 装 16 个 4bit 值，不跨 long。"""
    longs: list[int] = []
    for start in range(0, len(values), 16):
        word = 0
        for offset, value in enumerate(values[start:start + 16]):
            word |= (value & 0xF) << (offset * 4)
        if word >= 1 << 63:
            word -= 1 << 64
        longs.append(word)
    return longs


def _section(y: int, ore_at: tuple[int, int, int] | None = (3, 3, 3)) -> dict:
    values = [STONE] * 4096
    # 一层空气穴，用来验证「只画贴着空气的面」
    for lz in range(4, 8):
        for lx in range(4, 8):
            values[(8 * 16 + lz) * 16 + lx] = AIR
    if ore_at:
        lx, ly, lz = ore_at
        values[(ly * 16 + lz) * 16 + lx] = DIAMOND
    return {"Y": y, "Palette": PALETTE, "BlockStates": _pack_nibbles(values)}


def _world(tmp_path: Path) -> Path:
    world = tmp_path / "w"
    (world / "region").mkdir(parents=True)
    (world / "level.dat").write_bytes(b"stub")
    (world / "region" / "r.0.0.mca").write_bytes(b"stub")
    return world


def _run(tmp_path, **kwargs):
    kwargs.setdefault("y_min", 0)
    kwargs.setdefault("y_max", 15)
    world = _world(tmp_path)
    level = {"Sections": [_section(0)]}
    with mock.patch.object(vv, "_build_chunk_index", return_value={(0, 0): world / "region" / "r.0.0.mca"}), \
         mock.patch.object(vv, "_chunk_nbt", return_value=level), \
         mock.patch.object(vv, "read_level_dat", return_value={"name": "t", "version": "1.20.1"}):
        return vv.build_voxel(world, cx=0, cz=0, span=32, **kwargs)


def test_chunk_array_uses_palette(tmp_path):
    mats = vv._Materials()
    arr = vv._chunk_array({"Sections": [_section(0)]}, 0, 15, False, mats)
    assert len(arr) == 16 * 16 * 16
    assert mats.names[arr[0]] == "stone"
    # 洞穴那一格是空气（材质 0）
    assert arr[(8 * 16 + 4) * 16 + 4] == 0
    assert mats.names[arr[(3 * 16 + 3) * 16 + 3]] == "diamond_ore"


def test_air_is_material_zero(tmp_path):
    mats = vv._Materials()
    assert mats.get("air") == 0
    assert mats.get("cave_air") == 0
    assert mats.get("") == 0


def test_block_rgb_known_and_unknown():
    assert vv.block_rgb("diamond_ore") == vv.ORE_COLORS["diamond_ore"]
    assert vv.block_rgb("stone") == vv.BLOCK_COLORS["stone"]
    assert vv.block_rgb("oak_leaves")[1] > vv.block_rgb("oak_leaves")[0]
    # 没收录的方块也要有一个稳定的颜色
    first = vv.block_rgb("some_mod:weird_block")
    assert first == vv.block_rgb("some_mod:weird_block")


def test_surface_mode_emits_faces_and_counts(tmp_path):
    data = _run(tmp_path, mode="surface", max_faces=50000)
    assert data["ok"], data.get("message")
    assert data["faces"] > 0
    assert "air" not in data["counts"]
    assert data["counts"].get("stone", 0) > 0
    # 每面 8 字节
    raw = base64.b64decode(data["quads"])
    assert len(raw) == data["faces"] * 8
    x, y, z, face, mat = struct.unpack("<hhhBB", raw[:8])
    assert 0 <= face <= 5
    assert 0 <= mat < len(data["palette"])


def test_ores_mode_only_ores(tmp_path):
    data = _run(tmp_path, mode="ores", max_faces=50000)
    assert data["ok"], data.get("message")
    assert data["counts_total"] == 1
    assert "diamond_ore" in data["counts"]
    # 单个矿石方块 = 6 个面
    assert data["faces"] == 6
    assert data["counts"]["diamond_ore"] == 1


def test_blocks_mode_respects_filter(tmp_path):
    data = _run(tmp_path, mode="blocks", blocks=["stone"], max_faces=500)
    assert data["ok"], data.get("message")
    assert data["truncated"] is True
    assert data["faces"] <= 500
    assert set(data["counts"]) <= {"stone"}


def test_fluid_constants_and_opacity_payload(tmp_path):
    # 流体识别按短名（含 1.12 及更早的 flowing_*）
    assert vv._is_fluid("minecraft:water")
    assert vv._is_fluid("flowing_lava")
    assert not vv._is_fluid("stone")
    assert vv.FLUID_ALPHA["water"] < 255
    # payload 必须带 opacity，且和调色板等长（前端按它画半透明）
    data = _run(tmp_path, mode="surface", max_faces=50000)
    assert data["ok"], data.get("message")
    assert len(data["opacity"]) == len(data["palette"])
    assert all(0 < a <= 255 for a in data["opacity"])
    assert data["opacity"][0] == 255  # 空气索引 0 全不透明/不显示


def test_fluid_face_culling_lets_water_show_through(tmp_path):
    # 一层水盖在沙子上：贴空气的水面要出面，水贴沙子的内部面不画，
    # 沙子贴水的那一面要保留，这样透过半透明水面才能看到下面的沙子。
    palette = [
        {"Name": "minecraft:air"},
        {"Name": "minecraft:water"},
        {"Name": "minecraft:sand"},
    ]
    values = [0] * 4096
    # y=0 全是沙子，y=1 中间一格是水
    for lx in range(16):
        for lz in range(16):
            values[(0 * 16 + lz) * 16 + lx] = 2
    values[(1 * 16 + 8) * 16 + 8] = 1
    section = {"Y": 0, "Palette": palette, "BlockStates": _pack_nibbles(values)}
    world = _world(tmp_path)
    level = {"Sections": [section]}
    with mock.patch.object(vv, "_build_chunk_index", return_value={(0, 0): world / "region" / "r.0.0.mca"}), \
         mock.patch.object(vv, "_chunk_nbt", return_value=level), \
         mock.patch.object(vv, "read_level_dat", return_value={"name": "t", "version": "1.20.1"}):
        data = vv.build_voxel(world, cx=0, cz=0, span=32, y_min=0, y_max=15,
                              mode="surface", max_faces=50000)
    assert data["ok"], data.get("message")
    names = data["palette_names"]  # 方块名已转成短名
    water_idx = names.index("water")
    sand_idx = names.index("sand")
    assert data["opacity"][water_idx] == vv.FLUID_ALPHA["water"]
    assert data["opacity"][sand_idx] == 255
    # 沙子和水都出了面（沙子贴水的面没被剔除）
    assert data["counts"].get("sand", 0) > 0
    assert data["counts"].get("water", 0) > 0
