"""创世神面板：NBT 类型安全读写、版本能力识别与范围校验。

所有写入都以显式标签类型进行，绝不依赖 ``int -> TAG_Int`` 的默认推断，
避免 Byte / Short / Long 在保存时悄悄改型。

原版上限（vanilla cap）只做软警告，真正的硬边界是 NBT 标签本身的
可表达范围：超出前者说明游戏可能读档异常，超出后者根本无法编码。
"""

from __future__ import annotations

import math
import uuid as uuidlib
from dataclasses import dataclass
from typing import Any

from .nbt import (
    TAG_BYTE,
    TAG_BYTE_ARRAY,
    TAG_COMPOUND,
    TAG_DOUBLE,
    TAG_FLOAT,
    TAG_INT,
    TAG_INT_ARRAY,
    TAG_LIST,
    TAG_LONG,
    TAG_LONG_ARRAY,
    TAG_SHORT,
    TAG_STRING,
)

Node = tuple[int, Any]

# 1.13 扁平化、1.20.5 组件化、以及有 DataVersion 的起点
DV_FLATTENING = 1451  # 1.13 首个正式快照之后的稳定线
DV_COMPONENTS = 3837  # 1.20.5

_PRIMITIVE_TAGS = {
    TAG_BYTE,
    TAG_SHORT,
    TAG_INT,
    TAG_LONG,
    TAG_FLOAT,
    TAG_DOUBLE,
    TAG_BYTE_ARRAY,
    TAG_STRING,
    TAG_INT_ARRAY,
    TAG_LONG_ARRAY,
}

_TYPE_RANGES = {
    "byte": (-(2**7), 2**7 - 1),
    "short": (-(2**15), 2**15 - 1),
    "int": (-(2**31), 2**31 - 1),
    "long": (-(2**63), 2**63 - 1),
}

_TAG_BY_KIND = {
    "byte": TAG_BYTE,
    "short": TAG_SHORT,
    "int": TAG_INT,
    "long": TAG_LONG,
    "float": TAG_FLOAT,
    "double": TAG_DOUBLE,
    "string": TAG_STRING,
}

