"""远古版本支持的回归测试：Omniarchive 归档、老版本急救、版本限高。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from mc_launcher import legacy_fix, omniarchive
from mc_launcher.terrain_java import noise_mode_for_version, version_height_limits


class OmniarchiveTest(unittest.TestCase):
    def test_version_key_order(self):
        ids = ["b1.7.3", "a1.0.10", "inf-20100313", "a1.2.6", "b1.0", "b1.9-pre6", "a1.0.2_01"]
        ordered = sorted(ids, key=omniarchive.version_key)
        self.assertEqual(ordered[0], "inf-20100313")
        self.assertLess(ordered.index("a1.0.10"), ordered.index("a1.2.6"))
        self.assertLess(ordered.index("a1.2.6"), ordered.index("b1.0"))
        self.assertLess(ordered.index("b1.0"), ordered.index("b1.7.3"))

    def test_build_version_json(self):
        payload = omniarchive.build_version_json("b1.7.3", "https://example.invalid/b1.7.3.jar",
                                                 jar_size=1234, stage="beta")
        self.assertEqual(payload["id"], "b1.7.3")
        self.assertEqual(payload["type"], "old_beta")
        self.assertEqual(payload["mainClass"], "net.minecraft.client.Minecraft")
        self.assertIn("${auth_player_name}", payload["minecraftArguments"])
        self.assertEqual(payload["assets"], "pre-1.6")
        self.assertEqual(payload["assetIndex"]["id"], "pre-1.6")
        self.assertEqual(payload["javaVersion"]["majorVersion"], 8)
        names = [lib["name"] for lib in payload["libraries"]]
        self.assertIn("org.lwjgl.lwjgl:lwjgl:2.9.0", names)
        self.assertEqual(payload["downloads"]["client"]["url"], "https://example.invalid/b1.7.3.jar")

    def test_alpha_type(self):
        payload = omniarchive.build_version_json("a1.2.6", "https://example.invalid/a.jar", stage="alpha")
        self.assertEqual(payload["type"], "old_alpha")

    def test_write_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            info = omniarchive.write_version(Path(tmp), "b1.7.3",
                                             "https://example.invalid/b1.7.3.jar", jar_size=99, stage="beta")
            path = Path(info["json"])
            self.assertTrue(path.is_file())
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["downloads"]["client"]["size"], 99)

    def test_describe_falls_back(self):
        self.assertIn("Infdev", omniarchive.describe("inf-20100630-1835")["bug"])
        self.assertIn("Alpha", omniarchive.describe("a1.0.16")["bug"])
        self.assertIn("Beta", omniarchive.describe("b1.4")["bug"])


class LegacyFixTest(unittest.TestCase):
    def _cfg(self, root: Path):
        return SimpleNamespace(game_path=root)

    def test_sound_needed_for_old_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._cfg(Path(tmp))
            old = legacy_fix.sound_report(cfg, "b1.7.3")
            self.assertTrue(old["needed"])
            self.assertFalse(old["ready"])
            modern = legacy_fix.sound_report(cfg, "1.12.2")
            self.assertFalse(modern["needed"])
            self.assertTrue(modern["ready"])

    def test_import_resources_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "pack" / "resources"
            (source / "sound3" / "step").mkdir(parents=True)
            (source / "sound3" / "step" / "stone1.ogg").write_bytes(b"OggS")
            result = legacy_fix.import_resources(self._cfg(root), str(root / "pack"))
            self.assertTrue(result["ok"], result.get("message"))
            self.assertEqual(result["copied"], 1)
            target = root / "resources" / "sound3" / "step" / "stone1.ogg"
            self.assertTrue(target.is_file())

    def test_openal_range(self):
        self.assertTrue(legacy_fix._needs_openal("1.7.10"))
        self.assertTrue(legacy_fix._needs_openal("1.12.2"))
        self.assertFalse(legacy_fix._needs_openal("1.13.2"))
        self.assertFalse(legacy_fix._needs_openal("b1.7.3"))

    def test_fix_openal_copies_both_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            natives = root / "versions" / "1.20.1" / "natives"
            natives.mkdir(parents=True)
            (natives / "OpenAL.dll").write_bytes(b"MZ")
            cfg = self._cfg(root)
            report = legacy_fix.openal_report(cfg, "1.12.2")
            self.assertTrue(report["needed"])
            self.assertFalse(report["ready"])
            self.assertTrue(report["source"])
            result = legacy_fix.fix_openal(cfg, "1.12.2")
            self.assertTrue(result["ok"], result.get("message"))
            target = root / "versions" / "1.12.2" / "natives"
            self.assertTrue((target / "openal64.dll").is_file())
            self.assertTrue((target / "openal32.dll").is_file())
            self.assertTrue(legacy_fix.openal_report(cfg, "1.12.2")["ready"])

    def test_java_report(self):
        javas = [SimpleNamespace(major=8), SimpleNamespace(major=17), SimpleNamespace(major=21)]
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._cfg(Path(tmp))
            self.assertTrue(legacy_fix.java_report(cfg, "b1.7.3", javas)["ready"])
            self.assertFalse(legacy_fix.java_report(cfg, "26.1", javas)["ready"])
            pair = legacy_fix.java_report(cfg, "1.7.10", [])
            self.assertEqual(pair["needed"], 8)
            self.assertFalse(pair["ready"])


class HeightLimitTest(unittest.TestCase):
    def test_limits_by_version(self):
        self.assertEqual(version_height_limits("b1.7.3")["max_y"], 127)
        self.assertEqual(version_height_limits("a1.2.6")["max_y"], 127)
        self.assertEqual(version_height_limits("1.12.2")["max_y"], 255)
        self.assertEqual(version_height_limits("1.18.2")["min_y"], -64)
        self.assertEqual(version_height_limits("1.18.2")["max_y"], 319)
        self.assertEqual(version_height_limits("26.1")["max_y"], 319)

    def test_noise_mode_for_old_versions(self):
        self.assertEqual(noise_mode_for_version("b1.7.3"), 0)
        self.assertEqual(noise_mode_for_version("a1.2.6"), 0)
        self.assertEqual(noise_mode_for_version("1.12.2"), 0)
        self.assertEqual(noise_mode_for_version("1.21.4"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class BetacraftProxyTest(unittest.TestCase):
    def test_port_by_version(self):
        from mc_launcher import betacraft

        self.assertEqual(betacraft.proxy_port("a1.2.6"), betacraft.PORT_EARLY)
        self.assertEqual(betacraft.proxy_port("b1.2"), betacraft.PORT_EARLY)
        self.assertEqual(betacraft.proxy_port("b1.7.3"), betacraft.PORT_BETA)
        self.assertEqual(betacraft.proxy_port("1.5.2"), betacraft.PORT_RELEASE)
        self.assertEqual(betacraft.proxy_port("1.0"), betacraft.PORT_RELEASE)
        self.assertEqual(betacraft.proxy_port("1.6.4"), 0)
        self.assertEqual(betacraft.proxy_port("1.12.2"), 0)
        self.assertEqual(betacraft.proxy_port(""), 0)

    def test_args_only_for_legacy(self):
        from mc_launcher import betacraft

        args = betacraft.proxy_args("b1.7.3")
        self.assertIn("-Dhttp.proxyHost=betacraft.uk", args)
        self.assertIn("-Dhttp.proxyPort=11705", args)
        self.assertIn("-Djava.util.Arrays.useLegacyMergeSort=true", args)
        self.assertEqual(betacraft.proxy_args("1.20.1"), [])

    def test_report_flag(self):
        from mc_launcher import betacraft

        off = betacraft.report("1.5.2", False)
        self.assertTrue(off["needed"])
        self.assertFalse(off["enabled"])
        self.assertIn("没有声音", off["message"])
        modern = betacraft.report("1.20.1", True)
        self.assertFalse(modern["needed"])

    def test_launch_options_has_flag(self):
        from mc_launcher.launcher import LaunchOptions

        self.assertIn("betacraft_proxy", LaunchOptions.__dataclass_fields__)


class JavaLegacyDistTest(unittest.TestCase):
    def test_distributions_include_legacy_sources(self):
        from mc_launcher.java import (
            _DISTRIBUTIONS_BY_ID,
            installer_supported,
            list_java_distributions,
        )

        ids = {row["id"] for row in list_java_distributions()}
        self.assertIn("azul-legacy", ids)
        self.assertIn("redhat", ids)
        self.assertIn("oracle-archive", ids)
        self.assertFalse(installer_supported("azul-legacy"))
        self.assertTrue(_DISTRIBUTIONS_BY_ID["redhat"]["manual"])
        self.assertEqual(set(_DISTRIBUTIONS_BY_ID["azul-legacy"]["majors"]), {6, 7})

    def test_azul_legacy_rejects_jre(self):
        from mc_launcher.java import _fetch_azul_legacy_versions

        self.assertEqual(_fetch_azul_legacy_versions(7, 5, 3, "jre"), [])


class LegacyAssetsTest(unittest.TestCase):
    """在线兜底源：os-mc 的 resources.zip 与 Betacraft LegacyFix。"""

    def setUp(self):
        from mc_launcher import legacy_fix

        self.legacy_fix = legacy_fix
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self._originals = {
            "legacyfix_dir": legacy_fix.legacyfix_dir,
            "_download_file": legacy_fix._download_file,
            "legacyfix_asset": legacy_fix.legacyfix_asset,
        }
        legacy_fix.legacyfix_dir = lambda cfg=None: self.root / "libs"  # type: ignore[assignment]
        self.addCleanup(self._restore)

    def _restore(self):
        for name, value in self._originals.items():
            setattr(self.legacy_fix, name, value)

    def test_status_before_and_after_install(self):
        self.assertFalse(self.legacy_fix.legacyfix_status()["installed"])
        jar = self.root / "libs" / "legacyfix-2.0-20260502.jar"
        jar.parent.mkdir(parents=True)
        jar.write_bytes(b"x" * 1024)
        status = self.legacy_fix.legacyfix_status()
        self.assertTrue(status["installed"])
        self.assertEqual(status["version"], "2.0-20260502")
        self.assertEqual(status["size"], 1024)

    def test_download_verifies_sha1(self):
        def fake_download(url, target, **_kwargs):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"not the real jar")
            return target.stat().st_size

        self.legacy_fix._download_file = fake_download  # type: ignore[assignment]
        self.legacy_fix.legacyfix_asset = lambda timeout=20: {  # type: ignore[assignment]
            "url": "https://example.invalid/legacyfix.jar",
            "sha1": "0" * 40,
            "size": 0,
            "version": "test",
            "source": "unit",
        }
        result = self.legacy_fix.download_legacyfix()
        self.assertFalse(result["ok"])
        self.assertIn("sha1", result["message"].lower())

    def test_download_rejects_non_zip(self):
        def fake_download(url, target, **_kwargs):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"<html>not a zip</html>")
            return target.stat().st_size

        self.legacy_fix._download_file = fake_download  # type: ignore[assignment]
        cfg = SimpleNamespace(game_path=self.root / "game")
        result = self.legacy_fix.download_resources(cfg)
        self.assertFalse(result["ok"])
        self.assertIn("zip", result["message"])

    def test_asset_falls_back_to_builtin(self):
        from mc_launcher import net

        original = net.Http

        class Broken:
            def __init__(self, *args, **kwargs):
                pass

            def get_json_url(self, *args, **kwargs):
                raise RuntimeError("offline")

        net.Http = Broken  # type: ignore[assignment]
        self.addCleanup(lambda: setattr(net, "Http", original))
        self.legacy_fix.legacyfix_asset = self._originals["legacyfix_asset"]
        asset = self.legacy_fix.legacyfix_asset()
        self.assertTrue(asset["url"].endswith(".jar"))
        self.assertEqual(asset["source"], "内置固定地址")
