"""存档格式转换回归测试。

覆盖：Classic 2009 方块 ID 逐项迁移（16 种布料 → 羊毛 + metadata、
花/矿物/建筑块 ID 恒等、流动水/岩浆归一）、DataVersion 准确性、
Indev/McRegion 的方块索引转置与 Data nibble 拆分。

直接运行：``python tests/test_world_convert.py``
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mc_launcher import nbt, world_convert as W  # noqa: E402


class ClassicBlockMappingTest(unittest.TestCase):
    """Classic（2009）方块 → 现代 1.12.2 数字 ID + metadata 的逐项迁移。"""

    def test_cloth_ids_all_become_wool_35(self):
        """21–36 都是布料，必须全部映射到羊毛 ID 35，按色名写入 metadata。"""
        # 依据 Minecraft Wiki《Java Edition data values/Classic》与《Wool》：
        # Classic 21红→羊毛14，22橙→1，…，36白→0。
        expected_meta = {
            21: 14, 22: 1, 23: 4, 24: 5, 25: 13, 26: 13, 27: 9, 28: 3,
            29: 11, 30: 10, 31: 10, 32: 2, 33: 6, 34: 7, 35: 8, 36: 0,
        }
        blocks = bytes(range(21, 37))
        mapped, damage = W._classic_map_blocks(blocks)
        for i, classic_id in enumerate(range(21, 37)):
            self.assertEqual(mapped[i], 35, f"Classic {classic_id} 应为羊毛 35")
            self.assertEqual(damage[i], expected_meta[classic_id],
                             f"Classic {classic_id} metadata 错误")

    def test_cloth_damage_not_shifted_like_old_bug(self):
        """旧 bug 会把 22–34 错移成 37–49 并把 35–49 折叠成羊毛，须回归。"""
        mapped, damage = W._classic_map_blocks(bytes([21, 22, 23, 36]))
        # 旧实现里 22→37（蒲公英），damage[36]=2（品红）等，全部错误。
        self.assertNotEqual(mapped[1], 37)
        self.assertEqual(list(mapped), [35, 35, 35, 35])
        self.assertEqual(list(damage), [14, 1, 4, 0])

    def test_flowing_fluids_normalized(self):
        """流动水/岩浆（8/10）写为静止形态（9/11）。"""
        mapped, damage = W._classic_map_blocks(bytes([8, 10]))
        self.assertEqual(list(mapped), [9, 11])
        self.assertEqual(list(damage), [0, 0])

    def test_ids_37_to_49_are_identity(self):
        """花、蘑菇、金/铁块、台阶、砖、TNT、书架、苔石、黑曜石保持原 ID。"""
        original = bytes(range(37, 50))
        mapped, damage = W._classic_map_blocks(original)
        self.assertEqual(list(mapped), list(original))
        self.assertTrue(all(v == 0 for v in damage))

    def test_common_blocks_identity(self):
        """石头、草、泥土、圆石、木板、基岩、沙、沙砾、矿石、木头、玻璃等保持 ID。"""
        original = bytes([0, 1, 2, 3, 4, 5, 6, 7, 12, 13, 14, 15, 16, 17, 18, 19, 20])
        mapped, damage = W._classic_map_blocks(original)
        self.assertEqual(list(mapped), list(original))
        self.assertTrue(all(v == 0 for v in damage))

    def test_all_256_ids_safe(self):
        """整张 ID 表都能安全映射，且输出仍是 0–255 的合法字节。"""
        original = bytes(range(256))
        mapped, damage = W._classic_map_blocks(original)
        self.assertEqual(len(mapped), 256)
        self.assertEqual(len(damage), 256)
        self.assertTrue(all(0 <= v <= 255 for v in mapped))


class DataVersionTest(unittest.TestCase):
    """版本 → DataVersion 表准确性。"""

    def test_data_versions(self):
        # 依据 Minecraft Wiki《Data version》。
        self.assertEqual(W.DATA_VERSIONS["1.10.2"], 512)
        self.assertEqual(W.DATA_VERSIONS["1.10"], 510) if "1.10" in W.DATA_VERSIONS else None
        self.assertEqual(W.DATA_VERSIONS["1.12.2"], 1343)
        self.assertEqual(W.DATA_VERSIONS["1.13"], 1519)
        self.assertEqual(W.DATA_VERSIONS["1.21"], 3953)


class AnvilIndexLayoutTest(unittest.TestCase):
    """McRegion/Alpha → Anvil section 的方块索引转置与 metadata nibble 拆分。"""

    def _level(self, blocks: bytearray, data: bytearray | None = None):
        level = {"Blocks": (nbt.TAG_BYTE_ARRAY, blocks)}
        if data is not None:
            level["Data"] = (nbt.TAG_BYTE_ARRAY, data)
        return (nbt.TAG_COMPOUND, level)

    def test_block_index_transpose_and_data_nibbles(self):
        """旧索引 (x<<11)|(z<<7)|y → 新索引 (y<<8)|(z<<4)|x；data nibble 同步转置。"""
        # 旧 McRegion 区块 Blocks 数组是 16×16×256 = 32768 字节。
        blocks = bytearray(16 * 16 * 256)
        data = bytearray(16 * 16 * 256 // 2)
        # 在旧布局的 (x=1, z=2, y=3) 放置方块 5，metadata=7。
        old_index = (1 << 11) | (2 << 7) | 3
        blocks[old_index] = 5
        data[old_index >> 1] |= 7 << ((old_index & 1) << 2)
        tag, level, changed = W._mc_level_to_anvil(self._level(blocks, data))
        self.assertTrue(changed)
        sec_list = level["Sections"]
        # Sections 是 (TAG_LIST, (element_tag, [compound, ...]))
        sections = sec_list[1][1]
        # y=3 落在 section 0（y//16==0），section 是 (TAG_COMPOUND, {...})
        section = sections[0][1]
        new_index = (3 << 8) | (2 << 4) | 1
        self.assertEqual(section["Blocks"][1][new_index], 5)
        new_data = section["Data"][1]
        got = (new_data[new_index >> 1] >> ((new_index & 1) << 2)) & 0xF
        self.assertEqual(got, 7)


if __name__ == "__main__":
    unittest.main(verbosity=2)
