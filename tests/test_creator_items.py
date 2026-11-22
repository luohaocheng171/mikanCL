"""creator_items：从版本 jar / 模组 jar / 内置表扫描物品 ID。"""

from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from mc_launcher.creator_items import builtin_items, scan_item_ids


def _write_lang_jar(path: Path, assets: dict[str, dict[str, str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        for namespace, lang in assets.items():
            zf.writestr(
                f"assets/{namespace}/lang/en_us.json",
                json.dumps(lang, ensure_ascii=True),
            )
    return path


class ItemScanTest(unittest.TestCase):
    def test_builtin_contains_common_items(self):
        ids = {item["id"] for item in builtin_items()}
        self.assertIn("minecraft:diamond", ids)
        self.assertIn("minecraft:command_block", ids)

    def test_scan_version_jar_reads_item_and_block_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_lang_jar(
                root / "versions" / "1.20.1" / "1.20.1.jar",
                {
                    "minecraft": {
                        "item.minecraft.diamond": "Diamond",
                        "block.minecraft.stone": "Stone",
                        "gui.done": "Done",
                    }
                },
            )
            items = scan_item_ids(root, version_id="1.20.1", use_cache=False)
            ids = {item["id"] for item in items}
            self.assertIn("minecraft:diamond", ids)
            self.assertIn("minecraft:stone", ids)
            self.assertNotIn("gui.done", ids)

    def test_scan_mod_jar_uses_namespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_lang_jar(
                root / "mods" / "mymod.jar",
                {"mymod": {"item.mymod.ruby": "Ruby"}},
            )
            items = scan_item_ids(root, version_id="", use_cache=False)
            found = {item["id"]: item for item in items}
            self.assertIn("mymod:ruby", found)
            self.assertEqual(found["mymod:ruby"]["name"], "Ruby")

    def test_results_are_deduplicated_and_sorted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_lang_jar(
                root / "versions" / "v" / "v.jar",
                {"minecraft": {"item.minecraft.diamond": "Diamond"}},
            )
            items = scan_item_ids(root, version_id="v", use_cache=False)
            ids = [item["id"] for item in items]
            self.assertEqual(ids, sorted(set(ids)))

    def test_legacy_era_lists_every_jar_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jar = root / "mods" / "m.jar"
            jar.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(jar, "w") as zf:
                zf.writestr("assets/minecraft/models/item/diamond_sword.json", "{}")
                zf.writestr("assets/minecraft/models/item/apple.json", "{}")
                zf.writestr("assets/m/models/item/ruby.json", "{}")
            items = scan_item_ids(root, era="legacy", use_cache=False)
            ids = {item["id"] for item in items}
            # 旧版不再按内置数字表过滤：jar 里有多少注册名就列多少
            self.assertIn("minecraft:diamond_sword", ids)
            self.assertIn("minecraft:apple", ids)
            self.assertIn("m:ruby", ids)
            self.assertNotIn("minecraft:amethyst_shard", ids)

    def test_cache_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = root / "cache"
            _write_lang_jar(
                root / "game" / "mods" / "m.jar",
                {"m": {"item.m.thing": "Thing"}},
            )
            first = scan_item_ids(
                root / "game", version_id="", use_cache=True, cache_dir=cache
            )
            second = scan_item_ids(
                root / "game", version_id="", use_cache=True, cache_dir=cache
            )
            self.assertEqual(first, second)
            self.assertTrue(any(p.suffix == ".json" for p in cache.iterdir()))


if __name__ == "__main__":
    unittest.main()