# 常见原版物品的 1.12 及以前数字 ID；未收录的物品请直接填数字 ID。
LEGACY_ITEM_IDS: dict[str, int] = {
    "minecraft:air": 0,
    "minecraft:stone": 1,
    "minecraft:grass_block": 2,
    "minecraft:dirt": 3,
    "minecraft:cobblestone": 4,
    "minecraft:oak_planks": 5,
    "minecraft:bedrock": 7,
    "minecraft:sand": 12,
    "minecraft:gravel": 13,
    "minecraft:gold_ore": 14,
    "minecraft:iron_ore": 15,
    "minecraft:coal_ore": 16,
    "minecraft:oak_log": 17,
    "minecraft:glass": 20,
    "minecraft:lapis_ore": 21,
    "minecraft:lapis_block": 22,
    "minecraft:sandstone": 24,
    "minecraft:white_wool": 35,
    "minecraft:gold_block": 41,
    "minecraft:iron_block": 42,
    "minecraft:stone_slab": 44,
    "minecraft:bricks": 45,
    "minecraft:tnt": 46,
    "minecraft:bookshelf": 47,
    "minecraft:obsidian": 49,
    "minecraft:torch": 50,
    "minecraft:chest": 54,
    "minecraft:diamond_ore": 56,
    "minecraft:diamond_block": 57,
    "minecraft:crafting_table": 58,
    "minecraft:furnace": 61,
    "minecraft:redstone_ore": 73,
    "minecraft:ice": 79,
    "minecraft:snow_block": 80,
    "minecraft:clay": 82,
    "minecraft:netherrack": 87,
    "minecraft:soul_sand": 88,
    "minecraft:glowstone": 89,
    "minecraft:end_stone": 121,
    "minecraft:emerald_ore": 129,
    "minecraft:emerald_block": 133,
    "minecraft:beacon": 138,
    "minecraft:anvil": 145,
    "minecraft:quartz_block": 155,
    "minecraft:iron_shovel": 256,
    "minecraft:iron_pickaxe": 257,
    "minecraft:iron_axe": 258,
    "minecraft:flint_and_steel": 259,
    "minecraft:apple": 260,
    "minecraft:bow": 261,
    "minecraft:arrow": 262,
    "minecraft:coal": 263,
    "minecraft:diamond": 264,
    "minecraft:iron_ingot": 265,
    "minecraft:gold_ingot": 266,
    "minecraft:iron_sword": 267,
    "minecraft:wooden_sword": 268,
    "minecraft:wooden_shovel": 269,
    "minecraft:wooden_pickaxe": 270,
    "minecraft:wooden_axe": 271,
    "minecraft:stone_sword": 272,
    "minecraft:stone_shovel": 273,
    "minecraft:stone_pickaxe": 274,
    "minecraft:stone_axe": 275,
    "minecraft:diamond_sword": 276,
    "minecraft:diamond_shovel": 277,
    "minecraft:diamond_pickaxe": 278,
    "minecraft:diamond_axe": 279,
    "minecraft:stick": 280,
    "minecraft:bowl": 281,
    "minecraft:golden_sword": 283,
    "minecraft:golden_shovel": 284,
    "minecraft:golden_pickaxe": 285,
    "minecraft:golden_axe": 286,
    "minecraft:string": 287,
    "minecraft:feather": 288,
    "minecraft:gunpowder": 289,
    "minecraft:wheat_seeds": 295,
    "minecraft:wheat": 296,
    "minecraft:bread": 297,
    "minecraft:leather_helmet": 298,
    "minecraft:leather_chestplate": 299,
    "minecraft:leather_leggings": 300,
    "minecraft:leather_boots": 301,
    "minecraft:chainmail_helmet": 302,
    "minecraft:chainmail_chestplate": 303,
    "minecraft:chainmail_leggings": 304,
    "minecraft:chainmail_boots": 305,
    "minecraft:iron_helmet": 306,
    "minecraft:iron_chestplate": 307,
    "minecraft:iron_leggings": 308,
    "minecraft:iron_boots": 309,
    "minecraft:diamond_helmet": 310,
    "minecraft:diamond_chestplate": 311,
    "minecraft:diamond_leggings": 312,
    "minecraft:diamond_boots": 313,
    "minecraft:golden_helmet": 314,
    "minecraft:golden_chestplate": 315,
    "minecraft:golden_leggings": 316,
    "minecraft:golden_boots": 317,
    "minecraft:flint": 318,
    "minecraft:golden_apple": 322,
    "minecraft:enchanted_golden_apple": 322,
    "minecraft:water_bucket": 326,
    "minecraft:lava_bucket": 327,
    "minecraft:redstone": 331,
    "minecraft:snowball": 332,
    "minecraft:clay_ball": 337,
    "minecraft:sugar_cane": 338,
    "minecraft:paper": 339,
    "minecraft:book": 340,
    "minecraft:slime_ball": 341,
    "minecraft:ender_pearl": 368,
    "minecraft:blaze_rod": 369,
    "minecraft:ghast_tear": 370,
    "minecraft:gold_nugget": 371,
    "minecraft:glass_bottle": 374,
    "minecraft:potion": 373,
    "minecraft:spider_eye": 375,
    "minecraft:fermented_spider_eye": 376,
    "minecraft:blaze_powder": 377,
    "minecraft:magma_cream": 378,
    "minecraft:brewing_stand": 379,
    "minecraft:ender_eye": 381,
    "minecraft:experience_bottle": 384,
    "minecraft:fire_charge": 385,
    "minecraft:emerald": 388,
    "minecraft:nether_star": 399,
    "minecraft:netherbrick": 405,
    "minecraft:quartz": 406,
    "minecraft:prismarine_shard": 409,
    "minecraft:prismarine_crystals": 410,
    "minecraft:rabbit_foot": 414,
    "minecraft:rabbit_hide": 415,
    "minecraft:armor_stand": 416,
    "minecraft:iron_horse_armor": 417,
    "minecraft:golden_horse_armor": 418,
    "minecraft:diamond_horse_armor": 419,
    "minecraft:lead": 420,
    "minecraft:name_tag": 421,
    "minecraft:elytra": 443,
    "minecraft:totem_of_undying": 449,
}

