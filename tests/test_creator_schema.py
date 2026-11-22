"""creator_schema：类型保持、版本识别、上限校验与物品适配。"""

from __future__ import annotations

import gzip
import unittest

from mc_launcher import nbt
from mc_launcher.creator_schema import (
    VanillaCaps,
    build_item,
    describe_scalar,
    detect_era,
    get_node,
    identify_world,
    apply_player_edits,
    set_node,
    typed_to_json,
    json_to_typed,
    validate_number,
)
from mc_launcher.creator_versions import profile_for
from tests.creator_fixtures import build_legacy_player, build_level_dat, build_modern_player

TAG_INT = nbt.TAG_INT
TAG_DOUBLE = nbt.TAG_DOUBLE
TAG_FLOAT = nbt.TAG_FLOAT
TAG_STRING = nbt.TAG_STRING
TAG_COMPOUND = nbt.TAG_COMPOUND
TAG_BYTE = nbt.TAG_BYTE
TAG_SHORT = nbt.TAG_SHORT


class EraDetectionTest(unittest.TestCase):
    def test_modern_snapshot_is_components(self):
        self.assertEqual(detect_era(4189, "1.21.4"), "components")

    def test_1_20_1_is_flattened(self):
        self.assertEqual(detect_era(3465, "1.20.1"), "flattened")

    def test_pre_flattening(self):
        self.assertEqual(detect_era(1343, "1.12.2"), "legacy")

    def test_missing_version_is_unknown(self):
        self.assertEqual(detect_era(0, ""), "unknown")

    def test_old_classic_is_rejected_for_editing(self):
        self.assertEqual(detect_era(0, "rd-132211"), "pre_anvil")

    def test_anvil_without_data_version_is_editable_legacy(self):
        identity = identify_world({"version": 19133})
        self.assertEqual(identity.era, "legacy")
        self.assertTrue(identity.editable)

    def test_anvil_without_data_version_unknown_stays_readonly(self):
        identity = identify_world({"version": 0})
        self.assertEqual(identity.era, "unknown")
        self.assertFalse(identity.editable)


class TypedPathTest(unittest.TestCase):
    def setUp(self):
        _name, self.root = nbt.parse_nbt_typed(build_legacy_player())

    def test_get_node_keeps_type(self):
        node = get_node(self.root, "Health")
        self.assertEqual(node[0], TAG_FLOAT)

    def test_set_node_does_not_change_int_to_byte(self):
        set_node(self.root, "XpLevel", TAG_INT, 99)
        node = get_node(self.root, "XpLevel")
        self.assertEqual(node, (TAG_INT, 99))

    def test_nested_path(self):
        node = get_node(self.root, "Inventory.0.Slot")
        self.assertEqual(node, (TAG_BYTE, 0))


class CapsTest(unittest.TestCase):
    def test_health_cap_is_vanilla_max(self):
        self.assertEqual(VanillaCaps.health(), 1024.0)

    def test_enchant_cap(self):
        self.assertEqual(VanillaCaps.enchant_level(), 255)

    def test_stack_cap_legacy_is_signed_byte(self):
        self.assertEqual(VanillaCaps.max_count("legacy"), 127)

    def test_stack_cap_modern(self):
        self.assertEqual(VanillaCaps.max_count("components"), 99)

    def test_value_over_cap_is_warning_not_error(self):
        warnings = validate_number("Health", 20.0, 1024, "float")
        self.assertEqual(warnings, [])
        warnings = validate_number("Health", 4096.0, 1024, "float")
        self.assertEqual(warnings[0]["code"], "over_vanilla_cap")

    def test_type_range_is_hard_error(self):
        with self.assertRaises(ValueError):
            validate_number("XpLevel", 2**31, 2**31 - 1, "int")


