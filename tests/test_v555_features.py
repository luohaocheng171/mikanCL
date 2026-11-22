"""v5.5.5 回归测试：Candidate 序列化、半径输入、备份 0、加载器分类、
蓝图导入器、反熊系统、服务器核心转换器。
"""
from __future__ import annotations

import gzip
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
import sys  # noqa: E402

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mc_launcher import (  # noqa: E402
    anticheat, backup_manager, config, java, modloader, seed_world, server_migrate,
    structure_import,
)
from mc_launcher.nbt import write_nbt_typed  # noqa: E402

JS = (ROOT / "mc_launcher" / "ui_web" / "web" / "app.js").read_text(encoding="utf-8")


class CandidateSerializableTest(unittest.TestCase):
    def test_seed_asset_returns_plain_strings(self):
        """server_asset 的 url / alternatives 必须是纯字符串，能被 json.dumps。"""
        from mc_launcher.net import Candidate

        sources = SimpleNamespace(resource_candidates=lambda url: [
            Candidate("https://mirror.example/jar", source_name="镜像"),
            Candidate("https://official.example/jar", source_name="官方"),
        ])
        # 直接构造一个本地版本 JSON，避免走网络
        with tempfile.TemporaryDirectory() as tmp:
            vdir = Path(tmp) / "versions" / "1.20.1"
            vdir.mkdir(parents=True)
            (vdir / "1.20.1.json").write_text(
                '{"downloads":{"server":{"url":"https://official.example/server.jar"}}}',
                encoding="utf-8",
            )
            res = seed_world.server_asset("1.20.1", tmp, sources, remote=False)
        self.assertTrue(res["ok"])
        self.assertIsInstance(res["url"], str)
        for alt in res.get("alternatives", []):
            self.assertIsInstance(alt, str)
        import json
        json.dumps(res)

    def test_candidate_urls_helper(self):
        from mc_launcher.net import Candidate

        urls = seed_world._candidate_urls(
            [Candidate("https://a"), "https://b", {"url": "https://c"}, "https://a"],
            "https://fallback",
        )
        self.assertEqual(urls, ["https://a", "https://b", "https://c"])


class ConfigAndBackupTest(unittest.TestCase):
    def test_max_backups_zero_survives_roundtrip(self):
        import json

        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.json"
            cfg_path.write_text(json.dumps({"max_backups": 0}), encoding="utf-8")
            with patch.object(config, "CONFIG_PATH", cfg_path):
                cfg = config.Config.load()
            self.assertEqual(cfg.max_backups, 0)
        self.assertEqual(config.Config().max_backups, 20)

    def test_effective_limit_zero(self):
        cfg = SimpleNamespace(max_backups=0, world_backup_limits={})
        self.assertEqual(backup_manager.effective_limit(cfg, "world"), 0)


class LoaderGroupedTest(unittest.TestCase):
    def test_grouping_release_beta_legacy(self):
        with patch.object(modloader, "list_loader_versions", return_value=[
            "47.2.0", "48.0.1-beta", "31.2.0",
        ]):
            groups = modloader.list_loader_versions_grouped("forge", "1.20.1")
        self.assertEqual(groups["release"], ["47.2.0", "31.2.0"])
        self.assertEqual(groups["beta"], ["48.0.1-beta"])
        self.assertEqual(groups["legacy"], [])  # 1.20.1 不算远古

    def test_ancient_mc_goes_legacy(self):
        with patch.object(modloader, "list_loader_versions", return_value=["14.23.5.2859"]):
            groups = modloader.list_loader_versions_grouped("forge", "1.12.2")
        self.assertEqual(groups["legacy"], ["14.23.5.2859"])


