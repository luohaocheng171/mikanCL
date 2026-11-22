"""版本档案与按版本写入格式的回归测试。"""

from __future__ import annotations

import gzip
import json
import tempfile
import unittest
import uuid as uuidlib
import zipfile
from pathlib import Path

from mc_launcher import nbt
from mc_launcher.creator_schema import apply_player_edits, build_item
from mc_launcher.creator_service import CreatorService
from mc_launcher.creator_versions import (
    attribute_name,
    effect_id,
    legacy_anvil_label,
    profile_for,
    version_label,
)
from tests.creator_fixtures import build_level_dat, build_modern_player, make_world
from mc_launcher.nbt import (
    TAG_BYTE,
    TAG_COMPOUND,
    TAG_FLOAT,
    TAG_INT,
    TAG_LIST,
    TAG_SHORT,
    TAG_STRING,
)


class VersionProfileTest(unittest.TestCase):
    def test_1_8_is_legacy_with_int_dimension(self):
        profile = profile_for(0)
        self.assertEqual(profile.era, "legacy")
        self.assertEqual(profile.dimension_tag, TAG_INT)
        self.assertEqual(profile.player_storage, "level")
        # 1.7 起物品 NBT 的 id 就是命名空间字符串，不是数字
        self.assertEqual(profile.item_format, "string")
        self.assertTrue(profile.heal_legacy)

    def test_1_6_and_earlier_use_numeric_item_id(self):
        self.assertEqual(profile_for(0, "1.6.4").item_format, "numeric")
        self.assertEqual(profile_for(0, "1.8.9").item_format, "string")
        self.assertEqual(profile_for(0, "1.12.2").item_format, "string")

    def test_1_13_moves_player_to_playerdata(self):
        profile = profile_for(1519, "1.13")
        self.assertEqual(profile.era, "flattened")
        self.assertEqual(profile.player_storage, "playerdata")
        self.assertEqual(profile.item_format, "string")

    def test_1_16_dimension_is_string(self):
        profile = profile_for(2566, "1.16")
        self.assertEqual(profile.dimension_tag, TAG_STRING)

    def test_chinese_attribute_and_effect_aliases(self):
        self.assertEqual(attribute_name("攻击伤害", profile_for(0)), "generic.attackDamage")
        self.assertEqual(attribute_name("护甲", profile_for(3953, "1.21")), "minecraft:generic.armor")
        # 攻击距离/交互距离：1.20.5-1.21.1 必须保留 player. 前缀，1.21.2+ 去前缀
        self.assertEqual(
            attribute_name("攻击距离", profile_for(3837, "1.20.5")),
            "minecraft:player.entity_interaction_range",
        )
        self.assertEqual(
            attribute_name("minecraft:player.entity_interaction_range", profile_for(3837, "1.20.5")),
            "minecraft:player.entity_interaction_range",
        )
        self.assertEqual(
            attribute_name("方块交互距离", profile_for(4189, "1.21.4")),
            "minecraft:block_interaction_range",
        )
        self.assertEqual(
            attribute_name("实体交互距离", profile_for(4189, "1.21.4")),
            "minecraft:entity_interaction_range",
        )
        self.assertEqual(
            attribute_name("挖掘效率", profile_for(3953, "1.21")),
            "minecraft:player.mining_efficiency",
        )
        self.assertEqual(effect_id("速度", profile_for(0)), 1)
        self.assertEqual(effect_id("生命恢复", profile_for(3953, "1.21")), "minecraft:regeneration")
        with self.assertRaises(ValueError):
            effect_id("不存在", profile_for(0))
        with self.assertRaises(ValueError):
            effect_id(9999, profile_for(3953, "1.21"))

    def test_1_20_5_components(self):
        profile = profile_for(3837, "1.20.5")
        self.assertEqual(profile.era, "components")
        self.assertEqual(profile.effects_key, "active_effects")
        self.assertEqual(profile.effect_style, "namespaced")
        self.assertEqual(profile.count_tag, TAG_INT)

    def test_1_20_2_renames_active_effects(self):
        # 23w32a（1.20.2）起 ActiveEffects -> active_effects，效果 ID 改为命名空间字符串；
        # 阈值若错到 1.20.5，1.20.2 - 1.20.4 存档写的效果会被游戏忽略
        self.assertEqual(profile_for(3465, "1.20.1").effects_key, "ActiveEffects")
        self.assertEqual(profile_for(3465, "1.20.1").effect_style, "numeric")
        self.assertEqual(profile_for(3578, "1.20.2").effects_key, "active_effects")
        self.assertEqual(profile_for(3578, "1.20.2").effect_style, "namespaced")
        # 属性改名的阈值仍是 1.21，不能被效果改名提前带跑
        self.assertEqual(profile_for(3578, "1.20.2").attributes_key, "Attributes")

    def test_1_21_attributes_use_lowercase(self):
        profile = profile_for(3953, "1.21")
        self.assertEqual(profile.attributes_key, "attributes")
        self.assertEqual(profile.modifier_style, "id")

    def test_1_21_2_drops_generic_prefix(self):
        profile = profile_for(4080, "1.21.2")
        self.assertEqual(profile.attribute_name("generic.max_health"), "minecraft:max_health")

    def test_players_data_layout(self):
        profile = profile_for(3955, "1.21.1", players_data=True, singleplayer_uuid=True)
        self.assertEqual(profile.player_storage, "players")

    def test_offhand_slot_follows_version(self):
        self.assertIsNone(profile_for(0).offhand_slot)  # 1.8 没有副手
        self.assertEqual(profile_for(169, "1.9").offhand_slot, -106)
        # 1.12+ 也仍然是 150（字节 -106），不是 40
        self.assertEqual(profile_for(1132, "1.12").offhand_slot, -106)
        self.assertEqual(profile_for(3465, "1.20.1").offhand_slot, -106)
        self.assertTrue(profile_for(0).ender_items)

    def test_field_hints_describe_version_specific_ranges(self):
        from mc_launcher.creator_schema import field_hints

        legacy = field_hints(profile_for(0))
        modern = field_hints(profile_for(3837, "1.20.5"))
        self.assertIn("没有副手槽", legacy["inventory_slot"]["note"])
        # min/max 是 Byte 标签硬范围，不再把界面限制在 0-103 / -106
        self.assertEqual(legacy["inventory_slot"]["max"], 127)
        self.assertEqual(modern["inventory_slot"]["max"], 127)
        self.assertEqual(modern["inventory_slot"]["min"], -128)
        self.assertEqual(modern["inventory_slot"]["offhand"], -106)
        # Amplifier 是 Byte，最多 127；原版 255 只写在提示里
        self.assertEqual(legacy["effect_amplifier"]["max"], 127)
        self.assertIn("255", legacy["effect_amplifier"]["note"])
        self.assertEqual(legacy["xp_level"]["max"], 2**31 - 1)
        self.assertEqual(legacy["health"]["min"], -3.4028235e38)
        self.assertIn("1024", legacy["health"]["note"])
        # 附魔等级按标签类型放开：旧版 Short，1.20.5+ Int
        self.assertEqual(legacy["enchant_level"]["max"], 32767)
        self.assertEqual(modern["enchant_level"]["max"], 2**31 - 1)

    def test_version_labels(self):
        self.assertEqual(version_label(3465, "1.20.1"), "1.20.1")
        self.assertIn("1.21", version_label(3953, ""))
        self.assertIn("1.8", legacy_anvil_label({"version": 19133, "MapFeatures": 1}))


