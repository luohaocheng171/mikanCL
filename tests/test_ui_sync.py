"""双端功能对齐的静态回归：经典 Qt 与美化版 Web 的入口必须同时存在。"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN_WINDOW = ROOT / "mc_launcher" / "ui" / "main_window.py"
APP_JS = ROOT / "mc_launcher" / "ui_web" / "web" / "app.js"
CONFIG = ROOT / "mc_launcher" / "config.py"
MAIN = ROOT / "mc_launcher" / "main.py"


class UiSyncTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.window = MAIN_WINDOW.read_text(encoding="utf-8")
        cls.app = APP_JS.read_text(encoding="utf-8")
        cls.config = CONFIG.read_text(encoding="utf-8")
        cls.main = MAIN.read_text(encoding="utf-8")

    def test_qt_has_new_page_imports_and_registration(self) -> None:
        for symbol in ("ThirdPartyPage", "ChunkEditorPage", "TrainerPage"):
            self.assertIn(f"from .page_", self.window)
            self.assertIn(symbol, self.window)
        for key in (
            '("依赖中心", "thirdparty", "页面"',
            '("区块编辑", "chunks", "页面"',
            '("游戏修改器", "trainer", "页面"',
            '("thirdparty", self.thirdparty_page)',
            '("chunks", self.chunk_editor_page)',
            '("trainer", self.trainer_page)',
            '("thirdparty", self.thirdparty_page, "refresh")',
            '("chunks", self.chunk_editor_page, "refresh")',
            '("trainer", self.trainer_page, "refresh")',
        ):
            self.assertIn(key, self.window, f"经典版缺注册：{key}")

    def test_web_has_new_pages_and_routes(self) -> None:
        for entry in (
            "['skinpack', '皮肤包 / UI 材质包', 'skinpack']",
            "['gallery', '截图图库', 'gallery']",
            "['crash', '崩溃报告', 'crash']",
            "['forbric', 'Forbric', 'forbric']",
        ):
            self.assertIn(entry, self.app, f"美化版缺导航：{entry}")
        for route in (
            "skinpack: renderSkinPack",
            "gallery: renderGallery",
            "crash: renderCrash",
            "forbric: renderForbric",
        ):
            self.assertIn(route, self.app, f"美化版缺路由：{route}")
        for action in ("sp-export", "sp-import", "sp-ui-install", "forbric-run"):
            self.assertIn(f"ACT['{action}']", self.app)

    def test_feature_keys_exist_on_both_sides(self) -> None:
        for key in ("thirdparty", "chunks", "trainer"):
            self.assertIn(f'"{key}": True', self.config)
            self.assertIn(f'    "{key}",', self.config)
        from mc_launcher.config import FEATURE_PAGE_KEYS, Config

        cfg = Config()
        for key in ("thirdparty", "chunks", "trainer"):
            self.assertIn(key, FEATURE_PAGE_KEYS)
            self.assertTrue(cfg.feature_enabled(key))
        for label in ("trainer: '修改器'", "chunks: '区块编辑'", "thirdparty: '依赖 / 第三方组件'"):
            self.assertIn(label, self.app)

    def test_close_cleans_up_child_processes(self) -> None:
        self.assertIn("from ..process_guard import kill_all as _kill_child_processes", self.window)
        self.assertIn("_kill_child_processes()", self.window)
        self.assertIn("shutdown()", self.window)
        self.assertIn("_hard_exit(", self.main)

    def test_one_shot_render_kept_and_xray_kept(self) -> None:
        # 旧版正方形地图 + 矿透，保留半透明水体，但不要动态/续跑/抽稀
        self.assertNotIn("dynamicTiles", self.app)
        self.assertNotIn("ex3d-refill", self.app)
        self.assertNotIn("chunk_step", self.app)
        self.assertIn("EX3D_FS_TEX_A", self.app)
        self.assertIn("ACT['ex3d-xray']", self.app)
        self.assertIn("生成方块视图", self.app)


if __name__ == "__main__":
    unittest.main()
