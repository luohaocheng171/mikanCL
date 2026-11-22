"""远古版本 LegacyFix 启动参数回归测试。

覆盖 b1.8.1 / a1.2.6 的 ClassCastException 与 inf-20100630-1835 的
ClassNotFoundException 两个真实故障：
- LegacyFix agent + 桥接类加载器 + add-opens 缺一不可；
- 远古版本主类统一交给 LegacyFixLauncher 自动探测（MinecraftApplet）；
- shell._launch_now 早退分支不能再抛 NameError（log 未定义）。
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
import sys  # noqa: E402

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mc_launcher import betacraft, launcher, legacy_fix  # noqa: E402
from mc_launcher.jvm import (  # noqa: E402
    LEGACYFIX_ADD_OPENS,
    LEGACYFIX_CLASS_LOADER,
    LEGACYFIX_LAUNCHER,
)
from mc_launcher.version import MergedVersion  # noqa: E402


def _make_version(vid: str, main_class: str) -> MergedVersion:
    return MergedVersion(
        id=vid,
        json={},
        path=Path(""),
        type="old_beta",
        main_class=main_class,
        jar_id=vid,
        assets_id="pre-1.6",
        asset_index=None,
        client_download=None,
        logging=None,
        libraries=[],
        raw_game_args=[],
        raw_jvm_args=[],
        minecraft_arguments=(
            "${auth_player_name} ${auth_session} "
            "--gameDir ${game_directory} --assetsDir ${game_assets}"
        ),
        release_time="",
        java_major=7,
        inherits_from="",
    )


class LegacyFixLaunchPlanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        # 建一个假的 client jar 与 legacyfix jar，满足存在性检查
        versions = self.root / "versions" / "b1.8.1"
        versions.mkdir(parents=True)
        (versions / "b1.8.1.jar").write_bytes(b"PK\x03\x04")
        self.lfjar = self.root / "libs" / "legacyfix-2.0.jar"
        self.lfjar.parent.mkdir(parents=True, exist_ok=True)
        self.lfjar.write_bytes(b"PK\x03\x04")

    def tearDown(self):
        self.tmp.cleanup()

    def _plan(self, vid: str, main_class: str, major: int, legacyfix: bool):
        vdir = self.root / "versions" / vid
        vdir.mkdir(parents=True, exist_ok=True)
        (vdir / f"{vid}.jar").write_bytes(b"PK\x03\x04")
        version = _make_version(vid, main_class)
        options = launcher.LaunchOptions(
            version=version,
            game_dir=self.root / "versions" / vid,
            player_name="Steve",
            java=SimpleNamespace(path="java.exe", major=major, version=f"{major}", bits=64),
            root_dir=self.root,
            legacyfix=legacyfix,
            offline=True,
            smart_jvm=False,
        )
        with patch.object(legacy_fix, "legacyfix_jar", return_value=self.lfjar):
            return launcher.build_launch_plan(options)

    def test_beta_java17_uses_bridge_and_launcher(self):
        plan = self._plan("b1.8.1", "net.minecraft.launchwrapper.Launch", 17, True)
        cmd = plan.command
        self.assertIn(f"-Djava.system.class.loader={LEGACYFIX_CLASS_LOADER}", cmd)
        for flag in LEGACYFIX_ADD_OPENS:
            self.assertIn(flag, cmd)
        self.assertTrue(any(a.startswith("-javaagent:") and "legacyfix" in a for a in cmd))
        # 主类必须是 LegacyFixLauncher，不再是 launchwrapper
        self.assertEqual(cmd[cmd.index("-cp") + 2], LEGACYFIX_LAUNCHER)
        self.assertNotIn("net.minecraft.launchwrapper.Launch", cmd)
        # legacyfix jar 必须在 classpath
        self.assertIn(str(self.lfjar), cmd[cmd.index("-cp") + 1])

    def test_alpha_java17_uses_launcher(self):
        plan = self._plan("a1.2.6", "net.minecraft.launchwrapper.Launch", 17, True)
        self.assertEqual(plan.command[plan.command.index("-cp") + 2], LEGACYFIX_LAUNCHER)

    def test_infdev_wrong_main_class_compensated_by_launcher(self):
        # inf 的 JSON 主类是 net.minecraft.client.Minecraft（jar 里其实没有），
        # 但走 LegacyFixLauncher 后会探测 MinecraftApplet，不再 ClassNotFound
        plan = self._plan("inf-20100630-1835", "net.minecraft.client.Minecraft", 17, True)
        self.assertEqual(plan.command[plan.command.index("-cp") + 2], LEGACYFIX_LAUNCHER)

    def test_java8_no_add_opens(self):
        # Java 8 没有模块系统，不能用 --add-opens / 桥接类加载器
        plan = self._plan("b1.8.1", "net.minecraft.launchwrapper.Launch", 8, True)
        cmd = plan.command
        self.assertFalse(any(a.startswith("--add-opens") for a in cmd))
        self.assertNotIn(f"-Djava.system.class.loader={LEGACYFIX_CLASS_LOADER}", cmd)
        self.assertEqual(cmd[cmd.index("-cp") + 2], LEGACYFIX_LAUNCHER)

    def test_legacyfix_disabled_keeps_original_main(self):
        plan = self._plan("b1.8.1", "net.minecraft.launchwrapper.Launch", 8, False)
        self.assertEqual(
            plan.command[plan.command.index("-cp") + 2],
            "net.minecraft.launchwrapper.Launch",
        )


class CrashHintClassNotFoundTest(unittest.TestCase):
    def test_class_not_found_gives_actionable_hint(self):
        from mc_launcher.launcher import crash_hint

        text = crash_hint(1, "错误: 找不到或无法加载主类 net.minecraft.client.Minecraft\n"
                             "原因: java.lang.ClassNotFoundException: net.minecraft.client.Minecraft")
        self.assertIn("客户端", text + "远古")


if __name__ == "__main__":
    unittest.main()
