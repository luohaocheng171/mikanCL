"""实例健康度：把版本 / 依赖 / Mod 冲突 / 内存配置等分散检查汇总成一个结论。

页面只需要读取 level（green / yellow / red）与 issues 列表即可展示指示器，
不必再各自拼装检查逻辑。
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config
from .dependencies import scan_missing
from .version import load_version

_RED_KINDS = {"version", "client", "library", "java"}


@dataclass(frozen=True)
class HealthReport:
    level: str  # green / yellow / red
    label: str
    issues: list[str] = field(default_factory=list)


def _total_memory_mb() -> int:
    try:
        class MemoryStatusEx(ctypes.Structure):
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

        status = MemoryStatusEx()
        status.dwLength = ctypes.sizeof(MemoryStatusEx)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.ullTotalPhys // (1024 * 1024))
    except Exception:
        pass
    return 0


def _mod_issue(mods_dir: Path) -> tuple[list[str], list[str]]:
    """返回 (红色问题, 黄色问题)。检测失败时按无问题处理，避免误报。"""
    red: list[str] = []
    yellow: list[str] = []
    if not mods_dir.is_dir():
        return red, yellow
    try:
        from .content import detect_mod_conflicts, scan_mod_metadata

        metadata = scan_mod_metadata(mods_dir)
        conflicts = detect_mod_conflicts(metadata)
    except Exception:
        return red, yellow
    for conflict in conflicts:
        detail = str(conflict.get("detail") or conflict.get("modid") or "")
        if str(conflict.get("type") or "") == "missing_dependency":
            yellow.append(f"缺少前置：{detail}".rstrip("："))
        else:
            red.append(f"Mod 冲突：{detail}" if detail else "存在 Mod 冲突")
    return red, yellow


def instance_health(
    config: Config,
    version_id: str,
    javas: list,
    game_dir: Path | None = None,
) -> HealthReport:
    """聚合检查某个版本/实例，返回可直接展示的健康度结论。"""
    version_id = str(version_id or "").strip()
    if not version_id:
        return HealthReport("yellow", "未绑定版本", ["当前实例还没有绑定可启动的版本"])

    base = Path(game_dir) if game_dir is not None else config.game_path
    try:
        load_version(base, version_id)
    except Exception as exc:  # noqa: BLE001 - 任何读取失败都视为损坏
        return HealthReport("red", "需修复", [f"版本文件无法读取：{exc}"])

    red: list[str] = []
    yellow: list[str] = []
    try:
        _merged, missing = scan_missing(config, version_id, javas)
        for item in missing:
            text = f"缺少{getattr(item, 'name', '') or getattr(item, 'kind', '')}"
            detail = str(getattr(item, "detail", "") or "")
            if detail:
                text += f"（{detail}）"
            if str(getattr(item, "kind", "")) in _RED_KINDS:
                red.append(text)
            else:
                yellow.append(text)
    except Exception:
        pass

    mod_red, mod_yellow = _mod_issue(base / "mods")
    red.extend(mod_red)
    yellow.extend(mod_yellow)

    total = _total_memory_mb()
    if total and int(config.memory_mb) > int(total * 0.7):
        yellow.append(
            f"内存分配 {int(config.memory_mb)} MB 超过物理内存的 70%，可能触发系统换页"
        )

    issues = red + yellow
    if red:
        return HealthReport("red", "需修复", issues)
    if yellow:
        return HealthReport("yellow", "有警告", issues)
    return HealthReport("green", "健康", [])