# 原版附魔 ID（1.13 前的数字 ID 与 1.13+ 命名空间 ID 对应关系）
ENCHANTMENTS: dict[str, str] = {
    "minecraft:protection": "protection",
    "minecraft:fire_protection": "fire_protection",
    "minecraft:feather_falling": "feather_falling",
    "minecraft:blast_protection": "blast_protection",
    "minecraft:projectile_protection": "projectile_protection",
    "minecraft:respiration": "respiration",
    "minecraft:aqua_affinity": "aqua_affinity",
    "minecraft:thorns": "thorns",
    "minecraft:depth_strider": "depth_strider",
    "minecraft:frost_walker": "frost_walker",
    "minecraft:binding_curse": "binding_curse",
    "minecraft:sharpness": "sharpness",
    "minecraft:smite": "smite",
    "minecraft:bane_of_arthropods": "bane_of_arthropods",
    "minecraft:knockback": "knockback",
    "minecraft:fire_aspect": "fire_aspect",
    "minecraft:looting": "looting",
    "minecraft:sweeping_edge": "sweeping_edge",
    "minecraft:efficiency": "efficiency",
    "minecraft:silk_touch": "silk_touch",
    "minecraft:unbreaking": "unbreaking",
    "minecraft:fortune": "fortune",
    "minecraft:power": "power",
    "minecraft:punch": "punch",
    "minecraft:flame": "flame",
    "minecraft:infinity": "infinity",
    "minecraft:luck_of_the_sea": "luck_of_the_sea",
    "minecraft:lure": "lure",
    "minecraft:mending": "mending",
}

_LEGACY_ENCHANT_IDS = {
    "protection": 0,
    "fire_protection": 1,
    "feather_falling": 2,
    "blast_protection": 3,
    "projectile_protection": 4,
    "respiration": 5,
    "aqua_affinity": 6,
    "thorns": 7,
    "depth_strider": 8,
    "frost_walker": 9,
    "binding_curse": 10,
    "sharpness": 16,
    "smite": 17,
    "bane_of_arthropods": 18,
    "knockback": 19,
    "fire_aspect": 20,
    "looting": 21,
    "sweeping_edge": 22,
    "efficiency": 32,
    "silk_touch": 33,
    "unbreaking": 34,
    "fortune": 35,
    "power": 48,
    "punch": 49,
    "flame": 50,
    "infinity": 51,
    "luck_of_the_sea": 61,
    "lure": 62,
    "mending": 70,
}


class VanillaCaps:
    """原版可达的理论上限；不是 NBT 硬边界。"""

    @staticmethod
    def health() -> float:
        # generic.max_health 原版属性范围 1.0 - 1024.0
        return 1024.0

    @staticmethod
    def food() -> float:
        return 20.0

    @staticmethod
    def saturation() -> float:
        return 20.0

    @staticmethod
    def xp_level() -> int:
        # 原版经验条显示上限；Int 本身仍可容纳更大值
        return 21863

    @staticmethod
    def movement_speed() -> float:
        return 1024.0

    @staticmethod
    def attribute() -> float:
        return 2048.0

    @staticmethod
    def enchant_level() -> int:
        return 255

    @staticmethod
    def effect_duration() -> int:
        # 原版状态效果持续时间上限（游戏刻）
        return 1000000

    @staticmethod
    def random_tick_speed() -> int:
        return 4000

    @staticmethod
    def world_border_size() -> float:
        return 59999968.0

    @staticmethod
    def max_count(era: str) -> int:
        if era == "components":
            return 99
        return 127


def detect_era(data_version: int, version_name: str = "") -> str:
    """按 DataVersion 与版本名判断存档年代。

    返回 ``pre_anvil`` / ``unknown`` / ``legacy`` / ``flattened`` / ``components``。
    """
    name = str(version_name or "").strip().lower()
    if name.startswith(("rd-", "inf-", "indev", "alpha", "beta", "c0.", "a1.", "b1.")):
        return "pre_anvil"
    try:
        dv = int(data_version or 0)
    except (TypeError, ValueError):
        dv = 0
    if dv <= 0:
        if name.startswith(("1.", "snapshot", "latest")):
            return "unknown"
        return "unknown"
    if dv >= DV_COMPONENTS:
        return "components"
    if dv >= DV_FLATTENING:
        return "flattened"
    return "legacy"


def get_node(root: Node, path: str) -> Node:
    """按 ``A.B.0.C`` 读取节点，找不到时抛出 KeyError。"""
    node = root
    for part in str(path).split("."):
        tag, value = node
        if tag == TAG_COMPOUND:
            if part not in value:
                raise KeyError(path)
            node = value[part]
        elif tag == TAG_LIST:
            index = int(part)
            items = value[1]
            node = items[index]
        else:
            raise KeyError(path)
    return node


def _container(node: Node, part: str, create: bool) -> Node:
    tag, value = node
    if tag == TAG_COMPOUND:
        if part not in value:
            if not create:
                raise KeyError(part)
            child = (TAG_COMPOUND, {})
            value[part] = child
        return value[part]
    if tag == TAG_LIST:
        return value[1][int(part)]
    raise KeyError(part)


