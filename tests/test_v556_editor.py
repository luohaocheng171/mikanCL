"""v5.5.6 高级编辑器回归测试：SNBT、预修改、并排 diff、自动备份。"""

from __future__ import annotations

import gzip
import json
import tempfile
import unittest
from pathlib import Path

from mc_launcher import editor, nbt

SAMPLE_SNBT = """{
  Data: {
    LevelName: "world",
    GameType: 1,
    Difficulty: 2b,
    Time: 1234L,
    Health: 20.0f,
    Motion: [0.0d, -0.0784000015258789d, 0.0d],
    Colors: [B;1b,2b,3b],
    Scores: [I;10,20],
    Big: [L;1L,2L],
    Tags: [],
    Nested: {a: 1, "weird key": "x"},
    Items: [{id: "minecraft:stone", Count: 3b}]
  }
}"""


class SnbtTests(unittest.TestCase):
    def test_roundtrip_preserves_types(self):
        node = editor.snbt_load(SAMPLE_SNBT)
        again = editor.snbt_load(editor.snbt_dump(node))
        self.assertEqual(node, again)
        data = node[1]["Data"][1]
        self.assertEqual(data["Difficulty"][0], nbt.TAG_BYTE)
        self.assertEqual(data["Time"][0], nbt.TAG_LONG)
        self.assertEqual(data["Health"][0], nbt.TAG_FLOAT)
        self.assertEqual(data["Motion"][0], nbt.TAG_LIST)
        self.assertEqual(data["Motion"][1][0], nbt.TAG_DOUBLE)
        self.assertEqual(data["Colors"][0], nbt.TAG_BYTE_ARRAY)
        self.assertEqual(data["Scores"][0], nbt.TAG_INT_ARRAY)
        self.assertEqual(data["Big"][0], nbt.TAG_LONG_ARRAY)

    def test_mixed_list_rejected(self):
        with self.assertRaises(editor.SnbtError):
            editor.snbt_load('{a: [1, "two"]}')

    def test_error_reports_position(self):
        with self.assertRaises(editor.SnbtError) as ctx:
            editor.snbt_load('{\n  a: 1,\n  b: nope\n}')
        self.assertIn("第 3 行", str(ctx.exception))

    def test_escaped_strings(self):
        node = editor.snbt_load('{a: "line\\nbreak \\"q\\" \\\\"}')
        self.assertEqual(node[1]["a"][1], 'line\nbreak "q" \\')

    def test_empty_list_and_compound(self):
        node = editor.snbt_load('{a: [], b: {}}')
        self.assertEqual(node[1]["a"], (nbt.TAG_LIST, (nbt.TAG_END, [])))
        self.assertEqual(node[1]["b"], (nbt.TAG_COMPOUND, {}))


class NbtFileTests(unittest.TestCase):
    def _write_dat(self, path: Path, name: str = "world") -> None:
        root = (nbt.TAG_COMPOUND, {"Data": (nbt.TAG_COMPOUND, {
            "LevelName": (nbt.TAG_STRING, name),
            "Time": (nbt.TAG_LONG, 100),
            "Flag": (nbt.TAG_BYTE, 1),
        })})
        path.write_bytes(gzip.compress(nbt.write_nbt_typed("", root)))

    def test_open_save_keeps_gzip_and_root_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "level.dat"
            self._write_dat(target)
            opened = editor.open_target(target)
            self.assertTrue(opened["ok"])
            self.assertEqual(opened["kind"], "nbt")
            self.assertIn('LevelName: "world"', opened["text"])

            new_text = opened["text"].replace('LevelName: "world"', 'LevelName: "edited"')
            result = editor.save_target(target, new_text, keep=3)
            self.assertTrue(result["ok"], result)
            self.assertTrue(target.read_bytes()[:2] == b"\x1f\x8b")
            root_name, node = nbt.parse_nbt_typed(target.read_bytes())
            self.assertEqual(root_name, "")
            self.assertEqual(node[1]["Data"][1]["LevelName"][1], "edited")
            self.assertEqual(node[1]["Data"][1]["Time"][0], nbt.TAG_LONG)
            self.assertEqual(node[1]["Data"][1]["Flag"][0], nbt.TAG_BYTE)

    def test_invalid_nbt_text_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "level.dat"
            self._write_dat(target)
            before = target.read_bytes()
            result = editor.save_target(target, "{ Data: { ", force=True)
            self.assertFalse(result["ok"])
            self.assertEqual(target.read_bytes(), before)

    def test_no_write_before_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "level.dat"
            self._write_dat(target)
            before = target.read_bytes()
            editor.open_target(target)
            editor.compute_diff(target, "{}")
            self.assertEqual(target.read_bytes(), before)


