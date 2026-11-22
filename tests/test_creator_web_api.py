"""WebApi 的创世神接口冒烟：Qt/Web/Electron 共用同一套 service。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.creator_fixtures import make_world


def _api(root: Path):
    from mc_launcher.ui_web.shell import WebApi

    config = SimpleNamespace(
        game_path=root / "game",
        backup_root=root / "backups",
        selected_instance=lambda: SimpleNamespace(version_id="1.20.1"),
    )
    return WebApi(config)


class CreatorWebApiTest(unittest.TestCase):
    def test_world_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            world = make_world(root / "game")
            api = _api(root)

            worlds = api.creator_worlds()
            self.assertTrue(worlds["ok"])
            self.assertEqual([item["name"] for item in worlds["items"]], ["TestWorld"])

            opened = api.creator_open(str(world))
            self.assertTrue(opened["ok"])
            self.assertEqual(opened["state"]["era"], "flattened")
            self.assertEqual(opened["state"]["pending"], [])

            player = api.creator_read_player(str(world), "level")
            self.assertTrue(player["ok"])
            self.assertEqual(player["player"]["health"], 20.0)

            preview = api.creator_preview(
                {
                    "world": str(world),
                    "player_uuid": "level",
                    "player": {"health": 40.0, "pos": [1.5, 70.0, -3.5]},
                }
            )
            self.assertTrue(preview["ok"], preview)
            applied = api.creator_apply(preview["preview"]["token"])
            self.assertTrue(applied["ok"], applied)
            again = api.creator_read_player(str(world), "level")
            self.assertEqual(again["player"]["health"], 40.0)

    def test_scan_items_returns_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_world(root / "game")
            api = _api(root)
            res = api.creator_scan_items("diamond")
            self.assertTrue(res["ok"])
            self.assertGreater(res["total"], 0)
            self.assertTrue(any("diamond" in item["id"] for item in res["items"]))

    def test_ender_food_and_modifiers_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            world = make_world(root / "game")
            api = _api(root)
            preview = api.creator_preview(
                {
                    "world": str(world),
                    "player_uuid": "level",
                    "player": {
                        "food_level": 6,
                        "ender_items": [{"slot": 0, "id": "minecraft:golden_apple", "count": 2}],
                        "attributes": [
                            {
                                "name": "generic.movement_speed",
                                "base": 0.1,
                                "modifiers": [{"amount": 3.0, "operation": "add_value"}],
                            }
                        ],
                    },
                }
            )
            self.assertTrue(preview["ok"], preview)
            api.creator_apply(preview["preview"]["token"])
            player = api.creator_read_player(str(world), "level")["player"]
            self.assertEqual(player["food_level"], 6)
            self.assertEqual(player["ender_items"][0]["id"], "minecraft:golden_apple")
            self.assertEqual(player["attributes"][0]["modifiers"][0]["amount"], 3.0)

    def test_complete_selected_advancements(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            world = make_world(root / "game")
            folder = world / "advancements"
            folder.mkdir()
            (folder / "level.json").write_text(
                '{"a": {"done": false, "criteria": {"x": null}},'
                ' "b": {"done": false, "criteria": {"y": null}}}',
                encoding="utf-8",
            )
            api = _api(root)
            report = api.creator_advancements(str(world), "level")
            self.assertTrue(report["ok"])
            self.assertEqual(len(report["report"]["entries"]), 2)
            result = api.creator_complete_advancements(str(world), "level", ["a"])
            self.assertTrue(result["ok"])
            self.assertEqual(result["result"]["count"], 1)

    def test_convert_reports_error_for_missing_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_world(root / "game")
            api = _api(root)
            result = api.creator_convert(str(root / "missing"), "1.12.2")
            self.assertFalse(result["ok"])
            self.assertTrue(result["message"])

    def test_backups_listing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            world = make_world(root / "game")
            api = _api(root)
            preview = api.creator_preview(
                {"world": str(world), "player_uuid": "level", "player": {"health": 30.0}}
            )
            api.creator_apply(preview["preview"]["token"])
            backups = api.creator_backups(str(world))
            self.assertTrue(backups["ok"])
            self.assertEqual(len(backups["items"]), 1)
            self.assertTrue(backups["items"][0]["name"].startswith("TestWorld"))


if __name__ == "__main__":
    unittest.main()


class CreatorMobWebApiTest(unittest.TestCase):
    """存档内生物：走 WebApi（Qt / Web / Electron 共用）的扫描 → 预览 → 写入。"""

    def test_mob_flow(self):
        from tests.creator_fixtures import make_region
        from tests.test_creator_mobs import _chunk, _villager, _zombie

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            world = make_world(root / "game")
            (world / "region").mkdir()
            make_region(
                world / "entities" / "r.0.0.mca",
                {(0, 0): _chunk([_zombie(), _villager()], split=True)},
            )
            api = _api(root)
            scanned = api.creator_scan_mobs(str(world), "overworld", "", 8, True)
            self.assertTrue(scanned["ok"], scanned)
            mobs = scanned["report"]["mobs"]
            self.assertEqual(len(mobs), 2)
            zombie = next(item for item in mobs if item["id"] == "minecraft:zombie")
            preview = api.creator_mob_preview(
                {
                    "world": str(world),
                    "dimension": "overworld",
                    "edits": [
                        {
                            "uuid": zombie["uuid"],
                            "file": zombie["file"],
                            "changes": {"health": 42, "max_health": 42, "attack_damage": 9},
                        }
                    ],
                }
            )
            self.assertTrue(preview["ok"], preview)
            self.assertEqual(preview["preview"]["mobs"], 1)
            applied = api.creator_mob_apply(preview["preview"]["token"])
            self.assertTrue(applied["ok"], applied)
            self.assertEqual(applied["result"]["mobs"], 1)
            fresh = api.creator_scan_mobs(str(world), "overworld", "zombie", 8, True)
            row = fresh["report"]["mobs"][0]
            self.assertEqual(row["health"], 42.0)
            self.assertEqual(row["attack_damage"], 9.0)
