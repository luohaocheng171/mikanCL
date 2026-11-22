"""creator_service：三端共用的创世神面板业务门面。"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import tempfile
import types
import unittest
from pathlib import Path

from mc_launcher import launcher, nbt
from mc_launcher.creator_region import read_region
from mc_launcher.creator_service import CreatorService, PreviewExpired, saves_dirs
from tests.creator_fixtures import build_level_dat, make_region, make_world, write_ops
from tests.test_creator_region import _modern_chunk

import uuid as uuidlib


def _write_level(world: Path, **kwargs) -> None:
    (world / "level.dat").write_bytes(build_level_dat(**kwargs))


class _Config:
    """最小配置桩：只实现 saves_dirs 需要的字段。"""

    def __init__(self, root: Path, mode: str = "all", version: str = "1.20.1"):
        self.game_path = str(root)
        self.isolation_mode = mode
        self._version = version

    def selected_instance(self):
        return types.SimpleNamespace(version_id=self._version)

    def isolation_for(self, version_id: str) -> str:
        return self.isolation_mode

    def resolve_game_dirs(self, version_id: str):
        return launcher.resolve_game_dirs(Path(self.game_path), version_id, self.isolation_mode)


class SavesDirsTest(unittest.TestCase):
    def test_isolated_saves_come_first_when_isolation_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "saves").mkdir()
            isolated = root / "versions" / "1.20.1" / "game" / "saves"
            isolated.mkdir(parents=True)
            dirs = saves_dirs(_Config(root, "all", "1.20.1"))
            self.assertEqual(dirs[0][0], isolated)
            self.assertIn("游戏实际使用", dirs[0][1])
            self.assertEqual(dirs[-1][0], root / "saves")

    def test_shared_saves_come_first_without_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shared = root / "saves"
            shared.mkdir()
            (root / "versions" / "1.8.9" / "game" / "saves").mkdir(parents=True)
            dirs = saves_dirs(_Config(root, "none", "1.8.9"))
            self.assertEqual(dirs[0][0], shared)

    def test_unknown_version_scans_all_isolated_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "saves").mkdir()
            for version in ("1.8.9", "1.20.1"):
                (root / "versions" / version / "game" / "saves").mkdir(parents=True)
            dirs = saves_dirs(_Config(root, "all", ""))
            self.assertEqual(
                {path for path, _ in dirs},
                {
                    root / "versions" / "1.8.9" / "game" / "saves",
                    root / "versions" / "1.20.1" / "game" / "saves",
                    root / "saves",
                },
            )
            self.assertEqual(dirs[-1][0], root / "saves")


class ServiceOpenTest(unittest.TestCase):
    def test_open_reports_era_and_player_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = make_world(Path(tmp), data_version=3465, version_name="1.20.1")
            service = CreatorService(Path(tmp), Path(tmp) / "backups")
            state = service.open(world)
            self.assertEqual(state["era"], "flattened")
            self.assertTrue(state["editable"])
            self.assertEqual(state["player"]["health"], 20.0)
            self.assertEqual(state["player"]["dimension"], "minecraft:overworld")
            # 三端共用：效果/附魔预设带中文译名，1.20.1 的效果 ID 仍是数字
            effect = state["profile"]["effect_presets"][0]
            self.assertEqual(effect["label"], "速度")
            self.assertEqual(effect["id"], 1)
            self.assertTrue(state["profile"]["enchant_presets"])
            self.assertIn(
                "doTraderSpawning",
                {item["name"] for item in state["profile"]["gamerule_presets"]},
            )
            self.assertEqual(state["profile"]["data_version"], 3465)

    def test_ancient_world_is_editable(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = make_world(Path(tmp))
            _write_level(world, data_version=0, version_name="rd-132211")
            service = CreatorService(Path(tmp), Path(tmp) / "backups")
            state = service.open(world)
            # Indev / Alpha / Beta 的 level.dat 仍是 NBT，可以直接改数值与玩家数据
            self.assertTrue(state["editable"])
            self.assertEqual(state["era"], "ancient")
            self.assertTrue(state["scalars"])

    def test_playerdata_files_are_listed(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = make_world(Path(tmp))
            player = world / "playerdata" / "11111111-2222-3333-4444-555555555555.dat"
            player.write_bytes(build_level_dat()[:0] or (world / "level.dat").read_bytes())
            service = CreatorService(Path(tmp), Path(tmp) / "backups")
            state = service.open(world)
            uuids = [entry["uuid"] for entry in state["players"]]
            self.assertIn("11111111-2222-3333-4444-555555555555", uuids)
            # 1.13+ 游戏只读 playerdata，不再把 level.dat 的 Player 当作可编辑玩家
            self.assertNotIn("level", uuids)
            self.assertEqual(state["player_storage"], "playerdata")
            self.assertEqual(state["player_uuid"], "11111111-2222-3333-4444-555555555555")


class CurrentAccountTest(unittest.TestCase):
    def test_open_prefers_current_account_uuid(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = make_world(Path(tmp))
            first = "11111111-2222-3333-4444-555555555555"
            second = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
            for name in (first, second):
                (world / "playerdata" / f"{name}.dat").write_bytes(
                    (world / "level.dat").read_bytes()
                )
            service = CreatorService(Path(tmp), Path(tmp) / "backups")
            state = service.open(world, preferred_uuid=second.upper())
            self.assertEqual(state["player_uuid"], second)
            entry = next(item for item in state["players"] if item["uuid"] == second)
            self.assertTrue(entry["current"])
            self.assertIn("当前账号", entry["name"])

    def test_apply_writes_gzip_playerdata(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = make_world(Path(tmp))
            uuid_text = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
            player = world / "playerdata" / f"{uuid_text}.dat"
            player.write_bytes((world / "level.dat").read_bytes())
            service = CreatorService(Path(tmp), Path(tmp) / "backups")
            preview = service.preview(
                {
                    "world": str(world),
                    "player_uuid": uuid_text,
                    "player": {
                        "inventory": [{"slot": 0, "id": "minecraft:diamond", "count": 3}],
                    },
                }
            )
            result = service.apply(preview["token"])
            self.assertTrue(result["verified"], result["mismatches"])
            # 游戏只认 gzip NBT，未压缩会被判定为损坏
            self.assertEqual(player.read_bytes()[:2], b"\x1f\x8b")
            self.assertEqual((world / "level.dat").read_bytes()[:2], b"\x1f\x8b")
            _name, root = nbt.load_nbt_typed_file(player)
            items = root[1]["Inventory"][1][1]
            self.assertEqual(items[0][1]["id"], (nbt.TAG_STRING, "minecraft:diamond"))
            self.assertEqual(items[0][1]["Slot"][0], nbt.TAG_BYTE)


class PreviewApplyTest(unittest.TestCase):
    def _service(self, tmp: Path):
        world = make_world(tmp)
        return world, CreatorService(tmp, tmp / "backups")

    def test_preview_warns_above_vanilla_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            world, service = self._service(Path(tmp))
            preview = service.preview(
                {"world": str(world), "player": {"health": 4096.0}}
            )
            self.assertTrue(preview["token"])
            codes = [w["code"] for w in preview["warnings"]]
            self.assertIn("over_vanilla_cap", codes)

    def test_apply_writes_float_and_creates_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            world, service = self._service(Path(tmp))
            preview = service.preview(
                {"world": str(world), "player": {"health": 1024.0, "xp_level": 21863}}
            )
            result = service.apply(preview["token"])
            self.assertTrue(Path(result["backup"]).is_file())
            _name, root = nbt.load_nbt_typed_file(world / "level.dat")
            player = root[1]["Data"][1]["Player"][1]
            self.assertEqual(player["Health"], (nbt.TAG_FLOAT, 1024.0))
            self.assertEqual(player["XpLevel"], (nbt.TAG_INT, 21863))

    def test_preview_expires_when_source_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            world, service = self._service(Path(tmp))
            preview = service.preview({"world": str(world), "player": {"health": 30.0}})
            (world / "level.dat").write_bytes(build_level_dat(data_version=3465, version_name="1.20.2"))
            with self.assertRaises(PreviewExpired):
                service.apply(preview["token"])

    def test_apply_rejects_unknown_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            _world, service = self._service(Path(tmp))
            with self.assertRaises(PreviewExpired):
                service.apply("not-a-token")

    def test_invalid_type_is_rejected_before_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            world, service = self._service(Path(tmp))
            with self.assertRaises(ValueError):
                service.preview({"world": str(world), "player": {"xp_level": 2**31}})

    def test_world_fields_are_written_with_correct_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            world, service = self._service(Path(tmp))
            preview = service.preview(
                {
                    "world": str(world),
                    "level": {
                        "time": 999999,
                        "day_time": 999999,
                        "weather": "thunder",
                        "gamerules": {"randomTickSpeed": "1000"},
                        "border_size": 59999968.0,
                    },
                }
            )
            service.apply(preview["token"])
            _name, root = nbt.load_nbt_typed_file(world / "level.dat")
            data = root[1]["Data"][1]
            self.assertEqual(data["Time"], (nbt.TAG_LONG, 999999))
            self.assertEqual(data["thundering"], (nbt.TAG_BYTE, 1))
            self.assertEqual(data["GameRules"][1]["randomTickSpeed"], (nbt.TAG_STRING, "1000"))
            self.assertEqual(data["WorldBorder"][1]["Size"], (nbt.TAG_DOUBLE, 59999968.0))


class InventoryRoundTripTest(unittest.TestCase):
    """编辑背包不能丢物品自带的 NBT（名字、lore、容器内容等）。"""

    UUID = "11111111-2222-3333-4444-555555555555"

    def _service(self, tmp: Path, *, data_version: int = 3465, version_name: str = "1.20.1"):
        world = make_world(tmp, data_version=data_version, version_name=version_name)
        return world, CreatorService(tmp, tmp / "backups")

    def _write_player(self, world: Path, item) -> Path:
        root = (
            nbt.TAG_COMPOUND,
            {
                "Health": (nbt.TAG_FLOAT, 20.0),
                "XpLevel": (nbt.TAG_INT, 0),
                "Inventory": (nbt.TAG_LIST, (nbt.TAG_COMPOUND, [item])),
            },
        )
        path = world / "playerdata" / f"{self.UUID}.dat"
        path.write_bytes(__import__("gzip").compress(nbt.write_nbt_typed("", root)))
        return path

    def test_read_reports_raw_tag_and_apply_keeps_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            world, service = self._service(Path(tmp))
            item = (
                nbt.TAG_COMPOUND,
                {
                    "id": (nbt.TAG_STRING, "minecraft:diamond_sword"),
                    "Slot": (nbt.TAG_BYTE, 0),
                    "Count": (nbt.TAG_BYTE, 1),
                    "tag": (
                        nbt.TAG_COMPOUND,
                        {
                            "display": (
                                nbt.TAG_COMPOUND,
                                {"Name": (nbt.TAG_STRING, '{"text":"Excalibur"}')},
                            ),
                            "Enchantments": (
                                nbt.TAG_LIST,
                                (
                                    nbt.TAG_COMPOUND,
                                    [
                                        (
                                            nbt.TAG_COMPOUND,
                                            {
                                                "id": (nbt.TAG_STRING, "minecraft:sharpness"),
                                                "lvl": (nbt.TAG_SHORT, 5),
                                            },
                                        )
                                    ],
                                ),
                            ),
                        },
                    ),
                },
            )
            path = self._write_player(world, item)
            player = service.read_player(world, self.UUID)
            entry = player["inventory"][0]
            self.assertEqual(entry["enchantments"], [{"id": "minecraft:sharpness", "level": 5}])
            self.assertIsNotNone(entry["tag_json"])
            preview = service.preview(
                {"world": str(world), "player_uuid": self.UUID, "player": {"inventory": [entry]}}
            )
            service.apply(preview["token"])
            _name, reread = nbt.load_nbt_typed_file(path)
            tag = reread[1]["Inventory"][1][1][0][1]["tag"][1]
            self.assertEqual(tag["display"][1]["Name"], (nbt.TAG_STRING, '{"text":"Excalibur"}'))

    def test_enchantment_field_overrides_raw_tag(self):
        with tempfile.TemporaryDirectory() as tmp:
            world, service = self._service(Path(tmp))
            item = (
                nbt.TAG_COMPOUND,
                {
                    "id": (nbt.TAG_STRING, "minecraft:diamond_sword"),
                    "Slot": (nbt.TAG_BYTE, 0),
                    "Count": (nbt.TAG_BYTE, 1),
                    "tag": (
                        nbt.TAG_COMPOUND,
                        {
                            "Enchantments": (
                                nbt.TAG_LIST,
                                (
                                    nbt.TAG_COMPOUND,
                                    [
                                        (
                                            nbt.TAG_COMPOUND,
                                            {
                                                "id": (nbt.TAG_STRING, "minecraft:sharpness"),
                                                "lvl": (nbt.TAG_SHORT, 5),
                                            },
                                        )
                                    ],
                                ),
                            )
                        },
                    ),
                },
            )
            path = self._write_player(world, item)
            entry = service.read_player(world, self.UUID)["inventory"][0]
            entry["enchantments"] = [{"id": "minecraft:unbreaking", "level": 3}]
            preview = service.preview(
                {"world": str(world), "player_uuid": self.UUID, "player": {"inventory": [entry]}}
            )
            service.apply(preview["token"])
            _name, reread = nbt.load_nbt_typed_file(path)
            tag = reread[1]["Inventory"][1][1][0][1]["tag"][1]
            names = [item[1]["id"][1] for item in tag["Enchantments"][1][1]]
            self.assertEqual(names, ["minecraft:unbreaking"])

    def test_reads_component_damage(self):
        with tempfile.TemporaryDirectory() as tmp:
            world, service = self._service(Path(tmp), data_version=3953, version_name="1.21")
            item = (
                nbt.TAG_COMPOUND,
                {
                    "id": (nbt.TAG_STRING, "minecraft:diamond_sword"),
                    "Slot": (nbt.TAG_BYTE, 0),
                    "count": (nbt.TAG_INT, 1),
                    "components": (
                        nbt.TAG_COMPOUND,
                        {"minecraft:damage": (nbt.TAG_INT, 7)},
                    ),
                },
            )
            self._write_player(world, item)
            entry = service.read_player(world, self.UUID)["inventory"][0]
            self.assertEqual(entry["damage"], 7)
            self.assertIsNotNone(entry["tag_json"])


    def test_negative_count_and_details_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            world, service = self._service(Path(tmp), data_version=3953, version_name="1.21")
            item = (
                nbt.TAG_COMPOUND,
                {
                    "id": (nbt.TAG_STRING, "minecraft:diamond_sword"),
                    "Slot": (nbt.TAG_BYTE, 0),
                    "count": (nbt.TAG_INT, 1),
                },
            )
            path = self._write_player(world, item)
            entry = service.read_player(world, self.UUID)["inventory"][0]
            entry["count"] = -7
            entry["details"] = {
                "max_damage": 9999,
                "repair_cost": 3,
                "unbreakable": True,
                "rarity": "epic",
                "glint": "off",
                "nutrition": 20,
                "saturation": 9.5,
            }
            preview = service.preview(
                {"world": str(world), "player_uuid": self.UUID, "player": {"inventory": [entry]}}
            )
            service.apply(preview["token"])
            _name, reread = nbt.load_nbt_typed_file(path)
            saved = reread[1]["Inventory"][1][1][0][1]
            self.assertEqual(saved["count"], (nbt.TAG_INT, -7))
            components = saved["components"][1]
            self.assertEqual(components["minecraft:max_damage"], (nbt.TAG_INT, 9999))
            self.assertEqual(components["minecraft:unbreakable"], (nbt.TAG_COMPOUND, {}))
            self.assertEqual(components["minecraft:rarity"], (nbt.TAG_STRING, "epic"))
            self.assertEqual(
                components["minecraft:enchantment_glint_override"], (nbt.TAG_BYTE, 0)
            )
            self.assertEqual(components["minecraft:food"][1]["nutrition"], (nbt.TAG_INT, 20))


class ExtraFieldTest(unittest.TestCase):
    def test_apply_writes_food_ender_items_and_attribute_modifiers(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = make_world(Path(tmp))
            service = CreatorService(Path(tmp), Path(tmp) / "backups")
            preview = service.preview(
                {
                    "world": str(world),
                    "player": {
                        "food_level": 3,
                        "ender_items": [{"slot": 0, "id": "minecraft:diamond", "count": 5}],
                        "attributes": [
                            {
                                "name": "generic.max_health",
                                "base": 20.0,
                                "modifiers": [{"amount": 100.0, "operation": "add_value"}],
                            }
                        ],
                    },
                }
            )
            service.apply(preview["token"])
            _name, root = nbt.load_nbt_typed_file(world / "level.dat")
            player = root[1]["Data"][1]["Player"][1]
            self.assertEqual(player["foodLevel"], (nbt.TAG_INT, 3))
            ender = player["EnderItems"][1][1][0][1]
            self.assertEqual(ender["id"], (nbt.TAG_STRING, "minecraft:diamond"))
            modifier = player["Attributes"][1][1][0][1]["Modifiers"][1][1][0][1]
            self.assertEqual(modifier["Amount"], (nbt.TAG_DOUBLE, 100.0))

    def test_safe_teleport_without_region_keeps_y(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = make_world(Path(tmp))
            service = CreatorService(Path(tmp), Path(tmp) / "backups")
            preview = service.preview(
                {
                    "world": str(world),
                    "player": {"pos": [100.0, 70.0, 100.0], "safe_teleport": True},
                }
            )
            codes = [warning["code"] for warning in preview["warnings"]]
            self.assertIn("safe_teleport_missing_chunk", codes)
            service.apply(preview["token"])
            _name, root = nbt.load_nbt_typed_file(world / "level.dat")
            pos = root[1]["Data"][1]["Player"][1]["Pos"][1][1]
            self.assertEqual(pos[1][1], 70.0)


class AdvancementTest(unittest.TestCase):
    def test_selected_advancements_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = make_world(Path(tmp))
            folder = world / "advancements"
            folder.mkdir()
            path = folder / "level.json"
            path.write_text(
                json.dumps(
                    {
                        "minecraft:story/root": {"done": False, "criteria": {"tick": None}},
                        "minecraft:story/mine_stone": {"done": True, "criteria": {"get_stone": None}},
                    }
                ),
                encoding="utf-8",
            )
            service = CreatorService(Path(tmp), Path(tmp) / "backups")
            result = service.complete_advancements(
                world, "level", ["minecraft:story/root"]
            )
            self.assertEqual(result["count"], 1)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(payload["minecraft:story/root"]["done"])
            self.assertIsNotNone(payload["minecraft:story/root"]["criteria"]["tick"])


class OpsTest(unittest.TestCase):
    def test_read_and_write_ops_keeps_unknown_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = Path(tmp) / "server"
            write_ops(server / "ops.json", [("uuid-1", "Alice", 2, False)])
            payload = json.loads((server / "ops.json").read_text(encoding="utf-8"))
            payload[0]["custom"] = "keep-me"
            (server / "ops.json").write_text(json.dumps(payload), encoding="utf-8")
            service = CreatorService(Path(tmp), Path(tmp) / "backups")
            entries = service.read_ops(server)
            self.assertEqual(entries[0]["level"], 2)
            service.write_ops(server, [{"uuid": "uuid-1", "name": "Alice", "level": 4}])
            payload = json.loads((server / "ops.json").read_text(encoding="utf-8"))
            self.assertEqual(payload[0]["level"], 4)
            self.assertEqual(payload[0]["custom"], "keep-me")
            self.assertIn("bypassesPlayerLimit", payload[0])


class RegionPreviewTest(unittest.TestCase):
    def test_region_dry_run_counts_blocks(self):
        from tests.test_creator_region import _modern_chunk
        from tests.creator_fixtures import make_region

        with tempfile.TemporaryDirectory() as tmp:
            world = make_world(Path(tmp))
            region_dir = world / "region"
            make_region(region_dir / "r.0.0.mca", {(0, 0): _modern_chunk(3465, ["minecraft:stone"])})
            service = CreatorService(Path(tmp), Path(tmp) / "backups")
            report = service.preview_region(
                {"world": str(world), "old_id": "minecraft:stone", "new_id": "minecraft:diamond_block"}
            )
            self.assertEqual(report["files"], 1)
            self.assertEqual(report["replaced"], 4096)
            self.assertTrue(report["token"])


class NewWorldFieldsTest(unittest.TestCase):
    """新版本世界参数（计时器、出生角、流浪商人、锁难度等）按标签类型写入。"""

    def test_new_fields_use_correct_tag_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = make_world(Path(tmp), data_version=3465, version_name="1.20.1")
            service = CreatorService(Path(tmp), Path(tmp) / "backups")
            preview = service.preview(
                {
                    "world": str(world),
                    "level": {
                        "level_name": "Creative World",
                        "rain_time": 500,
                        "thunder_time": 700,
                        "clear_weather_time": 900,
                        "last_played": 1700000000123,
                        "spawn_angle": 90.5,
                        "wander_trader_chance": 25,
                        "wander_trader_delay": 1200,
                        "difficulty_locked": True,
                        "initialized": False,
                        "map_features": False,
                        "gamerules": {
                            "doTraderSpawning": "false",
                            "playersSleepingPercentage": "50",
                            "snowAccumulationHeight": "3",
                        },
                    },
                }
            )
            service.apply(preview["token"])
            _name, root = nbt.load_nbt_typed_file(world / "level.dat")
            data = root[1]["Data"][1]
            self.assertEqual(data["LevelName"], (nbt.TAG_STRING, "Creative World"))
            # LastPlayed 必须是 Long，写成 Int 会被游戏判为异常时间
            self.assertEqual(data["LastPlayed"][0], nbt.TAG_LONG)
            self.assertEqual(data["rainTime"], (nbt.TAG_INT, 500))
            self.assertEqual(data["thunderTime"], (nbt.TAG_INT, 700))
            self.assertEqual(data["clearWeatherTime"], (nbt.TAG_INT, 900))
            self.assertEqual(data["SpawnAngle"], (nbt.TAG_FLOAT, 90.5))
            self.assertEqual(data["WanderingTraderSpawnChance"], (nbt.TAG_INT, 25))
            self.assertEqual(data["DifficultyLocked"], (nbt.TAG_BYTE, 1))
            self.assertEqual(data["initialized"], (nbt.TAG_BYTE, 0))
            self.assertEqual(data["MapFeatures"], (nbt.TAG_BYTE, 0))
            rules = data["GameRules"][1]
            self.assertEqual(rules["doTraderSpawning"], (nbt.TAG_STRING, "false"))
            self.assertEqual(rules["playersSleepingPercentage"], (nbt.TAG_STRING, "50"))
            self.assertEqual(rules["snowAccumulationHeight"], (nbt.TAG_STRING, "3"))


class BuildPreviewTest(unittest.TestCase):
    def _world_with_region(self, tmp: Path, data_version: int = 3465) -> tuple[Path, Path]:
        world = make_world(tmp, data_version=data_version)
        region_dir = world / "region"
        make_region(
            region_dir / "r.0.0.mca",
            {(0, 0): _modern_chunk(data_version, ["minecraft:stone"])},
        )
        return world, region_dir

    def test_preview_and_apply_single_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            world, region_dir = self._world_with_region(Path(tmp))
            service = CreatorService(Path(tmp), Path(tmp) / "backups")
            preview = service.preview_build(
                {
                    "world": str(world),
                    "mode": "block",
                    "block": "minecraft:diamond_block",
                    "x": 2,
                    "y": 3,
                    "z": 4,
                }
            )
            self.assertEqual(preview["blocks"], 1)
            result = service.apply_build(preview["token"])
            self.assertTrue(Path(result["backup"]).is_file())
            archive = read_region(region_dir / "r.0.0.mca")
            payload = __import__("zlib").decompress(archive.slots[0].payload)
            _name, root = nbt.parse_nbt_typed(payload)
            section = root[1]["Level"][1]["Sections"][1][1][0][1]
            names = [
                entry[1]["Name"][1]
                for entry in section["block_states"][1]["palette"][1][1]
            ]
            self.assertIn("minecraft:diamond_block", names)

    def test_fill_preview_counts_volume(self):
        with tempfile.TemporaryDirectory() as tmp:
            world, _region_dir = self._world_with_region(Path(tmp))
            service = CreatorService(Path(tmp), Path(tmp) / "backups")
            preview = service.preview_build(
                {
                    "world": str(world),
                    "mode": "fill",
                    "block": "minecraft:glass",
                    "from": [0, 0, 0],
                    "to": [2, 2, 2],
                }
            )
            self.assertEqual(preview["blocks"], 27)

    def test_fill_rejects_oversized_volume(self):
        with tempfile.TemporaryDirectory() as tmp:
            world, _region_dir = self._world_with_region(Path(tmp))
            service = CreatorService(Path(tmp), Path(tmp) / "backups")
            with self.assertRaises(Exception):
                service.preview_build(
                    {
                        "world": str(world),
                        "mode": "fill",
                        "block": "minecraft:stone",
                        "from": [0, 0, 0],
                        "to": [100, 100, 100],
                    }
                )

    def test_missing_chunk_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            world, _region_dir = self._world_with_region(Path(tmp))
            service = CreatorService(Path(tmp), Path(tmp) / "backups")
            with self.assertRaises(Exception):
                service.preview_build(
                    {
                        "world": str(world),
                        "mode": "block",
                        "block": "minecraft:stone",
                        "x": 400,
                        "y": 5,
                        "z": 0,
                    }
                )

    def test_apply_build_expires_after_region_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            world, region_dir = self._world_with_region(Path(tmp))
            service = CreatorService(Path(tmp), Path(tmp) / "backups")
            preview = service.preview_build(
                {
                    "world": str(world),
                    "mode": "block",
                    "block": "minecraft:stone",
                    "x": 1,
                    "y": 1,
                    "z": 1,
                }
            )
            path = region_dir / "r.0.0.mca"
            path.write_bytes(path.read_bytes() + b"\x00" * 4096)
            with self.assertRaises(PreviewExpired):
                service.apply_build(preview["token"])

    def test_entity_spawn_writes_split_entities_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            world, _region_dir = self._world_with_region(Path(tmp), data_version=3953)
            service = CreatorService(Path(tmp), Path(tmp) / "backups")
            preview = service.preview_build(
                {
                    "world": str(world),
                    "mode": "entity",
                    "entity": "minecraft:cow",
                    "x": 4,
                    "y": 70,
                    "z": 4,
                    "count": 3,
                    "spread": 2.0,
                }
            )
            self.assertEqual(preview["entities"], 3)
            result = service.apply_build(preview["token"])
            self.assertEqual(result["entities"], 3)
            entity_file = world / "entities" / "r.0.0.mca"
            self.assertTrue(entity_file.is_file())
            archive = read_region(entity_file)
            payload = __import__("zlib").decompress(archive.slots[0].payload)
            _name, chunk = nbt.parse_nbt_typed(payload)
            self.assertEqual(len(chunk[1]["Entities"][1][1]), 3)

    def test_kill_entities_in_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            world, _region_dir = self._world_with_region(Path(tmp), data_version=3953)
            service = CreatorService(Path(tmp), Path(tmp) / "backups")
            spawn = service.preview_build(
                {
                    "world": str(world),
                    "mode": "entity",
                    "entity": "minecraft:cow",
                    "x": 4,
                    "y": 70,
                    "z": 4,
                    "count": 2,
                    "spread": 1.0,
                }
            )
            service.apply_build(spawn["token"])
            kill = service.preview_build(
                {
                    "world": str(world),
                    "mode": "kill",
                    "from": [0, 60, 0],
                    "to": [10, 80, 10],
                    "entity": "minecraft:cow",
                }
            )
            self.assertEqual(kill["removed"], 2)
            result = service.apply_build(kill["token"])
            self.assertEqual(result["removed"], 2)
            archive = read_region(world / "entities" / "r.0.0.mca")
            payload = __import__("zlib").decompress(archive.slots[0].payload)
            _name, chunk = nbt.parse_nbt_typed(payload)
            self.assertEqual(len(chunk[1]["Entities"][1][1]), 0)

    def test_entity_requires_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            world, _region_dir = self._world_with_region(Path(tmp))
            service = CreatorService(Path(tmp), Path(tmp) / "backups")
            with self.assertRaises(Exception):
                service.preview_build(
                    {"world": str(world), "mode": "entity", "x": 0, "y": 64, "z": 0}
                )


if __name__ == "__main__":
    unittest.main()
