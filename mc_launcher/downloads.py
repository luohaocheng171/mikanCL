"""全局下载任务管理器：统一登记、排队、暂停与取消，供下载中心展示。"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable

from PySide6.QtCore import QObject, QThread, Signal

ACTIVE_STATUS = {"排队中", "准备中", "下载中", "安装中", "已暂停"}
FINISHED_STATUS = {"已完成", "失败", "已取消"}


@dataclass
class DownloadTask:
    id: str
    kind: str
    name: str
    status: str = "排队中"
    percent: float = 0.0
    speed: float = 0.0
    detail: str = ""
    stage: str = ""
    files_done: int = 0
    files_total: int = 0
    message: str = ""
    target_dir: str = ""
    worker: QThread | None = None
    cancel: Callable[[], None] | None = None
    pause_event: threading.Event | None = None
    rebuild: Callable[["DownloadTask"], QThread | None] | None = None
    factory: Callable[["DownloadTask"], QThread | None] | None = None
    created: float = field(default_factory=time.time)
    started_at: float = 0.0
    finished_at: float = 0.0

    @property
    def active(self) -> bool:
        return self.status in ACTIVE_STATUS

    @property
    def finished(self) -> bool:
        return self.status in FINISHED_STATUS

    @property
    def paused(self) -> bool:
        return bool(self.pause_event is not None and self.pause_event.is_set())

    @property
    def pausable(self) -> bool:
        return self.pause_event is not None and not self.finished

    @property
    def retryable(self) -> bool:
        return self.rebuild is not None and self.finished

    def elapsed(self) -> float:
        if not self.started_at:
            return 0.0
        end = self.finished_at or time.time()
        return max(0.0, end - self.started_at)


class DownloadManager(QObject):
    """最多同时运行 max_concurrent 个任务，其余排队；任务可跨页面持续存在。"""

    changed = Signal()

    def __init__(self, max_concurrent: int = 2, parent: QObject | None = None):
        super().__init__(parent)
        self.max_concurrent = max(1, int(max_concurrent))
        self._tasks: list[DownloadTask] = []

    # ------------------------------------------------------------------
    def tasks(self) -> list[DownloadTask]:
        return list(self._tasks)

    def active_count(self) -> int:
        return sum(1 for task in self._tasks if task.active and task.status != "排队中")

    def find(self, task_id: str) -> DownloadTask | None:
        for task in self._tasks:
            if task.id == task_id:
                return task
        return None

    def submit(
        self,
        kind: str,
        name: str,
        factory: Callable[[DownloadTask], QThread | None],
        cancel: Callable[[], None] | None = None,
        pause: threading.Event | None = None,
        rebuild: Callable[[DownloadTask], QThread | None] | None = None,
        target_dir: str = "",
        detail: str = "",
    ) -> DownloadTask:
        """登记一个任务；有空闲槽位时立即由 factory 创建并启动 worker。"""
        task = DownloadTask(
            id=uuid.uuid4().hex[:8],
            kind=kind,
            name=name,
            factory=factory,
            cancel=cancel,
            pause_event=pause,
            rebuild=rebuild,
            target_dir=target_dir,
            detail=detail,
        )
        self._tasks.append(task)
        self._trim()
        self._pump()
        self.changed.emit()
        return task

    def track(
        self,
        kind: str,
        name: str,
        worker: QThread,
        cancel: Callable[[], None] | None = None,
        pause: threading.Event | None = None,
        target_dir: str = "",
    ) -> DownloadTask:
        """登记一个已在外部创建但尚未启动的 worker。"""
        return self.submit(
            kind,
            name,
            lambda _task: worker,
            cancel=cancel,
            pause=pause,
            target_dir=target_dir,
        )

    def update(
        self,
        task_id: str,
        percent: float | None = None,
        status: str | None = None,
        detail: str | None = None,
        speed: float | None = None,
        stage: str | None = None,
        files_done: int | None = None,
        files_total: int | None = None,
    ) -> None:
        task = self.find(task_id)
        if task is None or task.finished:
            return
        if percent is not None:
            task.percent = max(0.0, min(1.0, float(percent)))
        if status:
            task.status = status
        if detail is not None:
            task.detail = detail
        if speed is not None:
            task.speed = max(0.0, float(speed))
        if stage is not None:
            task.stage = stage
        if files_done is not None:
            task.files_done = max(0, int(files_done))
        if files_total is not None:
            task.files_total = max(0, int(files_total))
        self.changed.emit()

    def finish(self, task_id: str, ok: bool = True, message: str = "") -> None:
        task = self.find(task_id)
        if task is None or task.finished:
            return
        task.status = "已完成" if ok else "失败"
        task.percent = 1.0 if ok else task.percent
        task.speed = 0.0
        task.message = message
        task.finished_at = time.time()
        if task.pause_event is not None:
            task.pause_event.clear()
        self._pump()
        self.changed.emit()

    def finish_cancelled(self, task_id: str, message: str = "") -> None:
        """把任务标记为已取消（不显示成失败）。"""
        task = self.find(task_id)
        if task is None or task.finished:
            return
        task.status = "已取消"
        task.message = message
        task.speed = 0.0
        task.finished_at = time.time()
        if task.pause_event is not None:
            task.pause_event.clear()
        self._pump()
        self.changed.emit()

    def pause(self, task_id: str) -> None:
        """暂停任务：worker 在下一个检查点挂起，不丢弃已下载数据。"""
        task = self.find(task_id)
        if task is None or task.finished or task.pause_event is None:
            return
        task.pause_event.set()
        task.status = "已暂停"
        self.changed.emit()

    def resume(self, task_id: str) -> None:
        task = self.find(task_id)
        if task is None or task.finished or task.pause_event is None:
            return
        task.pause_event.clear()
        task.status = "准备中" if task.worker is None else "下载中"
        self._pump()
        self.changed.emit()

    def retry(self, task_id: str) -> None:
        """重新排队失败/已取消的任务，由 rebuild 重新创建 worker。"""
        task = self.find(task_id)
        if task is None or not task.finished or task.rebuild is None:
            return
        task.status = "排队中"
        task.percent = 0.0
        task.speed = 0.0
        task.detail = ""
        task.stage = ""
        task.files_done = 0
        task.files_total = 0
        task.message = ""
        task.finished_at = 0.0
        task.started_at = 0.0
        task.worker = None
        # 旧的 cancel 绑定的是上一次 worker 的事件，重建时必须丢弃；
        # rebuild 的 factory 会为新的 worker 重新创建事件并回填 task.cancel
        task.cancel = None
        if task.pause_event is not None:
            task.pause_event.clear()
        task.factory = task.rebuild
        self._pump()
        self.changed.emit()

    def cancel(self, task_id: str) -> None:
        task = self.find(task_id)
        if task is None or task.finished:
            return
        if task.cancel is not None:
            try:
                task.cancel()
            except Exception:  # noqa: BLE001 - 取消失败不应该影响界面
                pass
        worker = task.worker
        if worker is not None and hasattr(worker, "requestInterruption"):
            worker.requestInterruption()
        if task.pause_event is not None:
            task.pause_event.clear()
        task.status = "已取消"
        task.finished_at = time.time()
        if task.factory is not None and task.worker is None:
            task.factory = None
        self._pump()
        self.changed.emit()

    def clear_finished(self) -> None:
        self._tasks = [task for task in self._tasks if not task.finished]
        self.changed.emit()

    # ------------------------------------------------------------------
    def _trim(self) -> None:
        finished = [task for task in self._tasks if task.finished]
        if len(self._tasks) > 30:
            for task in finished[: len(self._tasks) - 30]:
                self._tasks.remove(task)

    def _pump(self) -> None:
        for task in list(self._tasks):
            if self.active_count() >= self.max_concurrent:
                break
            if task.finished or task.worker is not None or task.factory is None:
                continue
            task.status = "准备中"
            factory = task.factory
            task.factory = None
            try:
                worker = factory(task)
            except Exception as exc:  # noqa: BLE001
                task.status = "失败"
                task.message = str(exc)
                continue
            if worker is None:
                task.status = "已完成"
                continue
            task.worker = worker
            task.started_at = time.time()
            worker.finished.connect(lambda task_id=task.id: self._on_worker_finished(task_id))
            worker.start()
            self.changed.emit()

    def _on_worker_finished(self, task_id: str) -> None:
        task = self.find(task_id)
        if task is None or task.finished:
            self._pump()
            self.changed.emit()
            return
        task.status = "已完成"
        task.percent = 1.0
        task.finished_at = time.time()
        self._pump()
        self.changed.emit()