def set_node(root: Node, path: str, tag: int, value: Any) -> None:
    """写入节点并保留显式类型；中间 Compound 不存在时自动创建。"""
    parts = [part for part in str(path).split(".") if part]
    if not parts:
        raise ValueError("路径不能为空")
    node = root
    for part in parts[:-1]:
        node = _container(node, part, True)
    last = parts[-1]
    tag_node, node_value = node
    if tag_node == TAG_COMPOUND:
        node_value[last] = (tag, value)
    elif tag_node == TAG_LIST:
        items = node_value[1]
        index = int(last)
        while len(items) <= index:
            items.append((node_value[0], _default_value(node_value[0])))
        items[index] = (tag, value)
    else:
        raise KeyError(last)


def _default_value(tag: int) -> Any:
    if tag == TAG_COMPOUND:
        return {}
    if tag == TAG_LIST:
        return (0, [])
    if tag == TAG_STRING:
        return ""
    if tag in (TAG_BYTE_ARRAY, TAG_INT_ARRAY, TAG_LONG_ARRAY):
        return [] if tag != TAG_BYTE_ARRAY else bytearray()
    return 0


def validate_number(field: str, value: Any, cap: float, kind: str) -> list[dict]:
    """校验数字：类型越界抛 ValueError，超过原版上限只返回警告。"""
    if kind in _TYPE_RANGES:
        low, high = _TYPE_RANGES[kind]
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field} 需要整数") from exc
        if number < low or number > high:
            raise ValueError(f"{field} 超出 {kind} 范围（{low} ~ {high}）")
        actual: float = number
    elif kind in ("float", "double"):
        try:
            actual = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field} 需要数字") from exc
        if not math.isfinite(actual):
            raise ValueError(f"{field} 必须是有限数字")
        if kind == "float" and abs(actual) > 3.4028235e38:
            raise ValueError(f"{field} 超出 float 范围")
    else:
        raise ValueError(f"未知数值类型：{kind}")
    if cap is not None and abs(actual) > abs(float(cap)):
        return [
            {
                "code": "over_vanilla_cap",
                "field": field,
                "value": actual,
                "cap": cap,
                "message": f"{field} 超过原版上限 {cap}，游戏可能崩溃或读档失败",
            }
        ]
    return []


def _tag_for(kind: str) -> int:
    try:
        return _TAG_BY_KIND[kind]
    except KeyError as exc:
        raise ValueError(f"未知类型：{kind}") from exc


def _legacy_item_numeric(item_id: str) -> int:
    text = str(item_id).strip()
    if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
        return int(text)
    key = text if ":" in text else f"minecraft:{text}"
    if key in LEGACY_ITEM_IDS:
        return LEGACY_ITEM_IDS[key]
    raise ValueError(
        f"1.12 及更早版本需要数字物品 ID，「{text}」不在内置对照表中，请直接填写数字 ID"
    )


def _enchant_compound(name: str, level: int, era: str) -> Node:
    key = name if ":" in name else f"minecraft:{name}"
    short_name = ENCHANTMENTS.get(key, key.split(":", 1)[-1])
    if era == "legacy":
        numeric = _LEGACY_ENCHANT_IDS.get(short_name, -1)
        if numeric < 0:
            raise ValueError(f"旧版没有附魔「{name}」的数字 ID")
        return (
            TAG_COMPOUND,
            {"id": (TAG_SHORT, numeric), "lvl": (TAG_SHORT, int(level))},
        )
    return (TAG_COMPOUND, {"id": (TAG_STRING, f"minecraft:{short_name}"), "lvl": (TAG_SHORT, int(level))})


# 物品属性修饰符：组件化用字符串 operation，旧版用 0/1/2。
_OP_TO_STRING = {
    0: "add_value",
    1: "add_multiplied_base",
    2: "add_multiplied_total",
}
_OP_FROM_STRING = {
    "add_value": 0,
    "add": 0,
    "addition": 0,
    "add_multiplied_base": 1,
    "multiply_base": 1,
    "multiply": 1,
    "add_multiplied_total": 2,
    "multiply_total": 2,
}


def _operation_string(value, era: str) -> str:
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _OP_TO_STRING.values():
            return text
        if text in _OP_FROM_STRING:
            return _OP_TO_STRING[_OP_FROM_STRING[text]]
        return "add_value"
    try:
        return _OP_TO_STRING.get(int(value), "add_value")
    except (TypeError, ValueError):
        return "add_value"


