"""存档内生物数值编辑（血量 / 攻击伤害 / 交易价格）测试。"""

from __future__ import annotations

import tempfile
import unittest
import zlib
from pathlib import Path

from mc_launcher import creator_mobs, game_data, nbt
from mc_launcher.creator_region import _decompress, build_region_bytes, read_region
from tests.creator_fixtures import make_region

TAG = nbt


def _c(**fields):
    return (TAG.TAG_COMPOUND, fields)


def _list(tag, items):
    return (TAG.TAG_LIST, (tag, list(items)))


def _uuid_int_array(seed: int):
    return (TAG.TAG_INT_ARRAY, [seed, seed + 1, seed + 2, seed + 3])


def _item(item_id: str, count: int = 1):
    return _c(id=(TAG.TAG_STRING, item_id), Count=(TAG.TAG_BYTE, int(count)))


def _trade(buy: int, sell: str = "minecraft:emerald", uses: int = 0, max_uses: int = 12):
    return _c(
        buy=_item("minecraft:emerald", buy),
        sell=_item(sell, 1),
        uses=(TAG.TAG_INT, int(uses)),
        maxUses=(TAG.TAG_INT, int(max_uses)),
        specialPrice=(TAG.TAG_INT, 0),
        rewardExp=(TAG.TAG_BYTE, 1),
        priceMultiplier=(TAG.TAG_FLOAT, 0.05),
    )


def _zombie(names: str = "Zombie", uuid_seed: int = 0x11223344, health: float = 20.0):
    return _c(
        id=(TAG.TAG_STRING, "minecraft:zombie"),
        UUID=_uuid_int_array(uuid_seed),
        Pos=_list(TAG.TAG_DOUBLE, [(TAG.TAG_DOUBLE, 1.5), (TAG.TAG_DOUBLE, 64.0), (TAG.TAG_DOUBLE, 1.5)]),
        Health=(TAG.TAG_FLOAT, health),
        CustomName=(TAG.TAG_STRING, names),
        Attributes=_list(
            TAG.TAG_COMPOUND,
            [
                _c(Name=(TAG.TAG_STRING, "generic.max_health"), Base=(TAG.TAG_DOUBLE, 20.0)),
                _c(Name=(TAG.TAG_STRING, "generic.attack_damage"), Base=(TAG.TAG_DOUBLE, 3.0)),
            ],
        ),
    )


def _villager(uuid_seed: int = 0x55667788):
    return _c(
        id=(TAG.TAG_STRING, "minecraft:villager"),
        UUID=_uuid_int_array(uuid_seed),
        Pos=_list(TAG.TAG_DOUBLE, [(TAG.TAG_DOUBLE, 4.5), (TAG.TAG_DOUBLE, 64.0), (TAG.TAG_DOUBLE, 4.5)]),
        Health=(TAG.TAG_FLOAT, 20.0),
        VillagerData=_c(
            profession=(TAG.TAG_STRING, "minecraft:farmer"),
            level=(TAG.TAG_INT, 2),
            type=(TAG.TAG_STRING, "minecraft:plains"),
        ),
        Offers=_c(Recipes=_list(TAG.TAG_COMPOUND, [_trade(12, "minecraft:bread"), _trade(4, "minecraft:wheat")])),
    )


def _chunk(entities, *, data_version: int = 3465, split: bool = False) -> bytes:
    if split:
        root = _c(DataVersion=(TAG.TAG_INT, data_version), Entities=_list(TAG.TAG_COMPOUND, entities))
    else:
        root = _c(
            DataVersion=(TAG.TAG_INT, data_version),
            Level=_c(Entities=_list(TAG.TAG_COMPOUND, entities)),
        )
    return zlib.compress(TAG.write_nbt_typed("", root))


def _world(tmp: str, *, data_version: int = 3465, chunk: bytes | None = None):
    root = Path(tmp)
    world = root / "world"
    (world / "region").mkdir(parents=True)
    from tests.creator_fixtures import build_level_dat

    (world / "level.dat").write_bytes(build_level_dat(data_version=data_version))
    make_region(world / "region" / "r.0.0.mca", {(0, 0): chunk or _chunk([_zombie(), _villager()])})
    return world


