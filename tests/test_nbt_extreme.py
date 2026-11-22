"""NBT 极限数值引擎的无依赖回归测试。

直接运行：``python tests/test_nbt_extreme.py``
覆盖：类型位宽 / 类型提升 / 无符号位模式 / 大整数精度 / 附魔双轨 / 大一统 /
越界扫描 / 数值预设 / 路径安全 / 老版本数值附魔。
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mc_launcher import game_data, nbt, nbt_extreme as X  # noqa: E402

C, L, S, B, SH, I, G = (nbt.TAG_COMPOUND, nbt.TAG_LIST, nbt.TAG_STRING,
                        nbt.TAG_BYTE, nbt.TAG_SHORT, nbt.TAG_INT, nbt.TAG_LONG)

PASS = 0
FAIL = 0


def check(label, fn, expect=None):
    global PASS, FAIL
    try:
        value = fn()
        if expect is not None:
            assert value == expect, f"期望 {expect!r}，实际 {value!r}"
        print(f"[OK]   {label}: {value}")
        PASS += 1
        return value
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {label}: {type(exc).__name__}: {exc}")
        FAIL += 1
        return None


def legacy_item(extra=None):
    """旧版剑：tag.Enchantments 里 sharpness lvl=5s。"""
    ench = (C, {"id": (S, "minecraft:sharpness"), "lvl": (SH, 5)})
    tag = {"Enchantments": (L, (C, [ench]))}
    if extra:
        tag.update(extra)
    return (C, {"id": (S, "minecraft:diamond_sword"), "Count": (B, 1), "tag": (C, tag)})


def modern_item():
    """新版剑：components.minecraft:enchantments.levels。"""
    levels = (C, {"minecraft:sharpness": (I, 5)})
    return (C, {
        "id": (S, "minecraft:netherite_sword"), "count": (I, 1),
        "components": (C, {"minecraft:enchantments": (C, {"levels": levels})}),
    })


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="mikan_extreme_"))
    try:
        # ---------- 类型位宽表 ----------
        check("类型位宽表 4 项", lambda: len(X.type_limits()), 4)
        check("short 上限 32767", lambda: X.type_limits()[1]["signed_max"], 32767)
        check("byte 无符号上限 255", lambda: X.type_limits()[0]["unsigned_max"], 255)
        check("提升链 short->int", lambda: X.next_wider(SH), I)
        check("long 无法再提升", lambda: X.next_wider(G), None)

        # ---------- 数值编码 ----------
        check("有符号 short 32767", lambda: X.encode_number(32767, SH)["value"], 32767)
        check("int 40000 合法", lambda: X.encode_number(40000, I)["value"], 40000)
        check("long 最大值精度", lambda: X.encode_number(2**63 - 1, G)["value"], 2**63 - 1)
        check("byte 无符号 255 转 -1", lambda: X.encode_number(255, B, unsigned=True)["value"], -1)
        check("无符号回读值 255", lambda: X.encode_number(255, B, unsigned=True)["unsigned_value"], 255)
        check("超限 short 默认拒绝", lambda: _raises(lambda: X.encode_number(40000, SH)), True)
        check("超限 short 允许回绕", lambda: X.encode_number(40000, SH, wrap=True)["value"], -25536)
        check("十六进制输入", lambda: X.encode_number("0xFFFF", SH, unsigned=True)["value"], -1)
        check("auto_tag 40000 -> int", lambda: X.auto_tag(40000), I)
        check("auto_tag 255 无符号 -> byte", lambda: X.auto_tag(255, unsigned=True), B)

        # ---------- 附魔字典 ----------
        check("附魔字典 44 项", lambda: len(game_data.ENCHANTMENTS), 44)
        check("1.12.2 只有 31 项", lambda: len(game_data.enchantment_list("1.12.2")), 31)
        check("26.1 含 lunge", lambda: any(
            e["id"] == "minecraft:lunge" for e in game_data.enchantment_list("26.1")), True)
        check("1.20.1 无 breach", lambda: any(
            e["id"] == "minecraft:breach" for e in game_data.enchantment_list("1.20.1")), False)
        check("中文名查询", lambda: game_data.enchantment_info("sharpness")["cn"], "锋利")
        check("旧版数值 ID 映射", lambda: game_data.LEGACY_ENCHANTMENT_IDS[16], "sharpness")

        # ---------- 附魔扫描（旧版） ----------
        f_old = tmp / "old.dat"
        nbt.save_nbt_typed_file(f_old, "", (C, {"Inventory": (L, (C, [legacy_item()]))}))
        scan = X.enchant_scan(str(f_old), "1.20.1")
        check("旧版扫描 1 物品", lambda: scan["total_items"], 1)
        check("旧版格式 tag.Enchantments", lambda: scan["items"][0]["format"], "tag.Enchantments")
        check("旧版识别 legacy", lambda: scan["detected_format"], "legacy(<1.20.5)")

        # ---------- 附魔拉满（旧版，核心：突破 32767） ----------
        applied = X.enchant_apply(str(f_old), "1.20.1", 40000)
        check("旧版拉满 ok", lambda: applied["ok"], True)
        check("旧版改动 1 条", lambda: applied["changed"], 1)
        check("类型提升到 int", lambda: applied["apply"][0]["tag"], I)
        lvl = nbt.load_nbt_typed_file(f_old)[1][1]["Inventory"][1][1][0][1]["tag"][1]["Enchantments"][1][1][0][1]["lvl"]
        check("落盘等级 40000", lambda: lvl[1], 40000)
        check("落盘类型 int", lambda: lvl[0], I)
        check("确实突破 32767", lambda: lvl[1] > 32767, True)
        check("写前留备份", lambda: (tmp / "old.dat.mikancl-bak").exists(), True)

        # ---------- 附魔扫描 + 大一统（新版） ----------
        f_new = tmp / "new.dat"
        nbt.save_nbt_typed_file(f_new, "", (C, {"Inventory": (L, (C, [modern_item()]))}))
        scan2 = X.enchant_scan(str(f_new), "1.21")
        check("新版扫描 1 物品", lambda: scan2["total_items"], 1)
        check("新版格式 components", lambda: "components" in scan2["items"][0]["format"], True)
        check("新版识别 components", lambda: scan2["detected_format"], "components(≥1.20.5)")

        grand = X.grand_universal(str(f_new), "1.21", 100000)
        check("大一统 ok", lambda: grand["ok"], True)
        levels = nbt.load_nbt_typed_file(f_new)[1][1]["Inventory"][1][1][0][1]["components"][1]["minecraft:enchantments"][1]["levels"][1]
        check("注入附魔 42 项", lambda: len(levels), 42)
        check("大一统等级 100000", lambda: levels["minecraft:sharpness"][1], 100000)
        check("含 1.21 breach", lambda: "minecraft:breach" in levels, True)

        # ---------- 1.12.2 数值附魔 ----------
        f_legacy = tmp / "v121.dat"
        old_ench = (C, {"id": (SH, 16), "lvl": (SH, 5)})
        root = (C, {"Inventory": (L, (C, [
            (C, {"id": (S, "minecraft:diamond_sword"), "Count": (B, 1),
                 "tag": (C, {"ench": (L, (C, [old_ench]))})}),
        ]))})
        nbt.save_nbt_typed_file(f_legacy, "", root)
        scan3 = X.enchant_scan(str(f_legacy), "1.12.2")
        check("1.12.2 扫描到数值附魔", lambda: scan3["items"][0]["format"], "tag.ench")
        X.enchant_apply(str(f_legacy), "1.12.2", 32767)
        back = nbt.load_nbt_typed_file(f_legacy)[1][1]["Inventory"][1][1][0][1]["tag"][1]["ench"][1][1][0][1]["lvl"]
        check("1.12.2 等级写 32767", lambda: back[1], 32767)

        # ---------- 越界扫描 ----------
        scan_ov = X.scan_overflow(str(f_old))
        check("越界扫描有结果", lambda: scan_ov["total"] > 0, True)
        check("越界扫描含 limits", lambda: len(scan_ov["limits"]), 4)

        # ---------- promote_node 单节点 ----------
        f_node = tmp / "node.dat"
        nbt.save_nbt_typed_file(f_node, "", (C, {"Test": (SH, 100)}))
        pr = X.promote_node(str(f_node), "Test", 999999, auto=True)
        check("promote 类型 int", lambda: pr["tag"], I)
        check("promote 旧类型 short", lambda: pr["old_tag"], SH)
        back = nbt.load_nbt_typed_file(f_node)[1][1]["Test"]
        check("promote 落盘 999999", lambda: back[1], 999999)

        # ---------- 数值预设 ----------
        presets = X.numeric_presets("1.20.1")
        check("预设 14 项", lambda: len(presets), 14)
        check("堆叠预设无符号", lambda: next(p for p in presets if p["id"] == "stack_255")["unsigned"], True)
        f_pre = tmp / "pre.dat"
        nbt.save_nbt_typed_file(f_pre, "", (C, {"XpLevel": (I, 30)}))
        X.apply_preset(str(f_pre), "xp_level", value=2147483647)
        check("预设写入等级上限", lambda: nbt.load_nbt_typed_file(f_pre)[1][1]["XpLevel"][1], 2147483647)

        # ---------- 原理说明 ----------
        check("原理说明要点", lambda: len(X.explain()["points"]) >= 6, True)

        # ---------- 附魔 255 封顶（版本感知） ----------
        # 1.17.1 起游戏把附魔封顶 255；之前 short 可真实生效 32767
        check("1.20.1 封顶 255", lambda: X.enchant_effective_cap("1.20.1")["effective_max"], 255)
        check("1.20.1 标记 clamped", lambda: X.enchant_effective_cap("1.20.1")["clamped"], True)
        check("1.16.5 不封顶 32767", lambda: X.enchant_effective_cap("1.16.5")["effective_max"], 32767)
        check("1.16.5 不 clamped", lambda: X.enchant_effective_cap("1.16.5")["clamped"], False)
        check("1.12.2 不封顶", lambda: X.enchant_effective_cap("1.12.2")["effective_max"], 32767)
        check("1.17.1 边界封顶", lambda: X.enchant_effective_cap("1.17.1")["effective_max"], 255)
        # 新版写超限：返回 capped_notice 提示会被压回 255
        f_cap = tmp / "cap.dat"
        nbt.save_nbt_typed_file(f_cap, "", (C, {"Inventory": (L, (C, [legacy_item()]))}))
        cap_res = X.enchant_apply(str(f_cap), "1.20.1", level=32767)
        check("1.20.1 拉满有封顶提示", lambda: "255" in (cap_res.get("capped_notice") or ""), True)
        # 老版本写 32767 不应有封顶提示
        f_cap2 = tmp / "cap2.dat"
        nbt.save_nbt_typed_file(f_cap2, "", (C, {"Inventory": (L, (C, [legacy_item()]))}))
        cap_res2 = X.enchant_apply(str(f_cap2), "1.16.5", level=32767)
        check("1.16.5 拉满无封顶提示", lambda: (cap_res2.get("capped_notice") or "") == "", True)
        check("1.16.5 落盘 32767", lambda: nbt.load_nbt_typed_file(f_cap2)[1][1]["Inventory"][1][1][0][1]
              ["tag"][1]["Enchantments"][1][1][0][1]["lvl"][1], 32767)

        # ---------- 属性直改（绕过附魔上限） ----------
        f_attr = tmp / "attr.dat"
        nbt.save_nbt_typed_file(f_attr, "", (C, {"Inventory": (L, (C, [legacy_item()]))}))
        attr_res = X.attribute_apply(str(f_attr), "1.16.5", amount=1000.0)
        check("旧版属性写入计数", lambda: attr_res["changed"], 1)
        am = nbt.load_nbt_typed_file(f_attr)[1][1]["Inventory"][1][1][0][1]["tag"][1]["AttributeModifiers"][1][1][0][1]
        check("旧版属性名带 generic.", lambda: am["AttributeName"][1], "generic.attack_damage")
        check("旧版属性 Amount", lambda: am["Amount"][1], 1000.0)
        check("旧版属性槽位", lambda: am["Slot"][1], "mainhand")
        # UUID 必须在有符号 int 范围内，否则 struct.pack 会炸
        check("旧版 UUID 合法有符号", lambda: all(-2**31 <= v[1] < 2**31 for v in am["UUID"][1][1]), True)
        # 新版组件
        f_attr2 = tmp / "attr2.dat"
        nbt.save_nbt_typed_file(f_attr2, "", (C, {"Inventory": (L, (C, [modern_item()]))}))
        attr_res2 = X.attribute_apply(str(f_attr2), "1.20.5", amount=500.0)
        mods = nbt.load_nbt_typed_file(f_attr2)[1][1]["Inventory"][1][1][0][1]["components"][1]["minecraft:attribute_modifiers"][1][1][0][1]
        check("新版属性 type", lambda: mods["type"][1], "minecraft:attack_damage")
        check("新版属性 operation", lambda: mods["operation"][1], "add_value")
        check("新版属性 amount", lambda: mods["amount"][1], 500.0)
        # 超上限钳制到 2048
        f_attr3 = tmp / "attr3.dat"
        nbt.save_nbt_typed_file(f_attr3, "", (C, {"Inventory": (L, (C, [modern_item()]))}))
        attr_res3 = X.attribute_apply(str(f_attr3), "1.20.5", amount=99999)
        check("属性超上限钳制 2048", lambda: attr_res3["amount"], 2048.0)
        check("属性上限字段", lambda: attr_res3["limit"]["max"], 2048)
        # 1.21.2 去 generic. 前缀
        check("1.21.2 属性去前缀", lambda: X.attribute_apply(
            str(f_attr3), "1.21.2", amount=10)["attribute"], "minecraft:attack_damage")

        # ---------- 路径安全 ----------
        outside = tmp.parent / "mikan_ext_probe.dat"
        check("路径穿越被拒", lambda: _raises(
            lambda: X.promote_node(str(outside), "X", 5, root=str(tmp))), True)

        print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
        return 0 if FAIL == 0 else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _raises(fn) -> bool:
    try:
        fn()
    except (ValueError, FileNotFoundError, OSError, OverflowError):
        return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())
