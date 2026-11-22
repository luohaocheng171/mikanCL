"""下载健壮性回归：分段下载超时不再误报 WinError 2；Java 下载自动走国内镜像。

对应两个真实问题：
1. 分段下载时首段连接就在 http 层超时，part 文件还没创建，旧代码直接
   part.stat() 抛 FileNotFoundError(WinError 2)，把网络超时误报成「系统找不到
   指定的文件 ...part0」。
2. Temurin 的 GitHub 直链在国内常读超时，需要自动改写为清华 TUNA 镜像。

直接运行：``python tests/test_download_robust.py``
"""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mc_launcher import net  # noqa: E402
from mc_launcher.java import adoptium_mirror_url  # noqa: E402

MSI_21 = (
    "https://github.com/adoptium/temurin21-binaries/releases/download/"
    "jdk-21.0.13%2B9/OpenJDK21U-jdk_x64_windows_hotspot_21.0.13_9.msi"
)


class SegmentedTimeoutTest(unittest.TestCase):
    """连接在建立阶段就超时，不应抛 FileNotFoundError（旧 bug）。"""

    def test_timeout_does_not_raise_filenotfound(self):
        original_probe = net._probe_download_range
        original_open = net.open_with_ssl_fallback

        def fake_probe(candidate, timeout=20):
            return 4 * 1024 * 1024, True  # 声称支持分段、共 4MB

        def fake_open(request, timeout):
            raise TimeoutError("The read operation timed out")

        net._probe_download_range = fake_probe
        net.open_with_ssl_fallback = fake_open
        try:
            with tempfile.TemporaryDirectory() as tmp:
                dest = Path(tmp) / "x.msi"
                candidate = net.Candidate("https://example.com/x.msi", {}, "t", "测试")
                with self.assertRaises(Exception) as ctx:
                    net._segmented_download(candidate, dest, 4 * 1024 * 1024,
                                            threading.Event(), None, None, 2)
                self.assertNotIsInstance(ctx.exception, FileNotFoundError)
                self.assertNotIn("系统找不到指定的文件", str(ctx.exception))
        finally:
            net._probe_download_range = original_probe
            net.open_with_ssl_fallback = original_open


class AdoptiumMirrorTest(unittest.TestCase):
    def test_github_temurin_rewritten_to_tuna(self):
        url = adoptium_mirror_url(MSI_21)
        self.assertTrue(url.startswith("https://mirrors.tuna.tsinghua.edu.cn/Adoptium/21/jdk/x64/windows/"))
        self.assertTrue(url.endswith("OpenJDK21U-jdk_x64_windows_hotspot_21.0.13_9.msi"))

    def test_jre_zip_uses_jre_package(self):
        url = adoptium_mirror_url(
            "https://github.com/adoptium/temurin21-binaries/releases/download/"
            "jdk-21.0.13%2B9/OpenJDK21U-jre_x64_windows_hotspot_21.0.13_9.zip"
        )
        self.assertIn("/21/jre/x64/windows/", url)

    def test_non_temurin_has_no_mirror(self):
        self.assertEqual(
            adoptium_mirror_url(
                "https://corretto.aws/downloads/latest/amazon-corretto-21-x64-windows-jdk.msi"
            ), ""
        )

    def test_candidates_prefer_mirror_then_original(self):
        cands = net.Candidate  # 只是为了确认可用
        self.assertTrue(callable(cands))
        from mc_launcher.java import _java_candidates

        items = _java_candidates(MSI_21, "Java 安装程序")
        self.assertEqual(len(items), 2)
        self.assertIn("tuna.tsinghua.edu.cn", items[0].url)
        self.assertIn("github.com", items[1].url)
        self.assertIn("清华镜像", items[0].source_name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
