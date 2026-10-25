"""游戏文件下载与安装/补全（客户端、依赖库、natives、资源文件）。"""

from __future__ import annotations

import json
import shutil
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .config import Config
from .net import (
    Cancelled,
    Candidate,
    DownloadError,
    Http,
    SourceManager,
)
from .version import (
    LibraryFile,
    MergedVersion,
    VersionError,
    client_jar_path,
    load_version,
    logging_file_path,
)


@dataclass
class Progress:
    stage: str = ""
    detail: str = ""
    percent: float = 0.0
    speed: float = 0.0


@dataclass
class DownloadTask:
    candidates: list[Candidate]
    dest: Path
    size: int = 0
    sha1: str = ""
    label: str = ""


class GameInstaller:
    def __init__(
        self,
        config: Config,
        sources: SourceManager,
        progress_cb: Callable[[Progress], None] | None = None,
        log_cb: Callable[[str], None] | None = None,
        cancel: threading.Event | None = None,
        pause: threading.Event | None = None,
    ):
        self.config = config
        self.sources = sources
        self.http = Http(timeout=30)
        self.progress_cb = progress_cb
        self.log_cb = log_cb
        self.cancel = cancel or threading.Event()
        self.pause = pause
        self._last_emit = 0.0

    # ------------------------------------------------------------------
    def log(self, message: str) -> None:
        if self.log_cb:
            self.log_cb(message)

    def report(self, stage: str, percent: float, detail: str = "", speed: float = 0.0) -> None:
        if self.progress_cb:
            self.progress_cb(Progress(stage, detail, max(0.0, min(percent, 1.0)), speed))

    def _check_cancel(self) -> None:
        if self.cancel.is_set():
            raise Cancelled()

    # ------------------------------------------------------------------
    def install_version(self, entry: dict, version_id: str | None = None) -> MergedVersion:
        """按版本清单条目安装一个原版版本。"""
        version_id = version_id or str(entry.get("id") or "")
        if not version_id:
            raise VersionError("版本清单条目缺少 id")
        game_dir = self.config.game_path
        game_dir.mkdir(parents=True, exist_ok=True)
        versions_dir = game_dir / "versions"
        version_dir = versions_dir / version_id
        version_dir.mkdir(parents=True, exist_ok=True)

        self.report("准备安装", 0.01, f"{version_id} · 来自 {self.config.selected_source_id}")
        self.log(f"[安装] 开始安装 {version_id} 到 {game_dir}")

        json_dest = version_dir / f"{version_id}.json"
        json_candidates = self.sources.resource_candidates(str(entry.get("url") or ""))
        self._batch_download(
            [
                DownloadTask(
                    candidates=json_candidates,
                    dest=json_dest,
                    sha1=str(entry.get("sha1") or ""),
                    label=f"{version_id}.json",
                )
            ],
            stage="获取版本信息",
            base=0.01,
            span=0.02,
            workers=1,
        )
        self._check_cancel()

        merged = load_version(game_dir, version_id)
        self.log(
            f"[安装] 版本信息：{merged.type}，主类 {merged.main_class}，"
            f"依赖库 {len(merged.libraries)} 个，Java {merged.java_major}"
        )

        self._install_client(merged, version_id, 0.03, 0.04)
        downloaded_libs = self._install_libraries(merged, version_id, 0.07, 0.23)
        self._extract_natives(merged, version_id, downloaded_libs, 0.30, 0.02)
        self._install_assets(merged, 0.32, 0.64)
        self._install_logging(merged, 0.97, 0.02)

        self.report("安装完成", 1.0, f"{version_id} 安装完成")
        self.log(f"[安装] {version_id} 安装完成")
        return merged

    # ------------------------------------------------------------------
    def ensure_version(self, version_id: str) -> MergedVersion:
        """启动前补全版本文件（对 HMCL/Forge/Fabric 等继承版本同样有效）。"""
        game_dir = self.config.game_path
        self.report("检查文件", 0.01, version_id)
        merged = load_version(game_dir, version_id)
        self.log(
            f"[检查] {version_id}（{merged.type}）· 客户端 {merged.jar_id} · "
            f"资源索引 {merged.asset_index.get('id') if merged.asset_index else '无'}"
        )
        self._install_client(merged, version_id, 0.02, 0.06)
        downloaded_libs = self._install_libraries(merged, version_id, 0.08, 0.22)
        self._extract_natives(merged, version_id, downloaded_libs, 0.30, 0.02)
        self._install_assets(merged, 0.32, 0.64, force_copy=True)
        self._install_logging(merged, 0.97, 0.02)
        self.report("文件检查完成", 1.0, version_id)
        return merged

    # ------------------------------------------------------------------
    def _install_client(self, merged: MergedVersion, version_id: str, base: float, span: float) -> None:
        client = merged.client_download or {}
        url = str(client.get("url") or "")
        dest = client_jar_path(self.config.game_path, merged.jar_id)
        if not url:
            if dest.exists():
                self.log(f"[检查] 客户端 {dest.name} 已存在")
                self.report("检查客户端", base, dest.name)
                return
            raise VersionError(
                f"版本 {version_id} 缺少客户端下载信息，且本地不存在 {dest}。\n"
                "这可能是一个需要先用 HMCL/官方安装器安装的整合包版本。"
            )
        self.report("下载客户端", base, f"{merged.jar_id}.jar")
        self._batch_download(
            [
                DownloadTask(
                    candidates=self.sources.resource_candidates(url),
                    dest=dest,
                    size=int(client.get("size") or 0),
                    sha1=str(client.get("sha1") or ""),
                    label=f"{merged.jar_id}.jar",
                )
            ],
            stage="下载客户端",
            base=base,
            span=span,
            workers=1,
        )

    def _install_libraries(
        self, merged: MergedVersion, version_id: str, base: float, span: float
    ) -> dict[str, LibraryFile]:
        self.report("下载依赖库", base, f"{len(merged.libraries)} 个依赖")
        tasks: list[DownloadTask] = []
        for lib in merged.libraries:
            dest = self.config.libraries_path / lib.path
            tasks.append(
                DownloadTask(
                    candidates=self.sources.resource_candidates(lib.url),
                    dest=dest,
                    size=lib.size,
                    sha1=lib.sha1,
                    label=lib.label,
                )
            )
        self._batch_download(tasks, stage="下载依赖库", base=base, span=span, workers=8)
        return {lib.path: lib for lib in merged.libraries}

    def _extract_natives(
        self,
        merged: MergedVersion,
        version_id: str,
        libs: dict[str, LibraryFile],
        base: float,
        span: float,
    ) -> None:
        native_files = [lib for lib in libs.values() if lib.extract]
        if not native_files:
            return
        natives_dir = self.config.game_path / "versions" / version_id / "natives"
        natives_dir.mkdir(parents=True, exist_ok=True)
        # 清理旧文件（仅限目录内部，避免历史 DLL 冲突）
        for child in natives_dir.iterdir():
            try:
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            except OSError:
                pass
        self.report("解压运行库", base, f"{len(native_files)} 个 natives")
        total = len(native_files)
        for index, lib in enumerate(native_files, start=1):
            self._check_cancel()
            jar_path = self.config.libraries_path / lib.path
            if not jar_path.exists():
                raise VersionError(f"缺少 natives 压缩包：{jar_path}")
            try:
                with zipfile.ZipFile(jar_path) as archive:
                    for info in archive.infolist():
                        if info.is_dir():
                            continue
                        name = info.filename
                        if any(name.startswith(prefix) for prefix in lib.exclude):
                            continue
                        if name.startswith("META-INF/"):
                            continue
                        target = (natives_dir / name).resolve()
                        try:
                            if not target.is_relative_to(natives_dir.resolve()):
                                continue
                        except AttributeError:  # Python < 3.9
                            if not str(target).startswith(str(natives_dir.resolve())):
                                continue
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(info) as src, open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)
            except (OSError, zipfile.BadZipFile) as exc:
                raise VersionError(f"解压 natives 失败：{lib.filename}\n{exc}") from exc
            self.report("解压运行库", base + span * index / total, lib.filename)
        self.log(f"[检查] 已解压 {total} 个 natives 到 {natives_dir}")

    def _install_assets(
        self, merged: MergedVersion, base: float, span: float, force_copy: bool = False
    ) -> None:
        index_info = merged.asset_index
        if not index_info:
            self.log("[检查] 该版本不需要资源索引")
            return
        index_id = str(index_info.get("id") or merged.assets_id)
        index_path = self.config.assets_path / "indexes" / f"{index_id}.json"
        self._batch_download(
            [
                DownloadTask(
                    candidates=self.sources.resource_candidates(str(index_info.get("url") or "")),
                    dest=index_path,
                    size=int(index_info.get("size") or 0),
                    sha1=str(index_info.get("sha1") or ""),
                    label=f"indexes/{index_id}.json",
                )
            ],
            stage="获取资源索引",
            base=base,
            span=0.01,
            workers=1,
        )
        try:
            index_data = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise VersionError(f"资源索引无法解析：{index_path}\n{exc}") from exc

        objects = index_data.get("objects")
        if not isinstance(objects, dict):
            raise VersionError(f"资源索引格式错误：{index_path}")

        object_tasks: list[DownloadTask] = []
        names: dict[str, str] = {}
        for name, obj in objects.items():
            if not isinstance(obj, dict):
                continue
            digest = str(obj.get("hash") or "")
            if len(digest) < 4:
                continue
            rel = f"{digest[:2]}/{digest}"
            object_tasks.append(
                DownloadTask(
                    candidates=self.sources.resource_candidates(
                        f"https://resources.download.minecraft.net/{rel}"
                    ),
                    dest=self.config.assets_path / "objects" / rel,
                    size=int(obj.get("size") or 0),
                    label=name,
                )
            )
            names[digest] = str(name)

        self.report("下载资源文件", base + 0.01, f"{len(object_tasks)} 个资源")
        self._batch_download(
            object_tasks,
            stage="下载资源文件",
            base=base + 0.01,
            span=span - 0.02,
            workers=12,
        )

        virtual = bool(index_data.get("virtual"))
        map_to_resources = bool(index_data.get("map_to_resources"))
        if virtual:
            target_root = self.config.assets_path / "virtual" / index_id
            self._copy_objects(objects, target_root, names)
            self.log(f"[检查] 已建立虚拟资源目录：{target_root}")
        if map_to_resources:
            target_root = self.config.game_path / "resources"
            self._copy_objects(objects, target_root, names)
            self.log(f"[检查] 已复制旧版资源到：{target_root}")

    def _copy_objects(self, objects: dict, target_root: Path, names: dict[str, str]) -> None:
        """旧版资源（virtual / map_to_resources）需要按原名复制。"""
        target_root.mkdir(parents=True, exist_ok=True)
        copied = 0
        for name, obj in objects.items():
            if not isinstance(obj, dict):
                continue
            digest = str(obj.get("hash") or "")
            if len(digest) < 4:
                continue
            src = self.config.assets_path / "objects" / digest[:2] / digest
            if not src.exists():
                continue
            rel_name = str(obj.get("name") or names.get(digest) or name)
            dest = target_root / rel_name
            if dest.exists() and dest.stat().st_size == src.stat().st_size:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(src, dest)
                copied += 1
            except OSError:
                continue
        if copied:
            self.log(f"[检查] 复制了 {copied} 个旧版资源文件")

    def _install_logging(self, merged: MergedVersion, base: float, span: float) -> None:
        logging = merged.logging
        if not logging:
            return
        file_info = logging.get("file") if isinstance(logging.get("file"), dict) else {}
        url = str(file_info.get("url") or "")
        if not url:
            return
        dest = logging_file_path(self.config.game_path, logging)
        dest.parent.mkdir(parents=True, exist_ok=True)
        self._batch_download(
            [
                DownloadTask(
                    candidates=self.sources.resource_candidates(url),
                    dest=dest,
                    size=int(file_info.get("size") or 0),
                    sha1=str(file_info.get("sha1") or ""),
                    label=dest.name,
                )
            ],
            stage="下载日志配置",
            base=base,
            span=span,
            workers=1,
        )

    # ------------------------------------------------------------------
    def _batch_download(
        self,
        tasks: list[DownloadTask],
        stage: str,
        base: float,
        span: float,
        workers: int = 0,
    ) -> None:
        if not tasks:
            return
        workers = workers or max(8, int(getattr(self.config, "download_threads", 16)))
        self._check_cancel()

        total_bytes = sum(task.size for task in tasks if task.size > 0)
        unknown_count = sum(1 for task in tasks if task.size <= 0)
        total_units = max(total_bytes, len(tasks))
        done_units = [0]
        missing: list[DownloadTask] = []
        lock = threading.Lock()
        started_at = time.time()
        emitted = [0.0]

        def emit(force: bool = False) -> None:
            now = time.time()
            if not force and now - emitted[0] < 0.12:
                return
            emitted[0] = now
            with lock:
                done = done_units[0]
            fraction = min(1.0, done / total_units)
            elapsed = max(0.001, now - started_at)
            speed = done / elapsed if done else 0.0
            detail = f"{done / 1048576:.1f} / {total_units / 1048576:.1f} MB"
            if unknown_count:
                detail += f" · {unknown_count} 个未知大小"
            self.report(stage, base + span * fraction, detail, speed)

        self.report(stage, base, f"检查 {len(tasks)} 个文件…")
        for task in tasks:
            if self.cancel.is_set():
                raise Cancelled()
            size = task.size or None
            sha1 = task.sha1 if not task.size else None
            if self.http.is_valid(task.dest, size, sha1):
                with lock:
                    done_units[0] += task.size if task.size > 0 else 1
                continue
            missing.append(task)
        emit(force=True)

        if not missing:
            self.report(stage, base + span, "全部文件已就绪")
            return

        self.log(f"[下载] {stage}：需要下载 {len(missing)} 个文件")

        def work(task: DownloadTask) -> int:
            self._check_cancel()

            def on_chunk(count: int) -> None:
                if self.cancel.is_set():
                    raise Cancelled()
                with lock:
                    done_units[0] += count
                emit()

            return self.http.download(
                task.candidates,
                task.dest,
                size=task.size or None,
                sha1=task.sha1 or None,
                cancel=self.cancel,
                on_bytes=on_chunk,
                pause=self.pause,
            )

        def run_batch(batch: list[DownloadTask]) -> list[tuple[DownloadTask, str]]:
            failures: list[tuple[DownloadTask, str]] = []
            with ThreadPoolExecutor(max_workers=max(1, min(workers, len(batch)))) as pool:
                future_map = {pool.submit(work, task): task for task in batch}
                try:
                    for future in as_completed(future_map):
                        task = future_map[future]
                        try:
                            future.result()
                            # on_bytes 已按实际下载字节累加；未知大小只按文件数计 1 个单位
                            if task.size <= 0:
                                with lock:
                                    done_units[0] += 1
                        except Cancelled:
                            for pending in future_map:
                                pending.cancel()
                            raise
                        except Exception as exc:  # noqa: BLE001
                            failures.append((task, f"{task.label}: {exc}"))
                finally:
                    if failures:
                        for pending in future_map:
                            pending.cancel()
            return failures

        failures = run_batch(missing)
        if failures:
            # 网络抖动时再整批重试一次，避免个别文件拖垮整个安装
            retry = [task for task, _ in failures]
            self.log(f"[下载] {stage}：{len(retry)} 个文件失败，正在重试…")
            retry_failures = run_batch(retry)
            if retry_failures:
                emit(force=True)
                raise DownloadError(
                    f"{stage} 有 {len(retry_failures)} 个文件失败：\n"
                    + "\n".join(message for _, message in retry_failures[:6])
                )

        emit(force=True)
        self.report(stage, base + span, "完成")
