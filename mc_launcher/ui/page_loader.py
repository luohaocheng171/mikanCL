"""加载器安装页：Forge / NeoForge / Fabric / Quilt / LiteLoader 一键安装。"""

from __future__ import annotations

import threading

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME
from ..context import AppContext, wait_thread
from ..installer import GameInstaller
from ..java import pick_java
from ..modloader import LOADER_LABELS, install_loader, java_for_mc, list_loader_versions
from ..version import scan_installed_versions
from .widgets import Card, card_title_row, page_header


class LoaderManifestWorker(QThread):
    ok = Signal(list)

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx

    def run(self) -> None:
        try:
            payload, _name, _cached = self.ctx.sources.get_manifest()
            entries = payload.get("data", {}).get("versions", [])
            self.ok.emit([str(v.get("id")) for v in entries if v.get("type") == "release"][:200])
        except Exception:  # noqa: BLE001
            self.ok.emit([])


class LoaderVersionsWorker(QThread):
    ok = Signal(list)
    failed = Signal(str)

    def __init__(self, kind: str, mc_version: str, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.mc_version = mc_version

    def run(self) -> None:
        try:
            self.ok.emit(list_loader_versions(self.kind, self.mc_version))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class LoaderInstallWorker(QThread):
    progress = Signal(float, str)
    log = Signal(str)
    done = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        ctx: AppContext,
        instance_id: str,
        mc_version: str,
        kind: str,
        loader_version: str,
        java_path: str,
        parent=None,
    ):
        super().__init__(parent)
        self.ctx = ctx
        self.instance_id = instance_id
        self.mc_version = mc_version
        self.kind = kind
        self.loader_version = loader_version
        self.java_path = java_path
        self.cancel_event = threading.Event()
        self._last_percent = 0.0
        self._loader_phase = False

    def _emit(self, value: float, detail: str) -> None:
        # 加载器阶段会二次触发 install_version 的进度回调，这里只保证进度条不回退
        value = max(self._last_percent, max(0.0, min(1.0, value)))
        self._last_percent = value
        self.progress.emit(value, detail)

    def _on_progress(self, p) -> None:
        percent = float(getattr(p, "percent", 0.0))
        if self._loader_phase:
            # 0.42 ~ 0.98：加载器本身及其依赖库
            value = 0.42 + percent * 0.56
        else:
            # 0.05 ~ 0.40：基础原版版本
            value = 0.05 + percent * 0.35
        self._emit(value, str(getattr(p, "detail", "") or ""))

    def run(self) -> None:
        try:
            game_dir = self.ctx.config.instance_path(self.instance_id)
            clone = self.ctx.config.with_game_dir(game_dir)
            installer = GameInstaller(
                clone,
                self.ctx.sources,
                progress_cb=self._on_progress,
                log_cb=self.log.emit,
                cancel=self.cancel_event,
            )
            version_json = game_dir / "versions" / self.mc_version / f"{self.mc_version}.json"
            if not version_json.exists():
                self.log.emit(f"[加载器] 未检测到 Minecraft {self.mc_version}，先安装基础版本…")
                payload, _name, _cached = self.ctx.sources.get_manifest()
                entries = payload.get("data", {}).get("versions", [])
                entry = next(
                    (v for v in entries if str(v.get("id")) == self.mc_version), None
                )
                if entry is None:
                    raise RuntimeError(f"版本清单中找不到 Minecraft {self.mc_version}。")
                installer.install_version(entry)
            self._loader_phase = True
            self._emit(0.42, f"准备安装 {LOADER_LABELS[self.kind]}…")
            version_id = install_loader(
                installer,
                self.kind,
                self.mc_version,
                self.loader_version,
                java_path=self.java_path,
                log=self.log.emit,
                cancel=self.cancel_event,
            )
            config = self.ctx.config
            if self.instance_id == "default":
                config.default_version_id = version_id
            else:
                instance = config.get_instance(self.instance_id)
                if instance is not None:
                    instance.version_id = version_id
                    instance.loader = self.kind
                    instance.mc_version = self.mc_version
            config.save()
            self.ctx.bus.instances_changed.emit()
            self.ctx.bus.versions_changed.emit()
            self._emit(1.0, "安装完成")
            self.log.emit(f"[完成] {LOADER_LABELS[self.kind]} 已安装：{version_id}")
            self.done.emit(version_id)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class LoaderPage(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self._versions_worker: LoaderVersionsWorker | None = None
        self._install_worker: LoaderInstallWorker | None = None
        self._manifest_worker: LoaderManifestWorker | None = None
        self._build()
        self.ctx.bus.instances_changed.connect(self._reload_instances)
        self._reload_instances()
        self._start_manifest()
        self._refresh_loader_versions()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 20, 26, 20)
        outer.setSpacing(14)
        header, _layout = page_header(
            "加载器安装", "一键安装 Forge、NeoForge、Fabric、Quilt 与 LiteLoader"
        )
        outer.addWidget(header)

        form_card = Card()
        form_card.body.addWidget(
            card_title_row("安装配置", "Forge / NeoForge 会调用官方安装器，耗时取决于网络")
        )
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        self.instance_combo = QComboBox()
        self.instance_combo.currentIndexChanged.connect(self._on_instance_changed)
        self.mc_combo = QComboBox()
        self.mc_combo.setEditable(True)
        self.mc_combo.currentTextChanged.connect(lambda _t: self._refresh_loader_versions())
        self.kind_combo = QComboBox()
        for key, label in LOADER_LABELS.items():
            self.kind_combo.addItem(label, key)
        self.kind_combo.currentIndexChanged.connect(lambda _i: self._refresh_loader_versions())
        self.loader_combo = QComboBox()
        self.loader_combo.setEditable(True)
        self.refresh_button = QPushButton("刷新版本")
        self.refresh_button.setObjectName("Ghost")
        self.refresh_button.clicked.connect(self._refresh_loader_versions)
        self.install_button = QPushButton("开始安装")
        self.install_button.setObjectName("Primary")
        self.install_button.clicked.connect(self._install)

        for col, (label, widget) in enumerate(
            (
                ("目标实例", self.instance_combo),
                ("Minecraft 版本", self.mc_combo),
                ("加载器", self.kind_combo),
                ("加载器版本", self.loader_combo),
            )
        ):
            caption = QLabel(label)
            caption.setObjectName("Muted")
            grid.addWidget(caption, 0, col)
            grid.addWidget(widget, 1, col)
        grid.addWidget(self.refresh_button, 2, 3)
        form_card.body.addLayout(grid)
        action_row = QHBoxLayout()
        self.status_label = QLabel("选择版本与加载器后点击安装。")
        self.status_label.setObjectName("Tiny")
        self.status_label.setWordWrap(True)
        action_row.addWidget(self.status_label, 1)
        action_row.addWidget(self.install_button)
        form_card.body.addLayout(action_row)
        self.instance_hint = QLabel("")
        self.instance_hint.setObjectName("Tiny")
        self.instance_hint.setWordWrap(True)
        form_card.body.addWidget(self.instance_hint)
        outer.addWidget(form_card)

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
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        progress_card.body.addWidget(self.log_view, 1)
        outer.addWidget(progress_card, 1)

        tip = QLabel(
            "说明：LiteLoader 官方仅支持到 Minecraft 1.12.2；Fabric / Quilt 安装会自动补全依赖库；"
            "Forge / NeoForge 需要本机有匹配的 Java。"
        )
        tip.setObjectName("Muted")
        tip.setWordWrap(True)
        outer.addWidget(tip)

    # ------------------------------------------------------------------
    def _reload_instances(self) -> None:
        current = self.ctx.config.selected_instance_id
        self.instance_combo.blockSignals(True)
        self.instance_combo.clear()
        for instance in self.ctx.config.instance_list():
            label = instance.name
            if instance.mc_version:
                label += f" · {instance.mc_version}"
            self.instance_combo.addItem(label, instance.id)
        index = self.instance_combo.findData(current)
        self.instance_combo.setCurrentIndex(index if index >= 0 else 0)
        self.instance_combo.blockSignals(False)
        self._on_instance_changed(self.instance_combo.currentIndex())

    def _on_instance_changed(self, _index: int) -> None:
        instance_id = str(self.instance_combo.currentData() or "default")
        path = self.ctx.config.instance_path(instance_id)
        self.instance_hint.setText(f"安装目录：{path}")
        self._load_mc_versions(path)

    def _load_mc_versions(self, game_dir) -> None:
        current = self.mc_combo.currentText()
        self.mc_combo.blockSignals(True)
        self.mc_combo.clear()
        installed = scan_installed_versions(game_dir)
        for version in installed:
            self.mc_combo.addItem(version.id)
        if installed:
            self.mc_combo.setCurrentText(installed[0].id)
        self.mc_combo.blockSignals(False)
        if current and self.mc_combo.findText(current) < 0:
            self.mc_combo.setEditText(current)
        self._refresh_loader_versions()

    def _start_manifest(self) -> None:
        self._manifest_worker = LoaderManifestWorker(self.ctx, self)
        self._manifest_worker.ok.connect(self._on_manifest)
        self._manifest_worker.start()

    def _on_manifest(self, versions: list) -> None:
        existing = {self.mc_combo.itemText(i) for i in range(self.mc_combo.count())}
        current = self.mc_combo.currentText()
        self.mc_combo.blockSignals(True)
        for version in versions:
            if version not in existing:
                self.mc_combo.addItem(version)
        if current:
            self.mc_combo.setCurrentText(current)
        elif self.mc_combo.count():
            self.mc_combo.setCurrentIndex(0)
        self.mc_combo.blockSignals(False)
        self._refresh_loader_versions()

    def _refresh_loader_versions(self) -> None:
        kind = str(self.kind_combo.currentData() or "fabric")
        mc_version = self.mc_combo.currentText().strip()
        if not mc_version:
            return
        if self._versions_worker is not None and self._versions_worker.isRunning():
            self._versions_worker.wait(100)
        self.loader_combo.clear()
        self.loader_combo.addItem("自动选择最新版本", "")
        self.status_label.setText(f"正在获取 {LOADER_LABELS[kind]} 版本列表…")
        self._versions_worker = LoaderVersionsWorker(kind, mc_version, self)
        self._versions_worker.ok.connect(self._on_loader_versions)
        self._versions_worker.failed.connect(self._on_loader_versions_failed)
        self._versions_worker.start()

    def _on_loader_versions(self, versions: list) -> None:
        current = self.loader_combo.currentText()
        self.loader_combo.clear()
        self.loader_combo.addItem("自动选择最新版本", "")
        for version in versions:
            self.loader_combo.addItem(version, version)
        if current and self.loader_combo.findText(current) >= 0:
            self.loader_combo.setCurrentText(current)
        if not versions:
            kind = str(self.kind_combo.currentData() or "")
            self.status_label.setText(
                f"{LOADER_LABELS.get(kind, kind)} 没有适用于该 Minecraft 版本的版本。"
            )
        else:
            self.status_label.setText(f"找到 {len(versions)} 个可用版本。")

    def _on_loader_versions_failed(self, message: str) -> None:
        self.status_label.setText(message)
        self._append_log(f"[错误] {message}")

    # ------------------------------------------------------------------
    def _install(self) -> None:
        if self._install_worker is not None and self._install_worker.isRunning():
            return
        mc_version = self.mc_combo.currentText().strip()
        if not mc_version:
            QMessageBox.warning(self, APP_NAME, "请选择或输入 Minecraft 版本。")
            return
        kind = str(self.kind_combo.currentData() or "fabric")
        loader_version = str(self.loader_combo.currentData() or "")
        java_path = ""
        if kind in ("forge", "neoforge"):
            java, warning = pick_java(self.ctx.javas, java_for_mc(mc_version))
            if java is None:
                QMessageBox.warning(
                    self,
                    "缺少 Java",
                    f"安装 {LOADER_LABELS[kind]} 需要 Java {java_for_mc(mc_version)}。\n{warning}",
                )
                return
            java_path = java.path
        instance_id = str(self.instance_combo.currentData() or "default")
        self._install_worker = LoaderInstallWorker(
            self.ctx, instance_id, mc_version, kind, loader_version, java_path, self
        )
        self._install_worker.progress.connect(self._on_progress)
        self._install_worker.log.connect(self._append_log)
        self._install_worker.done.connect(self._on_done)
        self._install_worker.failed.connect(self._on_failed)
        self._install_worker.start()
        self.install_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_view.clear()
        self._append_log(
            f"[开始] 实例 {self.instance_combo.currentText()} · Minecraft {mc_version} · "
            f"{LOADER_LABELS[kind]} {loader_version or '最新'}"
        )

    def _on_progress(self, value: float, detail: str) -> None:
        self.progress_bar.setValue(int(value * 1000))
        if detail:
            self.progress_label.setText(detail)

    def _on_done(self, version_id: str) -> None:
        self.install_button.setEnabled(True)
        self.progress_bar.setValue(1000)
        self.progress_label.setText("安装完成")
        self.status_label.setText(f"已安装版本：{version_id}")
        self.ctx.bus.toast.emit(f"加载器安装完成：{version_id}")

    def _on_failed(self, message: str) -> None:
        self.install_button.setEnabled(True)
        self.progress_label.setText("安装失败")
        self._append_log(f"[错误] {message}")
        QMessageBox.warning(self, APP_NAME, message)

    def _append_log(self, message: str) -> None:
        self.log_view.appendPlainText(message)
        scrollbar = self.log_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def refresh(self) -> None:
        self._reload_instances()

    def shutdown(self) -> None:
        for worker in (self._versions_worker, self._install_worker, self._manifest_worker):
            if worker is not None and worker.isRunning():
                worker.wait(1500)
