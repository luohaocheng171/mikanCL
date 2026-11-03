"""智能 JVM 参数：按 Java 主版本选择 GC 与堆参数，降低 Minecraft 的 GC 卡顿与无谓开销。

Minecraft 会持续创建大量短命对象（实体、区块、网络包），G1GC + 较小的新生代占比
比默认参数更稳。这里的参数参考 PaperMC 的 Aikar's Flags，并针对客户端做了取舍：
- 堆 4 GB 以下不启用 AlwaysPreTouch，避免启动时一次性提交全部内存拖慢启动
- 用户自己写了 GC / 同名参数时自动跳过，避免冲突
"""

from __future__ import annotations

import re
import sys

from .hardware import total_memory_mb

_VERSION_1X_RE = re.compile(r"^1\.(\d+)(?:\.(\d+))?")
_VERSION_YEAR_RE = re.compile(r"^(\d{2})\.(\d+)")
_VERSION_SNAPSHOT_RE = re.compile(r"^(\d{2})w\d{2}")
_VERSION_OLD_RE = re.compile(r"^[abc]\d|^inf-|^rd-|^1\.rv|^2\.0$")

# 旧版 Forge（含修改过 jar 的整合包）需要放宽签名/补丁校验
LEGACY_FORGE_FLAGS = (
    "-Dfml.ignoreInvalidMinecraftCertificates=true",
    "-Dfml.ignorePatchDiscrepancies=true",
)
# Java 9+ 运行 1.12.2 及更早版本时，Forge / 部分模组会反射访问 JDK 内部包
LEGACY_ADD_OPENS = (
    "--add-opens=java.base/java.lang=ALL-UNNAMED",
    "--add-opens=java.base/java.util=ALL-UNNAMED",
    "--add-opens=java.base/java.lang.reflect=ALL-UNNAMED",
    "--add-opens=java.base/java.text=ALL-UNNAMED",
    "--add-opens=java.base/java.io=ALL-UNNAMED",
    "--add-opens=java.base/sun.nio.ch=ALL-UNNAMED",
    "--add-opens=java.desktop/java.awt.font=ALL-UNNAMED",
)


def _flag_key(flag: str) -> str:
    """用于判重的参数键：-XX:+X 与 -XX:-X 视为同一键，用户写任一形式都优先。"""
    if flag.startswith("-XX:"):
        body = flag[4:]
        if body[:1] in ("+", "-"):
            body = body[1:]
        return "-XX:" + body.split("=", 1)[0]
    if flag.startswith("-D"):
        return flag.split("=", 1)[0]
    return flag


def _gc_selector_present(existing: str) -> bool:
    text = existing or ""
    return any(
        f"-XX:+Use{gc}" in text or f"-XX:-Use{gc}" in text
        for gc in ("G1GC", "ZGC", "ShenandoahGC", "ParallelGC", "SerialGC", "EpsilonGC")
    )


def _filter_existing(args: list[str], existing: str) -> list[str]:
    """剔除用户已手动写过的同名参数，避免重复或覆盖用户配置。"""
    present = {_flag_key(item.split()[0]) for item in (existing or "").split() if item}
    seen: set[str] = set()
    result: list[str] = []
    for arg in args:
        key = _flag_key(arg)
        if key in present or key in seen:
            continue
        seen.add(key)
        result.append(arg)
    return result


def _mc_series(version_id: str) -> tuple[int, int, int] | None:
    """把版本号转成可比较元组：1.x → (1, x, y)，26.1 / 26w.. → (26, x, 0)。"""
    text = (version_id or "").strip()
    match = _VERSION_1X_RE.match(text)
    if match:
        return (1, int(match.group(1)), int(match.group(2) or 0))
    # 远古版本：a1.2.6 / b1.7.3 / c0.30 / inf-20100618 / rd-132211 / 1.rv-pre1
    if _VERSION_OLD_RE.match(text):
        return (1, 0, 0)
    match = _VERSION_YEAR_RE.match(text)
    if match:
        return (int(match.group(1)), int(match.group(2)), 0)
    match = _VERSION_SNAPSHOT_RE.match(text)
    if match:
        year = int(match.group(1))
        if year >= 26:
            return (year, 0, 0)
        # 17w43a 之前的快照属于 1.12 及更早（1.13 起不再需要 legacy 参数）
        if year <= 17:
            return (1, 12, 0)
        return (1, 21, 0)
    return None


def is_legacy_version(version_id: str) -> bool:
    """1.12.2 及更早版本需要旧版兼容参数（1.13 起 LWJGL3/新版启动参数已修复）。"""
    series = _mc_series(version_id)
    return series is not None and series < (1, 13, 0)


def uses_zgc_by_default(java_major: int, version_id: str) -> bool:
    """26.x 起官方默认改用分代 ZGC（需要 Java 25+）。"""
    series = _mc_series(version_id)
    return java_major >= 25 and series is not None and series[0] >= 26


