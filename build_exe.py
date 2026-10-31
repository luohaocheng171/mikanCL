"""一键打包 MikanCL 为单文件 exe：python build_exe.py"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
EXE_NAME = "MikanCL"

EXCLUDES = [
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DRender",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtGraphs",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtQuick3D",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtTest",
    "PySide6.QtWebEngineQuick",
]


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("未安装 PyInstaller，正在安装…")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        EXE_NAME,
        "--distpath",
        str(DIST),
        "--workpath",
        str(BUILD),
        "--specpath",
        str(BUILD),
    ]
    for module in EXCLUDES:
        command += ["--exclude-module", module]
    icon = ROOT / "assets" / "mikan.ico"
    if icon.exists():
        command += ["--icon", str(icon)]
    translations = ROOT / "mc_launcher" / "translations"
    if translations.is_dir():
        command += [
            "--add-data",
            f"{translations}{os.pathsep}mc_launcher/translations",
        ]
    data_dir = ROOT / "mc_launcher" / "data"
    if data_dir.is_dir():
        command += ["--add-data", f"{data_dir}{os.pathsep}mc_launcher/data"]
    resources = ROOT / "mc_launcher" / "resources"
    if resources.is_dir():
        # WebView2Loader.dll 必须原样打到 mc_launcher/resources，供内置浏览器调用 Edge 内核
        command += ["--add-data", f"{resources}{os.pathsep}mc_launcher/resources"]
    plugins = ROOT / "plugins"
    if plugins.is_dir():
        command += ["--add-data", f"{plugins}{os.pathsep}plugins"]
    command.append(str(ROOT / "run.py"))

    print("执行：", " ".join(command))
    result = subprocess.call(command, cwd=ROOT)
    if result != 0:
        print("打包失败。")
        return result

    exe = DIST / f"{EXE_NAME}.exe"
    if exe.exists():
        size = exe.stat().st_size / 1024 / 1024
        print(f"打包完成：{exe}（{size:.1f} MB）")
        print("提示：首次运行会在 exe 同目录创建 data 目录保存配置与缓存。")
        shutil.rmtree(BUILD / EXE_NAME, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