class EffectPresetTest(unittest.TestCase):
    """萌新中文名 / 老手原文切换，以及按版本过滤效果。"""

    def test_label_switches_between_chinese_and_raw(self):
        from mc_launcher.creator_versions import effect_label

        self.assertEqual(effect_label(10, profile_for(0)), "生命恢复")
        self.assertEqual(
            effect_label("minecraft:regeneration", profile_for(3953, "1.21")), "生命恢复"
        )
        self.assertEqual(effect_label("速度", profile_for(0)), "速度")
        # 老版本写数字 ID，1.20.2+ 写命名空间字符串
        self.assertEqual(effect_label(10, profile_for(3465, "1.20.1"), raw=True), "10")
        self.assertEqual(
            effect_label(10, profile_for(3953, "1.21"), raw=True), "minecraft:regeneration"
        )
        # 未知值原样返回，不吞掉模组效果
        self.assertEqual(effect_label("mymod:freeze"), "mymod:freeze")

    def test_presets_follow_game_version(self):
        from mc_launcher.creator_versions import effect_presets

        legacy = {item["number"] for item in effect_presets(profile_for(0))}
        modern = {item["number"] for item in effect_presets(profile_for(3953, "1.21"))}
        self.assertIn(1, legacy)
        self.assertNotIn(24, legacy)  # 1.9 才有发光
        self.assertIn(24, modern)
        self.assertIn(33, modern)  # 1.19 黑暗
        self.assertIn(39, modern)  # 1.21 寄生
        self.assertNotIn(
            33, {item["number"] for item in effect_presets(profile_for(2975, "1.18.2"))}
        )
        # 潮涌能量 1.13 才加入
        self.assertNotIn(
            29, {item["number"] for item in effect_presets(profile_for(1132, "1.12"))}
        )
        self.assertIn(
            29, {item["number"] for item in effect_presets(profile_for(1519, "1.13"))}
        )

    def test_preset_value_matches_effect_style(self):
        from mc_launcher.creator_versions import effect_presets

        legacy = next(p for p in effect_presets(profile_for(0)) if p["number"] == 1)
        modern = next(
            p for p in effect_presets(profile_for(3953, "1.21")) if p["number"] == 1
        )
        self.assertEqual(legacy["id"], 1)
        self.assertEqual(legacy["label"], "速度")
        self.assertEqual(modern["id"], "minecraft:speed")
        self.assertEqual(modern["name"], "speed")


