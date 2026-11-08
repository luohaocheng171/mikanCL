"""启动前 checklist 与 JVM 预热等 Qt 无关的公共逻辑（经典版与美化版共用）。

经典版 page_home 自己也有一份实现，这里只服务于 pywebview 外壳，
避免为了复用而把 PySide6 拖进美化版进程。
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def total_physical_memory_mb() -> int:
    """读取物理内存总量（MB）；失败返回 0。"""
    if os.name != "nt":
        return 0
    try:
        import ctypes

        class _MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = _MemoryStatusEx()
        stat.dwLength = ctypes.sizeof(_MemoryStatusEx)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return int(stat.ullTotalPhys // (1024 * 1024))
    except Exception:  # noqa: BLE001
        pass
    return 0


def integrated_gpu_name() -> str:
    """返回集成显卡名称；独立显卡或读取失败返回空串。"""
    if os.name != "nt":
        return ""
    try:
        import winreg
    except ImportError:
        return ""
    keywords = (
        "集成", "intel", "uhd graphics", "iris",
        "radeon(tm) graphics", "amd radeon graphics",
    )
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Video"
        ) as root:
            count, _, _ = winreg.QueryInfoKey(root)
            for i in range(count):
                sub = winreg.EnumKey(root, i)
                try:
                    with winreg.OpenKey(root, sub) as key:
                        for name in ("Device Description", "DriverDesc"):
                            try:
                                text, _ = winreg.QueryValueEx(key, name)
                            except OSError:
                                continue
                            lowered = str(text).lower()
                            if any(word in lowered for word in keywords):
                                return str(text)
                except OSError:
                    continue
    except OSError:
        return ""
    return ""


def mod_conflicts(game_dir: Path) -> list[str]:
    """扫描 mods 目录并返回冲突详情；没有冲突或读取失败返回空列表。"""
    try:
        from .content import detect_mod_conflicts, scan_mod_metadata
    except ImportError:
        return []
    mods_dir = Path(game_dir) / "mods"
    if not mods_dir.is_dir():
        return []
    try:
        metadata = scan_mod_metadata(mods_dir)
        return [
            str(item.get("detail") or item.get("modid") or item.get("type") or "")
            for item in detect_mod_conflicts(metadata)
        ]
    except Exception:  # noqa: BLE001
        return []


def preflight_report(game_dir: Path, memory_mb: int) -> dict:
    """启动前检查：blocked 为红标阻止项，warnings 为黄标警告。"""
    blocked: list[str] = []
    warnings: list[str] = []
    total_mb = total_physical_memory_mb()
    if total_mb > 0 and int(memory_mb or 0) > int(total_mb * 0.7):
        warnings.append(
            f"分配内存 {int(memory_mb)} MB 超过物理内存 70%（共 {total_mb} MB），可能出现内存不足或卡顿。"
        )
    try:
        free_gb = shutil.disk_usage(game_dir).free / (1024**3)
        if free_gb <= 2.0:
            blocked.append(f"磁盘剩余空间不足：仅剩 {free_gb:.1f} GB（需大于 2 GB）。")
    except OSError:
        pass
    conflicts = mod_conflicts(game_dir)
    if conflicts:
        blocked.append(
            f"检测到 {len(conflicts)} 个 Mod 冲突：\n" + "\n".join(f"- {t}" for t in conflicts[:3])
        )
    shader_dir = Path(game_dir) / "shaderpacks"
    has_shaders = shader_dir.is_dir() and any(shader_dir.iterdir())
    gpu = integrated_gpu_name()
    if gpu and has_shaders:
        warnings.append(f"检测到集成显卡（{gpu}）且已启用光影包，游戏性能可能不足。")
    return {"blocked": blocked, "warnings": warnings}
