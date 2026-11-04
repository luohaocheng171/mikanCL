"""从 PCL2 / HMCL 配置目录导入游戏版本与设置（对话框）。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ..context import AppContext
from ..launcher_import import ExternalProfile, import_profile, scan_profile


class ImportLauncherDialog(QDialog):
    """让用户选择 PCL / HMCL 的配置目录，勾选要导入的版本。"""

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._profile: ExternalProfile | None = None
        self.setWindowTitle("从 PCL / HMCL 导入")
        self.setMinimumSize(720, 520)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        tip = QLabel(
            "选择 PCL2 或 HMCL 的启动器目录（包含 .minecraft 的那一层，也可以直接选 .minecraft）。"
            "导入只登记本启动器没有的版本，不会复制或移动原目录里的任何文件。"
        )
        tip.setObjectName("Muted")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(r"例如 E:\1.20.1-Fabric 0.19.5-OptiFine_I6")
        row.addWidget(self.path_edit, 1)
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        scan = QPushButton("开始扫描")
        scan.clicked.connect(self._scan)
        row.addWidget(scan)
        layout.addLayout(row)

        self.summary = QLabel("尚未扫描")
        self.summary.setObjectName("Tiny")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.NoSelection)
        layout.addWidget(self.list, 1)

        options = QHBoxLayout()
        self.settings_check = QCheckBox("导入该版本的 PCL / HMCL 游戏设置（隔离、内存、JVM 参数等）")
        self.settings_check.setChecked(True)
        self.global_check = QCheckBox("同时导入全局设置（默认 Java 路径 / 内存）")
        options.addWidget(self.settings_check)
        options.addWidget(self.global_check)
        options.addStretch(1)
        layout.addLayout(options)

        bottom = QHBoxLayout()
        self.status = QLabel("")
        self.status.setObjectName("Tiny")
        self.status.setWordWrap(True)
        bottom.addWidget(self.status, 1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        bottom.addWidget(cancel)
        self.import_button = QPushButton("导入所选版本")
        self.import_button.setEnabled(False)
        self.import_button.clicked.connect(self._do_import)
        bottom.addWidget(self.import_button)
        layout.addLayout(bottom)

    # ------------------------------------------------------------------
    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "选择 PCL / HMCL 配置目录", self.path_edit.text().strip() or ""
        )
        if path:
            self.path_edit.setText(path)
            self._scan()

    def _scan(self) -> None:
        path = self.path_edit.text().strip().strip('"')
        if not path:
            self.status.setText("请先选择目录。")
            return
        profile = scan_profile(path)
        if profile is None:
            self.summary.setText("未识别到 PCL / HMCL 配置：目录里没有 .minecraft 或 versions。")
            self.list.clear()
            self.import_button.setEnabled(False)
            self._profile = None
            return
        self._profile = profile
        local_ids = set()
        try:
            for game_dir in self.ctx.config.game_dirs:
                versions = Path(game_dir.path) / "versions"
                if versions.is_dir():
                    local_ids.update(f.name for f in versions.iterdir() if f.is_dir())
        except OSError:
            pass
        self.list.clear()
        for version in profile.versions:
            text = f"{version.label}    {version.path.parent}"
            if version.version_id in local_ids:
                text += "    （本启动器已有，跳过）"
            item = QListWidgetItem(text)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(
                Qt.Unchecked if version.version_id in local_ids else Qt.Checked
            )
            item.setData(Qt.UserRole, version.version_id)
            self.list.addItem(item)
        self.summary.setText(
            f"识别为 {profile.kind} · 游戏目录 {profile.game_dir} · 共 {len(profile.versions)} 个版本"
        )
        for warning in profile.warnings:
            self.status.setText(warning)
        self.import_button.setEnabled(bool(profile.versions))

    def _do_import(self) -> None:
        if self._profile is None:
            return
        selected = [
            str(self.list.item(i).data(Qt.UserRole))
            for i in range(self.list.count())
            if self.list.item(i).checkState() == Qt.Checked
        ]
        if not selected:
            QMessageBox.information(self, "未选择版本", "请至少勾选一个要导入的版本。")
            return
        stats = import_profile(
            self.ctx.config,
            self._profile,
            selected,
            import_settings=self.settings_check.isChecked(),
            import_global=self.global_check.isChecked(),
        )
        self.ctx.bus.instances_changed.emit()
        self.ctx.bus.config_changed.emit()
        self.ctx.bus.versions_changed.emit()
        imported = stats.get("imported", [])
        skipped = stats.get("skipped", [])
        message = f"已导入 {len(imported)} 个版本"
        if skipped:
            message += f"，跳过 {len(skipped)} 个（本启动器已有或已导入）"
        message += "。\n导入的版本会作为独立实例出现在主页的实例列表中。"
        QMessageBox.information(self, "导入完成", message)
        self.accept()
