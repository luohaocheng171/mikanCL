"""下载中心：集中查看所有下载/安装任务，支持暂停、恢复、取消、重试与打开目录。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..context import AppContext
from ..downloads import DownloadTask
from .widgets import Card, page_header


def _format_speed(value: float) -> str:
    if value <= 0:
        return "—"
    units = ["B/s", "KB/s", "MB/s", "GB/s"]
    index = 0
    while value >= 1024 and index < len(units) - 1:
        value /= 1024
        index += 1
    return f"{value:.1f} {units[index]}"


def _format_eta(task: DownloadTask) -> str:
    if task.paused:
        return "已暂停"
    if task.finished or task.percent <= 0.01:
        return "—"
    elapsed = task.elapsed()
    if elapsed <= 0.5:
        return "—"
    remain = elapsed * (1.0 - task.percent) / task.percent
    if remain < 60:
        return f"{remain:.0f} 秒"
    if remain < 3600:
        return f"{remain / 60:.0f} 分"
    return f"{remain / 3600:.1f} 小时"


class TaskActions(QWidget):
    """一行任务的操作按钮；按钮可见性随任务状态变化。"""

    def __init__(self, page: "DownloadCenterPage", task_id: str):
        super().__init__()
        self.page = page
        self.task_id = task_id
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        self.pause_btn = self._make("暂停", self._toggle_pause)
        self.cancel_btn = self._make("取消", self._cancel)
        self.retry_btn = self._make("重试", self._retry)
        self.folder_btn = self._make("目录", self._open_dir)
        for button in (self.pause_btn, self.cancel_btn, self.retry_btn, self.folder_btn):
            layout.addWidget(button)

    def _make(self, text: str, handler) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("Mini")
        button.setCursor(Qt.PointingHandCursor)
        button.setFixedHeight(24)
        button.clicked.connect(handler)
        return button

    def _toggle_pause(self) -> None:
        manager = self.page.ctx.downloads
        task = manager.find(self.task_id)
        if task is None:
            return
        if task.paused:
            manager.resume(self.task_id)
        else:
            manager.pause(self.task_id)

    def _cancel(self) -> None:
        self.page.ctx.downloads.cancel(self.task_id)

    def _retry(self) -> None:
        self.page.ctx.downloads.retry(self.task_id)

    def _open_dir(self) -> None:
        self.page.open_target(self.task_id)

    def sync(self, task: DownloadTask) -> None:
        self.pause_btn.setVisible(task.pausable)
        self.pause_btn.setText("恢复" if task.paused else "暂停")
        self.cancel_btn.setVisible(task.active)
        self.retry_btn.setVisible(task.retryable)
        self.folder_btn.setVisible(bool(task.target_dir))
        self.folder_btn.setEnabled(bool(task.target_dir) and Path(task.target_dir).is_dir())


class DownloadCenterPage(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self._rows: dict[str, TaskActions] = {}
        self._ids: list[str] = []
        self._build()
        self.ctx.downloads.changed.connect(self.refresh)

    # ------------------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(16)

        header, header_layout = page_header(
            "下载中心",
            "所有下载与安装任务都会在这里排队执行，可随时暂停、恢复、取消或重试。",
        )
        self.summary = QLabel("暂无任务")
        self.summary.setObjectName("Tiny")
        header_layout.addWidget(self.summary)
        clear_btn = QPushButton("清理已完成")
        clear_btn.setObjectName("Ghost")
        clear_btn.clicked.connect(self._clear_finished)
        header_layout.addWidget(clear_btn)
        root.addWidget(header)

        card = Card(margins=14, spacing=10)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["任务", "类型", "状态", "进度", "速度", "剩余", "操作"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.Stretch)
        for column, width in ((1, 84), (2, 84), (3, 72), (4, 96), (5, 88), (6, 208)):
            head.setSectionResizeMode(column, QHeaderView.Fixed)
            self.table.setColumnWidth(column, width)
        self.table.verticalHeader().setDefaultSectionSize(38)
        card.body.addWidget(self.table)

        self.empty = QLabel("暂无下载任务。安装版本、下载内容或拖入文件后会出现在这里。")
        self.empty.setObjectName("Tiny")
        self.empty.setAlignment(Qt.AlignCenter)
        card.body.addWidget(self.empty)
        root.addWidget(card, 1)

        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        tasks = sorted(self.ctx.downloads.tasks(), key=lambda task: task.created)
        ids = [task.id for task in tasks]
        if ids != self._ids:
            self._rebuild(tasks)
        self._update(tasks)

        active = sum(1 for task in tasks if task.active)
        running = sum(1 for task in tasks if task.active and task.status != "排队中")
        self.summary.setText(
            f"运行 {running} · 排队 {active - running} · 共 {len(tasks)} 个任务"
        )

    def _rebuild(self, tasks: list[DownloadTask]) -> None:
        self._ids = [task.id for task in tasks]
        self._rows.clear()
        self.table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            name_item = QTableWidgetItem(task.name)
            name_item.setToolTip(task.name)
            self.table.setItem(row, 0, name_item)
            for column in range(1, 6):
                self.table.setItem(row, column, QTableWidgetItem(""))
            actions = TaskActions(self, task.id)
            self.table.setCellWidget(row, 6, actions)
            self._rows[task.id] = actions
        self.table.setVisible(bool(tasks))
        self.empty.setVisible(not tasks)

    def _update(self, tasks: list[DownloadTask]) -> None:
        for row, task in enumerate(tasks):
            if row >= self.table.rowCount():
                continue
            self.table.item(row, 0).setToolTip(task.detail or task.name)
            self.table.item(row, 1).setText(task.kind)
            status = self.table.item(row, 2)
            status.setText(task.status)
            status.setToolTip(task.message or task.detail)
            self.table.item(row, 3).setText(f"{task.percent * 100:.0f}%")
            self.table.item(row, 4).setText(_format_speed(task.speed))
            self.table.item(row, 5).setText(_format_eta(task))
            actions = self._rows.get(task.id)
            if actions is not None:
                actions.sync(task)

    def _clear_finished(self) -> None:
        self.ctx.downloads.clear_finished()

    def open_target(self, task_id: str) -> None:
        task = self.ctx.downloads.find(task_id)
        if task is None or not task.target_dir:
            return
        path = Path(task.target_dir)
        if not path.is_dir():
            self.ctx.bus.toast.emit(f"目录不存在：{path}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