class EnchantPresetTest(unittest.TestCase):
    """附魔译名与按版本过滤。"""

    def test_label(self):
        from mc_launcher.creator_schema import enchant_label

        self.assertEqual(enchant_label("minecraft:sharpness"), "锋利")
        self.assertEqual(enchant_label("锋利"), "锋利")
        self.assertEqual(enchant_label(16), "锋利")
        self.assertEqual(enchant_label("sharpness", raw=True), "minecraft:sharpness")
        self.assertEqual(enchant_label("mymod:custom"), "custom")

    def test_presets_cover_all_versions_with_support_flag(self):
        """附魔列表全量给出：本版本没有的也保留，用 supported=False 标注（Mod 可能支持）。"""
        from mc_launcher.creator_schema import enchantment_presets

        def supported(profile):
            return {item["name"] for item in enchantment_presets(profile) if item.get("supported")}

        def all_names(profile):
            return {item["name"] for item in enchantment_presets(profile)}

        # 1.12.2：锋利、经验修补（1.9 加入）可用；忠诚（1.13）与风爆不在原版里，
        # 但条目仍然全量给出，方便 Mod 环境下直接插入
        legacy = profile_for(1343, "1.12.2")
        self.assertIn("sharpness", supported(legacy))
        self.assertIn("mending", supported(legacy))
        self.assertNotIn("loyalty", supported(legacy))
        self.assertNotIn("wind_burst", supported(legacy))
        self.assertIn("loyalty", all_names(legacy))
        self.assertIn("wind_burst", all_names(legacy))

        # 1.9 起经验修补可用；1.21 起风爆/致密可用
        self.assertIn("mending", supported(profile_for(169, "1.9")))
        modern = supported(profile_for(3953, "1.21"))
        self.assertIn("wind_burst", modern)
        self.assertIn("density", modern)
        # 1.20.5 还没有风爆
        self.assertNotIn("wind_burst", supported(profile_for(3837, "1.20.5")))
        # 不支持时附带说明，供界面显示「需 Mod」
        gap = [item for item in enchantment_presets(profile_for(3837, "1.20.5"))
               if item["name"] == "wind_burst"][0]
        self.assertFalse(gap["supported"])
        self.assertTrue(gap["note"])


