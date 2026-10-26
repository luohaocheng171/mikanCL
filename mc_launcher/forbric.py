"""Forbric 三合一加载器（实验性）：抓取安装器、引导官方 GUI 安装、轮询版本文件。

Forbric 兼容 Fabric / Forge / NeoForge，但底层构建强绑定 Minecraft 26.2。
"""

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

from .config import CACHE_DIR
from .content import ContentError
from .net import Candidate, Http, USER_AGENT

FORBRIC_SUPPORTED_MC = "26.2"
FORBRIC_VERSION_ID = "26.2-forbric"
FORBRIC_TIMEOUT = 1800  # 秒：等待官方安装器写入版本文件的超时时间

_GITHUB_RELEASE_URL = (
    "https://api.github.com/repos/Ray-T-r/Minecraft-Forbric-mod-loader/releases/latest"
)


def is_forbric_supported(mc_version: str | None) -> bool:
    """空版本视为支持（默认全局目录），否则仅支持 26.2。"""
    value = (mc_version or "").strip()
    return not value or value == FORBRIC_SUPPORTED_MC


def fetch_latest_installer() -> tuple[str, str]:
    """从 GitHub 抓取最新版安装器，返回 (jar 下载地址, bat 下载地址)。"""
    http = Http(timeout=30)
    last_error: Exception | None = None
    for attempt in range(3):  # 用户网络不稳定，最多重试 3 次
        try:
            data = http.get_json_url(_GITHUB_RELEASE_URL, headers={"User-Agent": USER_AGENT})
            assets = data.get("assets") if isinstance(data, dict) else None
            if not isinstance(assets, list):
                raise ContentError("GitHub 发布信息格式不正确（缺少 assets）。")
            jar_url = ""
            bat_url = ""
            for asset in assets:
                if not isinstance(asset, dict):
                    continue
                name = str(asset.get("name") or "").lower()
                url = str(asset.get("browser_download_url") or "")
                if not url:
                    continue
                if name.endswith(".jar") and ("forbric" in name or "kernel" in name):
                    jar_url = url
                elif name.endswith(".bat"):
                    bat_url = url
            if not jar_url:
                raise ContentError("发布中没有找到 forbric-kernel-installer-*.jar。")
            if not bat_url:
                raise ContentError("发布中没有找到 Forbric-Installer.bat。")
            return jar_url, bat_url
        except Exception as exc:  # noqa: BLE001 - 请求失败做简单重试
            last_error = exc
            if attempt < 2:
                time.sleep(1 + attempt)  # 1~2 秒
    raise ContentError(f"获取 Forbric 最新安装器失败：{last_error}")


def download_installer(
    jar_url: str, bat_url: str, log: Callable[[str], None] | None = None
) -> Path:
    """下载 jar / bat 到缓存目录，返回 jar 路径；失败抛 ContentError。"""
    folder = CACHE_DIR / "forbric"
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ContentError(f"无法创建 Forbric 缓存目录 {folder}：{exc}") from exc
    jar_dest = folder / "forbric-kernel-installer.jar"
    bat_dest = folder / "Forbric-Installer.bat"
    try:
        if log:
            log("[Forbric] 下载安装器 jar…")
        Http(timeout=60).download(
            [Candidate(jar_url, {"User-Agent": USER_AGENT}, "forbric", "Forbric GitHub")],
            jar_dest,
        )
        if log:
            log("[Forbric] 下载 Forbric-Installer.bat…")
        Http(timeout=60).download(
            [Candidate(bat_url, {"User-Agent": USER_AGENT}, "forbric", "Forbric GitHub")],
            bat_dest,
        )
    except Exception as exc:  # noqa: BLE001 - 统一转为 ContentError
        raise ContentError(f"下载 Forbric 安装器失败：{exc}") from exc
    return jar_dest


def launch_installer(
    jar_path: Path, java_path: str, log: Callable[[str], None] | None = None
) -> subprocess.Popen:
    """用指定 Java 启动官方安装器 GUI。不要加 CREATE_NO_WINDOW，否则窗口弹不出来。"""
    if log:
        log(f"[Forbric] 启动安装器：{java_path} -jar {jar_path}")
    return subprocess.Popen(
        [java_path, "-jar", str(jar_path)],
        cwd=jar_path.parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def wait_for_version(
    game_dir: Path, cancel: threading.Event | None, log: Callable[[str], None] | None = None
) -> bool:
    """每 2 秒轮询版本文件；生成返回 True，取消返回 False，超时抛 ContentError。"""
    target = Path(game_dir) / "versions" / FORBRIC_VERSION_ID / f"{FORBRIC_VERSION_ID}.json"
    deadline = time.monotonic() + FORBRIC_TIMEOUT
    while True:
        if target.is_file():
            if log:
                log(f"[Forbric] 检测到版本文件：{target}")
            return True
        if cancel is not None and cancel.is_set():
            return False
        if time.monotonic() >= deadline:
            raise ContentError(
                f"Forbric 安装超时（{FORBRIC_TIMEOUT // 60} 分钟），"
                "请确认已在官方安装器窗口中点击 Install。"
            )
        time.sleep(2)