class ItemTest(unittest.TestCase):
    def test_legacy_item_uses_string_id_and_byte_count(self):
        node = build_item("minecraft:diamond_sword", 1, 0, "legacy")
        tag, fields = node
        self.assertEqual(tag, TAG_COMPOUND)
        # 1.8 的 id 是命名空间字符串；Short 数字只属于 1.6 及更早
        self.assertEqual(fields["id"], (TAG_STRING, "minecraft:diamond_sword"))
        self.assertEqual(fields["Count"][0], TAG_BYTE)

    def test_modern_item_uses_string_id_and_int_count(self):
        node = build_item("minecraft:diamond_sword", 64, 0, "components")
        _tag, fields = node
        self.assertEqual(fields["id"], (TAG_STRING, "minecraft:diamond_sword"))
        self.assertEqual(fields["count"], (TAG_INT, 64))

    def test_legacy_large_count_requires_explicit_migration(self):
        with self.assertRaises(ValueError):
            build_item("minecraft:diamond_sword", 999, 0, "legacy")
        node = build_item("minecraft:diamond_sword", 999, 0, "legacy", migrate_count=True)
        self.assertEqual(node[1]["Count"], (TAG_INT, 999))

    def test_components_count_above_vanilla_stack_is_allowed(self):
        # 1.20.5+ 的 count 是 Int，9999 超过原版堆叠 99 但仍可写入
        node = build_item("minecraft:diamond_sword", 9999, 0, "components")
        self.assertEqual(node[1]["count"], (TAG_INT, 9999))

    def test_enchant_level_above_255_is_allowed(self):
        # 旧版附魔等级是 Short，1000 超过原版 255 但仍可写入
        node = build_item(
            "minecraft:diamond_sword",
            1,
            0,
            "legacy",
            enchantments=[{"id": "sharpness", "level": 1000}],
        )
        entry = node[1]["tag"][1]["ench"][1][1][0][1]
        self.assertEqual(entry["lvl"], (TAG_SHORT, 1000))

    def test_negative_enchant_level_is_allowed(self):
        node = build_item(
            "minecraft:diamond_sword",
            1,
            0,
            "legacy",
            enchantments=[{"id": "sharpness", "level": -3}],
        )
        entry = node[1]["tag"][1]["ench"][1][1][0][1]
        self.assertEqual(entry["lvl"], (TAG_SHORT, -3))

    def test_enchant_level_beyond_short_is_rejected(self):
        with self.assertRaises(ValueError):
            build_item(
                "minecraft:diamond_sword",
                1,
                0,
                "legacy",
                enchantments=[{"id": "sharpness", "level": 40000}],
            )

    def test_negative_damage_is_allowed(self):
        node = build_item("minecraft:diamond_sword", 1, 0, "legacy", damage=-5)
        self.assertEqual(node[1]["Damage"], (TAG_SHORT, -5))

    def test_damage_beyond_short_is_rejected(self):
        with self.assertRaises(ValueError):
            build_item("minecraft:diamond_sword", 1, 0, "legacy", damage=40000)

    def test_unknown_era_rejected(self):
        with self.assertRaises(ValueError):
            build_item("minecraft:diamond_sword", 1, 0, "pre_anvil")

    def test_negative_count_is_allowed_in_legacy_byte_range(self):
        node = build_item("minecraft:diamond_sword", -5, 0, "legacy")
        self.assertEqual(node[1]["Count"], (TAG_BYTE, -5))

    def test_negative_count_is_allowed_in_components_int_range(self):
        node = build_item("minecraft:diamond_sword", -99999, 0, "components")
        self.assertEqual(node[1]["count"], (TAG_INT, -99999))

    def test_zero_damage_clears_raw_damage(self):
        node = build_item(
            "minecraft:diamond_sword",
            1,
            0,
            "components",
            damage=0,
            tag_json={
                "tag": 10,
                "value": {"minecraft:damage": {"tag": 3, "value": 9}},
            },
        )
        self.assertNotIn("minecraft:damage", node[1]["components"][1])

    def test_count_beyond_tag_range_is_rejected(self):
        with self.assertRaises(ValueError):
            build_item("minecraft:diamond_sword", -200, 0, "legacy")
        with self.assertRaises(ValueError):
            build_item("minecraft:diamond_sword", 128, 0, "legacy")


