"""下载中心：PCL 风格的任务卡片，展示当前阶段、进度、速度与剩余文件。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..context import AppContext
from ..downloads import DownloadTask
from .widgets import Badge, Card, page_header

_KIND_COLORS = {
    "原版": "blue",
    "游戏": "blue",
    "加载器": "orange",
    "整合包": "green",
    "内容": "blue",
    "Java": "gray",
    "下载": "gray",
}

_STATUS_COLORS = {
    "排队中": "gray",
    "准备中": "blue",
    "下载中": "blue",
    "安装中": "blue",
    "已暂停": "orange",
    "已完成": "green",
    "失败": "orange",
    "已取消": "gray",
}


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


def _format_elapsed(task: DownloadTask) -> str:
    total = int(task.elapsed())
    if total <= 0:
        return "—"
    if total < 60:
        return f"{total} 秒"
    if total < 3600:
        return f"{total // 60} 分 {total % 60} 秒"
    return f"{total // 3600} 小时 {total % 3600 // 60} 分"


def _primary_line(task: DownloadTask) -> str:
    if task.finished:
        return task.message or task.status
    if task.stage:
        return task.stage
    if task.detail:
        return task.detail.split(" · ")[0]
    return task.status


def _secondary_line(task: DownloadTask) -> str:
    if task.stage and task.detail:
        return task.detail
    if task.finished:
        return task.detail
    return ""


class TaskActions(QWidget):
    """一张任务卡片底部右侧的操作按钮；按钮可见性随任务状态变化。"""

    def __init__(self, page: "DownloadCenterPage", task_id: str):
        super().__init__()
        self.page = page
        self.task_id = task_id
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.pause_btn = self._make("暂停", self._toggle_pause)
        self.cancel_btn = self._make("取消", self._cancel)
        self.retry_btn = self._make("重试", self._retry)
        self.folder_btn = self._make("打开目录", self._open_dir)
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
        manager = self.page.ctx.downloads
        task = manager.find(self.task_id)
        if task is not None and task.active:
            answer = QMessageBox.question(
                self.page,
                "取消任务",
                f"确定要取消「{task.name}」吗？\n已下载的部分文件会保留，稍后可重试继续。",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        manager.cancel(self.task_id)

    def _retry(self) -> None:
        self.page.ctx.downloads.retry(self.task_id)

    def _open_dir(self) -> None:
        self.page.open_target(self.task_id)

    def sync(self, task: DownloadTask) -> None:
        self.pause_btn.setVisible(task.pausable)
        self.pause_btn.setText("继续" if task.paused else "暂停")
        self.cancel_btn.setVisible(task.active)
        self.retry_btn.setVisible(task.retryable)
        self.folder_btn.setVisible(bool(task.target_dir))
        self.folder_btn.setEnabled(bool(task.target_dir) and Path(task.target_dir).is_dir())


class TaskCard(Card):
    """单个任务卡片：标题 + 当前阶段 + 进度条 + 速度/剩余时间 + 操作。"""

    def __init__(self, page: "DownloadCenterPage", task: DownloadTask):
        super().__init__(margins=16, spacing=10)
        self.page = page
        self.task_id = task.id
        self.setMinimumHeight(132)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self.kind_badge = Badge(task.kind, _KIND_COLORS.get(task.kind, "gray"))
        title_row.addWidget(self.kind_badge)
        self.name_label = QLabel(task.name)
        self.name_label.setObjectName("CardTitle")
        self.name_label.setToolTip(task.name)
        title_row.addWidget(self.name_label, 1)
        self.status_badge = Badge(task.status, _STATUS_COLORS.get(task.status, "gray"))
        title_row.addWidget(self.status_badge)
        self.body.addLayout(title_row)

        self.stage_label = QLabel("")
        self.stage_label.setObjectName("TaskStage")
        self.stage_label.setWordWrap(True)
        self.body.addWidget(self.stage_label)

        self.detail_label = QLabel("")
        self.detail_label.setObjectName("Tiny")
        self.detail_label.setWordWrap(True)
        self.body.addWidget(self.detail_label)

        progress_row = QHBoxLayout()
        progress_row.setSpacing(10)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        progress_row.addWidget(self.progress, 1)
        self.percent_label = QLabel("0%")
        self.percent_label.setObjectName("Tiny")
        self.percent_label.setMinimumWidth(42)
        self.percent_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        progress_row.addWidget(self.percent_label)
        self.body.addLayout(progress_row)

        footer = QHBoxLayout()
        footer.setSpacing(12)
        self.meta_label = QLabel("")
        self.meta_label.setObjectName("Tiny")
        footer.addWidget(self.meta_label, 1)
        self.actions = TaskActions(page, task.id)
        footer.addWidget(self.actions)
        self.body.addLayout(footer)

        self.sync(task)

    def sync(self, task: DownloadTask) -> None:
        self.name_label.setText(task.name)
        self.kind_badge.setText(task.kind)
        self.status_badge.setText(task.status)
        self.status_badge.set_kind(_STATUS_COLORS.get(task.status, "gray"))

        stage = _primary_line(task)
        self.stage_label.setText(stage)
        self.stage_label.setVisible(bool(stage))
        secondary = _secondary_line(task)
        self.detail_label.setText(secondary)
        self.detail_label.setVisible(bool(secondary))

        self.progress.setValue(int(task.percent * 1000))
        percent_text = f"{task.percent * 100:.0f}%"
        self.percent_label.setText(percent_text)

        parts: list[str] = []
        if task.files_total > 0 and not task.finished:
            remaining = max(0, task.files_total - task.files_done)
            parts.append(f"剩余文件 {remaining}")
        if task.active and not task.paused:
            parts.append(f"速度 {_format_speed(task.speed)}")
        if task.active and not task.paused:
            parts.append(f"剩余时间 {_format_eta(task)}")
        parts.append(f"已用时 {_format_elapsed(task)}")
        self.meta_label.setText(" · ".join(parts))

        self.actions.sync(task)


class DownloadCenterPage(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self._cards: dict[str, TaskCard] = {}
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
            "所有下载与安装任务都在这里排队执行，可随时暂停、继续、取消或重试。",
        )
        clear_btn = QPushButton("清理已完成")
        clear_btn.setObjectName("Ghost")
        clear_btn.clicked.connect(self._clear_finished)
        header_layout.addWidget(clear_btn)
        root.addWidget(header)

        stats = Card(margins=16, spacing=10)
        stat_row = QHBoxLayout()
        stat_row.setSpacing(28)
        self.stat_progress = self._make_stat(stat_row, "总进度", "0%")
        self.stat_speed = self._make_stat(stat_row, "下载速度", "—")
        self.stat_files = self._make_stat(stat_row, "剩余文件", "—")
        self.stat_tasks = self._make_stat(stat_row, "任务", "0 个")
        stat_row.addStretch(1)
        stats.body.addLayout(stat_row)
        self.total_progress = QProgressBar()
        self.total_progress.setRange(0, 1000)
        self.total_progress.setTextVisible(False)
        stats.body.addWidget(self.total_progress)
        root.addWidget(stats)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        container = QWidget()
        self.list_layout = QVBoxLayout(container)
        self.list_layout.setContentsMargins(0, 0, 4, 0)
        self.list_layout.setSpacing(12)
        self.list_layout.addStretch(1)
        self.scroll.setWidget(container)
        root.addWidget(self.scroll, 1)

        self.empty = QLabel("暂无下载任务。安装版本、下载内容或拖入文件后会出现在这里。")
        self.empty.setObjectName("Tiny")
        self.empty.setAlignment(Qt.AlignCenter)
        root.addWidget(self.empty, 1)

        self.refresh()

    def _make_stat(self, row: QHBoxLayout, title: str, value: str) -> QLabel:
        box = QVBoxLayout()
        box.setSpacing(2)
        value_label = QLabel(value)
        value_label.setObjectName("StatValue")
        title_label = QLabel(title)
        title_label.setObjectName("Tiny")
        box.addWidget(value_label)
        box.addWidget(title_label)
        row.addLayout(box)
        return value_label

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        tasks = sorted(self.ctx.downloads.tasks(), key=lambda task: task.created)
        ids = [task.id for task in tasks]
        if ids != self._ids:
            self._rebuild(tasks)
        for task in tasks:
            card = self._cards.get(task.id)
            if card is not None:
                card.sync(task)
        self._update_stats(tasks)

    def _update_stats(self, tasks: list[DownloadTask]) -> None:
        active = [task for task in tasks if task.active]
        running = [task for task in active if task.status != "排队中"]
        total_active = sum(1 for task in tasks if task.active)

        if active:
            overall = sum(task.percent for task in active) / len(active)
            speed = sum(task.speed for task in active)
        elif tasks:
            overall = 1.0
            speed = 0.0
        else:
            overall = 0.0
            speed = 0.0
        remaining_files = sum(
            max(0, task.files_total - task.files_done)
            for task in active
            if task.files_total > 0
        )

        self.total_progress.setValue(int(overall * 1000))
        self.stat_progress.setText(f"{overall * 100:.0f}%")
        self.stat_speed.setText(_format_speed(speed))
        self.stat_files.setText(f"{remaining_files} 个" if remaining_files else "—")
        self.stat_tasks.setText(
            f"运行 {len(running)} · 排队 {total_active - len(running)} · 共 {len(tasks)}"
        )
        self.scroll.setVisible(bool(tasks))
        self.empty.setVisible(not tasks)

    def _rebuild(self, tasks: list[DownloadTask]) -> None:
        self._ids = [task.id for task in tasks]
        for card in self._cards.values():
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()
        for index, task in enumerate(tasks):
            card = TaskCard(self, task)
            self.list_layout.insertWidget(index, card)
            self._cards[task.id] = card

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
