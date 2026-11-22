"""WebApi 本次改动的回归测试：彻底移除冲突/依赖检测 + 多版本启动能力。

覆盖：
- 依赖检测 / Mod 冲突检测 API 与前端入口已整体删除
- running_games / stop_game 会话管理
- config.feature_enabled 对已移除功能强制关闭
- 经典版 preflight / health 不再因 Mod 冲突阻止启动

直接运行：``python tests/test_web_feature_changes.py``
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _api(root: Path):
    from mc_launcher.ui_web.shell import WebApi

    config = SimpleNamespace(
        game_path=root / "game",
        backup_root=root / "backups",
        selected_instance=lambda: SimpleNamespace(version_id="1.20.1"),
    )
    return WebApi(config)


class RemovedDetectionApiTest(unittest.TestCase):
    def test_detection_apis_are_gone(self):
        from mc_launcher import preflight
        from mc_launcher.ui_web.shell import WebApi

        for name in ("dependencies_scan", "third_party_modules", "install_dependency", "mod_scan"):
            self.assertFalse(hasattr(WebApi, name), f"{name} 仍然存在")
        self.assertFalse(hasattr(preflight, "mod_conflicts"))
        with tempfile.TemporaryDirectory() as tmp:
            api = _api(Path(tmp))
            listing = api.api_list("conflict", limit=50)
            self.assertNotIn("mod_scan", [item["name"] for item in listing["items"]])

    def test_frontend_has_no_conflict_scan(self):
        text = (ROOT / "mc_launcher" / "ui_web" / "web" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("mod_scan", text)
        self.assertNotIn("dependencies_scan", text)
        self.assertNotIn("冲突", text)


class SessionApiTest(unittest.TestCase):
    def test_stop_game_without_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            api = _api(Path(tmp))
            self.assertEqual(api.running_games()["versions"], [])
            res = api.stop_game("1.20.1")
            self.assertFalse(res["ok"])
            self.assertIn("没有正在运行", res["message"])

    def test_stop_game_with_fake_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            api = _api(Path(tmp))

            class FakeProcess:
                def __init__(self):
                    self.terminated = False

                def poll(self):
                    return None if not self.terminated else 0

            class FakeSession:
                def __init__(self):
                    self.process = FakeProcess()

                def stop(self):
                    self.process.terminated = True

            session = FakeSession()
            with api._sessions_lock:
                api._sessions["1.20.1"] = session
            self.assertEqual(api.running_games()["versions"], ["1.20.1"])
            res = api.stop_game("1.20.1")
            self.assertTrue(res["ok"])
            self.assertTrue(session.process.terminated)
            self.assertEqual(api.running_games()["versions"], [])


class ConfigFeatureRemovalTest(unittest.TestCase):
    def test_removed_features_forced_off(self):
        from mc_launcher.config import Config, REMOVED_FEATURES

        self.assertIn("deps", REMOVED_FEATURES)
        self.assertIn("modgraph", REMOVED_FEATURES)
        cfg = Config()
        # 即使旧配置里打开，也强制关闭。
        cfg.features["deps"] = True
        cfg.features["modgraph"] = True
        self.assertFalse(cfg.feature_enabled("deps"))
        self.assertFalse(cfg.feature_enabled("modgraph"))
        # 其它功能不受影响。
        self.assertTrue(cfg.feature_enabled("home"))


class PreflightNoModBlockTest(unittest.TestCase):
    def test_preflight_ignores_mod_conflicts(self):
        from mc_launcher import preflight

        with tempfile.TemporaryDirectory() as tmp:
            report = preflight.preflight_report(Path(tmp), 2048)
            self.assertEqual(report["blocked"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