class GamerulePresetTest(unittest.TestCase):
    """新版游戏规则按存档版本过滤（1.14 巡逻、1.17 睡觉比例、1.19.4 积雪、1.21.2 伤害开关）。"""

    def test_version_filter(self):
        from mc_launcher.creator_versions import gamerule_presets

        legacy = {item["name"] for item in gamerule_presets(profile_for(0))}
        self.assertIn("randomTickSpeed", legacy)
        self.assertIn("maxCommandChainLength", legacy)
        self.assertNotIn("doPatrolSpawning", legacy)
        self.assertNotIn("playersSleepingPercentage", legacy)

        v1201 = {item["name"] for item in gamerule_presets(profile_for(3465, "1.20.1"))}
        self.assertIn("doPatrolSpawning", v1201)
        self.assertIn("playersSleepingPercentage", v1201)
        self.assertIn("snowAccumulationHeight", v1201)
        self.assertNotIn("fallDamage", v1201)

        modern = {item["name"] for item in gamerule_presets(profile_for(3953, "1.21"))}
        self.assertIn("doWardenSpawning", modern)
        self.assertIn("doVinesSpread", modern)
        self.assertIn("tntExplosionDropDecay", modern)

    def test_rules_carry_type_and_label(self):
        from mc_launcher.creator_versions import gamerule_presets

        preset = next(
            item
            for item in gamerule_presets(profile_for(3953, "1.21"))
            if item["name"] == "playersSleepingPercentage"
        )
        self.assertEqual(preset["kind"], "int")
        self.assertEqual(preset["label"], "睡觉玩家比例")
        self.assertEqual(preset["default"], 100)
        bool_rule = next(
            item
            for item in gamerule_presets(profile_for(3953, "1.21"))
            if item["name"] == "doVinesSpread"
        )
        self.assertEqual(bool_rule["kind"], "bool")
        self.assertTrue(bool_rule["default"])


class VersionedPlayerWriteTest(unittest.TestCase):
    def test_legacy_player_gets_healf_and_int_dimension(self):
        root = (TAG_COMPOUND, {"Health": (TAG_FLOAT, 20.0), "Dimension": (TAG_STRING, "0")})
        apply_player_edits(root, {"health": 30.5}, profile_for(0))
        # 1.8 的 Health 是 Short（向上取整），真实值写在 HealF
        self.assertEqual(root[1]["Health"], (TAG_SHORT, 31))
        self.assertEqual(root[1]["HealF"], (TAG_FLOAT, 30.5))
        self.assertEqual(root[1]["Dimension"], (TAG_INT, 0))

    def test_modern_dimension_int_is_repaired_to_name(self):
        root = (TAG_COMPOUND, {"Dimension": (TAG_INT, -1)})
        apply_player_edits(root, {"health": 10}, profile_for(3465, "1.20.1"))
        self.assertEqual(root[1]["Dimension"], (TAG_STRING, "minecraft:the_nether"))

    def test_effects_use_namespaced_id_for_1_20_5(self):
        root = (TAG_COMPOUND, {})
        apply_player_edits(
            root,
            {"effects": [{"id": "minecraft:speed", "amplifier": 2, "duration": 600}]},
            profile_for(3837, "1.20.5"),
        )
        effect = root[1]["active_effects"][1][1][0][1]
        self.assertEqual(effect["id"], (TAG_STRING, "minecraft:speed"))
        self.assertEqual(effect["amplifier"], (TAG_BYTE, 2))
        self.assertEqual(effect["duration"], (TAG_INT, 600))
        self.assertNotIn("ActiveEffects", root[1])

    def test_legacy_effects_use_numeric_id(self):
        root = (TAG_COMPOUND, {})
        apply_player_edits(
            root,
            {"effects": [{"id": "minecraft:speed", "amplifier": 1, "duration": 200}]},
            profile_for(0),
        )
        effect = root[1]["ActiveEffects"][1][1][0][1]
        self.assertEqual(effect["Id"], (TAG_BYTE, 1))
        self.assertEqual(effect["Amplifier"], (TAG_BYTE, 1))

    def test_legacy_offhand_slot_is_reported(self):
        root = (TAG_COMPOUND, {})
        warnings = apply_player_edits(
            root,
            {"inventory": [{"slot": 40, "id": "minecraft:diamond_sword", "count": 1}]},
            profile_for(0),
        )
        self.assertTrue(any("没有副手槽" in item["message"] for item in warnings))
        self.assertIn("Inventory", root[1])

    def test_1_9_offhand_uses_minus_106(self):
        root = (TAG_COMPOUND, {})
        warnings = apply_player_edits(
            root,
            {"inventory": [{"slot": 40, "id": "minecraft:diamond_sword", "count": 1}]},
            profile_for(169, "1.9"),
        )
        self.assertTrue(any("-106" in item["message"] for item in warnings))

    def test_ender_slot_out_of_range_is_reported(self):
        root = (TAG_COMPOUND, {})
        warnings = apply_player_edits(
            root,
            {"ender_items": [{"slot": 27, "id": "minecraft:diamond", "count": 1}]},
            profile_for(3465, "1.20.1"),
        )
        self.assertTrue(any("末影箱" in item["message"] for item in warnings))

    def test_absorption_and_flying_are_written(self):
        root = (TAG_COMPOUND, {})
        apply_player_edits(
            root,
            {"absorption": 8.0, "flying": True, "food_exhaustion": 1.5, "invulnerable": True},
            profile_for(3465, "1.20.1"),
        )
        self.assertEqual(root[1]["AbsorptionAmount"], (TAG_FLOAT, 8.0))
        self.assertEqual(root[1]["Flying"], (TAG_BYTE, 1))
        self.assertEqual(root[1]["Mayfly"], (TAG_BYTE, 1))
        self.assertEqual(root[1]["foodExhaustionLevel"], (TAG_FLOAT, 1.5))
        self.assertEqual(root[1]["Invulnerable"], (TAG_BYTE, 1))


