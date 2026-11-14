"""整合包安装公共流水线。

拖拽导入（dropinstall.ModpackDropWorker）与内容中心安装（page_content.ContentInstallWorker）
原先各自实现了一遍「装基础版本 → 装加载器 → 校验 JSON → 刷 overrides」。
两边逻辑必须完全一致，否则改一处就会漏另一处，因此统一收敛到这里：

    pipeline = ModpackPipeline(ctx, target, log=..., cancel=..., pause=..., progress=...)
    version_id = pipeline.prepare(mc_version, loader, loader_version)
    pipeline.install_files(zip_path, meta)
    pipeline.register_instance(name, loader, mc_version, loader_version, modpack)

调用方只负责准备目标目录、解析整合包与展示进度。
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Callable

from .config import Instance, write_instance_manifest
from .content import ContentError
from .installer import GameInstaller
from .java import detect_java_installed, pick_java
from .modloader import install_loader, java_for_mc
from .net import Cancelled

# 进度回调签名：(百分比, 详情, 阶段, 速度, 已完成文件, 文件总数)
ProgressFn = Callable[[float, str, str, float, int, int], None]

_LOADER_PREFIXES = (
    ("neoforge", "neoforge"),
    ("forge", "forge"),
    ("fabric", "fabric"),
    ("quilt", "quilt"),
    ("liteloader", "liteloader"),
)


def _version_tuple(value: str) -> tuple[int, ...]:
    """把版本号转成可比较元组；末尾的 .0 会被忽略（1.20 与 1.20.0 等价）。"""
    parts = [int(item) for item in re.findall(r"\d+", value or "")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def _mc_from_version_id(version_id: str) -> str:
    """从版本 ID 中猜出 Minecraft 版本，例如 fabric-loader-0.15.11-1.20.1。"""
    candidates = re.findall(r"(?<![\d.])(\d+\.\d+(?:\.\d+)?)(?![\d.])", version_id or "")
    for item in candidates:
        if item.startswith("1."):
            return item
    return candidates[-1] if candidates else ""


def _loader_from_version_id(version_id: str) -> str:
    lowered = (version_id or "").lower()
    for key, prefix in _LOADER_PREFIXES:
        if key in lowered or prefix in lowered:
            return key
    return ""


def check_attach_target(
    version_id: str,
    mc_version: str,
    loader: str = "",
    *,
    target_mc: str = "",
    target_loader: str = "",
) -> str:
    """校验整合包能否附加到所选版本；返回空串表示可以附加。"""
    if not (version_id or "").strip():
        return "请选择一个已安装的游戏版本。"
    wanted = _version_tuple(mc_version)
    actual = _version_tuple(target_mc or _mc_from_version_id(version_id))
    if wanted and actual and wanted != actual:
        return (
            f"版本不匹配：整合包要求 Minecraft {mc_version}，"
            f"所选版本是 {target_mc or version_id}。"
            "请选择版本一致的实例，或改用「下载全新版本安装」。"
        )
    pack_loader = (loader or "").strip().lower()
    if pack_loader in ("vanilla", "原版"):
        pack_loader = ""
    actual_loader = (target_loader or _loader_from_version_id(version_id)).lower()
    if pack_loader != actual_loader:
        pack_name = pack_loader or "原版"
        actual_name = actual_loader or "原版"
        return (
            f"加载器不匹配：整合包使用 {pack_name}，所选版本是 {actual_name}。"
            "附加模式不会安装加载器，请选择加载器一致的版本，"
            "或改用「下载全新版本安装」。"
        )
    return ""



def _find_installed_loader(target: Path, mc_version: str, loader: str) -> str:
    """在目标目录里找已安装的同版本加载器，避免重复安装。"""
    versions = Path(target) / "versions"
    if not loader or not versions.is_dir():
        return ""
    lowered = loader.lower()
    prefixes = {
        "forge": ("forge-",),
        "neoforge": ("neoforge-",),
        "fabric": ("fabric-loader-",),
        "quilt": ("quilt-loader-",),
        "liteloader": ("liteloader-",),
    }.get(lowered, (f"{lowered}-",))
    for entry in versions.iterdir():
        if not entry.is_dir() or not entry.name.startswith(prefixes):
            continue
        if (entry / f"{entry.name}.json").is_file():
            return entry.name
    return ""


class ModpackPipeline:
    """一条整合包安装流水线。线程安全由调用方（QThread）保证。"""

    def __init__(
        self,
        ctx,
        target: Path,
        *,
        log: Callable[[str], None],
        cancel,
        pause,
        progress: ProgressFn | None = None,
        version_id: str = "",
    ):
        self.ctx = ctx
        self.target = Path(target)
        self.log = log
        self.cancel = cancel
        self.pause = pause
        self.progress = progress
        # 已存在的加载器版本 ID（恢复实例时由清单提供）
        self.version_id = version_id

    # ------------------------------------------------------------------
    def _emit(
        self,
        value: float,
        detail: str = "",
        stage: str = "",
        speed: float = 0.0,
        files_done: int = 0,
        files_total: int = 0,
    ) -> None:
        if self.progress is None:
            return
        self.progress(
            max(0.0, min(1.0, value)), detail, stage, speed, files_done, files_total
        )

    def _check_cancel(self) -> None:
        if self.cancel.is_set():
            raise Cancelled()

    # ------------------------------------------------------------------
    # ① 基础版本 + ② 加载器 + ③ 校验
    # ------------------------------------------------------------------
    def _make_installer(self) -> GameInstaller:
        return GameInstaller(
            self.ctx.config.with_game_dir(self.target),
            self.ctx.sources,
            progress_cb=lambda p: self._emit(
                0.05 + p.percent * 0.4,
                p.detail,
                stage=p.stage,
                speed=p.speed,
                files_done=p.files_done,
                files_total=p.files_total,
            ),
            log_cb=self.log,
            cancel=self.cancel,
            pause=self.pause,
        )

    def _install_base_version(self, installer: GameInstaller, mc_version: str, strict: bool = True) -> bool:
        """完整安装基础版本，失败自动重试最多 3 次。

        版本清单中找不到时：strict=True 抛错，strict=False 返回 False。
        """
        payload, _name, _cached = self.ctx.sources.get_manifest()
        entries = payload.get("data", {}).get("versions", [])
        entry = next((v for v in entries if str(v.get("id")) == mc_version), None)
        if entry is None:
            if not strict:
                return False
            raise ContentError(f"版本清单中找不到 Minecraft {mc_version}。")
        last_error: Exception | None = None
        for attempt in range(3):
            self._check_cancel()
            try:
                installer.install_version(entry)
                return True
            except Cancelled:
                raise
            except Exception as exc:  # noqa: BLE001 - 网络抖动自动重试
                last_error = exc
                self.log(
                    f"[整合包] 安装基础版本 {mc_version} 失败（第 {attempt + 1} 次）：{exc}"
                )
                if attempt < 2:
                    time.sleep(1)
        raise ContentError(f"Minecraft {mc_version} 安装失败（已重试 3 次）：{last_error}")

    def _install_loader(
        self,
        installer: GameInstaller,
        mc_version: str,
        loader: str,
        loader_version: str,
    ) -> str:
        """安装加载器；已有同版本加载器时直接复用。"""
        existing = _find_installed_loader(self.target, mc_version, loader)
        if existing:
            self.log(f"[整合包] 已安装 {loader}（{existing}），跳过加载器安装。")
            return existing
        self._emit(0.47, f"安装 {loader} 加载器…", stage=f"安装 {loader} 加载器")
        javas = self.ctx.javas or detect_java_installed()
        if javas and not self.ctx.javas:
            # 启动扫描尚未完成时兜底，避免误报“未找到可用 Java”
            self.ctx.javas = javas
        java, warning = pick_java(javas, java_for_mc(mc_version))
        if java is None:
            raise ContentError(
                f"整合包需要 Java {java_for_mc(mc_version)}，未找到可用 Java。{warning}"
            )
        last_error: Exception | None = None
        for attempt in range(3):
            self._check_cancel()
            try:
                version_id = install_loader(
                    installer,
                    loader,
                    mc_version,
                    loader_version,
                    java_path=java.path,
                    log=self.log,
                    cancel=self.cancel,
                )
                self.log(f"[整合包] 加载器版本：{version_id}")
                return version_id
            except Cancelled:
                raise
            except Exception as exc:  # noqa: BLE001 - 网络抖动自动重试
                last_error = exc
                self.log(
                    f"[整合包] 安装 {loader} 加载器失败（第 {attempt + 1} 次）：{exc}"
                )
                if attempt < 2:
                    time.sleep(1)
        raise ContentError(f"{loader} 加载器安装失败（已重试 3 次）：{last_error}")

    def _validate_version(self, mc_version: str, version_id: str) -> str:
        """确认版本 JSON 存在；加载器 JSON 缺失时回退原版，原版也缺失则中止。"""
        if (self.target / "versions" / version_id / f"{version_id}.json").is_file():
            return version_id
        fallback = self.target / "versions" / mc_version / f"{mc_version}.json"
        if fallback.is_file():
            self.log(
                f"[警告] 未找到加载器版本 {version_id} 的 JSON，已回退到原版 {mc_version}。"
            )
            return mc_version
        raise ContentError(
            f"版本安装失败：Minecraft {mc_version}（或加载器）未生成有效的版本 JSON，"
            "为保证启动可用，未写入整合包内容。"
        )

    def prepare(
        self,
        mc_version: str,
        loader: str = "",
        loader_version: str = "",
        *,
        strict_base: bool = True,
        preferred_version_id: str = "",
    ) -> str:
        """执行 ①②③，返回最终可启动的版本 ID。"""
        version_id = preferred_version_id or self.version_id or mc_version
        installer = self._make_installer()
        self._check_cancel()
        version_json = self.target / "versions" / mc_version / f"{mc_version}.json"
        if version_json.is_file():
            self.log(f"[整合包] 基础版本 {mc_version} 已存在，跳过。")
        else:
            self.log(f"[整合包] 安装基础版本 {mc_version}…")
            if not self._install_base_version(installer, mc_version, strict=strict_base):
                # 直装包允许版本清单里暂时没有该版本
                return ""
        if loader:
            version_id = self._install_loader(
                installer, mc_version, loader, loader_version
            )
            self.version_id = version_id
        return self._validate_version(mc_version, version_id)

    # ------------------------------------------------------------------
    # ④ overrides + mods
    # ------------------------------------------------------------------
    def install_files(self, source: Path, meta) -> None:
        self._check_cancel()
        self._emit(0.6, "准备下载整合包文件…", stage="下载整合包内容")

        def _files_progress(done: int, total: int) -> None:
            ratio = (done / total) if total else 0.0
            self._emit(
                0.6 + ratio * 0.3,
                f"{done}/{total} 文件",
                stage="下载整合包内容",
                files_done=done,
                files_total=total,
            )

        self.ctx.content.install_modpack_files(
            source,
            meta,
            self.target,
            log=self.log,
            cancel=self.cancel,
            progress=lambda value, detail: self._emit(
                0.6 + value * 0.35, detail, stage="下载整合包内容"
            ),
            pause=self.pause,
            files_progress=_files_progress,
        )

    def attach_files(
        self,
        version_id: str,
        source: Path,
        meta,
        *,
        root: Path | None = None,
        target_mc: str = "",
        target_loader: str = "",
    ) -> Path:
        """把整合包内容写入已有版本的游戏目录（不下载原版、不建实例）。"""
        error = check_attach_target(
            version_id,
            str(getattr(meta, "mc_version", "") or ""),
            str(getattr(meta, "loader", "") or ""),
            target_mc=target_mc,
            target_loader=target_loader,
        )
        if error:
            raise ContentError(error)
        target = self.ctx.config.resolve_game_dirs(version_id, root=root).primary
        self.target = Path(target)
        self.log(f"[整合包] 附加到已有版本 {version_id}：{self.target}")
        self.install_files(source, meta)
        return self.target

    # ------------------------------------------------------------------
    # 实例登记
    # ------------------------------------------------------------------
    def register_instance(
        self,
        name: str,
        *,
        version_id: str,
        loader: str = "",
        mc_version: str = "",
        loader_version: str = "",
        modpack: str = "",
        memory_mb: int = 0,
        window_title: str = "",
        extra_jvm_args: str = "",
    ) -> Instance:
        """同目录同版本复用已有实例，避免实例列表出现重复项。"""
        target_key = os.path.normcase(os.path.normpath(str(self.target)))
        instance = next(
            (
                item
                for item in self.ctx.config.instance_list()
                if item.version_id == version_id
                and os.path.normcase(os.path.normpath(item.game_dir)) == target_key
            ),
            None,
        )
        if instance is None:
            instance = self.ctx.config.add_instance(
                name,
                str(self.target),
                version_id=version_id,
                loader=loader,
                mc_version=mc_version,
                modpack=modpack,
                loader_version=loader_version,
                memory_mb=memory_mb,
                window_title=window_title,
                extra_jvm_args=extra_jvm_args,
            )
        write_instance_manifest(instance, self.target)
        self.ctx.config.select_instance(instance.id)
        self.ctx.config.save()
        self.ctx.bus.instances_changed.emit()
        return instance


__all__ = ["ModpackPipeline", "_find_installed_loader"]
