"""动态加载（种子复刻地形）与第三方组件的 Java 版本选择。

覆盖：
- NoiseTile 的覆盖 / 清晰度 / 取样；
- 会话登记瓦片时「更粗且被完全包住」的旧瓦片会被丢掉；
- noise_for_view 在覆盖不足时给出生成计划，覆盖够时不重复生成；
- 结构点位可以并入索引，让查找扫到未生成区域；
- thirdparty 会为 Java 21 编译的工具挑对运行时，选不到时明确报出来。
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from mc_launcher.save_map import NoiseTile, SaveMapSession


def _bare_session() -> SaveMapSession:
    """只构造带噪声相关字段的会话，不读盘。"""
    session = SaveMapSession.__new__(SaveMapSession)
    session.world = Path("dummy")
    session.key = "test"
    session.lock = threading.RLock()
    session.noise = []
    session.noise_error = ""
    session.dynamic = True
    session.min_y = -64
    session.max_y = 319
    session.sea = 63
    session.structures = {}
    session._stamp = 0
    return session


def test_noise_tile_covers_and_samples():
    data = (bytes([0] * 4 + [255] * 4)) * 8   # 8x8 瓦片：左半低、右半高
    tile = NoiseTile(0, 0, 1024, 8, data, -64, 319)
    assert tile.res == pytest.approx(128.0)
    assert tile.covers(0, 0)
    assert not tile.covers(600, 0)
    low = tile.sample(-400, 0)
    high = tile.sample(400, 0)
    assert low == -64
    assert high == 319
    assert tile.sample(9999, 0) is None


def test_add_noise_drops_coarser_covered_tile():
    session = _bare_session()
    session.add_noise(0, 0, 1024, 128, bytes(128 * 128))
    session.add_noise(0, 0, 4096, 512, bytes(512 * 512))
    # 小范围那块被新瓦片完全包住、清晰度也没更高，留着只会占内存
    assert len(session.noise) == 1
    assert session.noise[0].side == 4096


def test_noise_for_view_needs_finer_tile_when_zoomed_in():
    session = _bare_session()
    session.add_noise(0, 0, 2048, 128, bytes(128 * 128))    # 16 格/像素
    plan = session.noise_for_view(0, 0, 1024, 384)
    assert plan["need"] is True
    assert plan["px"] >= 256
    # 换一块清晰的之后就不用再生成
    session.add_noise(0, 0, 2048, 512, bytes(512 * 512))
    assert session.noise_for_view(0, 0, 1024, 384)["need"] is False
    # 跑到瓦片外面又需要生成
    assert session.noise_for_view(200000, 0, 1024, 384)["need"] is True


def test_structures_from_noise_join_index():
    session = _bare_session()
    added = session.add_structures([
        {"x": 128, "z": -64, "kind": "village", "id": "minecraft:village",
         "name": "村庄"},
        {"x": 128, "z": -64, "kind": "village", "id": "minecraft:village"},  # 重复
    ], "noise")
    assert added == 1
    item = session.structures[("minecraft:village", 128, -64)]
    assert item["source"] == "noise"
    assert item["name"] == "村庄"


class _Info:
    def __init__(self, path: str, major: int) -> None:
        self.path = path
        self.major = major


def test_thirdparty_picks_java_new_enough():
    from mc_launcher.thirdparty import _java_for

    javas = [_Info(r"C:\jdk17\bin\javaw.exe", 17), _Info(r"C:\jdk21\bin\javaw.exe", 21)]
    path, major, highest = _java_for(21, javas, "")
    assert path.endswith("jdk21\\bin\\javaw.exe")
    assert major == 21
    assert highest == 21

    # 只有 17 时不能硬上：返回空路径 + 本机最高版本，前端据此提示/自动装 Java 21
    path, major, highest = _java_for(21, [_Info(r"C:\jdk17\bin\javaw.exe", 17)], "")
    assert path == ""
    assert major == 0
    assert highest == 17


def test_mcaselector_declares_java_21():
    from mc_launcher.thirdparty import CATALOG

    entry = next(row for row in CATALOG if row["id"] == "mcaselector")
    assert entry["java_min"] == 21