class VersionedItemWriteTest(unittest.TestCase):
    def test_components_enchantments_are_compound_map(self):
        node = build_item(
            "minecraft:diamond_sword",
            1,
            0,
            profile_for(3955, "1.21.1"),
            enchantments=[{"id": "minecraft:sharpness", "level": 5}],
        )
        levels = node[1]["components"][1]["minecraft:enchantments"][1]["levels"]
        self.assertEqual(levels[0], TAG_COMPOUND)
        self.assertEqual(levels[1]["minecraft:sharpness"], (TAG_INT, 5))

    def test_legacy_item_uses_string_id_and_byte_count(self):
        node = build_item("minecraft:diamond_sword", 1, 0, profile_for(0))
        # 1.8 游戏自己写的就是命名空间字符串 ID；写成 Short 数字会让整格物品读成空气
        self.assertEqual(node[1]["id"], (TAG_STRING, "minecraft:diamond_sword"))
        self.assertEqual(node[1]["Count"][0], TAG_BYTE)
        self.assertEqual(node[1]["Damage"], (TAG_SHORT, 0))

    def test_legacy_attribute_modifier_drops_any_slot(self):
        # 1.8 的 tag.AttributeModifiers 不认 "any"（会被解析成 null 后丢弃），
        # 不写 Slot 才表示对所有槽位生效
        node = build_item(
            "minecraft:diamond_sword",
            1,
            0,
            profile_for(0),
            attributes=[{"name": "minecraft:generic.attack_damage", "amount": 100, "operation": "add_value", "slot": "any"}],
        )
        modifier = node[1]["tag"][1]["AttributeModifiers"][1][1][0][1]
        self.assertNotIn("Slot", modifier)
        self.assertEqual(modifier["AttributeName"], (TAG_STRING, "generic.attackDamage"))
        self.assertEqual(modifier["Operation"], (TAG_INT, 0))

    def test_modern_component_keeps_any_slot(self):
        node = build_item(
            "minecraft:diamond_sword",
            1,
            0,
            profile_for(3955, "1.21.1"),
            attributes=[{"name": "attack_damage", "amount": 100, "operation": "add_value", "slot": "any"}],
        )
        modifier = node[1]["components"][1]["minecraft:attribute_modifiers"][1]["modifiers"][1][1][0][1]
        self.assertEqual(modifier["slot"], (TAG_STRING, "any"))

    def test_1_6_item_still_uses_numeric_short_id(self):
        node = build_item("minecraft:diamond_sword", 1, 0, profile_for(0, "1.6.4"))
        self.assertEqual(node[1]["id"], (TAG_SHORT, 276))

    def test_armor_slot_36_to_39_is_rewritten_to_100_to_103(self):
        # 界面习惯写 36-39，但游戏只认 100-103，否则护甲会被忽略
        for legacy_slot, real_slot in ((36, 100), (37, 101), (38, 102), (39, 103)):
            node = build_item("minecraft:diamond_helmet", 1, legacy_slot, profile_for(0))
            self.assertEqual(node[1]["Slot"], (TAG_BYTE, real_slot))

    def test_offhand_40_is_rewritten_to_minus_106(self):
        node = build_item("minecraft:shield", 1, 40, profile_for(3465, "1.20.1"))
        self.assertEqual(node[1]["Slot"], (TAG_BYTE, -106))
        legacy = build_item("minecraft:shield", 1, 40, profile_for(0))
        # 1.8 没有副手，保持原样交给警告提示
        self.assertEqual(legacy[1]["Slot"], (TAG_BYTE, 40))


