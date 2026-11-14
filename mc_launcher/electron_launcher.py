"""Electron 独立版的定位、解包与启动。

Electron 自带 Chromium，不依赖 WebView2；它会用自己的 stdio 协议拉起
MikanCL-backend.exe，两边共用 APP_ROOT 下的同一份 data/。

主程序只负责三件事：把打包进 exe 的独立版释放到 data/electron/app、找到
可执行文件、把它拉起来后自己退出。这里不导入 Qt，首次启动判断界面框架时
也能安全调用。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import traceback
import zipfile
from pathlib import Path

from .config import APP_ROOT, DATA_DIR, LOG_DIR
from .relaunch import clean_env

_BUNDLE_NAME = "MikanCL-Electron.zip"
_BUNDLE_EXE = "MikanCL-Electron.exe"


def _log(message: str) -> None:
    """独立版排障日志：data/logs/electron.log。"""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_DIR / "electron.log", "a", encoding="utf-8") as file:
            file.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except OSError:
        pass


def _bundle_dir() -> Path:
    """随主 exe 一起分发的 Electron 资源目录（PyInstaller 解包目录或源码目录）。"""
    packed = getattr(sys, "_MEIPASS", "")
    if packed:
        return Path(packed) / "electron_bundle"
    return Path(__file__).resolve().parent.parent / "electron_bundle"


def _cache_dir() -> Path:
    return DATA_DIR / "electron" / "app"


def _cached_exe() -> Path:
    return _cache_dir() / "MikanCL.exe"


def _bundle_file(name: str) -> Path | None:
    folder = _bundle_dir()
    if not folder.is_dir():
        return None
    path = folder / name
    return path if path.is_file() else None


def _marker() -> Path:
    return _cache_dir().parent / "bundle.txt"


def _extract_bundle() -> Path | None:
    """把 electron_bundle/MikanCL-Electron.zip 释放到 data/electron/app。

    只在首次使用或内置包更新后执行一次；之后直接运行解包目录里的
    MikanCL.exe，不用担心每次启动都重新解压。
    """
    archive = _bundle_file(_BUNDLE_NAME)
    if archive is None:
        _log(f"未找到内置包：{_bundle_dir()}")
        return None
    _log(f"开始释放内置包：{archive} -> {_cache_dir()}")
    stamp = f"{archive.stat().st_size}"
    target = _cache_dir()
    marker = _marker()
    try:
        if _cached_exe().is_file() and marker.is_file() and marker.read_text(encoding="utf-8").strip() == stamp:
            return _cached_exe()
    except OSError:
        pass
    temp = target.with_name("app.tmp")
    try:
        shutil.rmtree(temp, ignore_errors=True)
        temp.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(temp)
        shutil.rmtree(target, ignore_errors=True)
        os.replace(temp, target)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(stamp, encoding="utf-8")
        _log(f"释放完成：{target}")
    except (OSError, zipfile.BadZipFile) as exc:
        _log(f"释放失败：{exc!r}\n{traceback.format_exc()}")
        shutil.rmtree(temp, ignore_errors=True)
        return None
    return _cached_exe() if _cached_exe().is_file() else None


def _portable_copy() -> Path | None:
    """兼容只带便携版 exe 的场景：复制到 data 下再运行。"""
    source = _bundle_file(_BUNDLE_EXE)
    if source is None:
        return None
    target = _cache_dir().parent / _BUNDLE_EXE
    try:
        if not target.is_file() or target.stat().st_size != source.stat().st_size:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    except OSError:
        return None
    return target


def _candidates() -> list[Path]:
    root = Path(APP_ROOT)
    electron_dir = root / "electron"
    result = [
        # 从主 exe 内置包释放出来的独立版
        _cached_exe(),
        _cache_dir().parent / _BUNDLE_EXE,
        # 解包版（electron-builder --dir 或手动解压）
        electron_dir / "MikanCL.exe",
        electron_dir / "dist" / "win-unpacked" / "MikanCL.exe",
        # 便携版（electron-builder portable）
        root / "MikanCL-Electron.exe",
    ]
    for folder in (electron_dir / "dist", electron_dir, root):
        try:
            result.extend(sorted(folder.glob("MikanCL-Electron*.exe")))
        except OSError:
            continue
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        if exe_dir != root:
            result.append(exe_dir / "MikanCL-Electron.exe")
            try:
                result.extend(sorted(exe_dir.glob("MikanCL-Electron*.exe")))
            except OSError:
                pass
    return result


def find_electron() -> Path | None:
    """返回可用的 Electron 可执行文件；没有构建产物时返回 None。"""
    env = os.environ.get("MIKAN_ELECTRON", "").strip()
    if env:
        path = Path(env)
        if path.is_file():
            return path
    seen: set[str] = set()
    for item in _candidates():
        key = str(item).lower()
        if key in seen:
            continue
        seen.add(key)
        if item.is_file():
            return item
    return None


def electron_installed() -> bool:
    """只做轻量判断，不触发解包：内置压缩包也算已安装。"""
    if find_electron() is not None:
        return True
    return _bundle_file(_BUNDLE_NAME) is not None or _bundle_file(_BUNDLE_EXE) is not None


def launch_electron() -> bool:
    """以独立进程启动 Electron 版；成功拉起返回 True。"""
    exe = find_electron()
    if exe is None:
        exe = _extract_bundle() or _portable_copy()
    if exe is None:
        _log("没有可用的 Electron 产物")
        return False
    _log(f"启动 Electron：{exe}")
    # 不能把 PyInstaller onefile 的 _PYI_* 变量带给 Electron：它会继续传给
    # Electron 后端（同样是 onefile），后端复用主程序已删除的 _MEI 目录就会
    # 报「Failed to load Python DLL」。clean_env 统一剔除。
    env = clean_env()
    env["MIKAN_APP_ROOT"] = str(APP_ROOT)
    # 独立版里切回经典 / 美化版时，需要重新拉起主启动器
    if getattr(sys, "frozen", False):
        env["MIKAN_MAIN_EXE"] = str(Path(sys.executable).resolve())
        env.pop("MIKAN_MAIN_CMD", None)
    else:
        env.pop("MIKAN_MAIN_EXE", None)
        env["MIKAN_MAIN_CMD"] = f'"{Path(sys.executable).resolve()}" "run.py"'
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    try:
        subprocess.Popen(
            [str(exe)],
            cwd=str(exe.parent),
            env=env,
            close_fds=True,
            creationflags=flags,
        )
    except OSError:
        return False
    return True