class ItemDetailTest(unittest.TestCase):
    """物品详情数值：最大耐久、修复成本、食物、稀有度等。"""

    def test_components_details_written(self):
        node = build_item(
            "minecraft:diamond_sword",
            1,
            0,
            "components",
            details={
                "max_damage": 9999,
                "repair_cost": 40,
                "unbreakable": True,
                "rarity": "epic",
                "glint": "on",
                "nutrition": 20,
                "saturation": 9.5,
            },
        )
        components = node[1]["components"][1]
        self.assertEqual(components["minecraft:max_damage"], (TAG_INT, 9999))
        self.assertEqual(components["minecraft:repair_cost"], (TAG_INT, 40))
        self.assertEqual(components["minecraft:unbreakable"], (TAG_COMPOUND, {}))
        self.assertEqual(components["minecraft:rarity"], (TAG_STRING, "epic"))
        self.assertEqual(components["minecraft:enchantment_glint_override"], (TAG_BYTE, 1))
        food = components["minecraft:food"][1]
        self.assertEqual(food["nutrition"], (TAG_INT, 20))
        self.assertEqual(food["saturation"], (TAG_FLOAT, 9.5))

    def test_components_details_cleared_when_default(self):
        node = build_item(
            "minecraft:diamond_sword",
            1,
            0,
            "components",
            details={
                "max_damage": 0,
                "repair_cost": 0,
                "unbreakable": False,
                "rarity": "common",
                "glint": "default",
                "nutrition": 0,
                "saturation": 0,
            },
        )
        components = node[1].get("components")
        if components:
            for key in (
                "minecraft:max_damage",
                "minecraft:repair_cost",
                "minecraft:unbreakable",
                "minecraft:rarity",
                "minecraft:enchantment_glint_override",
                "minecraft:food",
            ):
                self.assertNotIn(key, components[1])

    def test_legacy_details_written_to_tag(self):
        node = build_item(
            "minecraft:diamond_sword",
            1,
            0,
            "legacy",
            details={"repair_cost": 7, "unbreakable": True},
        )
        tag = node[1]["tag"][1]
        self.assertEqual(tag["RepairCost"], (TAG_INT, 7))
        self.assertEqual(tag["Unbreakable"], (TAG_BYTE, 1))

    def test_legacy_ignores_components_only_details(self):
        node = build_item(
            "minecraft:diamond_sword",
            1,
            0,
            "legacy",
            details={"max_damage": 9999, "rarity": "epic", "nutrition": 10},
        )
        tag = node[1].get("tag")
        if tag:
            self.assertNotIn("MaxDamage", tag[1])
            self.assertNotIn("rarity", tag[1])

    def test_bad_rarity_is_rejected(self):
        with self.assertRaises(ValueError):
            build_item("minecraft:diamond_sword", 1, 0, "components", details={"rarity": "legendary"})

    def test_bad_glint_is_rejected(self):
        with self.assertRaises(ValueError):
            build_item("minecraft:diamond_sword", 1, 0, "components", details={"glint": "glow"})


class PlayerEditTest(unittest.TestCase):
    def test_health_written_as_float(self):
        _name, root = nbt.parse_nbt_typed(build_modern_player())
        apply_player_edits(
            root,
            {"health": 1024.0, "food": 20.0, "xp_level": 21863, "pos": [1.5, 200.0, -3.5]},
            era="components",
        )
        self.assertEqual(get_node(root, "Health"), (TAG_FLOAT, 1024.0))
        self.assertEqual(get_node(root, "XpLevel"), (TAG_INT, 21863))
        pos = get_node(root, "Pos")
        self.assertEqual(pos[0], nbt.TAG_LIST)
        self.assertEqual(pos[1][1][1], (TAG_DOUBLE, 200.0))

    def test_legacy_negative_health_is_written_not_clamped(self):
        _name, root = nbt.parse_nbt_typed(build_legacy_player())
        apply_player_edits(root, {"health": -5.5}, profile_for(0))
        # 1.8 的 Health 是 Short（向上取整），负数也要保留而不是压成 0
        self.assertEqual(get_node(root, "Health"), (TAG_SHORT, -5))
        self.assertEqual(get_node(root, "HealF"), (TAG_FLOAT, -5.5))

    def test_legacy_health_beyond_short_is_clamped_with_warning(self):
        _name, root = nbt.parse_nbt_typed(build_legacy_player())
        warnings = apply_player_edits(root, {"health": 40000.0}, profile_for(0))
        self.assertEqual(get_node(root, "Health"), (TAG_SHORT, 32767))
        self.assertEqual(get_node(root, "HealF"), (TAG_FLOAT, 40000.0))
        self.assertTrue(
            any(item.get("field") == "Health" and "截断" in item.get("message", "") for item in warnings)
        )

    def test_health_above_vanilla_cap_warns_but_is_written(self):
        _name, root = nbt.parse_nbt_typed(build_modern_player())
        warnings = apply_player_edits(root, {"health": 5000.0}, era="components")
        self.assertEqual(get_node(root, "Health"), (TAG_FLOAT, 5000.0))
        self.assertEqual(warnings[0]["code"], "over_vanilla_cap")

    def test_dimension_written_as_string(self):
        _name, root = nbt.parse_nbt_typed(build_modern_player())
        apply_player_edits(root, {"dimension": "twilightforest:twilight_forest"}, era="components")
        self.assertEqual(
            get_node(root, "Dimension"),
            (TAG_STRING, "twilightforest:twilight_forest"),
        )

    def test_legacy_inventory_uses_string_id(self):
        _name, root = nbt.parse_nbt_typed(build_legacy_player())
        apply_player_edits(
            root,
            {"inventory": [{"slot": 0, "id": "minecraft:diamond", "count": 64}]},
            era="legacy",
        )
        entry = get_node(root, "Inventory")[1][1][0][1]
        self.assertEqual(entry["id"], (TAG_STRING, "minecraft:diamond"))
        self.assertEqual(entry["Count"], (TAG_BYTE, 64))

    def test_legacy_flying_is_written_into_abilities(self):
        root = (
            TAG_COMPOUND,
            {
                "abilities": (
                    TAG_COMPOUND,
                    {
                        "flying": (TAG_BYTE, 0),
                        "mayfly": (TAG_BYTE, 0),
                        "flySpeed": (TAG_FLOAT, 0.05),
                    },
                )
            },
        )
        apply_player_edits(root, {"flying": True}, profile_for(0))
        abilities = root[1]["abilities"][1]
        self.assertEqual(abilities["flying"], (TAG_BYTE, 1))
        self.assertEqual(abilities["mayfly"], (TAG_BYTE, 1))
        self.assertEqual(abilities["flySpeed"], (TAG_FLOAT, 0.05))
        self.assertNotIn("Flying", root[1])


