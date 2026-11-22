"""v5.5.4 收口批次的回归测试。

覆盖：Java 6/7 识别、老版本启动不再假成功、Omniarchive 并入版本清单与切源、
种子世界用游戏本体生成、创世神扫描全部存档 / 全量物品 / 全量图标 / 去候选。
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
import sys  # noqa: E402

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mc_launcher import item_icons, java, launcher, omniarchive, seed_world  # noqa: E402
from mc_launcher.config import Config  # noqa: E402
from mc_launcher.ui_web.shell import WebApi  # noqa: E402

JS = (ROOT / "mc_launcher" / "ui_web" / "web" / "app.js").read_text(encoding="utf-8")


class JavaDetectTest(unittest.TestCase):
    def _probe(self, version_text: str, tmp: str):
        exe = Path(tmp) / "java.exe"
        exe.write_bytes(b"")
        fake = SimpleNamespace(stdout="", stderr=version_text, returncode=0)
        with patch.object(java, "_run", return_value=fake):
            return java.probe_java(str(exe))

    def test_java_6_and_7_not_reported_as_8(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self._probe('java version "1.6.0_45"\n64-Bit', tmp).major, 6)
            self.assertEqual(self._probe('java version "1.7.0_80"\n64-Bit', tmp).major, 7)
            self.assertEqual(self._probe('java version "1.8.0_312"\n64-Bit', tmp).major, 8)

    def test_modern_java_major(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self._probe('openjdk version "21.0.2"\n64-Bit', tmp).major, 21)
            self.assertEqual(self._probe('openjdk version "17.0.9"\n64-Bit', tmp).major, 17)


class AncientJavaChoiceTest(unittest.TestCase):
    def test_ancient_versions_prefer_java_7(self):
        from mc_launcher.version import infer_java_major

        for vid in ("b1.7.3", "a1.2.6", "inf-20100618", "c0.30"):
            self.assertEqual(infer_java_major(vid), 7)
        self.assertEqual(infer_java_major("1.20.1"), 17)


class CrashHintTest(unittest.TestCase):
    def test_lwjgl_and_ancient_java_hints(self):
        text = launcher.crash_hint(1, 'Exception in thread "main" java.lang.UnsatisfiedLinkError: no lwjgl in java.library.path')
        self.assertIn("LWJGL", text)
        self.assertIn("Java 6/7", text)
        text2 = launcher.crash_hint(1, "java.lang.UnsupportedClassVersionError: bad class file version")
        self.assertIn("Java 6/7", text2)


class ManifestSourceTest(unittest.TestCase):
    def _fake_stage(self, stage, *, force=False, timeout=30):
        rows = {
            "beta": [{"id": "b1.7.3", "url": "http://example/b173.jar", "file": "b1.7.3.jar", "size": 1}],
            "alpha": [{"id": "a1.2.6", "url": "http://example/a126.jar", "file": "a1.2.6.jar", "size": 1}],
            "infdev": [{"id": "inf-20100618", "url": "http://example/inf.jar", "file": "inf.jar", "size": 1}],
        }
        key = str(stage).lower()
        return {"stage": key, "label": key, "source": "", "total": len(rows.get(key, [])),
                "items": rows.get(key, [])}

    def test_all_mode_merges_archive_into_old_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config()
            cfg.game_dir = tmp
            api = WebApi(cfg)
            source = SimpleNamespace(get_manifest=lambda force: (
                {"data": {"versions": [{"id": "1.20.1", "type": "release"}]}}, "Mojang 官方", False))
            with patch.object(WebApi, "_source_manager", return_value=source), \
                 patch.object(omniarchive, "list_stage", side_effect=self._fake_stage):
                merged = api.manifest(False, "all")
                only = api.manifest(False, "omni")
                official = api.manifest(False, "official")
        self.assertTrue(merged["ok"])
        self.assertEqual(merged["mode"], "all")
        ids = {row["id"] for row in merged["versions"]}
        self.assertIn("1.20.1", ids)
        self.assertTrue({"b1.7.3", "a1.2.6", "inf-20100618"}.issubset(ids))
        row = next(row for row in merged["versions"] if row["id"] == "b1.7.3")
        self.assertEqual(row["source"], "omni")
        self.assertEqual(row["type"], "old_beta")
        self.assertEqual({row["id"] for row in only["versions"]},
                         {"b1.7.3", "a1.2.6", "inf-20100618"})
        self.assertEqual({row["id"] for row in official["versions"]}, {"1.20.1"})


class SeedWorldTest(unittest.TestCase):
    def test_properties_and_name_sanitizing(self):
        props = seed_world._properties("1.20.1", "12345", "MyWorld")
        self.assertIn("level-seed=12345", props)
        self.assertIn("level-type=minecraft:normal", props)
        self.assertIn("generate-structures=true", props)
        ancient = seed_world._properties("b1.7.3", "42", "Ancient")
        self.assertIn("level-type=DEFAULT", ancient)
        self.assertEqual(seed_world._safe_name("a/b:c"), "a_b_c")

    def test_server_asset_reads_local_version_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            version_dir = Path(tmp) / "versions" / "1.20.1"
            version_dir.mkdir(parents=True)
            (version_dir / "1.20.1.json").write_text(json.dumps({
                "downloads": {"server": {"url": "http://example.invalid/server.jar", "size": 1}},
            }), encoding="utf-8")
            # 本机可能已经缓存过真实的 server.jar，指到临时目录才是可重复的
            with patch.object(seed_world, "JAR_DIR", Path(tmp) / "jars"):
                asset = seed_world.server_asset("1.20.1", tmp, remote=False)
                self.assertTrue(asset["ok"])
                self.assertEqual(asset["url"], "http://example.invalid/server.jar")
                self.assertTrue(asset["path"].endswith("1.20.1-server.jar"))
                missing = seed_world.server_asset("a1.2.6", tmp, remote=False)
                self.assertFalse(missing["ok"])
                self.assertIn("server.jar", missing["message"])


class CreatorFixesTest(unittest.TestCase):
    def test_icons_are_returned_for_every_requested_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config()
            cfg.game_dir = tmp
            api = WebApi(cfg)
            ids = [f"test:item_{index}" for index in range(220)]
            with patch.object(item_icons, "item_texture_uri", return_value=""):
                result = api.creator_item_icons(ids, "1.20.1")
            self.assertTrue(result["ok"])
            self.assertEqual(len(result["icons"]), 220)
            self.assertTrue(all(str(value).startswith("data:image/svg+xml")
                                for value in result["icons"].values()))

    def test_default_catalog_limit_is_full(self):
        import inspect

        default = inspect.signature(item_icons.catalog).parameters["limit"].default
        self.assertGreaterEqual(int(default), 10000)

    def test_frontend_no_candidate_truncation(self):
        self.assertIn("creator_worlds', ''", JS)  # 扫全部游戏目录
        self.assertNotIn("items.slice(0, 120)", JS)
        self.assertNotIn("missing.slice(0, 80)", JS)
        import re

        block = re.search(r"function crFilteredCatalog\(sc\) \{(.*?)\n\}", JS, re.S).group(1)
        self.assertNotIn("crSimilarity", block)  # 创世神目录不再塞相似度候选
        self.assertIn("craft_items', S.craft.version, S.craft.itemQuery, 10000", JS)
        self.assertIn("ACT['seed-game-run']", JS)
        self.assertIn("ACT['manifest-source']", JS)
        self.assertIn("S.selectedVersion = data.selected_version", JS)
        shell_src = (ROOT / "mc_launcher" / "ui_web" / "shell.py").read_text(encoding="utf-8")
        self.assertNotIn("[:160]", shell_src)
        self.assertIn("cfg.default_version_id = str(version_id", "".join(
            line for line in shell_src.splitlines(keepends=True) if "default_version_id" in line))


class ProcessGuardTest(unittest.TestCase):
    def test_kill_all_terminates_registered_children(self):
        from mc_launcher import process_guard

        class FakeProc:
            def __init__(self):
                self.pid = 424242
                self.killed = False
                self.waited = False

            def poll(self):
                return None if not self.killed else 0

            def kill(self):
                self.killed = True

            def wait(self, timeout=None):
                self.waited = True
                return 0

        proc = FakeProc()
        process_guard.register(proc)
        # 不依赖本机是否 Windows：强制走通用的 Proc.kill() 分支
        with patch.object(process_guard.sys, "platform", "linux"):
            count = process_guard.kill_all(wait=0)
        self.assertEqual(count, 1)
        self.assertTrue(proc.killed)
        self.assertTrue(proc.waited)

    def test_main_exits_route_through_guard(self):
        src = (ROOT / "mc_launcher" / "main.py").read_text(encoding="utf-8")
        self.assertIn("def _hard_exit", src)
        self.assertIn("kill_all()", src)
        self.assertNotIn("        os._exit(0)\n", src)
        self.assertNotIn("        os._exit(code)\n", src)


if __name__ == "__main__":
    unittest.main()
