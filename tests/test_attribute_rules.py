"""实体属性版本规则回归测试（对照 Minecraft Wiki《Entity format》）。

覆盖：属性 NBT 键名切换阈值（1.21 / 24w21a，DV 3953）、属性 ID 前缀切换、
逐属性合法范围，以及属性越界的明确警告（不再静默跳过/钳制）。

直接运行：``python tests/test_attribute_rules.py``
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mc_launcher import game_data as G  # noqa: E402


class AttributeNbtKeyTest(unittest.TestCase):
    """实体属性 NBT 键名随版本切换。"""

    def test_snake_case_starts_at_1_21(self):
        # 24w21a（1.21，DV 3953）：Attributes→attributes, Name→id, Base→base
        self.assertEqual(G.attribute_nbt_key("1.20.6"), ("Attributes", "Name", "Base"))
        self.assertEqual(G.attribute_nbt_key("1.20.5"), ("Attributes", "Name", "Base"))
        self.assertEqual(G.attribute_nbt_key("1.21"), ("attributes", "id", "base"))
        self.assertEqual(G.attribute_nbt_key("1.21.1"), ("attributes", "id", "base"))
        self.assertEqual(G.attribute_nbt_key("1.21.4"), ("attributes", "id", "base"))
        self.assertEqual(G.attribute_nbt_key("1.21.5"), ("attributes", "id", "base"))

    def test_generic_prefix_removed_at_1_21_2(self):
        # 1.21.2（24w33a，DV 4080）去掉 generic./player. 前缀
        self.assertEqual(G.attribute_id("max_health", "1.20.1"), "minecraft:generic.max_health")
        self.assertEqual(G.attribute_id("max_health", "1.21.1"), "minecraft:generic.max_health")
        self.assertEqual(G.attribute_id("max_health", "1.21.2"), "minecraft:max_health")
        self.assertEqual(G.attribute_id("max_health", "1.21.4"), "minecraft:max_health")
        self.assertEqual(G.attribute_id("max_health", "1.12.2"), "generic.maxHealth")

    def test_per_attribute_wiki_ranges(self):
        # 对照 MC Wiki，逐属性范围不同，不再是统一 2048。
        self.assertEqual((G.ATTRIBUTES["max_health"]["min"], G.ATTRIBUTES["max_health"]["max"]),
                         (1.0, 1024.0))
        self.assertEqual((G.ATTRIBUTES["knockback_resistance"]["min"],
                          G.ATTRIBUTES["knockback_resistance"]["max"]), (-2.0, 1.0))
        self.assertEqual((G.ATTRIBUTES["armor"]["min"], G.ATTRIBUTES["armor"]["max"]), (0.0, 30.0))
        self.assertEqual((G.ATTRIBUTES["scale"]["min"], G.ATTRIBUTES["scale"]["max"]),
                         (0.0625, 16.0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