class EnchantmentTest(unittest.TestCase):
    def test_legacy_enchant_accepts_chinese_and_numeric(self):
        node = build_item(
            "minecraft:diamond_sword",
            1,
            0,
            "legacy",
            enchantments=[
                {"id": "锋利", "level": 5},
                {"id": "#34", "level": 3},
            ],
        )
        entries = node[1]["tag"][1]["ench"][1][1]
        self.assertEqual(
            [(entry[1]["id"], entry[1]["lvl"]) for entry in entries],
            [((TAG_SHORT, 16), (TAG_SHORT, 5)), ((TAG_SHORT, 34), (TAG_SHORT, 3))],
        )

    def test_duplicate_enchant_keeps_last_level(self):
        node = build_item(
            "minecraft:diamond_sword",
            1,
            0,
            "legacy",
            enchantments=[
                {"id": "sharpness", "level": 1},
                {"id": "minecraft:sharpness", "level": 5},
            ],
        )
        entries = node[1]["tag"][1]["ench"][1][1]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0][1]["lvl"], (TAG_SHORT, 5))

    def test_unknown_enchant_reports_hint(self):
        with self.assertRaises(ValueError) as ctx:
            build_item("minecraft:diamond_sword", 1, 0, "legacy",
                       enchantments=[{"id": "不存在", "level": 1}])
        self.assertIn("中文名", str(ctx.exception))

    def test_modded_enchant_namespace_is_preserved(self):
        node = build_item(
            "minecraft:diamond_sword", 1, 0, "flattened",
            enchantments=[{"id": "mymod:custom_enchant", "level": 2}],
        )
        entries = node[1]["tag"][1]["Enchantments"][1][1]
        self.assertEqual(entries[0][1]["id"], (TAG_STRING, "mymod:custom_enchant"))
        # 旧版只认数字 ID，模组附魔必须明确报错而不是静默丢弃
        with self.assertRaises(ValueError):
            build_item(
                "minecraft:diamond_sword", 1, 0, "legacy",
                enchantments=[{"id": "mymod:custom_enchant", "level": 2}],
            )

    def test_1_8_rejects_enchant_that_only_exists_later(self):
        # 1.8 附魔表没有经验修补；静默写入等于「附魔没生效」
        with self.assertRaises(ValueError):
            build_item(
                "minecraft:diamond_sword", 1, 0, "legacy",
                enchantments=[{"id": "mending", "level": 1}],
            )

    def test_clearing_enchantments_removes_raw_tag_entries(self):
        # 界面把附魔清空时必须同步删掉 Raw NBT 里的旧附魔，否则会「删不掉」
        tag_json = {
            "tag": 10,
            "value": {
                "Enchantments": {"tag": 9, "element_tag": 10, "value": []},
                "AttributeModifiers": {"tag": 9, "element_tag": 10, "value": []},
                "display": {"tag": 10, "value": {"Name": {"tag": 8, "value": "x"}}},
            },
        }
        node = build_item(
            "minecraft:diamond_sword",
            1,
            0,
            "legacy",
            enchantments=[],
            attributes=[],
            tag_json=tag_json,
        )
        tag = node[1]["tag"][1]
        self.assertNotIn("Enchantments", tag)
        self.assertNotIn("AttributeModifiers", tag)
        self.assertIn("display", tag)

    def test_omitting_enchantments_keeps_raw_tag_entries(self):
        tag_json = {"tag": 10, "value": {"Enchantments": {"tag": 9, "element_tag": 10, "value": []}}}
        node = build_item("minecraft:diamond_sword", 1, 0, "legacy", tag_json=tag_json)
        self.assertIn("Enchantments", node[1]["tag"][1])


