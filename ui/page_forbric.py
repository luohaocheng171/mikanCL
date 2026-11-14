"""Forbric 加载器引导式安装页（实验性，仅支持 Minecraft 26.2，需要 Java 21）。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME
from ..config import CACHE_DIR
from ..context import AppContext, wait_thread
from ..forbric import FORBRIC_VERSION_ID, is_forbric_supported
from .forbric_worker import ForbricWorker
from .widgets import Badge, Card, card_title_row, page_header


class ForbricPage(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self._worker: ForbricWorker | None = None
        self._busy = False
        self._game_dir = ""
        self._build()
        self.ctx.bus.instances_changed.connect(self._reload_instances)
        self.ctx.bus.javas_changed.connect(self._reload_javas)
        self.refresh()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 20, 26, 20)
        outer.setSpacing(14)

        header, _layout = page_header(
            "Forbric 安装", "引导式安装 Forbric 三合一加载器（Fabric / Forge / NeoForge）"
        )
        outer.addWidget(header)

        # 说明卡
        tip_card = Card(margins=16, spacing=10)
        tip_row = QHBoxLayout()
        tip_row.setContentsMargins(0, 0, 0, 0)
        tip_row.setSpacing(10)
        tip_row.addWidget(Badge("实验性功能", "orange"))
        tip_label = QLabel(
            "Forbric（Fabric / Forge / NeoForge 三合一）仅支持 Minecraft 26.2 · 需要 Java 21。"
        )
        tip_label.setObjectName("Muted")
        tip_label.setWordWrap(True)
        tip_row.addWidget(tip_label, 1)
        tip_card.body.addLayout(tip_row)
        outer.addWidget(tip_card)

        # 配置区
        form_card = Card()
        form_card.body.addWidget(card_title_row("安装配置", "选择目标实例与 Java 21 运行环境"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        grid.addWidget(self._caption("目标实例"), 0, 0)
        self.instance_combo = QComboBox()
        self.instance_combo.currentIndexChanged.connect(self._on_instance_changed)
        grid.addWidget(self.instance_combo, 0, 1)
        grid.addWidget(self._caption("Java 21"), 1, 0)
        self.java_combo = QComboBox()
        grid.addWidget(self.java_combo, 1, 1)
        form_card.body.addLayout(grid)
        self.java_hint = QLabel("")
        self.java_hint.setObjectName("Tiny")
        self.java_hint.setWordWrap(True)
        form_card.body.addWidget(self.java_hint)
        self.warn_label = QLabel("")
        self.warn_label.setStyleSheet("color: #e8909a;")
        self.warn_label.setWordWrap(True)
        form_card.body.addWidget(self.warn_label)
        action_row = QHBoxLayout()
        action_row.addStretch(1)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setObjectName("Danger")
        self.cancel_button.clicked.connect(self._cancel)
        self.cancel_button.setEnabled(False)
        action_row.addWidget(self.cancel_button)
        self.start_button = QPushButton("开始安装")
        self.start_button.setObjectName("Primary")
        self.start_button.clicked.connect(self._start)
        action_row.addWidget(self.start_button)
        form_card.body.addLayout(action_row)
        outer.addWidget(form_card)

        # 进度区
        progress_card = Card(margins=14, spacing=8)
        progress_head = QHBoxLayout()
        self.progress_label = QLabel("就绪")
        self.progress_label.setObjectName("Muted")
        progress_head.addWidget(self.progress_label, 1)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedWidth(260)
        progress_head.addWidget(self.progress_bar)
        progress_card.body.addLayout(progress_head)
        self.log_view = QTextEdit()
        self.log_view.setObjectName("Console")
        self.log_view.setReadOnly(True)
        progress_card.body.addWidget(self.log_view, 1)
        outer.addWidget(progress_card, 1)

    @staticmethod
    def _caption(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("Muted")
        return label

    # ------------------------------------------------------------------
    def _reload_instances(self) -> None:
        current = self.ctx.config.selected_instance_id
        self.instance_combo.blockSignals(True)
        self.instance_combo.clear()
        items = {instance.id: instance for instance in self.ctx.config.instance_list()}
        for instance in items.values():
            label = "默认（全局目录）" if instance.id == "default" else instance.name
            self.instance_combo.addItem(label, instance.id)
        index = self.instance_combo.findData(current)
        self.instance_combo.setCurrentIndex(index if index >= 0 else 0)
        self.instance_combo.blockSignals(False)
        self._on_instance_changed(self.instance_combo.currentIndex())

    def _reload_javas(self) -> None:
        self.java_combo.blockSignals(True)
        self.java_combo.clear()
        for info in self.ctx.javas:
            if getattr(info, "major", None) == 21:
                self.java_combo.addItem(info.label, info.path)
        self.java_combo.blockSignals(False)
        if self.java_combo.count() == 0:
            self.java_hint.setText("未找到 Java 21，请先在「设置」页安装或手动指定 Java 21。")
        else:
            self.java_hint.setText("")

    def _on_instance_changed(self, _index: int) -> None:
        running = self._worker is not None and self._worker.isRunning()
        instance_id = str(self.instance_combo.currentData() or "default")
        instance = self.ctx.config.get_instance(instance_id)
        mc_version = ""
        if instance is not None:
            mc_version = (instance.mc_version or "").strip() or (instance.version_id or "").strip()
        if not is_forbric_supported(mc_version):
            self.warn_label.setText(f"当前实例版本为 {mc_version}，Forbric 目前仅支持 26.2")
            self.start_button.setEnabled(False)
        else:
            self.warn_label.setText("")
            self.start_button.setEnabled(not running)

    # ------------------------------------------------------------------
    def _start(self) -> None:
        if self._busy:
            return
        instance_id = str(self.instance_combo.currentData() or "default")
        java_path = str(self.java_combo.currentData() or "")
        if not java_path:
            QMessageBox.warning(self, APP_NAME, "请先选择 Java 21 运行环境。")
            return
        self._game_dir = str(self.ctx.config.instance_path(instance_id))
        worker = ForbricWorker(self.ctx, instance_id, self._game_dir, java_path, self)
        self._worker = worker
        self._busy = True
        worker.progress.connect(self._on_progress)
        worker.log.connect(self._append_log)
        worker.done.connect(self._on_done)
        worker.failed.connect(self._on_failed)
        cache = CACHE_DIR / "forbric"
        task = self.ctx.downloads.submit(
            kind="纯下载",
            name="Forbric 安装",
            factory=lambda _t: worker,
            cancel=lambda: worker.cancel(),
            target_dir=str(cache),
            detail="Forbric 加载器",
        )
        self._task_id = task.id
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setValue(0)
        self.progress_label.setText("准备安装")
        self.log_view.clear()
        self._append_log(
            f"[Forbric] 开始安装 → 实例：{self.instance_combo.currentText()} · 目录：{self._game_dir}"
        )

    def _cancel(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._append_log("[Forbric] 已请求取消。")
            self.cancel_button.setEnabled(False)

    def _on_progress(self, value: float, detail: str) -> None:
        self.progress_bar.setValue(int(max(0.0, min(1.0, value)) * 1000))
        self.progress_label.setText(detail)
        task_id = getattr(self, "_task_id", "")
        if task_id:
            self.ctx.downloads.update(task_id, percent=value, detail=detail)

    def _append_log(self, message: str) -> None:
        self.log_view.append(message)
        scrollbar = self.log_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_done(self, _version_id: str) -> None:
        self._busy = False
        self.cancel_button.setEnabled(False)
        self.progress_bar.setValue(1000)
        self.progress_label.setText("安装完成")
        self._append_log("[Forbric] 注册实例…")
        instance = self.ctx.config.add_instance(
            "Forbric 26.2",
            self._game_dir,
            version_id=FORBRIC_VERSION_ID,
            loader="forbric",
            mc_version="26.2",
        )
        self.ctx.config.select_instance(instance.id)
        self.ctx.config.save()
        self.ctx.bus.instances_changed.emit()
        self.ctx.bus.toast.emit("Forbric 安装成功，已注册实例")
        self._on_instance_changed(self.instance_combo.currentIndex())

    def _on_failed(self, message: str) -> None:
        self._busy = False
        self.cancel_button.setEnabled(False)
        self.progress_label.setText("安装失败")
        self._append_log(f"[错误] {message}")
        self._on_instance_changed(self.instance_combo.currentIndex())
        QMessageBox.warning(self, APP_NAME, message)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        self._reload_instances()
        self._reload_javas()

    def shutdown(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            wait_thread(self._worker, 2000)
