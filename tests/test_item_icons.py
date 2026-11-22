"""物品贴图 / 图集 / Mod 命名空间的无依赖回归测试。

直接运行：``python tests/test_item_icons.py``
用内存构造假的 jar，不依赖本机是否装有 Minecraft。
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

from mc_launcher import item_icons  # noqa: E402

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


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="mikan_icon_"))
    try:
        png = bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 32
        mod_jar = tmp / "thermal-1.20.1.jar"
        with zipfile.ZipFile(mod_jar, "w") as archive:
            archive.writestr("assets/thermal/textures/item/copper_ingot.png", png)
            archive.writestr("assets/thermal/textures/item/sawdust.png", png)
            archive.writestr("data/thermal/recipes/copper_ingot_from_smelting.json",
                             json.dumps({"type": "minecraft:smelting"}))
            archive.writestr("fabric.mod.json", json.dumps({"id": "thermal", "name": "Thermal"}))
        version_jar = tmp / "1.20.1.jar"
        with zipfile.ZipFile(version_jar, "w") as archive:
            archive.writestr("assets/minecraft/textures/item/diamond.png", png)
            archive.writestr("assets/minecraft/textures/item/iron_ingot.png", png)
        sources = [str(mod_jar), str(version_jar)]

        icons = check("extract_icons 抓到 4 张贴图", lambda: len(
            item_icons.extract_icons(sources)), 4)
        check("Mod 物品 ID 带命名空间", lambda: "thermal:copper_ingot" in
              item_icons.extract_icons(sources), True)
        check("原版物品 ID 带命名空间", lambda: "minecraft:diamond" in
              item_icons.extract_icons(sources), True)

        ns = check("Mod 命名空间数", lambda: item_icons.scan_mod_namespaces(
            [str(tmp)])["namespaces"], None)
        check("版本 jar 不被误认为 Mod", lambda: [n["id"] for n in ns], ["thermal"])
        check("命名空间记录了配方路径", lambda: len(ns[0]["recipes"]), 1)

        cat = check("catalog 查询 diamond", lambda: item_icons.catalog(
            sources, "1.20.1", query="diamond"), None)
        check("diamond 用真实游戏贴图", lambda: cat["items"][0]["icon_source"], "game")
        cat2 = item_icons.catalog(sources, "1.20.1", query="stone")
        check("未找到贴图时用占位图标", lambda: any(
            r["icon_source"] == "placeholder" for r in cat2["items"]), True)
        check("占位 SVG 是 data URI", lambda: item_icons.placeholder_icon(
            "minecraft:stone").startswith("data:image/svg+xml;base64,"), True)
        check("占位图标对长物品名不越界", lambda: len(item_icons.placeholder_icon(
            "minecraft:very_long_item_name_for_hash_test")) > 100, True)

        mod_cat = item_icons.catalog(sources, "1.20.1", query="copper")
        check("Mod 物品进入物品栏", lambda: any(
            r["id"] == "thermal:copper_ingot" for r in mod_cat["items"]), True)
        check("Mod 物品用真实贴图", lambda: any(
            r["id"] == "thermal:copper_ingot" and r["icon_source"] == "game"
            for r in mod_cat["items"]), True)

        rp = item_icons.build_resource_pack("1.20.1", mod_cat["items"])
        check("1.20.1 资源包格式号", lambda: rp["pack_format"], 15)
        check("资源包贴图目录为单数", lambda: rp["folder"], "item")
        with zipfile.ZipFile(io.BytesIO(rp["bytes"])) as archive:
            names = archive.namelist()
            meta = json.loads(archive.read("pack.mcmeta"))["pack"]
        check("资源包含 pack.mcmeta", lambda: "pack.mcmeta" in names, True)
        check("资源包写入 Mod 贴图", lambda: any(
            n.startswith("assets/thermal/textures/item/") for n in names), True)
        check("资源包格式号写入正确", lambda: meta["pack_format"], 15)

        legacy = item_icons.build_resource_pack("1.12.2", [])
        check("1.12.2 用旧贴图目录", lambda: legacy["folder"], "items")
        check("1.12.2 资源包格式号", lambda: legacy["pack_format"], 3)

        print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
        return 0 if FAIL == 0 else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