class ItemAttributeTest(unittest.TestCase):
    def test_components_item_writes_attribute_modifiers(self):
        node = build_item(
            "minecraft:diamond_sword",
            1,
            0,
            "components",
            attributes=[
                {
                    "name": "minecraft:generic.attack_damage",
                    "amount": 100.0,
                    "operation": "add_value",
                    "slot": "mainhand",
                }
            ],
        )
        components = node[1]["components"][1]
        modifiers = components["minecraft:attribute_modifiers"][1]["modifiers"]
        self.assertEqual(modifiers[0], nbt.TAG_LIST)
        values = modifiers[1][1][0][1]
        self.assertEqual(values["type"], (TAG_STRING, "minecraft:generic.attack_damage"))
        self.assertEqual(values["amount"], (TAG_DOUBLE, 100.0))
        self.assertEqual(values["slot"], (TAG_STRING, "mainhand"))
        self.assertEqual(values["operation"], (TAG_STRING, "add_value"))

    def test_legacy_item_writes_tag_attribute_modifiers(self):
        node = build_item(
            "minecraft:diamond_sword",
            1,
            0,
            "legacy",
            attributes=[{"name": "generic.attack_damage", "amount": 50, "operation": 0}],
        )
        modifiers = node[1]["tag"][1]["AttributeModifiers"]
        self.assertEqual(modifiers[0], nbt.TAG_LIST)
        values = modifiers[1][1][0][1]
        self.assertEqual(values["AttributeName"], (TAG_STRING, "generic.attackDamage"))
        self.assertEqual(values["Amount"], (TAG_DOUBLE, 50.0))
        self.assertEqual(values["Operation"], (TAG_INT, 0))
        # "any" 不能写进 1.8 的 Slot（会被丢弃），省略 Slot 才表示全局生效
        self.assertNotIn("Slot", values)


