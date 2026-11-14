"""截图图库：按实例读取 screenshots/，懒加载预览，支持打包与删除。"""

from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .widgets import Card, page_header, related_features_row

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".gif"}


class GalleryPage(QWidget):
    """截图列表 + 预览；只在切到本页时扫描目录（懒加载）。"""

    def __init__(self, ctx, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self._loaded = False
        self._items: dict[int, Path] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)
        header, header_layout = page_header(
            self.tr("截图图库"),
            self.tr("浏览当前实例的 screenshots/，支持预览、打包 zip、打开与删除。"),
        )
        self.refresh_button = QPushButton(self.tr("刷新"))
        self.refresh_button.setObjectName("Mini")
        self.refresh_button.clicked.connect(self.refresh)
        header_layout.addWidget(self.refresh_button)
        layout.addWidget(header)

        card = Card()
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.path_label = QLabel("")
        self.path_label.setObjectName("Tiny")
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bar.addWidget(self.path_label, 1)
        open_dir = QPushButton(self.tr("打开目录"))
        open_dir.setObjectName("Mini")
        open_dir.clicked.connect(self._open_dir)
        bar.addWidget(open_dir)
        export_button = QPushButton(self.tr("打包所选"))
        export_button.setObjectName("Mini")
        export_button.clicked.connect(self._export_selected)
        bar.addWidget(export_button)
        delete_button = QPushButton(self.tr("删除所选"))
        delete_button.setObjectName("Mini")
        delete_button.clicked.connect(self._delete_selected)
        bar.addWidget(delete_button)
        card.body.addLayout(bar)

        splitter = QSplitter(Qt.Horizontal)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(
            [self.tr("文件"), self.tr("修改时间"), self.tr("大小")]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.cellDoubleClicked.connect(lambda *_: self._open_selected())
        splitter.addWidget(self.table)

        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(8)
        self.preview = QLabel(self.tr("选择一张截图以预览"))
        self.preview.setObjectName("GalleryPreview")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(260, 180)
        self.preview.setWordWrap(True)
        preview_layout.addWidget(self.preview, 1)
        open_button = QPushButton(self.tr("用默认看图工具打开"))
        open_button.setObjectName("Mini")
        open_button.clicked.connect(self._open_selected)
        preview_layout.addWidget(open_button)
        splitter.addWidget(preview_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        card.body.addWidget(splitter, 1)
        layout.addWidget(card, 1)
        layout.addWidget(related_features_row(self.ctx, "gallery"))

    # ------------------------------------------------------------------
    def _screenshots_dir(self) -> Path:
        cfg = self.ctx.config
        instance = cfg.selected_instance()
        base = cfg.instance_path(instance.id)
        if instance.version_id:
            return cfg.resolve_game_dirs(instance.version_id, base).targets("screenshots")[0]
        return base / "screenshots"

    def refresh(self) -> None:
        self._loaded = True
        folder = self._screenshots_dir()
        self.path_label.setText(str(folder))
        self.path_label.setToolTip(str(folder))
        self.table.setRowCount(0)
        self._items.clear()
        self.preview.setText(self.tr("选择一张截图以预览"))
        self.preview.setPixmap(QPixmap())
        try:
            files = sorted(
                (
                    p
                    for p in folder.iterdir()
                    if p.is_file() and p.suffix.lower() in _IMAGE_SUFFIXES
                ),
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
            name_item = QTableWidgetItem(path.name)
            name_item.setToolTip(str(path))
            self.table.setItem(row, 0, name_item)
            stamp = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            self.table.setItem(row, 1, QTableWidgetItem(stamp))
            self.table.setItem(row, 2, QTableWidgetItem(f"{stat.st_size / 1024:.0f} KB"))
            self._items[row] = path

    def _selected_paths(self) -> list[Path]:
        rows = {index.row() for index in self.table.selectionModel().selectedRows()} if self.table.selectionModel() else set()
        return [self._items[row] for row in sorted(rows) if row in self._items]

    def _on_selection_changed(self) -> None:
        paths = self._selected_paths()
        path = paths[-1] if paths else None
        if path is None:
            self.preview.setText(self.tr("选择一张截图以预览"))
            self.preview.setPixmap(QPixmap())
            return
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.preview.setText(self.tr("无法读取该图片"))
            return
        self.preview.setPixmap(
            pixmap.scaled(
                self.preview.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )

    def _open_selected(self) -> None:
        paths = self._selected_paths()
        if paths:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths[-1])))

    def _open_dir(self) -> None:
        folder = self._screenshots_dir()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _export_selected(self) -> None:
        paths = self._selected_paths() or list(self._items.values())[:1]
        if not paths:
            QMessageBox.information(self, self.tr("截图图库"), self.tr("还没有可打包的截图。"))
            return
        default_dir = self.ctx.config.backup_root / "screenshots"
        try:
            default_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            default_dir = Path.home()
        name = f"screenshots-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
        target, _filter = QFileDialog.getSaveFileName(
            self, self.tr("导出截图压缩包"), str(default_dir / name), "Zip (*.zip)"
        )
        if not target:
            return
        try:
            with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                for path in paths:
                    archive.write(path, path.name)
        except OSError as exc:
            QMessageBox.warning(self, self.tr("导出失败"), str(exc))
            return
        self.ctx.bus.toast.emit(self.tr("已导出 {0} 张截图。").format(len(paths)))

    def _delete_selected(self) -> None:
        paths = self._selected_paths()
        if not paths:
            return
        answer = QMessageBox.question(
            self,
            self.tr("删除截图"),
            self.tr("确定删除选中的 {0} 个文件？此操作不可撤销。").format(len(paths)),
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
                self, self.tr("删除截图"), self.tr("有 {0} 个文件删除失败。").format(failed)
            )
        self.refresh()