class MirrorWriteTest(unittest.TestCase):
    def _write_player(self, path: Path, root_name: str = "") -> None:
        data = gzip.decompress(build_modern_player())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def test_level_player_and_playerdata_are_both_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            world = make_world(root)
            player_uuid = "11111111-2222-3333-4444-555555555555"
            self._write_player(world / "playerdata" / f"{player_uuid}.dat")
            service = CreatorService(root, root / "backups")
            state = service.open(world)
            self.assertEqual(state["player_uuid"], player_uuid)
            preview = service.preview(
                {"world": str(world), "player_uuid": player_uuid, "player": {"health": 33.0}}
            )
            self.assertEqual(len(preview["targets"]), 2)
            result = service.apply(preview["token"])
            self.assertTrue(result["verified"], result["mismatches"])

            for target in preview["targets"]:
                path = Path(target)
                root_name, node = nbt.load_nbt_typed_file(path)
                fields = node[1] if path.name != "level.dat" else node[1]["Data"][1]["Player"][1]
                self.assertEqual(fields["Health"], (TAG_FLOAT, 33.0), str(path))

    def test_players_data_layout_is_used_for_modern_world(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            world = root / "saves" / "ModernWorld"
            world.mkdir(parents=True)
            (world / "level.dat").write_bytes(build_level_dat(data_version=3955, version_name="1.21.1"))
            player_uuid = str(uuidlib.uuid4())
            self._write_player(world / "players" / "data" / f"{player_uuid}.dat")

            service = CreatorService(root, root / "backups")
            state = service.open(world)
            self.assertEqual(state["player_storage"], "players")
            self.assertEqual(state["player_uuid"], player_uuid)
            preview = service.preview(
                {"world": str(world), "player_uuid": player_uuid, "player": {"xp_level": 77}}
            )
            result = service.apply(preview["token"])
            self.assertTrue(result["verified"], result["mismatches"])
            _name, node = nbt.load_nbt_typed_file(world / "players" / "data" / f"{player_uuid}.dat")
            self.assertEqual(node[1]["XpLevel"], (TAG_INT, 77))
            self.assertFalse((world / "playerdata").exists())


class ItemScanTest(unittest.TestCase):
    def test_modern_jar_items_definitions(self):
        from mc_launcher.creator_items import _items_from_jar

        with tempfile.TemporaryDirectory() as tmp:
            jar = Path(tmp) / "1.21.8.jar"
            with zipfile.ZipFile(jar, "w") as zf:
                zf.writestr("assets/minecraft/items/diamond.json", "{}")
                zf.writestr(
                    "assets/minecraft/lang/en_us.json",
                    json.dumps({"item.minecraft.diamond": "Diamond"}),
                )
            items = {
                item["id"]: item["name"]
                for item in _items_from_jar(jar, "components")[0]
            }
            self.assertEqual(items.get("minecraft:diamond"), "Diamond")

    def test_legacy_jar_uses_models_and_camel_lang(self):
        from mc_launcher.creator_items import _items_from_jar

        with tempfile.TemporaryDirectory() as tmp:
            jar = Path(tmp) / "1.8.9.jar"
            with zipfile.ZipFile(jar, "w") as zf:
                zf.writestr("assets/minecraft/models/item/diamond_sword.json", "{}")
                zf.writestr("assets/minecraft/blockstates/stone.json", "{}")
                zf.writestr(
                    "assets/minecraft/lang/en_US.lang",
                    "tile.stone.name=Stone\nitem.swordDiamond.name=Diamond Sword\n",
                )
            items = {
                item["id"]: item["name"] for item in _items_from_jar(jar, "legacy")[0]
            }
            # 旧版 ID 来自模型/方块状态（真实注册名），显示名再回查驼峰语言键
            self.assertEqual(items.get("minecraft:stone"), "Stone")
            self.assertEqual(items.get("minecraft:diamond_sword"), "Diamond Sword")
            self.assertIn("minecraft:stone", _items_from_jar(jar, "legacy")[1])


if __name__ == "__main__":
    unittest.main()