class TextFileTests(unittest.TestCase):
    def test_crlf_and_bom_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "server.properties"
            target.write_bytes(b"\xef\xbb\xbfmotd=hello\r\nmax-players=20\r\n")
            opened = editor.open_target(target)
            self.assertTrue(opened["ok"])
            self.assertEqual(opened["eol"], "CRLF")
            self.assertIn("motd=hello", opened["text"])
            result = editor.save_target(target, opened["text"].replace("hello", "hi"))
            self.assertTrue(result["ok"], result)
            raw = target.read_bytes()
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
            self.assertIn(b"motd=hi\r\n", raw)

    def test_gbk_file_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "notes.txt"
            target.write_bytes("中文内容\n第二行".encode("gb18030"))
            opened = editor.open_target(target)
            self.assertTrue(opened["ok"])
            self.assertEqual(opened["encoding"], "gb18030")
            self.assertIn("中文内容", opened["text"])
            editor.save_target(target, opened["text"] + "\n第三行")
            self.assertIn("第三行", target.read_bytes().decode("gb18030"))

    def test_json_syntax_blocked_then_forced(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "config.json"
            target.write_text('{"a": 1}', encoding="utf-8")
            blocked = editor.save_target(target, '{"a": }')
            self.assertFalse(blocked["ok"])
            self.assertIn("JSON", blocked["message"])
            forced = editor.save_target(target, '{"a": }', force=True)
            self.assertTrue(forced["ok"], forced)
            self.assertTrue(forced["warning"])
            # 强制写入的内容保持原样（用户明确选择忽略语法检查）
            self.assertEqual(target.read_text(encoding="utf-8"), '{"a": }')

    def test_truncated_file_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "big.txt"
            target.write_text("x" * 200, encoding="utf-8")
            opened = editor.open_target(target, max_bytes=50)
            self.assertTrue(opened["ok"])
            self.assertTrue(opened["truncated"])
            self.assertTrue(opened["read_only"])

    def test_binary_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "thumb.png"
            target.write_bytes(bytes(range(256)) * 4)
            opened = editor.open_target(target)
            self.assertFalse(opened["ok"])


class DiffTests(unittest.TestCase):
    def test_diff_stats_and_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "a.txt"
            target.write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
            result = editor.compute_diff(target, "one\nTWO\nthree\nfour\nfive\n")
            self.assertTrue(result["ok"])
            stats = result["stats"]
            self.assertEqual(stats["changed"], 1)
            self.assertEqual(stats["added"], 1)
            self.assertEqual(stats["removed"], 0)
            self.assertFalse(result["identical"])
            kinds = [row["type"] for row in result["rows"]]
            self.assertIn("change", kinds)
            self.assertIn("add", kinds)

    def test_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "a.txt"
            target.write_text("same\n", encoding="utf-8")
            result = editor.compute_diff(target, "same\n")
            self.assertTrue(result["identical"])
            self.assertEqual(result["stats"]["added"], 0)

    def test_context_collapse(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "a.txt"
            lines = [f"line{i}" for i in range(60)]
            target.write_text("\n".join(lines) + "\n", encoding="utf-8")
            edited = list(lines)
            edited[30] = "changed"
            result = editor.compute_diff(target, "\n".join(edited) + "\n", context=2)
            skips = [row for row in result["rows"] if row["type"] == "skip"]
            self.assertTrue(skips)
            self.assertGreater(skips[0]["count"], 10)


class BackupTests(unittest.TestCase):
    def test_backup_created_and_pruned(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "cfg.ini"
            target.write_text("v=0\n", encoding="utf-8")
            for index in range(1, 5):
                result = editor.save_target(target, f"v={index}\n", keep=2)
                self.assertTrue(result["ok"], result)
            items = editor.list_backups(target)["items"]
            self.assertEqual(len(items), 2)

    def test_keep_zero_never_prunes(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "cfg.ini"
            target.write_text("v=0\n", encoding="utf-8")
            for index in range(1, 4):
                editor.save_target(target, f"v={index}\n", keep=0)
            self.assertEqual(len(editor.list_backups(target)["items"]), 3)

    def test_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "cfg.ini"
            target.write_text("origin\n", encoding="utf-8")
            editor.save_target(target, "changed\n")
            backup = editor.list_backups(target)["items"][0]["name"]
            result = editor.restore_backup(target, backup)
            self.assertTrue(result["ok"], result)
            self.assertEqual(target.read_text(encoding="utf-8").strip(), "origin")

    def test_restore_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "cfg.ini"
            target.write_text("x\n", encoding="utf-8")
            result = editor.restore_backup(target, "../../evil.bak")
            self.assertFalse(result["ok"])


class BrowseAndTargetsTests(unittest.TestCase):
    def test_browse_lists_dirs_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sub").mkdir()
            (root / "a.txt").write_text("x", encoding="utf-8")
            result = editor.browse(root)
            self.assertTrue(result["ok"])
            self.assertEqual(result["entries"][0]["name"], "sub")
            self.assertTrue(result["entries"][0]["dir"])

    def test_quick_targets_collects_known_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "options.txt").write_text("fov:0.5", encoding="utf-8")
            (root / "saves" / "world").mkdir(parents=True)
            (root / "saves" / "world" / "level.dat").write_bytes(gzip.compress(b""))
            result = editor.quick_targets(root)
            self.assertTrue(result["ok"])
            names = [item["name"] for group in result["groups"] for item in group["items"]]
            self.assertIn("options.txt", names)
            self.assertIn("level.dat", names)


class WebApiEditorTests(unittest.TestCase):
    def _api(self):
        from mc_launcher.ui_web.shell import WebApi

        api = object.__new__(WebApi)

        class Cfg:
            max_backups = 5
            game_path = ""

        api.config = Cfg()
        return api

    def test_rpc_roundtrip(self):
        api = self._api()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "options.txt"
            target.write_text("lang:zh_CN\n", encoding="utf-8")
            opened = api.editor_open(str(target))
            self.assertTrue(opened["ok"])
            diff = api.editor_diff(str(target), "lang:en_US\n")
            self.assertTrue(diff["ok"])
            self.assertEqual(diff["stats"]["changed"], 1)
            saved = api.editor_save(str(target), "lang:en_US\n")
            self.assertTrue(saved["ok"], saved)
            self.assertTrue(saved["backup"])
            backups = api.editor_backups(str(target))
            self.assertEqual(len(backups["items"]), 1)
            restored = api.editor_restore(str(target), backups["items"][0]["name"])
            self.assertTrue(restored["ok"])
            self.assertEqual(target.read_text(encoding="utf-8").strip(), "lang:zh_CN")

    def test_rpc_error_paths(self):
        api = self._api()
        self.assertFalse(api.editor_open("")["ok"])
        self.assertFalse(api.editor_save("")["ok"])
        self.assertFalse(api.editor_diff("/nope/missing.txt", "x")["ok"])
        self.assertEqual(api.editor_backups("/nope/missing.txt")["items"], [])
        self.assertFalse(api.editor_restore("/nope/missing.txt", "x.bak")["ok"])


if __name__ == "__main__":
    unittest.main()