class PlayerExtraFieldTest(unittest.TestCase):
    def test_food_level_ender_items_and_modifiers(self):
        _name, root = nbt.parse_nbt_typed(build_level_dat())
        player = root[1]["Data"][1]["Player"]
        apply_player_edits(
            player,
            {
                "food_level": 7,
                "ender_items": [
                    {"slot": 0, "id": "minecraft:diamond", "count": 12},
                ],
                "attributes": [
                    {
                        "name": "generic.movement_speed",
                        "base": 0.1,
                        "modifiers": [
                            {"amount": 5.0, "operation": 1},
                        ],
                    }
                ],
            },
            era="flattened",
        )
        self.assertEqual(get_node(player, "foodLevel"), (TAG_INT, 7))
        ender = get_node(player, "EnderItems")
        self.assertEqual(ender[0], nbt.TAG_LIST)
        self.assertEqual(ender[1][1][0][1]["id"], (TAG_STRING, "minecraft:diamond"))
        attribute = get_node(player, "Attributes")[1][1][0][1]
        self.assertEqual(attribute["Base"], (TAG_DOUBLE, 0.1))
        modifier = attribute["Modifiers"][1][1][0][1]
        self.assertEqual(modifier["Amount"], (TAG_DOUBLE, 5.0))
        self.assertEqual(modifier["Operation"], (TAG_INT, 1))
        # 未指定名字时用 UUID 作为唯一标识，避免同名修饰符互相覆盖
        self.assertEqual(modifier["Name"][0], TAG_STRING)
        self.assertTrue(modifier["Name"][1])

    def test_components_1205_keeps_pascal_attributes(self):
        _name, root = nbt.parse_nbt_typed(build_modern_player())
        apply_player_edits(
            root,
            {
                "attributes": [
                    {
                        "name": "minecraft:generic.max_health",
                        "base": 20.0,
                        "modifiers": [{"amount": 100.0, "operation": 1}],
                    }
                ]
            },
            era="components",
        )
        attribute = get_node(root, "Attributes")[1][1][0][1]
        self.assertEqual(attribute["Name"], (TAG_STRING, "minecraft:generic.max_health"))
        self.assertEqual(attribute["Base"], (TAG_DOUBLE, 20.0))
        modifier = attribute["Modifiers"][1][1][0][1]
        self.assertEqual(modifier["Amount"], (TAG_DOUBLE, 100.0))
        self.assertEqual(modifier["Operation"], (TAG_INT, 1))

    def test_121_attribute_modifiers_use_lowercase_keys(self):
        _name, root = nbt.parse_nbt_typed(build_modern_player())
        apply_player_edits(
            root,
            {
                "attributes": [
                    {
                        "name": "minecraft:generic.max_health",
                        "base": 20.0,
                        "modifiers": [{"amount": 100.0, "operation": "add_value"}],
                    }
                ]
            },
            era=profile_for(3955),
        )
        attribute = get_node(root, "attributes")[1][1][0][1]
        self.assertEqual(attribute["id"], (TAG_STRING, "minecraft:generic.max_health"))
        self.assertEqual(attribute["base"], (TAG_DOUBLE, 20.0))
        modifier = attribute["modifiers"][1][1][0][1]
        self.assertEqual(modifier["amount"], (TAG_DOUBLE, 100.0))
        self.assertEqual(modifier["operation"], (TAG_STRING, "add_value"))


class ScalarLabelTest(unittest.TestCase):
    """「全部数值」译名：能确定的字段翻译，认不出的交给界面显示原文。"""

    def test_known_player_field(self):
        label, note = describe_scalar("Health")
        self.assertEqual(label, "生命值")
        self.assertIn("1024", note)

    def test_known_world_field(self):
        self.assertEqual(describe_scalar("WorldGenSettings.seed")[0], "世界种子")
        self.assertEqual(describe_scalar("RandomSeed")[0], "世界种子")

    def test_game_rule_label(self):
        label, note = describe_scalar("GameRules.keepInventory")
        self.assertEqual(label, "游戏规则：死亡不掉落")
        self.assertIn("true", note)

    def test_unknown_game_rule_keeps_raw_name(self):
        self.assertEqual(describe_scalar("GameRules.customModRule")[0], "游戏规则：customModRule")

    def test_axis_field(self):
        self.assertEqual(describe_scalar("Pos.2")[0], "坐标 Z")
        self.assertEqual(describe_scalar("Motion.0")[0], "运动速度 X")

    def test_gateway_field(self):
        self.assertEqual(describe_scalar("DragonFight.Gateways.1")[0], "末地折跃门坐标")

    def test_nested_field_falls_back_to_last_segment(self):
        # 模组把原版字段塞进自定义容器时，仍然按最后一段给译名
        label, _note = describe_scalar("ForgeCaps.some.Health")
        self.assertEqual(label, "生命值")

    def test_unknown_field_returns_empty(self):
        self.assertEqual(describe_scalar("CustomModdedField"), ("", ""))
        self.assertEqual(describe_scalar(""), ("", ""))


class TypedJsonTest(unittest.TestCase):
    def test_roundtrip_preserves_long_precision(self):
        node = (nbt.TAG_LONG, 9007199254740993)
        data = typed_to_json(node)
        self.assertEqual(json_to_typed(data), node)

    def test_roundtrip_list(self):
        node = (nbt.TAG_LIST, (TAG_DOUBLE, [(TAG_DOUBLE, 1.0), (TAG_DOUBLE, 2.0)]))
        self.assertEqual(json_to_typed(typed_to_json(node)), node)

    def test_reject_unknown_tag(self):
        with self.assertRaises(ValueError):
            json_to_typed({"tag": 99, "value": 1})


if __name__ == "__main__":
    unittest.main()