class MobScanTest(unittest.TestCase):
    def test_scan_lists_mobs_with_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = _world(tmp)
            report = creator_mobs.scan_mobs(world / "region", version="1.20.1")
            ids = sorted(item["id"] for item in report["mobs"])
            self.assertEqual(ids, ["minecraft:villager", "minecraft:zombie"])
            zombie = next(item for item in report["mobs"] if item["id"] == "minecraft:zombie")
            self.assertEqual(zombie["health"], 20.0)
            self.assertEqual(zombie["max_health"], 20.0)
            self.assertEqual(zombie["attack_damage"], 3.0)
            self.assertTrue(zombie["uuid"])
            villager = next(item for item in report["mobs"] if item["id"] == "minecraft:villager")
            self.assertEqual(villager["level"], 2)
            self.assertEqual(len(villager["trades"]), 2)
            self.assertEqual(villager["trades"][0]["buy"]["count"], 12)

    def test_scan_skips_non_mob_entities(self):
        with tempfile.TemporaryDirectory() as tmp:
            item_entity = _c(
                id=(TAG.TAG_STRING, "minecraft:item"),
                UUID=_uuid_int_array(9),
                Item=_item("minecraft:stone"),
            )
            world = _world(tmp, chunk=_chunk([item_entity]))
            report = creator_mobs.scan_mobs(world / "region", version="1.20.1")
            self.assertEqual(report["mobs"], [])

    def test_query_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = _world(tmp)
            report = creator_mobs.scan_mobs(world / "region", version="1.20.1", query="vill")
            self.assertEqual([item["id"] for item in report["mobs"]], ["minecraft:villager"])


