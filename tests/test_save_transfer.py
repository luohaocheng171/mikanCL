"""存档抢救（迁移可用文件）回归：坏文件被跳过，好文件进新存档，种子可同步。

直接运行：``python tests/test_save_transfer.py``
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mc_launcher.save_repair import scan_transferable, transfer_usable  # noqa: E402
from tests.creator_fixtures import make_world  # noqa: E402


class SaveTransferTest(unittest.TestCase):
    def _prepare(self, root: Path):
        source = make_world(root / "game")
        target = make_world(root / "game2")
        playerdata = source / "playerdata"
        playerdata.mkdir(exist_ok=True)
        good = playerdata / "good.dat"
        good.write_bytes((source / "level.dat").read_bytes())
        bad = playerdata / "bad.dat"
        bad.write_bytes(b"this is not nbt at all")
        return source, target, good, bad

    def test_scan_flags_broken_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, _target, good, bad = self._prepare(Path(tmp))
            report = scan_transferable(source)
            ok_map = {item["rel"]: item["ok"] for item in report["items"]}
            self.assertTrue(ok_map["playerdata/good.dat"])
            self.assertFalse(ok_map["playerdata/bad.dat"])
            self.assertGreaterEqual(report["broken"], 1)

    def test_transfer_copies_only_usable(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target, _good, _bad = self._prepare(Path(tmp))
            result = transfer_usable(source, target)
            self.assertTrue(result["ok"], result)
            self.assertIn("playerdata/good.dat", result["copied"])
            self.assertNotIn("playerdata/bad.dat", result["copied"])
            self.assertTrue((target / "playerdata" / "good.dat").is_file())
            self.assertFalse((target / "playerdata" / "bad.dat").exists())

    def test_transfer_refuses_same_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, _target, _good, _bad = self._prepare(Path(tmp))
            result = transfer_usable(source, source)
            self.assertFalse(result["ok"])

    def test_transfer_does_not_overwrite_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target, _good, _bad = self._prepare(Path(tmp))
            existing = target / "playerdata" / "good.dat"
            existing.parent.mkdir(parents=True, exist_ok=True)
            existing.write_bytes(b"keep me")
            result = transfer_usable(source, target)
            self.assertEqual(existing.read_bytes(), b"keep me")
            self.assertTrue(any(item["rel"] == "playerdata/good.dat" for item in result["skipped"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
