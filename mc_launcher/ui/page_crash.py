"""崩溃报告中心：浏览 data/logs/crashes/ 下归档的崩溃日志。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..config import DATA_DIR
from .widgets import Card, page_header

_MAX_PREVIEW = 220 * 1024  # 只读取尾部 220KB，避免超大日志卡住 UI


class CrashReportPage(QWidget):
    """崩溃日志列表与预览；切页时才扫描目录。"""

    def __init__(self, ctx, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self._items: dict[int, Path] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)
        header, header_layout = page_header(
            self.tr("崩溃报告"),
            self.tr("启动器会把游戏异常退出的日志归档到这里，方便排查或反馈问题。"),
        )
        refresh_button = QPushButton(self.tr("刷新"))
        refresh_button.setObjectName("Mini")
        refresh_button.clicked.connect(self.refresh)
        header_layout.addWidget(refresh_button)
        layout.addWidget(header)

        card = Card()
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.path_label = QLabel(str(self._crash_dir()))
        self.path_label.setObjectName("Tiny")
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bar.addWidget(self.path_label, 1)
        for text, handler in (
            (self.tr("打开目录"), self._open_dir),
            (self.tr("复制摘要"), self._copy_summary),
            (self.tr("删除所选"), self._delete_selected),
        ):
            button = QPushButton(text)
            button.setObjectName("Mini")
            button.clicked.connect(handler)
            bar.addWidget(button)
        card.body.addLayout(bar)

        splitter = QSplitter(Qt.Horizontal)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(
            [self.tr("日志文件"), self.tr("时间"), self.tr("大小")]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        splitter.addWidget(self.table)

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setObjectName("Console")
        self.preview.setPlaceholderText(self.tr("选择一份崩溃日志查看内容…"))
        splitter.addWidget(self.preview)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        card.body.addWidget(splitter, 1)
        layout.addWidget(card, 1)

    # ------------------------------------------------------------------
    @staticmethod
    def _crash_dir() -> Path:
        return DATA_DIR / "logs" / "crashes"

    def refresh(self) -> None:
        folder = self._crash_dir()
        self.path_label.setText(str(folder))
        self.table.setRowCount(0)
        self._items.clear()
        self.preview.clear()
        try:
            files = sorted(
                (p for p in folder.iterdir() if p.is_file()),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return
        for row, path in enumerate(files):
            try:
                stat = path.stat()
            except OSError:
                continue
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(path.name))
            self.table.setItem(
                row, 1, QTableWidgetItem(datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"))
            )
            self.table.setItem(row, 2, QTableWidgetItem(f"{stat.st_size / 1024:.0f} KB"))
            self._items[row] = path

    def _selected_paths(self) -> list[Path]:
        rows = {index.row() for index in self.table.selectionModel().selectedRows()} if self.table.selectionModel() else set()
        return [self._items[row] for row in sorted(rows) if row in self._items]

    def _on_selection_changed(self) -> None:
        paths = self._selected_paths()
        path = paths[-1] if paths else None
        if path is None:
            self.preview.clear()
            return
        try:
            size = path.stat().st_size
            with path.open("rb") as handle:
                if size > _MAX_PREVIEW:
                    handle.seek(size - _MAX_PREVIEW)
                    prefix = "[已截断：仅显示日志尾部]\n"
                else:
                    prefix = ""
                text = handle.read().decode("utf-8", errors="replace")
        except OSError as exc:
            self.preview.setPlainText(str(exc))
            return
        self.preview.setPlainText(prefix + text)
        cursor = self.preview.textCursor()
        cursor.movePosition(cursor.MoveOperation.Start)
        self.preview.setTextCursor(cursor)

    def _copy_summary(self) -> None:
        paths = self._selected_paths()
        if not paths:
            return
        path = paths[-1]
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            QMessageBox.warning(self, self.tr("崩溃报告"), str(exc))
            return
        lines = [f"{line}" for line in text.splitlines() if "Caused by" in line or "Exception" in line or "Error" in line]
        summary = "\n".join(lines[-12:]) or "\n".join(text.splitlines()[-12:])
        QGuiApplication.clipboard().setText(f"{path.name}\n{summary}")
        self.ctx.bus.toast.emit(self.tr("崩溃摘要已复制到剪贴板。"))

    def _open_dir(self) -> None:
        folder = self._crash_dir()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _delete_selected(self) -> None:
        paths = self._selected_paths()
        if not paths:
            return
        answer = QMessageBox.question(
            self,
            self.tr("删除崩溃报告"),
            self.tr("确定删除选中的 {0} 份日志？").format(len(paths)),
        )
        if answer != QMessageBox.Yes:
            return
        failed = 0
        for path in paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                failed += 1
        if failed:
            QMessageBox.warning(
                self, self.tr("删除崩溃报告"), self.tr("有 {0} 个文件删除失败。").format(failed)
            )
        self.refresh()
