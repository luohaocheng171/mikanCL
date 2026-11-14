"""本机硬件探测：物理内存、CPU 线程数与内存分配建议。"""

from __future__ import annotations

import os


def total_memory_mb() -> int:
    """读取物理内存总量（MB）；非 Windows 或读取失败返回 0。"""
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
    except Exception:  # noqa: BLE001 - 探测失败时按未知处理
        pass
    return 0


def cpu_logical_count() -> int:
    try:
        return int(os.cpu_count() or 0)
    except (TypeError, ValueError):
        return 0


def recommend_memory_mb(total_mb: int | None = None) -> int:
    """按物理内存 25% 建议游戏内存（512MB 对齐，2–8 GB）。

    4 GB 及以下的小内存机器给 1 GB，避免系统被挤爆；读不到内存时给 4 GB。
    """
    total = int(total_mb if total_mb is not None else total_memory_mb())
    if total <= 0:
        return 4096
    if total <= 4096:
        return 1024
    raw = (total * 25 // 100) // 512 * 512
    return max(2048, min(8192, raw))


def memory_summary() -> str:
    """返回形如 “15.9 GB 内存 · 16 线程 CPU” 的简短描述。"""
    parts: list[str] = []
    total = total_memory_mb()
    if total:
        parts.append(f"{total / 1024:.1f} GB 内存")
    cores = cpu_logical_count()
    if cores:
        parts.append(f"{cores} 线程 CPU")
    return " · ".join(parts)