def _operation_int(value) -> int:
    if isinstance(value, str):
        return _OP_FROM_STRING.get(value.strip().lower(), 0)
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return number if number in _OP_TO_STRING else 0


def _uuid_pair(text: str) -> tuple[int, int]:
    try:
        value = uuidlib.UUID(str(text))
    except (ValueError, AttributeError):
        value = uuidlib.uuid4()
    most = value.int >> 64
    least = value.int & ((1 << 64) - 1)
    if most >= 1 << 63:
        most -= 1 << 64
    if least >= 1 << 63:
        least -= 1 << 64
    return most, least


def item_attribute_modifier(entry: dict, era: str) -> Node:
    """物品属性修饰符：1.20.5+ 写入 ``minecraft:attribute_modifiers`` 组件。"""
    name = str(entry.get("name") or entry.get("type") or entry.get("AttributeName") or "").strip()
    if not name:
        raise ValueError("物品属性修饰符缺少属性名")
    amount = float(entry.get("amount", entry.get("Amount", 0)) or 0)
    slot = str(entry.get("slot", entry.get("Slot", "any")) or "any").strip().lower()
    if slot in ("", "any"):
        slot = "any"
    ident = str(entry.get("id") or entry.get("uuid") or uuidlib.uuid4())
    if era == "components":
        attribute = name if ":" in name else f"minecraft:{name}"
        return (
            TAG_COMPOUND,
            {
                "type": (TAG_STRING, attribute),
                "id": (TAG_STRING, ident),
                "amount": (TAG_DOUBLE, amount),
                "operation": (TAG_STRING, _operation_string(entry.get("operation"), era)),
                "slot": (TAG_STRING, slot),
            },
        )
    most, least = _uuid_pair(ident)
    return (
        TAG_COMPOUND,
        {
            "AttributeName": (TAG_STRING, name.split(":", 1)[-1]),
            "Name": (TAG_STRING, str(entry.get("display") or "mikancl")),
            "Amount": (TAG_DOUBLE, amount),
            "Operation": (TAG_INT, _operation_int(entry.get("operation"))),
            "UUIDMost": (TAG_LONG, most),
            "UUIDLeast": (TAG_LONG, least),
            "Slot": (TAG_STRING, slot),
        },
    )


def player_attribute_modifier(entry: dict, era: str) -> Node:
    """玩家 Attributes 里的 Modifiers 条目（结构与物品组件不同）。"""
    ident = str(entry.get("id") or entry.get("uuid") or uuidlib.uuid4())
    amount = float(entry.get("amount", entry.get("Amount", 0)) or 0)
    name = str(entry.get("name") or entry.get("Name") or "")
    if era == "components":
        fields = {
            "id": (TAG_STRING, ident),
            "amount": (TAG_DOUBLE, amount),
            "operation": (TAG_STRING, _operation_string(entry.get("operation"), era)),
        }
        return (TAG_COMPOUND, fields)
    most, least = _uuid_pair(ident)
    return (
        TAG_COMPOUND,
        {
            "Name": (TAG_STRING, name.split(":", 1)[-1] if ":" in name else name),
            "Amount": (TAG_DOUBLE, amount),
            "Operation": (TAG_INT, _operation_int(entry.get("operation"))),
            "UUIDMost": (TAG_LONG, most),
            "UUIDLeast": (TAG_LONG, least),
        },
    )



