"""整合包管理：集中查看本启动器导入的整合包实例，支持启动、修复与清理。"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..content import ContentError
from ..context import AppContext, wait_thread
from ..installer import GameInstaller
from ..java import pick_java
from ..modloader import install_loader, java_for_mc
from .widgets import Badge, Card, page_header

LOADER_LABELS = {
    "forge": "Forge",
    "neoforge": "NeoForge",
    "fabric": "Fabric",
    "quilt": "Quilt",
    "liteloader": "LiteLoader",
    "optifine": "OptiFine",
}


def _game_dir(instance) -> Path:
    return Path(os.path.expandvars(instance.game_dir)).expanduser()


def _count_entries(folder: Path, pattern: str) -> int:
    try:
        return sum(1 for item in folder.glob(pattern) if item.is_file())
    except OSError:
        return 0


def _count_dirs(folder: Path) -> int:
    try:
        return sum(1 for item in folder.iterdir() if item.is_dir())
    except OSError:
        return 0


class RepairWorker(QThread):
    """补全实例缺失的原版文件与加载器版本。"""

    ok = Signal(str)
    failed = Signal(str)

    def __init__(self, ctx: AppContext, instance, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.instance = instance

    def run(self) -> None:
        try:
            target = _game_dir(self.instance)
            mc_version = self.instance.mc_version or self.instance.version_id
            if not mc_version:
                raise ContentError("该实例没有记录 Minecraft 版本，无法自动修复。")
            clone = self.ctx.config.with_game_dir(target)
            installer = GameInstaller(clone, self.ctx.sources, log_cb=lambda _line: None)
            version_id = self.instance.version_id or mc_version
            if not (target / "versions" / mc_version / f"{mc_version}.json").is_file():
                payload, _name, _cached = self.ctx.sources.get_manifest()
                entries = payload.get("data", {}).get("versions", [])
                entry = next((v for v in entries if str(v.get("id")) == mc_version), None)
                if entry is None:
                    raise ContentError(f"版本清单中找不到 Minecraft {mc_version}。")
                installer.install_version(entry)
            if (
                self.instance.loader
                and not (target / "versions" / version_id / f"{version_id}.json").is_file()
            ):
                java, warning = pick_java(self.ctx.javas, java_for_mc(mc_version))
                if java is None:
                    raise ContentError(
                        f"需要 Java {java_for_mc(mc_version)}，未找到可用 Java。{warning}"
                    )
                version_id = install_loader(
                    installer,
                    self.instance.loader,
                    mc_version,
                    self.instance.loader_version,
                    java_path=java.path,
                    log=lambda _line: None,
                )
            installer.ensure_version(version_id)
            self.ok.emit(version_id)
        except Exception as exc:  # noqa: BLE001 - 统一反馈到界面
            self.failed.emit(f"修复失败：{exc}")


class ModpackPage(QWidget):
    """整合包实例列表。"""

    launch_requested = Signal(str, str)  # instance_id, version_id

    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self._rows: list[tuple[str, str]] = []  # (instance_id, version_id)
        self._repair_worker: RepairWorker | None = None
        self._build_ui()
        self.ctx.bus.instances_changed.connect(self.refresh)
        self.refresh()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        header, header_layout = page_header(
            "整合包",
            "这里列出所有由整合包导入的实例，可启动、修复或清理",
        )
        self.count_badge = Badge("0 个", "green")
        header_layout.addWidget(self.count_badge)
        header_layout.addStretch(1)
        layout.addWidget(header)

        card = Card()
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["整合包", "MC 版本", "加载器", "Mod", "存档", "操作"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(False)
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, header_view.ResizeMode.Stretch)
        for column in range(1, 6):
            header_view.setSectionResizeMode(column, header_view.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 96)
        self.table.setColumnWidth(2, 96)
        self.table.setColumnWidth(3, 70)
        self.table.setColumnWidth(4, 70)
        self.table.setColumnWidth(5, 268)
        self.table.verticalHeader().setDefaultSectionSize(42)
        card.body.addWidget(self.table)

        self.empty_label = QLabel("还没有整合包实例。把整合包压缩包拖进窗口即可导入。")
        self.empty_label.setObjectName("Hint")
        self.empty_label.setAlignment(Qt.AlignCenter)
        card.body.addWidget(self.empty_label)
        layout.addWidget(card, 1)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        instances = [item for item in self.ctx.config.instance_list() if item.modpack]
        self.count_badge.setText(f"{len(instances)} 个")
        self.table.setRowCount(0)
        self._rows = []
        self.empty_label.setVisible(not instances)
        self.table.setVisible(bool(instances))
        for instance in instances:
            self._add_row(instance)

    def _add_row(self, instance) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._rows.append((instance.id, instance.version_id or instance.mc_version))
        target = _game_dir(instance)
        version = instance.version_id or instance.mc_version or "-"
        mc_version = instance.mc_version or "-"
        loader = LOADER_LABELS.get((instance.loader or "").lower(), instance.loader or "原版")
        mods = _count_entries(target / "mods", "*.jar")
        saves = _count_dirs(target / "saves")
        name_item = QTableWidgetItem(instance.name)
        name_item.setToolTip(str(target))
        self.table.setItem(row, 0, name_item)
        self.table.setItem(row, 1, QTableWidgetItem(mc_version))
        self.table.setItem(row, 2, QTableWidgetItem(f"{loader} · {version}" if version != "-" else loader))
        self.table.setItem(row, 3, QTableWidgetItem(str(mods)))
        self.table.setItem(row, 4, QTableWidgetItem(str(saves)))
        self.table.setCellWidget(row, 5, self._make_actions(instance))

    def _make_actions(self, instance) -> QWidget:
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        launch = QPushButton("启动")
        launch.setObjectName("Mini")
        launch.clicked.connect(lambda: self._launch(instance))
        repair = QPushButton("修复")
        repair.setObjectName("Mini")
        repair.clicked.connect(lambda: self._repair(instance))
        folder = QPushButton("打开目录")
        folder.setObjectName("Mini")
        folder.clicked.connect(lambda: self._open_folder(instance))
        remove = QPushButton("删除")
        remove.setObjectName("Mini")
        remove.clicked.connect(lambda: self._remove(instance))
        for button in (launch, repair, folder, remove):
            layout.addWidget(button)
        layout.addStretch(1)
        return wrapper

    # ------------------------------------------------------------------
    def _launch(self, instance) -> None:
        version_id = instance.version_id or instance.mc_version
        if not version_id:
            QMessageBox.warning(
                self,
                "无法启动",
                f"实例「{instance.name}」没有可用的游戏版本，请先点击“修复”补全版本。",
            )
            return
        self.launch_requested.emit(instance.id, version_id)

    def _repair(self, instance) -> None:
        if self._repair_worker is not None and self._repair_worker.isRunning():
            QMessageBox.information(self, "请稍候", "上一个修复任务还在进行中。")
            return
        worker = RepairWorker(self.ctx, instance, self)
        self._repair_worker = worker

        def done(version_id: str) -> None:
            missing = _game_dir(instance) / "missing_mods.txt"
            message = f"实例「{instance.name}」已修复，版本：{version_id}"
            if missing.is_file():
                message += (
                    "\n\n仍有部分文件下载失败（已记录在 missing_mods.txt），"
                    "可再次点击“修复”重试。"
                )
            QMessageBox.information(self, "修复完成", message)

        def failed(message: str) -> None:
            QMessageBox.warning(self, "修复失败", message)

        worker.ok.connect(done)
        worker.failed.connect(failed)
        worker.finished.connect(worker.deleteLater)
        worker.start()
        QMessageBox.information(
            self, "开始修复", "正在检查并补全版本文件，完成后会提示结果。"
        )

    def _open_folder(self, instance) -> None:
        target = _game_dir(instance)
        target.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def _remove(self, instance) -> None:
        target = _game_dir(instance)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("删除整合包实例")
        box.setText(f"确定要删除「{instance.name}」吗？")
        box.setInformativeText(
            "“删除并清空目录”会把实例目录中的存档、Mod 一起删除；"
            "“仅移除实例”只从启动器列表里去掉，文件保留。"
        )
        wipe = box.addButton("删除并清空目录", QMessageBox.DestructiveRole)
        keep = box.addButton("仅移除实例", QMessageBox.AcceptRole)
        cancel = box.addButton("取消", QMessageBox.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is None or clicked is cancel:
            return
        if clicked is wipe:
            shared = Path(self.ctx.config.game_path).expanduser()
            if target.resolve() == shared.resolve():
                QMessageBox.warning(self, "无法删除", "该实例与全局游戏目录相同，已取消清空操作。")
            else:
                try:
                    shutil.rmtree(target, ignore_errors=True)
                except OSError as exc:
                    QMessageBox.warning(self, "删除失败", f"无法清空实例目录：{exc}")
                    return
        self.ctx.config.remove_instance(instance.id)
        self.ctx.bus.instances_changed.emit()

    # ------------------------------------------------------------------
    def shutdown(self) -> None:
        wait_thread(self._repair_worker, 3000)
