"""打包 MikanCL Electron 独立内核。

用法：
    python build_electron.py              # 只打 Python 后端（dist-electron/backend）
    python build_electron.py --all        # 后端 + Electron 解包版 + 单文件内置包
    python build_electron.py --portable   # 额外生成可单独分发的便携版 exe

主启动器是单文件 exe：electron_bundle/MikanCL-Electron.zip 会被 build_exe.py
一起打进 MikanCL.exe，用户第一次切到独立版时释放到 data/electron/app 并缓存，
之后每次启动都直接运行缓存目录，不需要重新解压。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist-electron"
BACKEND_DIST = DIST / "backend"
BUNDLE = ROOT / "electron_bundle"
BUILD = ROOT / "build-electron"
EXE_NAME = "MikanCL-backend"
ENTRY = ROOT / "electron_backend_run.py"

EXCLUDES = [
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DRender",
    "PySide6.QtBluetooth",
    "PySide6.QtCharts",
    "PySide6.QtConcurrent",
    "PySide6.QtDataVisualization",
    "PySide6.QtDesigner",
    "PySide6.QtGraphs",
    "PySide6.QtHelp",
    "PySide6.QtLocation",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtNetwork",
    "PySide6.QtNfc",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtPrintSupport",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickControls2",
    "PySide6.QtQuickWidgets",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtSql",
    "PySide6.QtStateMachine",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtTest",
    "PySide6.QtUiTools",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSockets",
    "PySide6.QtXml",
    "webview",
    "pythonnet",
    "clr",
    "clr_loader",
    "tkinter",
    "unittest",
    "pydoc",
]

# Electron 自己提供前端文件，后端不需要 ui_web/web
DATA_DIRS = (
    ("mc_launcher/translations", "mc_launcher/translations"),
    ("mc_launcher/data", "mc_launcher/data"),
    ("mc_launcher/resources", "mc_launcher/resources"),
    ("plugins", "plugins"),
)

HIDDEN_IMPORTS = ("mc_launcher.world_convert",)


def _app_version() -> str:
    try:
        from mc_launcher import APP_VERSION

        return str(APP_VERSION)
    except Exception:  # noqa: BLE001
        return "0.0.0"


def _version_file(version: str) -> Path:
    parts = (version.split(".") + ["0", "0", "0", "0"])[:4]
    while len(parts) < 4:
        parts.append("0")
    nums = ", ".join(str(int(part) if part.isdigit() else 0) for part in parts)
    content = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({nums}), prodvers=({nums}),
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('080404b0', [
        StringStruct('CompanyName', 'MikanCL'),
        StringStruct('FileDescription', 'MikanCL Electron Backend'),
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


def build_backend() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("未安装 PyInstaller，正在安装…")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    version = _app_version()
    BACKEND_DIST.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--console",
        "--name",
        EXE_NAME,
        f"--distpath={BACKEND_DIST}",
        f"--workpath={BUILD}",
        f"--specpath={BUILD}",
        f"--version-file={_version_file(version)}",
    ]
    for module in EXCLUDES:
        command += ["--exclude-module", module]
    for module in HIDDEN_IMPORTS:
        command += ["--hidden-import", module]

    icon = ROOT / "assets" / "mikan.ico"
    if icon.is_file():
        command += ["--icon", str(icon)]

    for folder, target in DATA_DIRS:
        source = ROOT / folder
        if source.is_dir():
            command += ["--add-data", f"{source};{target}"]

    command.append(str(ENTRY))
    print("执行：", " ".join(command))
    result = subprocess.call(command, cwd=ROOT)
    if result != 0:
        print("后端打包失败。")
        return result

    exe = BACKEND_DIST / f"{EXE_NAME}.exe"
    if exe.exists():
        size = exe.stat().st_size / 1024 / 1024
        print(f"后端打包完成：{exe}（{size:.1f} MB）")
    return 0


def _npm() -> str | None:
    env = os.environ.get("MIKAN_NPM", "").strip()
    if env and Path(env).is_file():
        return env
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "MikanBuild" / "node"
    for name in ("npm.cmd", "npm"):
        candidate = local / name
        if candidate.is_file():
            return str(candidate)
        path = shutil.which(name)
        if path:
            return path
    return None


def _node_env(npm: str) -> dict[str, str]:
    """把便携版 Node 的目录加进 PATH，npm 脚本里的 node 才能被找到。"""
    env = dict(os.environ)
    folder = str(Path(npm).resolve().parent)
    env["PATH"] = folder + os.pathsep + env.get("PATH", "")
    env.setdefault("ELECTRON_MIRROR", "https://npmmirror.com/mirrors/electron/")
    env.setdefault(
        "ELECTRON_BUILDER_BINARIES_MIRROR",
        "https://npmmirror.com/mirrors/electron-builder-binaries/",
    )
    return env


def _zip_unpacked() -> int:
    """把 win-unpacked 压成单文件内置包，供主 exe 携带。"""
    source = ROOT / "electron" / "dist" / "win-unpacked"
    if not (source / "MikanCL.exe").is_file():
        print(f"未找到 Electron 解包版：{source}")
        return 1
    BUNDLE.mkdir(parents=True, exist_ok=True)
    target = BUNDLE / "MikanCL-Electron.zip"
    temp = target.with_suffix(".zip.tmp")
    count = 0
    try:
        with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for item in sorted(source.rglob("*")):
                if not item.is_file():
                    continue
                archive.write(item, item.relative_to(source).as_posix())
                count += 1
        os.replace(temp, target)
    except OSError as exc:
        temp.unlink(missing_ok=True)
        print(f"压缩 Electron 失败：{exc}")
        return 1
    size = target.stat().st_size / 1024 / 1024
    print(f"内置包完成：{target}（{count} 个文件，{size:.1f} MB）")
    return 0


def build_electron(unpacked: bool = False, portable: bool = False) -> int:
    npm = _npm()
    if npm is None:
        print("未检测到 Node.js/npm，跳过 Electron 安装包。")
        print("安装 Node.js 后运行：cd electron && npm install && npm run pack")
        return 0
    env = _node_env(npm)
    electron_dir = ROOT / "electron"
    if not (electron_dir / "node_modules").is_dir():
        print("安装 Electron 依赖（首次需要联网下载 Chromium）…")
        result = subprocess.call(
            [npm, "install", "--no-audit", "--no-fund"], cwd=electron_dir, env=env
        )
        if result != 0:
            print("npm install 失败。")
            return result
    if unpacked or not portable:
        print("构建 Electron 解包版…")
        result = subprocess.call([npm, "run", "pack"], cwd=electron_dir, env=env)
        if result != 0:
            return result
        exe = electron_dir / "dist" / "win-unpacked" / "MikanCL.exe"
        if exe.is_file():
            size = exe.stat().st_size / 1024 / 1024
            print(f"Electron 解包版完成：{exe}（{size:.1f} MB）")
        result = _zip_unpacked()
        if result != 0:
            return result
    if portable:
        print("构建 Electron 便携版…")
        result = subprocess.call([npm, "run", "dist"], cwd=electron_dir, env=env)
        if result != 0:
            return result
        found = sorted((electron_dir / "dist").glob("MikanCL-Electron-*.exe"))
        if found:
            BUNDLE.mkdir(parents=True, exist_ok=True)
            target = BUNDLE / "MikanCL-Electron.exe"
            shutil.copy2(found[-1], target)
            size = target.stat().st_size / 1024 / 1024
            print(f"Electron 便携版完成：{target}（{size:.1f} MB）")
    return 0


def main() -> int:
    unpacked = "--pack" in sys.argv or "--all" in sys.argv or "--portable" in sys.argv
    portable = "--portable" in sys.argv
    result = build_backend()
    if result != 0:
        return result
    if unpacked or portable:
        return build_electron(unpacked=unpacked, portable=portable)
    print("下一步：python build_electron.py --all 生成内置独立版；再运行 python build_exe.py 打进单文件 exe。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
