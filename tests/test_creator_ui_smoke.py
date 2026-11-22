"""Qt 创世神面板离屏冒烟测试。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from tests.creator_fixtures import make_world  # noqa: E402


def _make_ctx(root: Path):
    # 与真实 Config 保持一致：game_path / backup_root 是属性，
    # 当前版本通过 selected_instance().version_id 获取。
    config = SimpleNamespace(
        game_path=root / "game",
        backup_root=root / "backups",
        selected_instance=lambda: SimpleNamespace(version_id="1.20.1"),
    )
    return SimpleNamespace(config=config)


class CreatorPageSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_page_loads_world_and_collects_request(self):
        from mc_launcher.ui.page_creator import CreatorPage

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_world(root / "game")
            page = CreatorPage(_make_ctx(root))
            self.assertEqual(page.world_combo.count(), 1)
            self.assertIsNotNone(page.state)
            page.health.setValue(1024.0)
            page.xp_level.setValue(21863)
            request = page._collect_request()
            self.assertEqual(request["player"]["health"], 1024.0)
            self.assertEqual(request["player"]["xp_level"], 21863)
            # 未改动的世界字段不会被提交，避免把默认方案写回存档
            self.assertNotIn("gamerules", request["level"])
            page.random_tick.setValue(7)
            page.absorption.setValue(4.0)
            request = page._collect_request()
            self.assertEqual(request["level"]["gamerules"]["randomTickSpeed"], "7")
            self.assertEqual(request["player"]["absorption"], 4.0)

    def test_item_picker_filters(self):
        from mc_launcher.ui.page_creator import ItemPicker

        items = [
            {"id": "minecraft:diamond", "name": "钻石"},
            {"id": "minecraft:stone", "name": "石头"},
        ]
        dialog = ItemPicker(items)
        dialog.search.setText("diamond")
        self.assertEqual(dialog.list.count(), 1)
        dialog.list.setCurrentRow(0)
        self.assertEqual(dialog.selected_id(), "minecraft:diamond")


if __name__ == "__main__":
    unittest.main()