def build_item(
    item_id: str,
    count: int,
    slot: int,
    era: str,
    *,
    damage: int = 0,
    enchantments: list[dict] | None = None,
    attributes: list[dict] | None = None,
    tag_json: dict | None = None,
    migrate_count: bool = False,
) -> Node:
    """构造物品 Compound，按年代选择数字/命名空间 ID 与数量类型。"""
    if era == "pre_anvil":
        raise ValueError("该存档年代不是 Anvil 结构，请先使用存档格式转换器升级")
    if era == "unknown":
        raise ValueError("无法确定存档年代，已拒绝写入物品")
    count = int(count)
    if count < 0:
        raise ValueError("数量不能为负数")
    cap = VanillaCaps.max_count(era)
    if count > cap:
        if era in ("legacy", "flattened") and migrate_count:
            if count > 2**31 - 1:
                raise ValueError("数量超出 TAG_Int 范围")
        else:
            raise ValueError(f"当前存档数量上限为 {cap}；如需更大数量必须显式迁移计数类型")

    fields: dict[str, Node] = {"Slot": (TAG_BYTE, int(slot))}
    if era == "legacy":
        fields["id"] = (TAG_SHORT, _legacy_item_numeric(item_id))
        fields["Count"] = (TAG_INT if migrate_count else TAG_BYTE, count)
    elif era == "flattened":
        fields["id"] = (TAG_STRING, str(item_id))
        fields["Count"] = (TAG_INT if migrate_count else TAG_BYTE, count)
    else:
        fields["id"] = (TAG_STRING, str(item_id))
        fields["count"] = (TAG_INT, count)

    # 先合并原始 NBT，再写数值与附魔：显式字段始终覆盖 Raw 里的同名内容，
    # 未在界面改动的部分（名字、lore、容器内容等）原样保留。
    if tag_json:
        node = json_to_typed(tag_json)
        key = "components" if era == "components" else "tag"
        if node[0] != TAG_COMPOUND:
            raise ValueError("Raw NBT 必须是 Compound")
        if key in fields and isinstance(fields[key][1], dict):
            fields[key][1].update(node[1])
        else:
            fields[key] = node

    if era == "legacy":
        fields["Damage"] = (TAG_SHORT, int(damage))
    elif era == "flattened":
        if damage:
            fields["Damage"] = (TAG_INT, int(damage))
    elif damage:
        fields.setdefault("components", (TAG_COMPOUND, {}))
        components = fields["components"][1]
        if isinstance(components, dict):
            components["minecraft:damage"] = (TAG_INT, int(damage))

    enchants = [dict(item) for item in (enchantments or [])]
    if enchants:
        for entry in enchants:
            level = int(entry.get("level", 1))
            if level < 0 or level > VanillaCaps.enchant_level():
                raise ValueError(f"附魔等级必须在 0 - {VanillaCaps.enchant_level()} 之间")
        entries = [
            _enchant_compound(str(entry.get("id")), int(entry.get("level", 1)), era)
            for entry in enchants
        ]
        if era == "components":
            fields.setdefault("components", (TAG_COMPOUND, {}))
            components = fields["components"][1]
            if isinstance(components, dict):
                components["minecraft:enchantments"] = (
                    TAG_COMPOUND,
                    {"levels": (TAG_LIST, (TAG_COMPOUND, entries))},
                )
        else:
            fields.setdefault("tag", (TAG_COMPOUND, {}))
            tag_value = fields["tag"][1]
            if isinstance(tag_value, dict):
                tag_value["Enchantments"] = (TAG_LIST, (TAG_COMPOUND, entries))

    modifiers = [dict(entry) for entry in (attributes or [])]
    if modifiers:
        nodes = [item_attribute_modifier(entry, era) for entry in modifiers]
        if era == "components":
            fields.setdefault("components", (TAG_COMPOUND, {}))
            components = fields["components"][1]
            if isinstance(components, dict):
                components["minecraft:attribute_modifiers"] = (
                    TAG_COMPOUND,
                    {"modifiers": (TAG_LIST, (TAG_COMPOUND, nodes))},
                )
        else:
            fields.setdefault("tag", (TAG_COMPOUND, {}))
            tag_value = fields["tag"][1]
            if isinstance(tag_value, dict):
                tag_value["AttributeModifiers"] = (TAG_LIST, (TAG_COMPOUND, nodes))
    return (TAG_COMPOUND, fields)


def _effects_key(root: Node) -> str:
    if root[0] != TAG_COMPOUND:
        raise ValueError("玩家数据根节点必须是 Compound")
    return "active_effects" if "active_effects" in root[1] else "ActiveEffects"


def _build_item_list(entries, era: str) -> Node:
    return (
        TAG_LIST,
        (
            TAG_COMPOUND,
            [
                build_item(
                    str(entry.get("id")),
                    int(entry.get("count", 1)),
                    int(entry.get("slot", 0)),
                    era,
                    damage=int(entry.get("damage", 0) or 0),
                    enchantments=entry.get("enchantments"),
                    attributes=entry.get("attributes"),
                    tag_json=entry.get("tag_json"),
                    migrate_count=bool(entry.get("migrate_count")),
                )
                for entry in entries
            ],
        ),
    )


