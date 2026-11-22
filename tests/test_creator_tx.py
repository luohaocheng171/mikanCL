"""creator_tx：锁、严格备份与事务回滚。"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from mc_launcher.creator_tx import (
    LockError,
    WorldLock,
    strict_backup,
    FileTransaction,
)

from tests.creator_fixtures import make_world


class LockTest(unittest.TestCase):
    def test_second_lock_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = make_world(Path(tmp))
            first = WorldLock(world)
            first.acquire()
            try:
                with self.assertRaises(LockError):
                    WorldLock(world).acquire()
            finally:
                first.release()

    def test_lock_is_reusable_after_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = make_world(Path(tmp))
            with WorldLock(world):
                pass
            with WorldLock(world):
                pass

    def test_missing_session_lock_is_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = make_world(Path(tmp))
            (world / "session.lock").unlink()
            with WorldLock(world):
                self.assertTrue((world / "session.lock").is_file())


class BackupTest(unittest.TestCase):
    def test_backup_contains_all_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            world = make_world(root)
            (world / "playerdata" / "abc.dat").write_bytes(b"player")
            info = strict_backup(world, root / "backups", "1.20.1")
            self.assertTrue(info.archive.is_file())
            with zipfile.ZipFile(info.archive) as zf:
                names = set(zf.namelist())
            self.assertIn("TestWorld/level.dat", names)
            self.assertIn("TestWorld/playerdata/abc.dat", names)
            self.assertNotIn("TestWorld/session.lock", names)

    def test_backup_manifest_hashes_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            world = make_world(root)
            info = strict_backup(world, root / "backups", "1.20.1")
            digest = hashlib.sha256((world / "level.dat").read_bytes()).hexdigest()
            self.assertEqual(info.hashes["TestWorld/level.dat"], digest)

    def test_unreadable_file_aborts_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            world = make_world(root)
            bad = world / "playerdata" / "bad.dat"
            bad.write_bytes(b"x")
            with mock.patch.object(Path, "read_bytes", side_effect=OSError("denied")):
                with self.assertRaises(OSError):
                    strict_backup(world, root / "backups", "1.20.1")


class TransactionTest(unittest.TestCase):
    def test_commit_writes_all_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "a.dat"
            b = root / "b.dat"
            a.write_bytes(b"old-a")
            tx = FileTransaction(root)
            tx.add(a, b"new-a")
            tx.add(b, b"new-b")
            tx.commit()
            self.assertEqual(a.read_bytes(), b"new-a")
            self.assertEqual(b.read_bytes(), b"new-b")
            self.assertEqual(list(root.glob("*.creator-*")), [])

    def test_failure_rolls_back_previous_replacements(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "a.dat"
            b = root / "b.dat"
            a.write_bytes(b"old-a")
            b.write_bytes(b"old-b")
            tx = FileTransaction(root)
            tx.add(a, b"new-a")
            tx.add(b, b"new-b")
            real_replace = os.replace
            calls = {"n": 0}

            def flaky(src, dst):
                calls["n"] += 1
                if calls["n"] == 2:
                    raise OSError("disk full")
                return real_replace(src, dst)

            with mock.patch("os.replace", side_effect=flaky):
                with self.assertRaises(OSError):
                    tx.commit()
            self.assertEqual(a.read_bytes(), b"old-a")
            self.assertEqual(b.read_bytes(), b"old-b")

    def test_journal_removed_after_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "a.dat"
            target.write_bytes(b"old")
            tx = FileTransaction(root, journal_dir=root / ".journal")
            tx.add(target, b"new")
            tx.commit()
            self.assertFalse((root / ".journal").exists() and any((root / ".journal").iterdir()))

    def test_journal_records_pending_transaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "a.dat"
            target.write_bytes(b"old")
            journal_dir = root / ".journal"
            tx = FileTransaction(root, journal_dir=journal_dir)
            tx.add(target, b"new")
            real_replace = os.replace
            calls = {"n": 0}

            def always_fail(src, dst):
                calls["n"] += 1
                raise OSError("locked")

            with mock.patch("os.replace", side_effect=always_fail):
                with self.assertRaises(OSError):
                    tx.commit()
            files = list(journal_dir.glob("*.json"))
            self.assertTrue(files, "回滚失败时应保留 journal 供人工恢复")
            payload = json.loads(files[0].read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "failed")
            self.assertEqual(payload["entries"][0]["target"], str(target))


if __name__ == "__main__":
    unittest.main()
