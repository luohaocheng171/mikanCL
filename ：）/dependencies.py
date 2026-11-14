"""第三方模块清单与游戏依赖检查：把「缺什么」和「怎么补」集中在这里。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import auth, forbric, terracotta
from .config import DATA_DIR, Config
from .java import JavaInfo
from .version import (
    MergedVersion,
    VersionError,
    client_jar_path,
    load_version,
    logging_file_path,
)

# 第三方模块下载免责声明：展示在新页面顶部，并同步写入用户协议
DISCLAIMER = (
    "本页集中列出所有因许可、体积或官方分发渠道限制而无法随启动器内置的第三方依赖。"
    "以下模块仅为方便用户而提供下载 / 跳转入口，均由各自作者独立维护，"
    "MikanCL 与其作者无隶属、授权或担保关系。下载、安装或使用过程中出现的任何问题"
    "（包括但不限于游戏崩溃、存档或文件损坏、账号风险等）由使用者自行承担，"
    "MikanCL 作者概不负责。请自行确认来源与许可后再使用。"
)


def authlib_injector_path(config: Config) -> Path:
    if config.authlib_injector_path:
        return Path(config.authlib_injector_path)
    return auth.injector_jar_path()


def _java_runtime_entry(javas: list[JavaInfo] | None) -> dict:
    """汇总本机已检测到的 Java；没有则提示前往 Java 中心获取。"""
    detected = [j for j in (javas or []) if getattr(j, "path", "")]
    return {
        "id": "java-runtime",
        "name": "Java 运行时（JRE / JDK）",
        "category": "运行环境",
        "summary": "Minecraft 必需运行时；各发行版许可不同且体积较大，不适合随启动器打包",
        "license": "各发行版不同（GPLv2+CE 等）",
        "homepage": "https://adoptium.net/",
        "installed": bool(detected),
        "path": str(detected[0].path) if detected else str(DATA_DIR / "runtime"),
        "version": f"已检测 {len(detected)} 个" if detected else "未检测到",
        "action": "navigate",
        "target": "java",
        "action_text": "前往 Java 中心",
    }


def _forbric_installed(config: Config) -> bool:
    target = (
        config.game_path
        / "versions"
        / forbric.FORBRIC_VERSION_ID
        / f"{forbric.FORBRIC_VERSION_ID}.json"
    )
    return target.is_file()


def third_party_modules(
    config: Config, javas: list[JavaInfo] | None = None
) -> list[dict]:
    """返回所有不可内置的第三方依赖清单（含安装状态），供依赖页表格展示。

    覆盖联机、登录、运行环境与加载器四类：前两类可在本页直接下载，
    后两类因安装流程依赖官方安装器，只提供「前往对应页面」的跳转入口。
    """
    injector = authlib_injector_path(config)
    installed_injector = injector.exists() and injector.stat().st_size > 1024
    try:
        terracotta_path = str(terracotta.install_dir())
    except Exception:  # noqa: BLE001 - 不支持的架构只在下载时才会报错
        terracotta_path = ""
    return [
        {
            "id": "terracotta",
            "name": "陶瓦联机（Terracotta）",
            "category": "联机组件",
            "summary": "房间码 P2P 联机组件，多人联机页依赖此运行时；AGPL-3.0 独立程序，不能内置",
            "license": "AGPL-3.0",
            "homepage": "https://terracotta.glavo.site",
            "installed": terracotta.is_installed(),
            "path": terracotta_path,
            "version": terracotta.TERRACOTTA_VERSION,
            "action": "install",
            "target": "",
            "action_text": "下载",
        },
        {
            "id": "authlib-injector",
            "name": "authlib-injector",
            "category": "登录组件",
            "summary": "外置登录（皮肤站）所需的 Java agent 注入组件；AGPL-3.0，由作者单独发布",
            "license": "AGPL-3.0",
            "homepage": "https://authlib-injector.yushi.moe",
            "installed": installed_injector,
            "path": str(injector),
            "version": "最新版",
            "action": "install",
            "target": "",
            "action_text": "下载",
        },
        _java_runtime_entry(javas),
        {
            "id": "mod-loaders",
            "name": "Mod 加载器（Forge / Fabric / NeoForge / Quilt）",
            "category": "Mod 加载器",
            "summary": "需按游戏版本调用官方安装器生成，许可与版本各不相同，不能随启动器打包",
            "license": "各自开源许可（LGPL-2.1 / Apache-2.0 等）",
            "homepage": "https://fabricmc.net/",
            "installed": None,
            "path": "",
            "version": "按版本安装",
            "action": "navigate",
            "target": "loaders",
            "action_text": "前往 Mod 加载器",
        },
        {
            "id": "forbric",
            "name": "Forbric 加载器",
            "category": "Mod 加载器",
            "summary": "实验性加载器，安装器取自作者 GitHub 发布页，仅支持指定版本且不内置",
            "license": "作者仓库声明为准",
            "homepage": "https://github.com/Ray-T-r/Minecraft-Forbric-mod-loader",
            "installed": _forbric_installed(config),
            "path": "",
            "version": forbric.FORBRIC_VERSION_ID,
            "action": "navigate",
            "target": "forbric",
            "action_text": "前往 Forbric",
        },
    ]


def install_third_party(
    module_id: str,
    config: Config,
    log: Callable[[str], None] | None = None,
    progress: Callable[[float, str], None] | None = None,
    cancel=None,
) -> str:
    """下载并安装指定第三方模块，返回安装后的路径。"""
    key = str(module_id or "").strip().lower()
    if key == "terracotta":
        return str(terracotta.install(log=log, progress=progress, cancel=cancel))
    if key == "authlib-injector":
        return str(auth.ensure_authlib_injector(config, log=log))
    raise ValueError(f"未知的第三方模块：{module_id}")


# ---------------------------------------------------------------------------
# 游戏依赖检查
# ---------------------------------------------------------------------------
@dataclass
class MissingItem:
    """一条缺失依赖记录。kind 决定补全方式：java 走 Java 下载，其余走版本文件补全。"""

    kind: str
    name: str
    detail: str = ""

    @property
    def is_java(self) -> bool:
        return self.kind == "java"


def required_java(merged: MergedVersion) -> int:
    try:
        return int(merged.java_major or 21)
    except (TypeError, ValueError):
        return 21


def _asset_objects_missing(config: Config, merged: MergedVersion) -> tuple[int, int]:
    """返回 (缺失资源对象数, 资源对象总数)；索引文件缺失时返回 (-1, 0)。"""
    assets_id = str(merged.assets_id or "")
    index_path = config.assets_path / "indexes" / f"{assets_id}.json"
    if not index_path.is_file():
        return -1, 0
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return -1, 0
    objects = data.get("objects") if isinstance(data, dict) else None
    if not isinstance(objects, dict):
        return 0, 0
    total = 0
    missing = 0
    objects_dir = config.assets_path / "objects"
    for info in objects.values():
        if not isinstance(info, dict):
            continue
        sha1 = str(info.get("hash") or "")
        if not sha1:
            continue
        total += 1
        if not (objects_dir / sha1[:2] / sha1).is_file():
            missing += 1
    return missing, total


def scan_missing(
    config: Config, version_id: str, javas: list[JavaInfo]
) -> tuple[MergedVersion | None, list[MissingItem]]:
    """检查某版本是否缺少 Java / 客户端 / 依赖库 / 资源 / 日志配置。

    返回 (合并后的版本信息或 None, 缺失项列表)。读取版本失败时返回一条 kind="version"。
    """
    game_dir = config.game_path
    try:
        merged = load_version(game_dir, version_id)
    except (VersionError, OSError) as exc:
        return None, [MissingItem("version", version_id, str(exc))]

    items: list[MissingItem] = []

    java_major = required_java(merged)
    if not any(int(getattr(j, "major", 0) or 0) >= java_major for j in javas or []):
        items.append(
            MissingItem(
                "java",
                f"Java {java_major}",
                "未检测到满足要求的 Java，补全将下载 Adoptium JRE",
            )
        )

    client = merged.client_download or {}
    jar_path = client_jar_path(game_dir, merged.jar_id)
    if not jar_path.is_file() and str(client.get("url") or ""):
        items.append(MissingItem("client", f"客户端 {merged.jar_id}.jar", str(jar_path)))

    missing_libs = [
        lib
        for lib in merged.libraries
        if str(lib.url or "") and not (config.libraries_path / lib.path).is_file()
    ]
    if missing_libs:
        items.append(
            MissingItem(
                "library",
                f"依赖库（缺 {len(missing_libs)} 个）",
                f"共 {len(merged.libraries)} 个，例如 {missing_libs[0].path}",
            )
        )

    missing_objects, total_objects = _asset_objects_missing(config, merged)
    if missing_objects < 0:
        items.append(
            MissingItem("assets", "资源索引", f"缺少 indexes/{merged.assets_id}.json")
        )
    elif missing_objects:
        items.append(
            MissingItem(
                "assets",
                f"游戏资源（缺 {missing_objects} 个）",
                f"资源索引共 {total_objects} 个对象",
            )
        )

    log_path = logging_file_path(game_dir, merged.logging)
    if merged.logging and not log_path.is_file():
        items.append(MissingItem("logging", "日志配置", str(log_path)))

    return merged, items


def summarize_missing(items: list[MissingItem]) -> str:
    """把缺失项压成一行可读文本，供确认弹窗使用。"""
    return "、".join(item.name for item in items)