def apply_player_edits(root: Node, edits: dict, era: str) -> list[dict]:
    """把状态页草稿写入玩家 NBT，返回软警告列表。"""
    warnings: list[dict] = []
    if root[0] != TAG_COMPOUND:
        raise ValueError("玩家数据根节点必须是 Compound")
    fields = root[1]

    if "health" in edits:
        value = float(edits["health"])
        warnings += validate_number("Health", value, VanillaCaps.health(), "float")
        fields["Health"] = (TAG_FLOAT, value)
    if "food" in edits:
        value = float(edits["food"])
        warnings += validate_number("foodSaturationLevel", value, VanillaCaps.saturation(), "float")
        fields["foodSaturationLevel"] = (TAG_FLOAT, value)
    if "food_level" in edits:
        value = int(edits["food_level"])
        warnings += validate_number("foodLevel", value, 20, "int")
        fields["foodLevel"] = (TAG_INT, value)
    if "xp_level" in edits:
        value = int(edits["xp_level"])
        warnings += validate_number("XpLevel", value, VanillaCaps.xp_level(), "int")
        fields["XpLevel"] = (TAG_INT, value)
    if "xp_progress" in edits:
        fields["XpP"] = (TAG_FLOAT, float(edits["xp_progress"]))
    if "game_type" in edits:
        fields["playerGameType"] = (TAG_INT, int(edits["game_type"]))
    if "dimension" in edits:
        fields["Dimension"] = (TAG_STRING, str(edits["dimension"]))
    if "pos" in edits:
        pos = list(edits["pos"])
        if len(pos) != 3:
            raise ValueError("坐标需要 3 个分量")
        fields["Pos"] = (
            TAG_LIST,
            (TAG_DOUBLE, [(TAG_DOUBLE, float(value)) for value in pos]),
        )
    if "inventory" in edits:
        fields["Inventory"] = _build_item_list(edits["inventory"], era)
    if "ender_items" in edits:
        fields["EnderItems"] = _build_item_list(edits["ender_items"], era)
    if "attributes" in edits:
        nodes = []
        for entry in edits["attributes"]:
            name = str(entry.get("name"))
            base = float(entry.get("base", 0))
            warnings += validate_number(
                f"Attributes[{entry.get('name')}]", base, VanillaCaps.attribute(), "double"
            )
            values: dict[str, Node] = {}
            if era == "components":
                values["id"] = (
                    TAG_STRING,
                    name if ":" in name else f"minecraft:{name}",
                )
                values["base"] = (TAG_DOUBLE, base)
                modifiers = [dict(item) for item in (entry.get("modifiers") or [])]
                if modifiers:
                    values["modifiers"] = (
                        TAG_LIST,
                        (
                            TAG_COMPOUND,
                            [player_attribute_modifier(item, era) for item in modifiers],
                        ),
                    )
            else:
                values["Name"] = (TAG_STRING, name)
                values["Base"] = (TAG_DOUBLE, base)
                modifiers = [dict(item) for item in (entry.get("modifiers") or [])]
                if modifiers:
                    values["Modifiers"] = (
                        TAG_LIST,
                        (
                            TAG_COMPOUND,
                            [
                                player_attribute_modifier(
                                    dict(item, name=item.get("name") or name), era
                                )
                                for item in modifiers
                            ],
                        ),
                    )
            nodes.append((TAG_COMPOUND, values))
        fields["Attributes"] = (TAG_LIST, (TAG_COMPOUND, nodes))
    if "effects" in edits:
        key = _effects_key(root)
        nodes = []
        for entry in edits["effects"]:
            duration = int(entry.get("duration", 0))
            amplifier = int(entry.get("amplifier", 0))
            warnings += validate_number("ActiveEffects.Duration", duration, VanillaCaps.effect_duration(), "int")
            warnings += validate_number("ActiveEffects.Amplifier", amplifier, 255, "byte")
            nodes.append(
                (
                    TAG_COMPOUND,
                    {
                        "Id": (TAG_BYTE, int(entry.get("id", 1))),
                        "Amplifier": (TAG_BYTE, amplifier),
                        "Duration": (TAG_INT, duration),
                        "Ambient": (TAG_BYTE, 1 if entry.get("ambient") else 0),
                        "ShowParticles": (TAG_BYTE, 0 if entry.get("hide_particles") else 1),
                        "ShowIcon": (TAG_BYTE, 1),
                    },
                )
            )
        fields[key] = (TAG_LIST, (TAG_COMPOUND, nodes))
    return warnings


