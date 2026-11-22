"""NBT 建筑生成与深层控制的回归测试。

直接运行：``python tests/test_nbt_build.py``
覆盖：版本能力检测 / 结构文件生成与读回 / 建筑模板 / 结构方块物品 /
/give 命令 / /place 命令版本边界 / level.dat 深层控制 / 26.1 分文件报错 / 路径安全。
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mc_launcher import nbt, nbt_build as B  # noqa: E402

C, L, S, Bt, SH, I, LO, D = (nbt.TAG_COMPOUND, nbt.TAG_LIST, nbt.TAG_STRING,
                             nbt.TAG_BYTE, nbt.TAG_SHORT, nbt.TAG_INT,
                             nbt.TAG_LONG, nbt.TAG_DOUBLE)

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


def _raises(fn) -> bool:
    try:
        fn()
    except (ValueError, FileNotFoundError, OSError):
        return True
    return False


def _level_world(folder: Path) -> Path:
    """造一个带最小 level.dat 的世界。"""
    world = folder / "world"
    world.mkdir(parents=True, exist_ok=True)
    data = (C, {"Data": (C, {
        "SpawnX": (I, 0), "SpawnY": (I, 64), "SpawnZ": (I, 0),
        "DayTime": (LO, 1000), "Difficulty": (Bt, 2), "hardcore": (Bt, 0),
        "WorldBorder": (C, {"center_x": (D, 0.0), "size": (D, 1000.0)}),
    })})
    nbt.save_nbt_typed_file(world / "level.dat", "", data)
    return world


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="mikan_build_test_"))
    try:
        # ---------- 版本能力 ----------
        check("1.12.2 无 /place", lambda: B.capabilities("1.12.2")["place_command"], False)
        check("1.12.2 有结构方块", lambda: B.capabilities("1.12.2")["structure_block"], True)
        check("1.19 有 /place", lambda: B.capabilities("1.19")["place_command"], True)
        check("1.20.4 无 strict", lambda: B.capabilities("1.20.4")["place_template_strict"], False)
        check("1.21.5 有 strict", lambda: B.capabilities("1.21.5")["place_template_strict"], True)
        check("1.20.1 目录 structures", lambda: B.capabilities("1.20.1")["structure_dir"], "structures")
        check("1.21 目录 structure", lambda: B.capabilities("1.21")["structure_dir"], "structure")
        check("1.20.1 未重构", lambda: B.capabilities("1.20.1")["level_dat_restructured"], False)
        check("26.1 已重构", lambda: B.capabilities("26.1")["level_dat_restructured"], True)
        check("1.11 BE id structure_block",
              lambda: B.capabilities("1.11")["structure_block_be_id"], "structure_block")
        check("1.10 BE id Structure",
              lambda: B.capabilities("1.10")["structure_block_be_id"], "Structure")
        check("空版本保守 False", lambda: B.capabilities("")["place_command"], False)
        check("1.16.1 无 SpawnAngle", lambda: B.capabilities("1.16.1")["spawn_angle"], False)
        check("1.16.2 有 SpawnAngle", lambda: B.capabilities("1.16.2")["spawn_angle"], True)

        # ---------- 建筑模板 ----------
        for tmpl in B.BUILD_TEMPLATES:
            size, blocks = B.template_blocks(tmpl["id"])
            check(f"模板 {tmpl['id']} 有方块", lambda b=blocks: len(b) > 0, True)
        check("非法模板报错", lambda: _raises(lambda: B.template_blocks("nope")), True)

        # ---------- 结构文件生成与读回 ----------
        p = tmp / "hut.nbt"
        r = B.build_template("hut", data_version=3953, path=str(p))
        check("结构文件写出", lambda: r["ok"], True)
        check("结构文件 blocks 数", lambda: r["blocks"] > 0, True)
        name, node = nbt.load_nbt_typed_file(p)
        root = node[1]
        check("读回 size 3 元", lambda: len(root["size"][1][1]), 3)
        check("读回 size 值", lambda: [v[1] for v in root["size"][1][1]], [5, 5, 5])
        check("读回 palette 非空", lambda: len(root["palette"][1][1]) > 0, True)
        check("读回 blocks 数一致", lambda: len(root["blocks"][1][1]), r["blocks"])
        check("读回 DataVersion", lambda: root["DataVersion"][1], 3953)
        check("palette 含 air", lambda: any(
            e[1]["Name"][1] == "minecraft:air" for e in root["palette"][1][1]), True)
        # 每个 block 的 state 必须落在 palette 范围内
        check("block state 索引合法", lambda: all(
            0 <= b[1]["state"][1] < len(root["palette"][1][1])
            for b in root["blocks"][1][1]), True)

        # 自定义结构（含 Properties）
        p2 = tmp / "custom.nbt"
        B.write_structure_file(str(p2), (2, 1, 1), [
            {"pos": [0, 0, 0], "state": "minecraft:oak_log",
             "properties": {"axis": "y"}},
            {"pos": [1, 0, 0], "state": "minecraft:stone"},
        ])
        _, n2 = nbt.load_nbt_typed_file(p2)
        palette2 = n2[1]["palette"][1][1]
        props_ok = any(
            "Properties" in e[1] and e[1]["Properties"][1]["axis"][1] == "y"
            for e in palette2)
        check("自定义结构保留 Properties", lambda: props_ok, True)

        # ---------- 结构方块物品 ----------
        sb = B.structure_block_item("1.20.1", "mikancl:hut", (100, 64, 200), (5, 5, 5))
        check("结构方块生成", lambda: sb["ok"], True)
        be = sb["item"]["tag"][1]["BlockEntityTag"][1]
        check("BE mode=LOAD", lambda: be["mode"][1], "LOAD")
        check("BE name", lambda: be["name"][1], "mikancl:hut")
        check("BE posX", lambda: be["posX"][1], 100)
        check("BE posY", lambda: be["posY"][1], 64)
        check("BE posZ", lambda: be["posZ"][1], 200)
        check("BE sizeX", lambda: be["sizeX"][1], 5)
        check("BE rotation 默认", lambda: be["rotation"][1], "NONE")
        check("BE integrity float", lambda: so(be["integrity"]), 1.0)
        # 非法 rotation 会被纠正
        sb2 = B.structure_block_item("1.20.1", "x", (0, 64, 0), (1, 1, 1), rotation="BAD")
        check("非法 rotation 纠正", lambda: sb2["item"]["tag"][1]["BlockEntityTag"][1]["rotation"][1], "NONE")
        # 1.10 用旧 BE id
        sb3 = B.structure_block_item("1.10", "x", (0, 64, 0), (1, 1, 1))
        check("1.10 BE id", lambda: sb3["be_id"], "Structure")
        # 1.9 以前无结构方块
        sb4 = B.structure_block_item("1.9", "x", (0, 64, 0), (1, 1, 1))
        check("1.9 无结构方块", lambda: sb4["ok"], False)
        # 未填版本
        sb5 = B.structure_block_item("", "x", (0, 64, 0), (1, 1, 1))
        check("空版本拒绝结构方块", lambda: sb5["ok"], False)

        # ---------- /give 命令 ----------
        g = B.give_command("1.20.1", sb["item"])
        check("/give 生成", lambda: g["ok"], True)
        check("/give 含 structure_block", lambda: "minecraft:structure_block" in g["command"], True)
        check("/give 含 BlockEntityTag", lambda: "BlockEntityTag" in g["command"], True)
        check("/give 含 posX:100", lambda: "posX:100" in g["command"], True)
        check("/give 空版本拒绝", lambda: B.give_command("", sb["item"])["ok"], False)

        # ---------- /place 命令 ----------
        pc = B.place_command("1.19", "mikancl:hut", (10, 70, -5))
        check("/place 1.19 可用", lambda: pc["ok"], True)
        check("/place 命令格式", lambda: pc["command"].startswith("/place template mikancl:hut 10 70 -5"), True)
        check("/place 1.18 不可用", lambda: B.place_command("1.18", "x", (0, 64, 0))["ok"], False)
        pc_strict = B.place_command("1.21.5", "x", (0, 64, 0), strict=True)
        check("/place strict 1.21.5", lambda: pc_strict["command"].endswith("strict"), True)
        pc_nostrict = B.place_command("1.20.1", "x", (0, 64, 0), strict=True)
        check("/place strict 1.20.1 不追加", lambda: pc_nostrict["command"].endswith("strict"), False)

        # ---------- 完整方案 ----------
        plan = B.build_plan("1.20.1", "hut", (100, 64, 200))
        kinds = [m["kind"] for m in plan["methods"]]
        check("方案含结构方块", lambda: "structure_block" in kinds, True)
        check("方案含 /give", lambda: "give_structure_block" in kinds, True)
        check("方案含 /place", lambda: "place_command" in kinds, True)
        check("方案含命令方块", lambda: "command_block" in kinds, True)
        plan_old = B.build_plan("1.12.2", "hut", (0, 64, 0))
        old_kinds = [m["kind"] for m in plan_old["methods"]]
        check("1.12.2 只有结构方块族", lambda: "place_command" not in old_kinds, True)
        check("空版本方案拒绝", lambda: B.build_plan("", "hut", (0, 64, 0))["ok"], False)

        # ---------- 结构文件写入数据包路径 ----------
        check("1.20.1 数据包路径用 structures", lambda: B.structure_datapack_path(
            str(tmp), "mikancl", "hut", "1.20.1").as_posix().endswith("structures/hut.nbt"), True)
        check("1.21 数据包路径用 structure", lambda: B.structure_datapack_path(
            str(tmp), "mikancl", "hut", "1.21").as_posix().endswith("structure/hut.nbt"), True)

        # ---------- 深层控制目录 ----------
        rows_120 = B.control_catalog("1.20.1")
        check("控制项 41 条", lambda: len(rows_120), 41)
        rows_261 = B.control_catalog("26.1")
        check("26.1 有移位项", lambda: sum(1 for r in rows_261 if r["moved_in_26_1"]) > 0, True)
        # spawn_angle 在 1.12.2 不可用
        rows_old = {r["id"]: r for r in B.control_catalog("1.12.2")}
        check("1.12.2 spawn_angle 不可用", lambda: rows_old["spawn_angle"]["available"], False)
        check("1.12.2 spawn_x 可用", lambda: rows_old["spawn_x"]["available"], True)
        # 26.1 天气走分文件
        rows_261_map = {r["id"]: r for r in rows_261}
        check("26.1 天气走 weather.dat", lambda: "weather.dat" in rows_261_map["clear_weather_time"]["path"], True)
        check("1.20.1 天气在 level.dat", lambda: rows_120[[r["id"] for r in rows_120].index("clear_weather_time")]["path"], "Data.clearWeatherTime")
        check("分类非空", lambda: len(B.control_categories("1.20.1")) > 0, True)

        # ---------- 深层控制写入 ----------
        world = _level_world(tmp)
        r1 = B.apply_control(str(world), "spawn_x", 999, "1.20.1")
        check("写 spawn_x", lambda: (r1["ok"], r1["readback"]), (True, 999))
        r2 = B.apply_control(str(world), "day_time", 18000, "1.20.1")
        check("写 day_time", lambda: r2["readback"], 18000)
        check("day_time 用 long 标签", lambda: r2["tag"], LO)
        r3 = B.apply_control(str(world), "difficulty", 3, "1.20.1")
        check("写 difficulty", lambda: r3["readback"], 3)
        r4 = B.apply_control(str(world), "border_size", 2000.0, "1.20.1")
        check("写 border_size", lambda: r4["readback"], 2000.0)
        # 备份确实生成了
        check("写前生成备份", lambda: bool(r1.get("backup")) and Path(r1["backup"]).exists(), True)
        # 版本不足应拒绝
        check("spawn_angle 1.12.2 拒绝", lambda: _raises(
            lambda: B.apply_control(str(world), "spawn_angle", 90, "1.12.2")), True)
        # 26.1 分文件缺失应明确报错（不臆造）
        r5 = B.apply_control(str(world), "clear_weather_time", 100, "26.1")
        check("26.1 缺 weather.dat 报错", lambda: r5["ok"], False)
        check("报错提到 weather.dat", lambda: "weather.dat" in r5.get("message", ""), True)
        # 未知控制项
        check("未知控制项报错", lambda: _raises(
            lambda: B.apply_control(str(world), "nope_field", 1, "1.20.1")), True)

        # ---------- 路径安全 ----------
        check("结构文件路径穿越被拒", lambda: _raises(lambda: B.write_structure_file(
            str(tmp.parent / "escape.nbt"), (1, 1, 1), [], root=str(tmp))), True)

        # ---------- 原理说明 ----------
        check("原理说明要点", lambda: len(B.explain()["points"]) >= 6, True)

        print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
        return 0 if FAIL == 0 else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def so(node) -> float:
    """把 typed float 节点读成 float，便于断言。"""
    return float(node[1])


if __name__ == "__main__":
    raise SystemExit(main())
