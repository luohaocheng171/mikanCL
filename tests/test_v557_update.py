"""v5.5.7：种子世界 Java 选择兼容 + 启动器更新器（Go 版 mcu.exe）。

覆盖：
- seed_world._java_for 同时接受 JavaInfo 数据类与 dict（截图里的崩溃回归）
- update.list_releases / find_release / check_update 的解析与排序
- download_update 落到临时目录、过小文件拒绝、失败清理
- apply_update 交给内置 Go 更新器时的参数拼装
- cleanup_old_files 清理上次更新残留
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import os
from pathlib import Path
from unittest import TestCase, mock

from mc_launcher import seed_world, update
from mc_launcher.java import JavaInfo


def _release_payload(tag: str, *, body: str = "", exe: str | None = None,
                     prerelease: bool = False, published: str = "2026-11-01T00:00:00Z") -> dict:
    assets = []
    if exe:
        assets.append({
            "name": exe,
            "browser_download_url": f"https://example.invalid/{exe}",
            "size": 4096,
        })
    return {
        "tag_name": tag,
        "name": f"MikanCL {tag}",
        "body": body,
        "html_url": f"https://github.com/{update.REPO}/releases/tag/{tag}",
        "published_at": published,
        "prerelease": prerelease,
        "assets": assets,
    }


class _FakeResponse(io.BytesIO):
    def __init__(self, payload: bytes, url: str = ""):
        super().__init__(payload)
        self._url = url
        self.headers = {"Content-Length": str(len(payload))}

    def geturl(self) -> str:
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class JavaForTests(TestCase):
    def test_accepts_java_info_objects(self):
        """截图里的 'JavaInfo' object has no attribute 'get' 回归。"""
        path = str(Path(sys.executable))
        javas = [JavaInfo(path=path, version="17.0.9", major=17, bits=64)]
        self.assertEqual(seed_world._java_for("1.20.1", javas), path)

    def test_accepts_dicts(self):
        path = str(Path(sys.executable))
        self.assertEqual(seed_world._java_for("1.14.4", [{"path": path, "major": 8}]), path)

    def test_prefers_high_major_for_new_versions(self):
        path = str(Path(sys.executable))
        javas = [
            JavaInfo(path=path, version="8u999", major=8, bits=64),
            JavaInfo(path=path, version="21.0.1", major=21, bits=64),
        ]
        self.assertEqual(seed_world._java_for("1.21.4", javas), path)

    def test_empty_and_broken_inputs(self):
        self.assertEqual(seed_world._java_for("1.14.4", None), "")
        self.assertEqual(seed_world._java_for("1.14.4", []), "")
        self.assertEqual(seed_world._java_for("1.14.4", [{"path": "/definitely/not/here"}]), "")
        self.assertEqual(seed_world._java_for("1.14.4", [None, {}, "x"]), "")

    def test_explicit_java_path_wins(self):
        path = str(Path(sys.executable))
        self.assertEqual(seed_world._java_for("1.14.4", [], path), path)


class VersionMathTests(TestCase):
    def test_version_tuple(self):
        self.assertEqual(update._version_tuple("5.5.7"), (5, 5, 7, 0))
        self.assertEqual(update._version_tuple("v5.5"), (5, 5, 0, 0))
        self.assertEqual(update._version_tuple(""), (0, 0, 0, 0))

    def test_is_newer(self):
        self.assertTrue(update.is_newer("5.5.7", "5.5.6"))
        self.assertFalse(update.is_newer("5.5.6", "5.5.6"))
        self.assertFalse(update.is_newer("5.4.9", "5.5.6"))

    def test_clean_tag(self):
        self.assertEqual(update._clean_tag("v5.5.7"), "5.5.7")
        self.assertEqual(update._clean_tag("release-5.5.7"), "5.5.7")
        self.assertEqual(update._clean_tag("5.5.7"), "5.5.7")


class ReleaseListTests(TestCase):
    def _patch(self, payload, *, kind="list"):
        if kind == "list":
            data = json.dumps(payload).encode()
        else:
            data = payload
        return mock.patch.object(update, "_request", lambda url, timeout=12.0: _FakeResponse(data))

    def test_list_sorted_with_relation(self):
        payload = [
            _release_payload("v5.4.0", exe="MikanCL-5.4.0.exe"),
            _release_payload("v9.9.9", exe="MikanCL-9.9.9.exe"),
            _release_payload("v5.5.6", exe="MikanCL-5.5.6.exe"),
        ]
        with self._patch(payload):
            result = update.list_releases(10)
        self.assertTrue(result["ok"], result)
        tags = [row["tag"] for row in result["items"]]
        self.assertEqual(tags, ["9.9.9", "5.5.6", "5.4.0"])
        self.assertEqual(result["latest"], "9.9.9")
        rel = {row["tag"]: row["relation"] for row in result["items"]}
        self.assertEqual(rel["9.9.9"], "newer")
        self.assertIn(rel["5.4.0"], ("older", "same"))

    def test_prerelease_filtered(self):
        payload = [
            _release_payload("6.0.0-beta", exe="b.exe", prerelease=True),
            _release_payload("5.5.6", exe="a.exe"),
        ]
        with self._patch(payload):
            result = update.list_releases(10)
        self.assertEqual([row["tag"] for row in result["items"]], ["5.5.6"])

    def test_asset_picked(self):
        payload = [_release_payload("5.5.6", exe="MikanCL.exe")]
        with self._patch(payload):
            result = update.list_releases(10)
        item = result["items"][0]
        self.assertTrue(item["downloadable"])
        self.assertTrue(item["asset_url"].endswith("MikanCL.exe"))

    def test_api_failure_falls_back_to_html(self):
        html = b'<a href="/luohaocheng171/mikanCL/releases/tag/v5.4.0">x</a>' \
               b'<a href="/luohaocheng171/mikanCL/releases/tag/v5.5.0">y</a>'

        def fake(url, timeout=12.0):
            if "api.github.com" in url:
                raise OSError("blocked")
            return _FakeResponse(html)

        with mock.patch.object(update, "_request", fake):
            result = update.list_releases(10)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["source"], "html")
        self.assertEqual(result["items"][0]["tag"], "5.5.0")

    def test_all_sources_fail(self):
        with mock.patch.object(update, "_request", mock.Mock(side_effect=OSError("down"))):
            result = update.list_releases(10)
        self.assertFalse(result["ok"])
        self.assertEqual(result["items"], [])

    def test_find_release_by_tag(self):
        payload = [
            _release_payload("5.5.6", exe="a.exe"),
            _release_payload("5.4.0", exe="b.exe"),
        ]
        with self._patch(payload):
            self.assertEqual(update.find_release("5.4.0")["tag"], "5.4.0")
            self.assertEqual(update.find_release("")["tag"], "5.5.6")
            self.assertIsNone(update.find_release("1.0.0"))

    def test_check_update_shape(self):
        payload = [_release_payload("99.0.0", exe="a.exe", body="notes")]
        with self._patch(payload):
            info = update.check_update()
        self.assertTrue(info["ok"])
        self.assertTrue(info["has_update"])
        self.assertTrue(info["downloadable"])
        self.assertEqual(info["current"], __import__("mc_launcher").APP_VERSION)
        self.assertIn("releases", info)
        json.dumps(info)  # 必须能直接给 WebView 序列化


class DownloadTests(TestCase):
    def test_download_into_temp_dir(self):
        blob = b"MZ" + b"\0" * (200 * 1024)
        info = {"asset_url": "https://example.invalid/a.exe", "asset_name": "a.exe", "tag": "5.5.7"}
        seen = []

        def fake(url, timeout=30):
            seen.append(url)
            return _FakeResponse(blob)

        with mock.patch.object(update, "_request", fake):
            path = update.download_update(info)
        try:
            self.assertTrue(path.is_file())
            self.assertEqual(path.name, "a.exe")
            self.assertIn(update.TEMP_PREFIX, path.parent.name)
            self.assertEqual(path.read_bytes()[:2], b"MZ")
        finally:
            update._purge(path.parent)

    def test_download_rejects_tiny_file(self):
        info = {"asset_url": "https://example.invalid/t.exe", "asset_name": "t.exe"}
        parent = {}

        def fake(url, timeout=30):
            return _FakeResponse(b"MZtiny")

        real_mkdtemp = tempfile.mkdtemp

        def tracking_mkdtemp(prefix="", dir=None):
            path = real_mkdtemp(prefix=prefix, dir=dir)
            parent["dir"] = path
            return path

        with mock.patch.object(update, "_request", fake), \
                mock.patch.object(update.tempfile, "mkdtemp", tracking_mkdtemp):
            with self.assertRaises(update.UpdateError):
                update.download_update(info)
        self.assertFalse(Path(parent["dir"]).exists())

    def test_download_without_asset(self):
        with self.assertRaises(update.UpdateError):
            update.download_update({"asset_url": ""})


class ApplyUpdateTests(TestCase):
    def test_embedded_updater_present(self):
        path = update.embedded_updater()
        if path is None:
            # 源码仓库按 .gitignore 不带 *.exe；mcu.exe 是 build_updater.py 的构建产物。
            # 只有已编译过更新器（打包环境）才校验二进制内容。
            self.skipTest("内置更新器未编译（源码仓库态），运行 python build_updater.py 生成")
        self.assertGreater(path.stat().st_size, 64 * 1024)
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(2), b"MZ")

    def test_apply_update_uses_go_engine(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "MikanCL.exe"
            target.write_bytes(b"MZ old")
            new = root / "new.exe"
            new.write_bytes(b"MZ new")
            captured = {}

            class FakePopen:
                def __init__(self, args, **kwargs):
                    captured["args"] = args
                    captured["kwargs"] = kwargs

            # 源码仓库不带 mcu.exe（构建产物），mock 一个假路径，保证测的是
            # 「有 Go 更新器时走 Go 引擎」这条分支，而不是退化到 bat fallback。
            fake_updater = root / "mcu.exe"
            fake_updater.write_bytes(b"MZ fake")
            with mock.patch.object(update, "current_executable", return_value=target), \
                    mock.patch.object(update, "extract_updater", return_value=fake_updater), \
                    mock.patch.object(update.subprocess, "Popen", FakePopen):
                result = update.apply_update(new, relaunch=True)
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["engine"], "go")
            args = captured["args"]
            self.assertIn("-target", args)
            self.assertIn(str(target), args)
            self.assertIn("-source", args)
            self.assertIn(str(new), args)
            self.assertIn("-pid", args)
            self.assertIn("-cleanup", args)
            self.assertTrue(Path(args[0]).name.lower().endswith(".exe"))
            self.assertTrue(captured["kwargs"]["close_fds"])

    def test_apply_update_rejects_bad_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "MikanCL.exe"
            target.write_bytes(b"MZ")
            with mock.patch.object(update, "current_executable", return_value=target):
                self.assertFalse(update.apply_update(Path(tmp) / "missing.exe")["ok"])
                txt = Path(tmp) / "x.txt"
                txt.write_text("hi", encoding="utf-8")
                self.assertFalse(update.apply_update(txt)["ok"])
            with mock.patch.object(update, "current_executable", return_value=None):
                self.assertFalse(update.apply_update(Path(tmp) / "x.txt")["ok"])

    def test_update_install_rollback_message(self):
        from mc_launcher.ui_web.shell import WebApi

        api = object.__new__(WebApi)
        older = {"tag": "5.4.0", "relation": "older", "asset_url": "https://x/y.exe",
                 "downloadable": True}
        with mock.patch.object(WebApi, "update_check", return_value={"ok": True, "has_update": True}), \
                mock.patch("mc_launcher.update.find_release", return_value=older), \
                mock.patch("mc_launcher.ui_web.shell._spawn") as spawn:
            spawn.return_value.id = "job1"
            result = api.update_install("5.4.0")
        self.assertTrue(result["ok"], result)
        self.assertIn("回档", result["message"])


class CleanupTests(TestCase):
    def test_cleanup_removes_stale_temp(self):
        temp_root = Path(tempfile.gettempdir())
        folder = Path(tempfile.mkdtemp(prefix=update.TEMP_PREFIX, dir=temp_root))
        (folder / "x.exe").write_bytes(b"MZ")
        leftover = temp_root / f"mcu-test-{os.getpid()}.tmp"
        leftover.write_bytes(b"MZ")
        try:
            update.cleanup_old_files(0, attempts=2)
            self.assertFalse(folder.exists())
            self.assertFalse(leftover.exists())
        finally:
            update._purge(folder)
            update._purge(leftover)

    def test_cleanup_never_raises(self):
        with mock.patch.object(update.tempfile, "gettempdir", return_value="Z:/nonexistent-dir"):
            update.cleanup_old_files(0, attempts=1)