# ----------------------------------------------------------------------
# 带类型 JSON：供 Raw NBT 文本框使用
#   {"tag": 3, "value": 5}
#   {"tag": 10, "value": {"Name": {"tag": 8, "value": "x"}}}
#   {"tag": 9, "element_tag": 6, "value": [...]}
# Long / Long Array 用十进制字符串，避免 JS 精度丢失。
# ----------------------------------------------------------------------
def typed_to_json(node: Node) -> dict:
    tag, value = node
    if tag == TAG_COMPOUND:
        return {"tag": tag, "value": {name: typed_to_json(child) for name, child in value.items()}}
    if tag == TAG_LIST:
        element_tag, items = value
        return {
            "tag": tag,
            "element_tag": element_tag,
            "value": [typed_to_json(item) for item in items],
        }
    if tag == TAG_LONG:
        return {"tag": tag, "value": str(int(value))}
    if tag == TAG_LONG_ARRAY:
        return {"tag": tag, "value": [str(int(item)) for item in value]}
    if tag == TAG_BYTE_ARRAY:
        return {"tag": tag, "value": list(bytes(value))}
    if tag in (TAG_FLOAT, TAG_DOUBLE):
        return {"tag": tag, "value": float(value)}
    return {"tag": tag, "value": value}


def json_to_typed(data: Any) -> Node:
    if not isinstance(data, dict) or "tag" not in data:
        raise ValueError("节点必须是包含 tag 字段的对象")
    try:
        tag = int(data["tag"])
    except (TypeError, ValueError) as exc:
        raise ValueError("tag 必须是整数") from exc
    if tag == TAG_COMPOUND:
        children = data.get("value") or {}
        if not isinstance(children, dict):
            raise ValueError("Compound 的 value 必须是对象")
        return (tag, {str(name): json_to_typed(child) for name, child in children.items()})
    if tag == TAG_LIST:
        element_tag = int(data.get("element_tag", TAG_END_PLACEHOLDER))
        raw_items = data.get("value") or []
        if not isinstance(raw_items, list):
            raise ValueError("List 的 value 必须是数组")
        items = [json_to_typed(item) for item in raw_items]
        for item in items:
            if item[0] != element_tag:
                raise ValueError("List 元素类型与 element_tag 不一致")
        return (tag, (element_tag, items))
    if tag == TAG_LONG:
        return (tag, int(str(data.get("value"))))
    if tag == TAG_LONG_ARRAY:
        return (tag, [int(str(item)) for item in (data.get("value") or [])])
    if tag == TAG_BYTE_ARRAY:
        return (tag, bytearray(int(item) for item in (data.get("value") or [])))
    if tag == TAG_INT_ARRAY:
        return (tag, [int(item) for item in (data.get("value") or [])])
    if tag == TAG_STRING:
        return (tag, str(data.get("value", "")))
    if tag in (TAG_BYTE, TAG_SHORT, TAG_INT):
        return (tag, int(data.get("value", 0)))
    if tag in (TAG_FLOAT, TAG_DOUBLE):
        return (tag, float(data.get("value", 0)))
    raise ValueError(f"不支持的标签类型：{tag}")


class _Placeholder:
    """List 缺省 element_tag 时使用；真正比较前会被覆盖。"""

    def __int__(self):
        return 0


TAG_END_PLACEHOLDER = _Placeholder()


@dataclass
class WorldIdentity:
    era: str
    data_version: int
    version_name: str
    editable: bool
    reason: str = ""


def identify_world(data: dict) -> WorldIdentity:
    """从 level.dat 的 Data 读取版本信息并给出是否可编辑。"""
    dv = int(data.get("DataVersion") or 0)
    version = data.get("Version")
    name = ""
    if isinstance(version, dict):
        name = str(version.get("Name") or "")
    era = detect_era(dv, name)
    if era == "pre_anvil":
        return WorldIdentity(era, dv, name, False, "该存档不是 Anvil 格式，请先使用存档格式转换器升级")
    if era == "unknown":
        # 1.2 - 1.8 的 Anvil 存档不写 DataVersion，只有 level 格式号 19133。
        # 这类存档的物品仍是数字 ID + Byte 数量，按 legacy 读写是安全的。
        try:
            level_format = int(data.get("version") or 0)
        except (TypeError, ValueError):
            level_format = 0
        if level_format == 19133:
            return WorldIdentity(
                "legacy", dv, "1.8 或更早（未声明 DataVersion）", True,
                "存档未声明 DataVersion，按 1.13 前格式读写",
            )
        return WorldIdentity(era, dv, name, False, "无法确定存档年代，已切换为只读模式")
    return WorldIdentity(era, dv, name, True)


ENCHANTMENT_NAMES = tuple(sorted(ENCHANTMENTS))