class MobEditTest(unittest.TestCase):
    def test_edit_health_attack_and_trade_price(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = _world(tmp)
            report = creator_mobs.scan_mobs(world / "region", version="1.20.1")
            zombie = next(item for item in report["mobs"] if item["id"] == "minecraft:zombie")
            villager = next(item for item in report["mobs"] if item["id"] == "minecraft:villager")
            edits = [
                {
                    "uuid": zombie["uuid"],
                    "file": zombie["file"],
                    "changes": {"health": 40, "max_health": 40, "attack_damage": 12},
                },
                {
                    "uuid": villager["uuid"],
                    "file": villager["file"],
                    "changes": {"trade_ratio": 0.5, "trades": [{"index": 1, "max_uses": 30}]},
                },
            ]
            dry = creator_mobs.apply_edits(world / "region", edits, version="1.20.1", dry_run=True)
            self.assertEqual(dry["mobs"], 2)
            self.assertEqual(dry["archives"], {})
            stats = creator_mobs.apply_edits(world / "region", edits, version="1.20.1")
            self.assertEqual(stats["mobs"], 2)
            for text, archive in stats["archives"].items():
                (world / "region" / Path(text).name).write_bytes(build_region_bytes(archive))

            again = creator_mobs.scan_mobs(world / "region", version="1.20.1")
            zombie2 = next(item for item in again["mobs"] if item["id"] == "minecraft:zombie")
            self.assertEqual(zombie2["health"], 40.0)
            self.assertEqual(zombie2["max_health"], 40.0)
            self.assertEqual(zombie2["attack_damage"], 12.0)
            villager2 = next(item for item in again["mobs"] if item["id"] == "minecraft:villager")
            # 12 → 6，4 → 2；第二条的 maxUses 改成 30
            self.assertEqual(villager2["trades"][0]["buy"]["count"], 6)
            self.assertEqual(villager2["trades"][1]["buy"]["count"], 2)
            self.assertEqual(villager2["trades"][1]["max_uses"], 30)

    def test_apply_without_changes_reports_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = _world(tmp)
            stats = creator_mobs.apply_edits(world / "region", [], version="1.20.1")
            self.assertEqual(stats["mobs"], 0)

    def test_legacy_attribute_names_are_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = _world(tmp, data_version=1343)
            report = creator_mobs.scan_mobs(world / "region", version="1.12.2")
            zombie = next(item for item in report["mobs"] if item["id"] == "minecraft:zombie")
            self.assertEqual(zombie["max_health"], 20.0)
            stats = creator_mobs.apply_edits(
                world / "region",
                [{"uuid": zombie["uuid"], "file": zombie["file"], "changes": {"max_health": 60}}],
                version="1.12.2",
            )
            for text, archive in stats["archives"].items():
                Path(text).write_bytes(build_region_bytes(archive))
            archive = read_region(world / "region" / "r.0.0.mca")
            _name, root = TAG.parse_nbt_typed(
                _decompress(archive.slots[0].compression, archive.slots[0].payload)
            )
            entities = root[1]["Level"][1]["Entities"][1][1]
            fields = entities[0][1]
            self.assertIn("Attributes", fields)
            attrs = {
                game_data.canonical_attribute(str(item[1]["Name"][1])): item[1]["Base"][1]
                for item in fields["Attributes"][1][1]
            }
            self.assertEqual(attrs["max_health"], 60.0)
            self.assertEqual(attrs["attack_damage"], 3.0)

    def test_121_uses_lowercase_attributes(self):
        with tempfile.TemporaryDirectory() as tmp:
            chunk = _chunk(
                [
                    _c(
                        id=(TAG.TAG_STRING, "minecraft:zombie"),
                        UUID=_uuid_int_array(0x2222),
                        Pos=_list(TAG.TAG_DOUBLE, [(TAG.TAG_DOUBLE, 0.0)] * 3),
                        Health=(TAG.TAG_FLOAT, 20.0),
                        attributes=_list(
                            TAG.TAG_COMPOUND,
                            [
                                _c(
                                    id=(TAG.TAG_STRING, "minecraft:max_health"),
                                    base=(TAG.TAG_DOUBLE, 20.0),
                                )
                            ],
                        ),
                    )
                ],
                data_version=3953,
                split=True,
            )
            world = _world(tmp, data_version=3953, chunk=chunk)
            report = creator_mobs.scan_mobs(world / "region", version="1.21")
            mob = report["mobs"][0]
            self.assertEqual(mob["max_health"], 20.0)
            stats = creator_mobs.apply_edits(
                world / "region",
                [{"uuid": mob["uuid"], "file": mob["file"], "changes": {"max_health": 80}}],
                version="1.21",
            )
            archive = stats["archives"][mob["file"]]
            _name, root = TAG.parse_nbt_typed(
                _decompress(archive.slots[0].compression, archive.slots[0].payload)
            )
            fields = root[1]["Entities"][1][1][0][1]
            self.assertIn("attributes", fields)
            entry = fields["attributes"][1][1][0][1]
            self.assertEqual(entry["id"][1], "minecraft:max_health")
            self.assertEqual(entry["base"][1], 80.0)


if __name__ == "__main__":
    unittest.main()


class ServiceMobTest(unittest.TestCase):
    """服务层：预览只读、应用前强制备份、写入后能读回。"""

    def _prepared(self, tmp: str):
        from mc_launcher.creator_service import CreatorService
        from tests.creator_fixtures import make_world

        world = make_world(Path(tmp), data_version=3465, version_name="1.20.1")
        (world / "region").mkdir()
        # 1.17+ 实体单独存 entities/ 目录（根级 Entities）
        make_region(
            world / "entities" / "r.0.0.mca",
            {(0, 0): _chunk([_zombie(), _villager()], split=True)},
        )
        service = CreatorService(Path(tmp), Path(tmp) / "backups")
        return service, world

    def test_preview_then_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            service, world = self._prepared(tmp)
            report = service.scan_mobs(world, "overworld", "", 8)
            self.assertGreaterEqual(len(report["mobs"]), 2)
            zombie = next(item for item in report["mobs"] if item["id"] == "minecraft:zombie")
            preview = service.preview_mob_edits(
                {
                    "world": str(world),
                    "dimension": "overworld",
                    "edits": [
                        {
                            "uuid": zombie["uuid"],
                            "file": zombie["file"],
                            "changes": {"health": 100, "max_health": 100},
                        }
                    ],
                }
            )
            self.assertEqual(preview["mobs"], 1)
            self.assertTrue(preview["token"])
            # 预览阶段不落盘
            self.assertEqual(
                next(item for item in service.scan_mobs(world, "overworld", "", 8, True)["mobs"]
                     if item["id"] == "minecraft:zombie")["health"],
                20.0,
            )
            result = service.apply_mob_edits(preview["token"])
            self.assertEqual(result["mobs"], 1)
            self.assertTrue(Path(result["backup"]).is_file())
            fresh = service.scan_mobs(world, "overworld", "", 8, True)
            zombie2 = next(item for item in fresh["mobs"] if item["id"] == "minecraft:zombie")
            self.assertEqual(zombie2["health"], 100.0)
            self.assertEqual(zombie2["max_health"], 100.0)

    def test_preview_rejects_empty_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            service, world = self._prepared(tmp)
            from mc_launcher.creator_service import CreatorError

            with self.assertRaises(CreatorError):
                service.preview_mob_edits({"world": str(world), "edits": []})
