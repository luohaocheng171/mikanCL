"""物品清单「从本地版本 jar 动态枚举」的回归测试。

直接运行：``python tests/test_item_enum.py``
不依赖本机是否装有 Minecraft：在临时目录里构造假的
``versions/<id>/<id>.jar`` 再断言枚举 / 贴图 / 兜底行为。
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mc_launcher import item_icons  # noqa: E402

PNG = bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 32


def _make_game(root: Path, version: str = "1.20.1", legacy: bool = False) -> Path:
    """构造 <root>/versions/<version>/<version>.jar 的最小版本 jar。"""
    jar_dir = root / "versions" / version
    jar_dir.mkdir(parents=True, exist_ok=True)
    jar = jar_dir / f"{version}.jar"
    with zipfile.ZipFile(jar, "w") as archive:
        if legacy:
            archive.writestr("assets/minecraft/textures/items/apple.png", PNG)
            archive.writestr("assets/minecraft/textures/items/stick.png", PNG)
        else:
            archive.writestr("assets/minecraft/textures/item/apple.png", PNG)
            archive.writestr("assets/minecraft/textures/item/diamond_sword.png", PNG)
            archive.writestr("assets/minecraft/textures/block/stone.png", PNG)
            archive.writestr("assets/minecraft/models/item/apple.json", "{}")
            archive.writestr("assets/minecraft/models/item/diamond_sword.json", "{}")
            archive.writestr("assets/minecraft/models/item/no_texture_item.json", "{}")
            archive.writestr("assets/minecraft/blockstates/stone.json", "{}")
            # 非原版命名空间不应混入原版物品清单
            archive.writestr("assets/thermal/textures/item/sawdust.png", PNG)
    return jar


def test_enumerate_from_jar(tmp_path: Path) -> None:
    game = tmp_path / "game"
    _make_game(game)
    result = item_icons.enumerate_items("1.20.1", game)
    assert result["source"] == "jar", result
    ids = [row["id"] for row in result["items"]]
    assert ids == sorted(ids), "物品应按 id 排序"
    assert "minecraft:apple" in ids
    assert "minecraft:diamond_sword" in ids
    assert "minecraft:stone" in ids  # blockstates 里的方块物品
    assert "minecraft:no_texture_item" in ids
    assert not any(row["id"].startswith("thermal:") for row in result["items"])
    rows = {row["id"]: row for row in result["items"]}
    assert rows["minecraft:apple"]["texture_available"] is True
    assert rows["minecraft:stone"]["texture_available"] is True  # 用方块贴图
    assert rows["minecraft:no_texture_item"]["texture_available"] is False
    assert all(row["source"] == "jar" for row in result["items"])
    assert result["count"] == len(result["items"])
    assert Path(result["jar"]).is_file()


def test_item_texture(tmp_path: Path) -> None:
    game = tmp_path / "game"
    _make_game(game)
    raw = item_icons.item_texture("1.20.1", "minecraft:apple", game)
    assert raw == PNG
    assert item_icons.item_texture("1.20.1", "minecraft:not_exists", game) is None
    uri = item_icons.item_texture_uri("1.20.1", "minecraft:apple", game)
    assert uri.startswith("data:image/png;base64,")


def test_legacy_textures(tmp_path: Path) -> None:
    game = tmp_path / "game112"
    _make_game(game, version="1.12.2", legacy=True)
    result = item_icons.enumerate_items("1.12.2", game)
    ids = [row["id"] for row in result["items"]]
    assert ids == ["minecraft:apple", "minecraft:stick"]
    assert result["legacy_texture_dir"] is True


def test_missing_jar_is_empty_and_safe(tmp_path: Path) -> None:
    game = tmp_path / "empty_game"
    game.mkdir()
    result = item_icons.enumerate_items("1.20.1", game)
    assert result["items"] == []
    assert result["count"] == 0
    assert result["source"] == "none"
    assert result["note"], "找不到 jar 时应当说明原因"
    # 版本号为空、目录不存在、game_dir 缺失都不能抛异常
    assert item_icons.enumerate_items("", game)["items"] == []
    assert item_icons.enumerate_items("1.20.1", tmp_path / "no_such_dir")["items"] == []
    assert item_icons.enumerate_items("1.20.1")["items"] == []
    assert item_icons.item_texture("1.20.1", "minecraft:apple", game) is None


def test_catalog_prefers_jar(tmp_path: Path) -> None:
    game = tmp_path / "game"
    _make_game(game)
    cat = item_icons.catalog([], "1.20.1", query="apple", game_dir=game)
    assert cat["source"] == "jar", cat
    assert cat["items"], cat
    assert cat["items"][0]["id"] == "minecraft:apple"
    assert cat["items"][0]["icon_source"] == "game"
    # 不在 jar 里的旧内置物品（比如 1.7 的老 ID）不会凭空出现
    assert not any(row["id"] == "minecraft:golden_pickaxe" for row in cat["items"])


def test_catalog_builtin_fallback(tmp_path: Path) -> None:
    game = tmp_path / "no_versions"
    game.mkdir()
    cat = item_icons.catalog([], "1.20.1", query="apple", game_dir=game)
    assert cat["source"] == "builtin", cat
    assert any(row["id"] == "minecraft:apple" for row in cat["items"])
    assert cat["note"], "回退内置表时应当说明原因"


def main() -> int:
    checks = [
        test_enumerate_from_jar,
        test_item_texture,
        test_legacy_textures,
        test_missing_jar_is_empty_and_safe,
        test_catalog_prefers_jar,
        test_catalog_builtin_fallback,
    ]
    passed = 0
    failed = 0
    for fn in checks:
        tmp = Path(tempfile.mkdtemp(prefix="mikan_enum_"))
        try:
            fn(tmp)
            print(f"[OK]   {fn.__name__}")
            passed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"[FAIL] {fn.__name__}: {type(exc).__name__}: {exc}")
            failed += 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n结果：{passed} 通过 / {failed} 失败")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
