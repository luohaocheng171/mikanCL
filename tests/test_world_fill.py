"""补生成区块（world_fill）的离线测试。

不启动真实服务端：只验证「哪些区块算没生成」「版本不匹配要拦住」「缓存要作废」
这些真正容易出错的判定逻辑。真机验证放过 1.20.1 全流程（542 个区块，
still_missing=0），所以这里不重复跑几分钟的服务端。
"""
from __future__ import annotations

import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from tests.creator_fixtures import TAG_INT, TAG_STRING, make_region, make_world
from mc_launcher import world_fill as wf
from mc_launcher.nbt import TAG_COMPOUND, write_nbt_typed


def _chunk_nbt(status: str) -> bytes:
    """造一个 1.18+ 形状的最小 chunk：根上就有 Status。"""
    root = (TAG_COMPOUND, {
        "DataVersion": (TAG_INT, 3465),
        "xPos": (TAG_INT, 0),
        "zPos": (TAG_INT, 0),
        "Status": (TAG_STRING, status),
        "sections": (TAG_COMPOUND, {}),
    })
    return zlib.compress(write_nbt_typed("", root))


class StatusProbeTest(unittest.TestCase):
    def test_head_status_finds_full(self):
        status = wf._head_status(_chunk_nbt("minecraft:full"), 2)
        self.assertEqual(status, "minecraft:full")

    def test_head_status_partial_generation(self):
        self.assertEqual(wf._head_status(_chunk_nbt("minecraft:features"), 2),
                         "minecraft:features")

    def test_head_status_bad_payload(self):
        self.assertIsNone(wf._head_status(b"not a zlib stream", 2))

    def test_head_status_uncompressed_legacy(self):
        # compression=3 表示不压缩（1.15 之前的 level.dat 常见），也要能取到
        raw = write_nbt_typed("", (TAG_COMPOUND, {"Status": (TAG_STRING, "full")}))
        self.assertEqual(wf._head_status(raw, 3), "full")


class StatusManyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_counts_full_and_empty_slots(self):
        world = make_world(self.tmp)
        make_region(world / "region" / "r.0.0.mca", {
            (0, 0): _chunk_nbt("minecraft:full"),
            (1, 0): _chunk_nbt("minecraft:empty"),
        })
        state = wf.status_many(world, [(0, 0), (1, 0), (2, 0)])
        self.assertTrue(state[(0, 0)])
        self.assertFalse(state[(1, 0)])       # 半成品：Status 不是 full
        self.assertFalse(state[(2, 0)])       # 头里没槽位：从没生成

    def test_missing_region_file_is_all_missing(self):
        world = make_world(self.tmp)
        state = wf.status_many(world, [(64, 64), (65, 64)])
        self.assertEqual(state, {(64, 64): False, (65, 64): False})

    def test_broken_chunk_counts_as_missing(self):
        world = make_world(self.tmp)
        make_region(world / "region" / "r.0.0.mca", {(0, 0): b"\x00" * 32})
        self.assertFalse(wf.status_many(world, [(0, 0)])[(0, 0)])

    def test_plan_reports_counts(self):
        world = make_world(self.tmp)
        make_region(world / "region" / "r.0.0.mca", {
            (0, 0): _chunk_nbt("minecraft:full"),
            (1, 0): _chunk_nbt("minecraft:empty"),
        })
        report = wf.plan(world, 8, 0, radius_chunks=1)
        self.assertTrue(report["ok"])
        self.assertEqual(report["side"], 3)
        self.assertEqual(report["total"], 9)
        self.assertEqual(report["full"], 1)
        self.assertEqual(report["missing"], 8)
        self.assertEqual(report["version"], "1.20.1")

    def test_plan_truncates_long_lists(self):
        world = make_world(self.tmp)
        make_region(world / "region" / "r.0.0.mca", {})
        report = wf.plan(world, 0, 0, radius_chunks=4, limit=5)
        self.assertEqual(report["missing"], 81)
        self.assertEqual(len(report["missing_chunks"]), 5)
        self.assertTrue(report["truncated"])

    def test_legacy_chunk_without_status_is_full(self):
        """1.12 及更早的区块没有 Status 字段，有数据就应当当成已生成。"""
        world = make_world(self.tmp)
        root = (TAG_COMPOUND, {"Level": (TAG_COMPOUND, {"xPos": (TAG_INT, 0)})})
        payload = zlib.compress(write_nbt_typed("", root) + b"\x00" * 600)
        make_region(world / "region" / "r.0.0.mca", {(0, 0): payload})
        self.assertTrue(wf.status_many(world, [(0, 0)])[(0, 0)])


class StreamTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_iter_missing_skips_full_and_stays_near_center(self):
        world = make_world(self.tmp)
        make_region(world / "region" / "r.0.0.mca", {
            (0, 0): _chunk_nbt("minecraft:full"),
        })
        chunks = list(wf.iter_missing(world, 8, 0, 40, max_results=12))
        self.assertEqual(len(chunks), 12)
        self.assertNotIn((0, 0), chunks)
        self.assertTrue(all(max(abs(x), abs(z)) <= 40 for x, z in chunks))
        self.assertLessEqual(max(abs(chunks[0][0]), abs(chunks[0][1])), 2)

    def test_plan_with_huge_radius_streams_instead_of_enumerating(self):
        """半径填到几十万格时也必须秒回，不能展开 (2r+1)² 个坐标。"""
        world = make_world(self.tmp)
        make_region(world / "region" / "r.0.0.mca", {
            (0, 0): _chunk_nbt("minecraft:full"),
        })
        report = wf.plan(world, 0, 0, radius_chunks=400, limit=5)
        self.assertTrue(report["ok"])
        self.assertTrue(report["estimated"])
        self.assertEqual(report["missing"], wf.SCAN_BUDGET)
        self.assertEqual(len(report["missing_chunks"]), 5)
        # 概览只回前 64 个坐标，不能把 20 万个塞进 JSON
        self.assertLessEqual(len(report["missing_chunks"]), 64)


class GuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_refuses_version_upgrade(self):
        world = make_world(self.tmp, version_name="1.20.1")
        make_region(world / "region" / "r.0.0.mca", {(0, 0): _chunk_nbt("minecraft:empty")})
        result = wf.fill_world(world, "1.16.5", self.tmp)
        self.assertFalse(result["ok"])
        self.assertEqual(result.get("needs_version"), "1.20.1")
        self.assertIn("数据升级", result["message"])

    def test_same_minor_version_is_allowed(self):
        """1.20.1 的存档用 1.20.4 补，只算小版本升级，不该被拦在这里。

        把 prepare_server 打成桩，避免测试真的去下 50MB 服务端。
        """
        from unittest import mock

        world = make_world(self.tmp, version_name="1.20.1")
        make_region(world / "region" / "r.0.0.mca", {})
        stub = {"ok": False, "message": "stub: 测试不下载服务端"}
        with mock.patch("mc_launcher.seed_world.prepare_server", return_value=stub):
            result = wf.fill_world(world, "1.20.4", self.tmp)
        self.assertNotIn("needs_version", result)
        self.assertEqual(result["message"], stub["message"])

    def test_missing_level_dat(self):
        result = wf.fill_world(self.tmp / "nope", "1.20.1", self.tmp)
        self.assertFalse(result["ok"])

    def test_world_in_use_detects_lock(self):
        world = make_world(self.tmp)
        self.assertFalse(wf.world_in_use(world))
        lock = world / "session.lock"
        handle = open(lock, "r+b")
        try:
            if hasattr(handle, "fileno"):
                try:
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    try:
                        self.assertTrue(wf.world_in_use(world))
                    finally:
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                except (ImportError, OSError):
                    self.skipTest("当前平台不支持文件锁检查")
        finally:
            handle.close()


class BatchTest(unittest.TestCase):
    def test_batches_are_inside_forceload_limit(self):
        chunks = [(x, z) for x in range(-20, 21) for z in range(-20, 21)]
        groups = wf._batches(chunks, wf.BATCH_SIDE, (0, 0))
        self.assertTrue(groups)
        self.assertLessEqual(wf.BATCH_SIDE * wf.BATCH_SIDE, wf.FORCELOAD_LIMIT)
        covered = set()
        for _key, group in groups:
            covered.update(group)
        self.assertEqual(covered, set(chunks))
        # 第一个批次应当在中心附近
        first_key = groups[0][0]
        self.assertLessEqual(max(abs(first_key[0]), abs(first_key[1])), 2)

    def test_level_name_is_absolute_forward_slash(self):
        world = Path("data/demo/world").resolve()
        name = wf._level_name(world)
        self.assertTrue(name.startswith("/") or ":" in name)
        self.assertNotIn("\\", name)


class SessionInvalidateTest(unittest.TestCase):
    def test_invalidate_clears_cached_chunks(self):
        from mc_launcher.save_map import SaveMapSession

        tmp = Path(tempfile.mkdtemp())
        world = make_world(tmp)
        make_region(world / "region" / "r.0.0.mca", {
            (0, 0): _chunk_nbt("minecraft:full"),
            (1, 0): _chunk_nbt("minecraft:full"),
        })
        # 补上高度图数据，让 expand 能真的解出区块
        session = SaveMapSession(world)
        session.heights[(0, 0)] = {"HeightMap": [64] * 256}
        session.failed.add((1, 0))
        result = session.invalidate()
        self.assertEqual(result["chunks_done"], 0)
        self.assertEqual(session.heights, {})
        self.assertEqual(session.failed, set())

    def test_invalidate_single_chunk_keeps_others(self):
        from mc_launcher.save_map import SaveMapSession

        tmp = Path(tempfile.mkdtemp())
        world = make_world(tmp)
        make_region(world / "region" / "r.0.0.mca", {(0, 0): _chunk_nbt("minecraft:full")})
        session = SaveMapSession(world)
        session.heights[(0, 0)] = {"HeightMap": [64] * 256}
        session.heights[(1, 0)] = {"HeightMap": [70] * 256}
        session.invalidate([(1, 0)])
        self.assertIn((0, 0), session.heights)
        self.assertNotIn((1, 0), session.heights)


if __name__ == "__main__":
    unittest.main()
