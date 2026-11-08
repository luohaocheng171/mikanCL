"""一键打包 MikanCL（PyInstaller 版）：python build_exe.py

使用 onedir 模式：美化版 pywebview / WebView2 的运行时文件很多，
onefile 每次启动都要解压，既慢又容易触发杀软误报。

调试：设置环境变量 MIKAN_BUILD_CONSOLE=1 可生成带控制台的版本，方便看报错。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
EXE_NAME = "MikanCL"

# 明确不参与打包的模块，减少体积
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
    "PySide6.QtQuick3D",
    "PySide6.QtSerialPort",
    "PySide6.QtTest",
    "PySide6.QtWebEngineQuick",
    "tkinter",
    "unittest",
    "pydoc",
]

# 运行时资源：翻译、内置数据、浏览器 DLL、美化版前端、插件
DATA_DIRS = (
    ("mc_launcher/translations", "mc_launcher/translations"),
    ("mc_launcher/data", "mc_launcher/data"),
    ("mc_launcher/resources", "mc_launcher/resources"),
    ("mc_launcher/ui_web/web", "mc_launcher/ui_web/web"),
    ("plugins", "plugins"),
)

# pywebview 在 Windows 依赖 pythonnet + WebView2 互操作程序集
# （webview 自带 PyInstaller 钩子，会自动收集 lib/js，这里只补隐藏导入）
HIDDEN_IMPORTS = (
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
    "clr",
    "clr_loader",
    "clr_loader.util",
    "pythonnet",
)

COLLECT_ALL = ()


def _app_version() -> str:
    try:
        from mc_launcher import APP_VERSION

        return str(APP_VERSION)
    except Exception:  # noqa: BLE001
        return "0.0.0"


def _version_file(version: str) -> Path:
    """生成 Windows 版本信息文件（资源管理器里显示的产品/文件版本）。"""
    parts = (version.split(".") + ["0", "0", "0", "0"])[:4]
    while len(parts) < 4:
        parts.append("0")
    nums = ", ".join(str(int(p) if p.isdigit() else 0) for p in parts)
    content = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({nums}), prodvers=({nums}),
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('080404b0', [
        StringStruct('CompanyName', 'MikanCL'),
        StringStruct('FileDescription', 'MikanCL Minecraft Launcher'),
        StringStruct('FileVersion', '{version}'),
        StringStruct('ProductName', 'MikanCL'),
        StringStruct('ProductVersion', '{version}'),
        StringStruct('OriginalFilename', '{EXE_NAME}.exe'),
        StringStruct('LegalCopyright', 'MikanCL contributors'),
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
"""
    path = BUILD / "version_info.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("未安装 PyInstaller，正在安装…")
        import subprocess

        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    version = _app_version()
    console = os.environ.get("MIKAN_BUILD_CONSOLE") == "1"
    DIST.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        EXE_NAME,
        f"--distpath={DIST}",
        f"--workpath={BUILD}",
        f"--specpath={BUILD}",
        "--console" if console else "--windowed",
        f"--version-file={_version_file(version)}",
    ]
    for module in EXCLUDES:
        command += ["--exclude-module", module]

    for module in HIDDEN_IMPORTS:
        command += ["--hidden-import", module]

    for package in COLLECT_ALL:
        command += ["--collect-all", package]

    icon = ROOT / "assets" / "mikan.ico"
    if icon.is_file():
        command += ["--icon", str(icon)]

    for folder, target in DATA_DIRS:
        source = ROOT / folder
        if source.is_dir():
            command += ["--add-data", f"{source};{target}"]

    command.append(str(ROOT / "run.py"))

    print("执行：", " ".join(command))
    import subprocess

    result = subprocess.call(command, cwd=ROOT)
    if result != 0:
        print("打包失败。")
        return result

    app_dir = DIST / EXE_NAME
    exe = app_dir / f"{EXE_NAME}.exe"
    if exe.exists():
        # 可选：把固定版本 WebView2 Runtime 一并复制进安装目录，彻底免联网
        runtime = ROOT / "webview2"
        if runtime.is_dir():
            target = app_dir / "webview2"
            import shutil

            shutil.copytree(runtime, target, dirs_exist_ok=True)
            print(f"已内置 WebView2 Runtime：{target}")
        total = sum(f.stat().st_size for f in app_dir.rglob("*") if f.is_file())
        print(f"打包完成：{app_dir}（合计 {total / 1024 / 1024:.1f} MB）")
        print("提示：直接分发整个 MikanCL 目录；首次运行会在 exe 同目录创建 data 目录。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