class StructureImportTest(unittest.TestCase):
    def _make_structure(self, path: Path):
        # 最小 Mojang structure：size 2×1×1，palette 一个 stone
        from mc_launcher.nbt import TAG_COMPOUND, TAG_INT, TAG_LIST, TAG_STRING

        def int_list(values):
            return (TAG_LIST, (TAG_INT, [(TAG_INT, v) for v in values]))

        palette_entry = (TAG_COMPOUND, {"Name": (TAG_STRING, "minecraft:stone")})
        block_entry = (TAG_COMPOUND, {
            "nx": (TAG_INT, 0), "ny": (TAG_INT, 0), "nz": (TAG_INT, 0), "state": (TAG_INT, 0),
        })
        fields = {
            "size": int_list([2, 1, 1]),
            "palette": (TAG_LIST, (TAG_COMPOUND, [palette_entry])),
            "blocks": (TAG_LIST, (TAG_COMPOUND, [block_entry])),
            "entities": (TAG_LIST, (TAG_COMPOUND, [])),
        }
        path.write_bytes(gzip.compress(write_nbt_typed("", (TAG_COMPOUND, fields))))

    def test_preview_parses_nbt(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test.nbt"
            self._make_structure(p)
            res = structure_import.preview(str(p), 10, 64, 20)
            self.assertTrue(res["ok"])
            self.assertEqual(res["size"], [2, 1, 1])
            self.assertEqual(res["count"], 1)
            self.assertIn("minecraft:stone", res["top_blocks"][0][0])

    def test_era_detection(self):
        self.assertEqual(structure_import._era_for("1.12.2"), "legacy")
        self.assertEqual(structure_import._era_for("1.20.1"), "flattened")
        self.assertEqual(structure_import._era_for("1.21.4"), "components")


class AnticheatTest(unittest.TestCase):
    def test_command_frequency(self):
        lines = [f"<Steve> issued server command: /give @a diamond 64" for _ in range(35)]
        res = anticheat.scan_command_frequency(lines, threshold=30)
        self.assertEqual(len(res["findings"]), 1)
        self.assertEqual(res["findings"][0]["command"], "/give")

    def test_no_false_positive(self):
        lines = ["<Steve> issued server command: /tp @a 0 64 0"]
        res = anticheat.scan_command_frequency(lines, threshold=30)
        self.assertEqual(res["findings"], [])


class ServerMigrateTest(unittest.TestCase):
    def _make_level(self, world: Path, with_bukkit: bool):
        world.mkdir(parents=True, exist_ok=True)
        data_fields = {"LevelName": (8, "Test"), "GameRules": (10, {})}
        if with_bukkit:
            data_fields["Bukkit"] = (10, {"AllowFlight": (1, 1)})
        fields = {"Data": (10, data_fields)}
        (world / "level.dat").write_bytes(gzip.compress(write_nbt_typed("", (10, fields))))

    def test_preview_finds_bukkit(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = Path(tmp) / "world"
            self._make_level(world, True)
            res = server_migrate.preview(world)
            self.assertTrue(res["ok"])
            self.assertEqual(res["total"], 1)
            self.assertIn("Bukkit", res["changes"][0]["keys"])

    def test_convert_strips_and_preserves_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = Path(tmp) / "world"
            self._make_level(world, True)
            res = server_migrate.convert(world, backup=False)
            self.assertTrue(res["ok"])
            self.assertEqual(res["converted"], 1)
            from mc_launcher.nbt import load_nbt_typed_file

            _name, typed = load_nbt_typed_file(world / "level.dat")
            data = typed[1]["Data"][1]
            self.assertNotIn("Bukkit", data)
            self.assertIn("LevelName", data)
            self.assertEqual(data["LevelName"][0], 8)  # 类型保留为 String

    def test_deployment_plan(self):
        self.assertIn("Fabric", server_migrate.deployment_plan("fabric")["core"])


class FrontendTest(unittest.TestCase):
    def test_radius_number_input(self):
        self.assertIn('id="seedRadius" type="number"', JS)

    def test_loader_groups(self):
        self.assertIn("正式版（稳定）", JS)
        self.assertIn("测试版（快照 / RC）", JS)
        self.assertIn("远古版（旧 MC 分支）", JS)

    def test_backup_zero_hint(self):
        self.assertIn("0=不删除", JS)

    def test_no_manifest_truncation(self):
        self.assertNotIn("rows.slice(0, 140)", JS)

    def test_new_feature_cards(self):
        for title in ("蓝图 / 建筑生成器", "反熊防御系统", "服务器核心转换器"):
            self.assertIn(title, JS)


if __name__ == "__main__":
    unittest.main()