def version_jvm_args(
    version_id: str, java_major: int, existing: str = ""
) -> list[str]:
    """按 Minecraft 版本补充兼容性参数（与性能开关无关，避免旧版本直接崩溃）。"""
    args: list[str] = []
    legacy = is_legacy_version(version_id)
    lowered = (version_id or "").lower()

    if legacy:
        # MC-129374：1.13-pre2 之前线程栈太小，整合包/Forge 容易 StackOverflow
        args.append("-Xss1M")
        # Java 7+ TimSort 对不合规比较器抛 IllegalArgumentException（MC-61156）
        args.append("-Djava.util.Arrays.useLegacyMergeSort=true")
        if "forge" in lowered and "neoforge" not in lowered:
            args.extend(LEGACY_FORGE_FLAGS)

    # 旧版本被手动指定到 Java 9+ 时，补上模块开放，避免反射访问被拒绝
    if legacy and java_major >= 9:
        args.extend(LEGACY_ADD_OPENS)

    # Java 24 起 JNI/FFM 受限访问需要显式放行，否则 LWJGL 会刷警告甚至失败
    if java_major >= 24:
        args.append("--enable-native-access=ALL-UNNAMED")

    # macOS + LWJGL3 必须在主线程启动
    if sys.platform == "darwin" and not legacy and java_major >= 8:
        args.append("-XstartOnFirstThread")

    return _filter_existing(args, existing)


def smart_jvm_args(
    java_major: int, memory_mb: int, existing: str = "", mc_version: str = ""
) -> list[str]:
    """返回适配该 Java 版本、游戏版本与堆大小的调优参数（不含 -Xmx / -Xms）。"""
    if java_major <= 0:
        return []
    # Java 7 及更早没有 G1 完整参数集，只补 PermGen 上限，避免旧版整合包 OOM
    if java_major < 8:
        return ["-XX:MaxPermSize=256M"]

    args: list[str] = ["-XX:+DisableExplicitGC", "-XX:+PerfDisableSharedMem"]

    if not _gc_selector_present(existing):
        if uses_zgc_by_default(java_major, mc_version):
            # 26.x 官方默认分代 ZGC（Java 25 起 Generational ZGC 已是默认模式）
            args.append("-XX:+UseZGC")
            if memory_mb >= 4096:
                args.append("-XX:+AlwaysPreTouch")
        else:
            region = "16M" if memory_mb >= 12288 else "8M"
            args.extend(
                [
                    "-XX:+UseG1GC",
                    "-XX:+ParallelRefProcEnabled",
                    "-XX:MaxGCPauseMillis=200",
                    "-XX:+UnlockExperimentalVMOptions",
                    "-XX:G1NewSizePercent=30",
                    "-XX:G1MaxNewSizePercent=40",
                    f"-XX:G1HeapRegionSize={region}",
                    "-XX:G1ReservePercent=20",
                    "-XX:G1HeapWastePercent=5",
                    "-XX:G1MixedGCCountTarget=4",
                    "-XX:InitiatingHeapOccupancyPercent=15",
                    "-XX:G1MixedGCLiveThresholdPercent=90",
                    "-XX:G1RSetUpdatingPauseTimePercent=5",
                    "-XX:SurvivorRatio=32",
                    "-XX:MaxTenuringThreshold=1",
                    "-Dusing.aikars.flags=https://mcflags.emc.gs",
                    "-Daikars.new.flags=true",
                ]
            )
            # 大堆预触碰可以稳定内存布局，但会延长启动；小堆不加
            if memory_mb >= 4096:
                args.append("-XX:+AlwaysPreTouch")

    return _filter_existing(args, existing)


def jvm_summary(
    java_major: int, memory_mb: int, mc_version: str = "", existing: str = ""
) -> str:
    """给日志/界面用的简短描述。"""
    if java_major <= 0:
        gc = "Java 版本未知"
    elif java_major < 8:
        gc = "Java 7 默认 GC（PermGen 256M）"
    elif _gc_selector_present(existing):
        gc = "自定义 GC（已保留你的参数）"
    elif uses_zgc_by_default(java_major, mc_version):
        gc = "ZGC（26.x 默认）"
    else:
        gc = "G1GC" if java_major >= 9 else "G1GC（Java 8 实验参数）"
    return f"Java {java_major} · {memory_mb} MB · {gc}"


def memory_warning(memory_mb: int) -> str:
    """分配内存超过物理内存 60% 时给出提示，避免系统换页拖慢游戏。"""
    total = total_memory_mb()
    if total and memory_mb > total * 0.6:
        return (
            f"已分配 {memory_mb} MB，超过本机物理内存的 60%（共 {total} MB），"
            "可能导致系统换页反而更卡；建议调低或关闭其他占内存程序。"
        )
    return ""


__all__ = [
    "is_legacy_version",
    "jvm_summary",
    "memory_warning",
    "smart_jvm_args",
    "uses_zgc_by_default",
    "version_jvm_args",
]
