"""一键打包 MikanCL（PyInstaller 版）：python build_exe.py

默认 onefile 单文件模式：所有依赖打进一个 exe，分发方便；代价是每次启动
都要先把运行时解压到临时目录，启动比 onedir 慢几秒。

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
    "PySide6.QtBluetooth",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtDesigner",
    "PySide6.QtGraphs",
    "PySide6.QtHelp",
    "PySide6.QtLocation",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtNfc",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    # QtWebEngineCore 依赖 QtQml/QtQuick/QtPositioning，不能排除，否则经典版
    # 内置浏览器与登录窗口会报 libshiboken: could not import module
    "PySide6.QtQuick3D",
    "PySide6.QtQuickControls2",
    "PySide6.QtQuickWidgets",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtSql",
    "PySide6.QtStateMachine",
    "PySide6.QtTest",
    "PySide6.QtUiTools",
    "PySide6.QtWebEngineQuick",
    "tkinter",
    "unittest",
    "pydoc",
    # 下面这些模块本项目完全没用到，排除后能少收一批 Qt 插件
    "PySide6.QtDBus",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtSerialBus",
    "PySide6.QtTextToSpeech",
    "PySide6.QtWebSockets",
    "PySide6.QtNetworkAuth",
    "PySide6.QtHttpServer",
    "PySide6.QtSpatialAudio",
    # 已确认：源码里没有任何 import / 动态导入引用以下模块
    "PySide6.QtAxContainer",
    "PySide6.QtCanvasPainter",
    "PySide6.QtConcurrent",
    "PySide6.QtGraphsWidgets",
    "PySide6.QtLabsStyleKit",
    # 同上：QtOpenGL / QtOpenGLWidgets / QtPrintSupport 都是 QtWebEngine 的
    # 运行时依赖，排除后 exe 启动即崩溃
    "PySide6.QtQuickTest",
    "PySide6.QtWebView",
    "PySide6.QtXml",
]

# 运行时资源：内置数据、浏览器 DLL、美化版前端、插件
# translations 只带编译后的 .qm；.ts 是 Qt Linguist 源文件，运行时不读取
DATA_DIRS = (
    ("mc_launcher/data", "mc_launcher/data"),
    ("mc_launcher/resources", "mc_launcher/resources"),
    ("mc_launcher/ui_web/web", "mc_launcher/ui_web/web"),
    ("plugins", "plugins"),
)

# pywebview 在 Windows 依赖 pythonnet + WebView2 互操作程序集
# （webview 自带 PyInstaller 钩子，会自动收集 lib/js，这里只补隐藏导入）
HIDDEN_IMPORTS = (
    "mc_launcher.world_convert",
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
    "clr",
    "clr_loader",
    "clr_loader.util",
    "pythonnet",
)

# 单文件模式下 pywebview 的 JS / WebView2 互操作 DLL 必须一并收进 exe
COLLECT_ALL = ("webview",)


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
        "--onefile",
        "--name",
        EXE_NAME,
        f"--distpath={DIST}",
        f"--workpath={BUILD}",
        f"--specpath={BUILD}",
        "--console" if console else "--windowed",
        "--optimize",
        "2",
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

    # 翻译只收 .qm（运行时 i18n 只加载 .qm）
    for qm in sorted((ROOT / "mc_launcher" / "translations").glob("*.qm")):
        command += ["--add-data", f"{qm};mc_launcher/translations"]

    # Electron 独立版内置包：第一次切到独立版时释放到 data/electron/app
    electron_bundle = ROOT / "electron_bundle"
    if (electron_bundle / "MikanCL-Electron.zip").is_file():
        command += ["--add-data", f"{electron_bundle};electron_bundle"]
        size = (electron_bundle / "MikanCL-Electron.zip").stat().st_size / 1024 / 1024
        print(f"已附带 Electron 内置包（{size:.1f} MB）")
    else:
        print("提示：未找到 electron_bundle/MikanCL-Electron.zip，单文件将不含独立版。")
        print("      先运行 python build_electron.py --all 生成内置包。")

    command.append(str(ROOT / "run.py"))

    print("执行：", " ".join(command))
    import subprocess

    result = subprocess.call(command, cwd=ROOT)
    if result != 0:
        print("打包失败。")
        return result

    exe = DIST / f"{EXE_NAME}.exe"
    if exe.exists():
        size = exe.stat().st_size / 1024 / 1024
        print(f"打包完成：{exe}（{size:.1f} MB，单文件）")
        print("提示：单文件版本首次启动要先解压运行时，会比 onedir 慢几秒；首次运行会在 exe 同目录创建 data 目录。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
