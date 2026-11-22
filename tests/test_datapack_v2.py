"""数据包编辑器 v2 版本矩阵 / Mod 覆盖 / 双包导出的回归测试。

直接运行：``python tests/test_datapack_v2.py``
"""
from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mc_launcher import datapack as dp  # noqa: E402

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


def shaped():
    return {
        "name": "test_shaped", "type": "shaped",
        "grid": ["AAA", "A A", "   "],
        "key": {"A": "minecraft:diamond"},
        "result": {"item": "minecraft:diamond_block"}, "count": 2,
    }


def smelting():
    return {
        "name": "test_smelting", "type": "smelting",
        "ingredient": "minecraft:raw_iron",
        "result": {"item": "minecraft:iron_ingot"}, "count": 1,
        "experience": 0.7, "cookingtime": 200,
    }


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="mikan_dp_"))
    try:
        check("1.20.1 数据包格式号=15", lambda: dp.pack_format_for_version("1.20.1"), 15)
        check("1.20.5 数据包格式号=41", lambda: dp.pack_format_for_version("1.20.5"), 41)
        check("1.21.2 数据包格式号=57", lambda: dp.pack_format_for_version("1.21.2"), 57)
        check("1.21.4 资源包格式号=46", lambda: dp.pack_format_for_version(
            "1.21.4", "resource"), 46)

        old = dp.recipe_to_json(shaped(), 15, "1.20.1")
        check("1.20.1 result 用 item", lambda: "item" in old["result"], True)
        check("1.20.1 key 用 item 对象", lambda: old["key"]["A"], {"item": "minecraft:diamond"})
        new = dp.recipe_to_json(shaped(), 57, "1.21.2")
        check("1.21.2 result 用 id", lambda: "id" in new["result"], True)
        check("1.21.2 key 是 ID 字符串", lambda: new["key"]["A"], "minecraft:diamond")
        check("1.21.2 产物数量", lambda: new["result"]["count"], 2)

        old_cook = dp.recipe_to_json(smelting(), 15, "1.20.1")
        new_cook = dp.recipe_to_json(smelting(), 57, "1.21.2")
        check("1.20.1 熔炉 ingredient 是对象", lambda: old_cook["ingredient"],
              {"item": "minecraft:raw_iron"})
        check("1.21.2 熔炉 ingredient 是字符串", lambda: new_cook["ingredient"],
              "minecraft:raw_iron")
        check("熔炉经验与时长保留", lambda: (new_cook["experience"], new_cook["cookingtime"]),
              (0.7, 200))

        with_components = dict(smelting(), components={"minecraft:custom_name": "Mikan"})
        check("1.20.5+ 支持 components", lambda: dp.recipe_to_json(
            with_components, 41, "1.20.5")["result"]["components"],
              {"minecraft:custom_name": "Mikan"})
        check("1.20.1 忽略 components", lambda: "components" in dp.recipe_to_json(
            with_components, 15, "1.20.1")["result"], False)

        loot = {"name": "zombie", "entries": [
            {"item": "minecraft:rotten_flesh", "min": 0, "max": 2, "weight": 3}]}
        lj = dp.loot_to_json(loot, "1.21.2")
        check("item 条目字段恒为 name", lambda: lj["pools"][0]["entries"][0]["name"],
              "minecraft:rotten_flesh")
        check("掉落数量允许下限 0", lambda: lj["pools"][0]["entries"][0]["functions"][0]["count"],
              {"min": 0, "max": 2})
        check("loot_table 条目 1.21 用 value", lambda: dp.loot_to_json(
            {"entries": [{"entry_type": "loot_table", "table": "minecraft:chests/simple_dungeon"}]},
            "1.21")["pools"][0]["entries"][0]["value"], "minecraft:chests/simple_dungeon")
        check("loot_table 条目 1.20.1 用 name", lambda: "name" in dp.loot_to_json(
            {"entries": [{"entry_type": "loot_table", "table": "minecraft:chests/simple_dungeon"}]},
            "1.20.1")["pools"][0]["entries"][0], True)

        spec = {
            "name": "mikan_pack", "version": "1.21.2",
            "recipes": [shaped(), smelting(),
                        dict(shaped(), name="copper_ingot_from_smelting",
                             namespace="thermal", override=True)],
            "loot_tables": [dict(loot, path="entities/zombie",
                                 namespace="minecraft", override=True)],
        }
        built = dp.build_pack(spec)
        check("build_pack 用单数战利品表目录", lambda: any(
            "loot_table/entities/zombie.json" in k for k in built["files"]), True)
        check("Mod 覆盖配方写到 mod 命名空间", lambda: any(
            k.startswith("data/thermal/recipes/") for k in built["files"]), True)
        check("覆盖清单被记录", lambda: len(built["overrides"]), 2)
        check("1.21.2 格式号自动取 57", lambda: built["pack_format"], 57)

        old_spec = dict(spec, version="1.20.1")
        check("1.20.1 用复数战利品表目录", lambda: any(
            "loot_tables/entities/zombie.json" in k for k in dp.build_pack(old_spec)["files"]), True)

        check("1.12.2 明确拒绝", lambda: dp.validate_pack(
            dict(spec, version="1.12.2"))["ok"], False)
        check("1.12.2 拒绝说明含原因", lambda: "没有数据包系统" in dp.validate_pack(
            dict(spec, version="1.12.2"))["errors"][0], True)

        plan = dp.pack_plan(spec)
        check("安装说明含 datapacks 与 resourcepacks", lambda: (
            any("datapacks" in x for x in plan["install"]) and
            any("resourcepacks" in x for x in plan["install"])), True)

        exported = dp.export_bundle(spec, str(tmp))
        check("双包导出成功", lambda: exported["ok"], True)
        check("数据包文件存在", lambda: Path(exported["data_pack"]).is_file(), True)
        check("资源包文件存在", lambda: Path(exported["resource_pack"]).is_file(), True)
        with zipfile.ZipFile(exported["data_pack"]) as bundle:
            names = bundle.namelist()
            recipe = json.loads(bundle.read("data/mikancl/recipes/test_shaped.json"))
            meta = json.loads(bundle.read("pack.mcmeta"))["pack"]
        check("数据包含覆盖配方", lambda: "data/thermal/recipes/copper_ingot_from_smelting.json" in names, True)
        check("数据包内配方已按版本生成", lambda: recipe["key"]["A"], "minecraft:diamond")
        check("数据包 pack.mcmeta 格式号", lambda: meta["pack_format"], 57)
        with zipfile.ZipFile(exported["resource_pack"]) as bundle:
            rmeta = json.loads(bundle.read("pack.mcmeta"))["pack"]
        check("资源包用独立格式号", lambda: rmeta["pack_format"], 42)

        # 1.21.9 起 pack.mcmeta 需要 min_format / max_format
        fut = dp.build_pack(dict(spec, version="1.21.9", pack_format=69))
        fut_meta = json.loads(fut["files"]["pack.mcmeta"])["pack"]
        check("1.21.9 写 min_format", lambda: "min_format" in fut_meta, True)
        check("1.21.9 写 max_format", lambda: fut_meta["max_format"], 999)

        # 读取 1.21.2 简化 ingredient 的现有配方
        raw_new = {
            "type": "minecraft:crafting_shaped",
            "pattern": ["##"], "key": {"#": "minecraft:stick"},
            "result": {"id": "minecraft:torch", "count": 4},
        }
        model = dp._from_recipe_json(raw_new, "jar", "data/x/recipes/torch.json")
        check("能解析简单 ingredient", lambda: model["key"]["#"], "minecraft:stick")
        check("能解析 id 型 result", lambda: model["result"]["item"], "minecraft:torch")

        # 扫描单数 loot_table 目录
        d = tmp / "scanpack" / "data" / "minecraft" / "loot_table"
        d.mkdir(parents=True)
        (d / "custom.json").write_text(json.dumps({"type": "minecraft:entity", "pools": []}), encoding="utf-8")
        scanned = dp.scan_recipe_sources([str(tmp / "scanpack")])
        check("能扫描单数 loot_table 目录", lambda: len(scanned["loot_tables"]), 1)

        print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
        return 0 if FAIL == 0 else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
