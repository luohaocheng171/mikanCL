"""NBT 工作室 / 游戏数据字典的无依赖回归测试。

直接运行：``python tests/test_nbt_studio.py``
不依赖 pytest，全部使用标准库 + 项目自身模块；临时文件放在系统临时目录，
测试结束后自动清理。
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mc_launcher import game_data, nbt, nbt_studio  # noqa: E402

C = nbt.TAG_COMPOUND
L = nbt.TAG_LIST
S = nbt.TAG_STRING
D = nbt.TAG_DOUBLE
I = nbt.TAG_INT
B = nbt.TAG_BYTE
G = nbt.TAG_LONG

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
    except Exception as exc:  # noqa: BLE001 - 测试主体集中汇报
        print(f"[FAIL] {label}: {type(exc).__name__}: {exc}")
        FAIL += 1
        return None
    return value


def sample_root():
    return (C, {
        "Data": (C, {
            "LevelName": (S, "TestWorld"),
            "RandomSeed": (G, 123456789),
            "GameRules": (C, {
                "keepInventory": (S, "false"),
                "randomTickSpeed": (S, "3"),
            }),
            "Attributes": (L, (C, [
                (C, {"Name": (S, "minecraft:generic.max_health"), "Base": (D, 20.0)}),
                (C, {"Name": (S, "minecraft:generic.movement_speed"), "Base": (D, 0.25)}),
            ])),
            # typed list 的每个元素都必须是 (tag, value) 节点
            "Pos": (L, (D, [(D, 1.0), (D, 64.0), (D, 2.0)])),
        }),
    })


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="mikan_nbt_"))
    try:
        world = tmp / "world"
        world.mkdir()
        level = world / "level.dat"
        nbt.save_nbt_typed_file(level, "", sample_root())

        tree = nbt_studio.read_tree(str(level))
        check("read_tree 根节点类型", lambda: tree["root_tag_name"], "TAG_Compound")
        check("read_tree 展开节点数 > 12", lambda: tree["total"] > 12, True)
        check("列表下标出现在 pointer", lambda: any(
            n["pointer"] and isinstance(n["pointer"][-1], int) for n in tree["nodes"]), True)
        check("set_value 改字符串", lambda: nbt_studio.set_value(
            str(level), "Data/LevelName", "Renamed")["value"], "Renamed")
        check("set_value 改列表元素", lambda: nbt_studio.set_value(
            str(level), "Data/Pos/1", 99.5)["value"], 99.5)
        check("add_node 加布尔", lambda: nbt_studio.add_node(
            str(level), "Data", "allowCommands", B, 1)["name"], "allowCommands")
        check("delete_node 删长整型", lambda: nbt_studio.delete_node(
            str(level), "Data/RandomSeed")["pointer"], ["Data", "RandomSeed"])
        check("batch_edit 混合动作全部成功", lambda: nbt_studio.batch_edit(
            str(level), [
                {"action": "set", "pointer": "Data/LevelName", "value": "Batch"},
                {"action": "add", "pointer": "Data/GameRules",
                 "name": "mobGriefing", "tag": S, "value": "false"},
            ])["ok"], True)
        check("回读确认改动落盘", lambda: (
            nbt.load_nbt_typed_file(level)[1][1]["Data"][1]["LevelName"][1],
            nbt.load_nbt_typed_file(level)[1][1]["Data"][1]["allowCommands"][1],
            "RandomSeed" in nbt.load_nbt_typed_file(level)[1][1]["Data"][1],
        ), ("Batch", 1, False))

        check("read_gamerules 定位 level.dat", lambda: nbt_studio.read_gamerules(
            str(world), "1.20.1")["location"], "level.dat:Data.GameRules")
        check("write_gamerules 按版本写驼峰键", lambda: nbt_studio.write_gamerules(
            str(world), {"keepInventory": True, "randomTickSpeed": 7,
                         "doMobSpawning": False}, "1.20.1")["applied"],
              {"keepInventory": "true", "randomTickSpeed": "7", "doMobSpawning": "false"})
        check("回读规则值", lambda: nbt_studio.read_gamerules(
            str(world), "1.20.1")["values"]["keepInventory"], "true")
        check("反转规则旧版取反", lambda: game_data.normalize_gamerule_value(
            "elytra_movement_check", True, "1.20.1"), "false")
        check("反转规则新版不取反", lambda: game_data.normalize_gamerule_value(
            "elytra_movement_check", True, "1.21.11"), "true")

        check("读实体属性条数", lambda: len(nbt_studio.read_entity_attributes(
            str(level), "1.20.1")["rows"]), 2)
        check("写实体属性 1.21.4", lambda: nbt_studio.set_entity_attributes(
            str(level), [{"name": "max_health", "base": 80},
                         {"name": "movement_speed", "base": 1.4}], "1.21.4")["changed"], 2)
        check("属性 ID 已去 generic 前缀", lambda: all(
            "generic." not in r["id"] for r in nbt_studio.read_entity_attributes(
                str(level), "1.21.4")["rows"]), True)
        check("属性上限钳制", lambda: [r["base"] for r in nbt_studio.read_entity_attributes(
            str(level), "1.21.4")["rows"] if r["name"] == "max_health"], [80.0])

        check("默认掉落物", lambda: len(nbt_studio.default_mob_drops(
            "zombie", "1.21")["drops"]) > 0, True)
        built = nbt_studio.build_mob_loot(
            "zombie", [{"item": "minecraft:diamond", "min": 1, "max": 3, "weight": 5}],
            "1.21.2", "thermal")
        check("战利品表目录按版本单数", lambda: built["relative_path"],
              "data/thermal/loot_table/entities/zombie.json")
        check("item 条目字段恒为 name", lambda: built["json"]["pools"][0]["entries"][0]["name"],
              "minecraft:diamond")
        check("1.20.1 用复数目录", lambda: nbt_studio.build_mob_loot(
            "zombie", [{"item": "minecraft:bone"}], "1.20.1")["relative_path"],
              "data/minecraft/loot_tables/entities/zombie.json")
        written = nbt_studio.write_mob_loot(
            str(world), "zombie", [{"item": "minecraft:diamond", "min": 1, "max": 3}],
            "1.21.2", "thermal")
        check("战利品表写入并返回路径", lambda: Path(written["file"]).is_file(), True)
        check("写入内容是合法 JSON", lambda: json.loads(
            Path(written["file"]).read_text(encoding="utf-8"))["type"], "minecraft:entity")
        check("pack.mcmeta 已生成", lambda: (world / "datapacks" / "mikancl_mob_loot" /
                                          "pack.mcmeta").is_file(), True)

        sp = tmp / "server.properties"
        sp.write_text("# comment\nview-distance=10\nsimulation-distance=10\n", encoding="utf-8")
        check("server.properties 读取", lambda: nbt_studio.server_properties(
            str(sp))["values"]["view-distance"], "10")
        check("server.properties 写入新键", lambda: nbt_studio.server_properties(
            str(sp), {"simulation-distance": 6, "spawn-protection": 0})["applied"],
              {"simulation-distance": "6", "spawn-protection": "0"})
        check("注释与未改动行保留", lambda: sp.read_text(
            encoding="utf-8").startswith("# comment\nview-distance=10"), True)

        outside = tmp.parent / "mikan_outside_probe.dat"
        check("路径穿越被拒绝", lambda: _expect_error(
            lambda: nbt_studio.read_tree(str(outside), root=str(world))), True)

        check("NBT 标签类型数", lambda: len(nbt_studio.schema()["tags"]), 13)
        check("NBT 字典分组数", lambda: len(nbt_studio.schema()["groups"]), 7)

        # 数据字典的版本边界
        check("1.20.5 数据包=41", lambda: game_data.pack_format_for(
            "1.20.5", "data")["format"], 41)
        check("1.20.5 资源包=32", lambda: game_data.pack_format_for(
            "1.20.5", "resource")["format"], 32)
        check("1.12.2 无数据包", lambda: game_data.pack_format_for(
            "1.12.2", "data")["format"], None)
        check("1.16 属性带命名空间", lambda: game_data.attribute_id(
            "movement_speed", "1.16.5"), "minecraft:generic.movement_speed")
        check("1.21.2 属性去前缀", lambda: game_data.attribute_id(
            "movement_speed", "1.21.2"), "minecraft:movement_speed")
        check("驼峰规则归一", lambda: game_data.canonical_gamerule(
            "doMobSpawning"), "spawn_mobs")

        # Qt 页面首次加载会在空目录上调这个函数；曾因 items 未定义抛 UnboundLocalError
        from mc_launcher.save_repair import list_world_candidates  # 惰性导入

        check("不存在的存档目录返回空表", lambda: list_world_candidates(
            str(tmp / "definitely_missing_saves")), [])

        print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
        return 0 if FAIL == 0 else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _expect_error(fn) -> bool:
    """断言调用抛出异常；用于路径安全等负向用例。"""
    try:
        fn()
    except (ValueError, FileNotFoundError, OSError):
        return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())
