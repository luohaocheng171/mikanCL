"""存档工具对话框：世界属性编辑器与版本转换器。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import saves_tools


class _WorldPicker(QWidget):
    """世界下拉框 + 刷新按钮，供两个对话框共用。"""

    def __init__(self, game_dir, parent=None):
        super().__init__(parent)
        self.game_dir = Path(game_dir)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.combo = QComboBox()
        self.combo.setMinimumWidth(240)
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.reload)
        layout.addWidget(self.combo, 1)
        layout.addWidget(self.refresh_btn)
        self._worlds: list[saves_tools.WorldMeta] = []
        self.reload()

    def reload(self) -> None:
        self.combo.clear()
        self._worlds = saves_tools.list_worlds(self.game_dir)
        for meta in self._worlds:
            label = f"{meta.name}  ·  {meta.version_name or '未知版本'}"
            self.combo.addItem(label, meta.folder)

    def current(self) -> saves_tools.WorldMeta | None:
        index = self.combo.currentIndex()
        if index < 0 or index >= len(self._worlds):
            return None
        return self._worlds[index]


class WorldEditorDialog(QDialog):
    """编辑世界常用属性；保存前自动备份 level.dat。"""

    def __init__(self, game_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle("存档编辑器")
        self.setMinimumWidth(520)
        self._meta: saves_tools.WorldMeta | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        self.picker = _WorldPicker(game_dir, self)
        layout.addWidget(self.picker)

        self.summary = QLabel("")
        self.summary.setObjectName("Tiny")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        self.name_edit = QLineEdit()
        form.addRow("世界名称", self.name_edit)

        self.mode_combo = QComboBox()
        for value, label in saves_tools.GAME_MODE_LABELS.items():
            self.mode_combo.addItem(label, value)
        form.addRow("游戏模式", self.mode_combo)

        self.difficulty_combo = QComboBox()
        for value, label in saves_tools.DIFFICULTY_LABELS.items():
            self.difficulty_combo.addItem(label, value)
        form.addRow("难度", self.difficulty_combo)

        self.weather_combo = QComboBox()
        for value, label in saves_tools.WEATHER_LABELS.items():
            self.weather_combo.addItem(label, value)
        form.addRow("天气", self.weather_combo)

        self.day_time_spin = QSpinBox()
        self.day_time_spin.setRange(0, 2147483)
        self.day_time_spin.setToolTip("0 = 清晨，6000 = 正午，12000 = 黄昏，18000 = 午夜")
        form.addRow("世界时间", self.day_time_spin)

        spawn_row = QHBoxLayout()
        spawn_row.setContentsMargins(0, 0, 0, 0)
        spawn_row.setSpacing(6)
        self.spawn_x = QSpinBox()
        self.spawn_y = QSpinBox()
        self.spawn_z = QSpinBox()
        for spin, name in ((self.spawn_x, "X"), (self.spawn_y, "Y"), (self.spawn_z, "Z")):
            spin.setRange(-30000000, 30000000)
            spin.setPrefix(f"{name} ")
            spawn_row.addWidget(spin)
        form.addRow("出生点", spawn_row)

        self.hardcore_check = QCheckBox("极限模式")
        self.allow_commands_check = QCheckBox("允许作弊指令")
        flags = QHBoxLayout()
        flags.setContentsMargins(0, 0, 0, 0)
        flags.addWidget(self.hardcore_check)
        flags.addWidget(self.allow_commands_check)
        flags.addStretch(1)
        form.addRow("开关", flags)

        self.keep_inventory_check = QCheckBox("死亡不掉落（keepInventory）")
        form.addRow("规则", self.keep_inventory_check)

        layout.addLayout(form)

        tip = QLabel(
            "保存前会先把原始 level.dat 备份为同目录的 level.dat.<时间戳>.bak（保留最近 5 份）。"
            "请先完全退出游戏，否则改动可能被游戏覆盖。"
        )
        tip.setObjectName("Tiny")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        buttons = QDialogButtonBox()
        self.save_btn = buttons.addButton("保存修改", QDialogButtonBox.AcceptRole)
        buttons.addButton("取消", QDialogButtonBox.RejectRole)
        self.save_btn.clicked.connect(self._save)
        layout.addWidget(buttons)

        self.picker.combo.currentIndexChanged.connect(self._load_current)
        self._load_current()

    def _load_current(self) -> None:
        meta = self.picker.current()
        self._meta = meta
        enabled = meta is not None
        for widget in (
            self.name_edit,
            self.mode_combo,
            self.difficulty_combo,
            self.weather_combo,
            self.day_time_spin,
            self.spawn_x,
            self.spawn_y,
            self.spawn_z,
            self.hardcore_check,
            self.allow_commands_check,
            self.keep_inventory_check,
            self.save_btn,
        ):
            widget.setEnabled(enabled)
        if meta is None:
            self.summary.setText("这个版本目录下还没有世界存档。")
            return
        self.summary.setText(
            f"文件夹：{meta.folder} · 当前版本：{meta.version_name or '未知'} "
            f"(DataVersion {meta.data_version})"
        )
        self.name_edit.setText(meta.name)
        index = self.mode_combo.findData(meta.game_type)
        self.mode_combo.setCurrentIndex(max(0, index))
        index = self.difficulty_combo.findData(meta.difficulty)
        self.difficulty_combo.setCurrentIndex(max(0, index))
        index = self.weather_combo.findData(meta.weather)
        self.weather_combo.setCurrentIndex(max(0, index))
        self.day_time_spin.setValue(max(0, min(self.day_time_spin.maximum(), meta.day_time)))
        self.spawn_x.setValue(meta.spawn[0])
        self.spawn_y.setValue(meta.spawn[1])
        self.spawn_z.setValue(meta.spawn[2])
        self.hardcore_check.setChecked(meta.hardcore)
        self.allow_commands_check.setChecked(meta.allow_commands)
        self.keep_inventory_check.setChecked(
            str(meta.game_rules.get("keepInventory", "")).lower() == "true"
        )

    def _save(self) -> None:
        meta = self._meta
        if meta is None:
            return
        try:
            updated = saves_tools.apply_edits(
                meta.path,
                {
                    "name": self.name_edit.text().strip(),
                    "game_type": self.mode_combo.currentData(),
                    "difficulty": self.difficulty_combo.currentData(),
                    "weather": self.weather_combo.currentData(),
                    "day_time": self.day_time_spin.value(),
                    "spawn": (
                        self.spawn_x.value(),
                        self.spawn_y.value(),
                        self.spawn_z.value(),
                    ),
                    "hardcore": self.hardcore_check.isChecked(),
                    "allow_commands": self.allow_commands_check.isChecked(),
                    "game_rules": {
                        "keepInventory": "true" if self.keep_inventory_check.isChecked() else "false"
                    },
                },
            )
        except saves_tools.SaveToolError as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        QMessageBox.information(
            self,
            "已保存",
            f"世界「{updated.name}」已更新。\n原始 level.dat 已备份到同目录的 .bak 文件。",
        )
        self.accept()


class WorldConvertDialog(QDialog):
    """把存档的版本标记改写为目标版本。"""

    def __init__(self, game_dir, installed_versions: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("存档转换器")
        self.setMinimumWidth(540)
        self._meta: saves_tools.WorldMeta | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        self.picker = _WorldPicker(game_dir, self)
        layout.addWidget(self.picker)

        self.summary = QLabel("")
        self.summary.setObjectName("Tiny")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        self.target_combo = QComboBox()
        self.target_combo.setEditable(True)
        self.target_combo.setInsertPolicy(QComboBox.NoInsert)
        for version_id in installed_versions:
            self.target_combo.addItem(version_id)
        self.target_combo.setCurrentText("")
        self.target_combo.lineEdit().setPlaceholderText("例如 1.20.1")
        form.addRow("目标版本", self.target_combo)

        self.data_version_spin = QSpinBox()
        self.data_version_spin.setRange(0, 99999)
        self.data_version_spin.setToolTip("0 表示清除 DataVersion（1.9 以前的旧格式）")
        form.addRow("DataVersion", self.data_version_spin)

        self.snapshot_check = QCheckBox("标记为快照版本")
        form.addRow("选项", self.snapshot_check)

        layout.addLayout(form)

        tip = QLabel(
            "转换只改写 level.dat 中的 DataVersion 与 Version 标记，不做区块数据升级。\n"
            "用低版本打开高版本存档仍可能失败或损坏世界，转换前建议先整份备份世界目录。"
            "写入前会自动备份 level.dat。"
        )
        tip.setObjectName("Tiny")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        buttons = QDialogButtonBox()
        self.convert_btn = buttons.addButton("开始转换", QDialogButtonBox.AcceptRole)
        buttons.addButton("取消", QDialogButtonBox.RejectRole)
        self.convert_btn.clicked.connect(self._convert)
        layout.addWidget(buttons)

        self.picker.combo.currentIndexChanged.connect(self._load_current)
        self.target_combo.currentTextChanged.connect(self._sync_data_version)
        self._load_current()

    def _load_current(self) -> None:
        meta = self.picker.current()
        self._meta = meta
        enabled = meta is not None
        self.convert_btn.setEnabled(enabled)
        self.target_combo.setEnabled(enabled)
        if meta is None:
            self.summary.setText("这个版本目录下还没有世界存档。")
            return
        self.summary.setText(
            f"文件夹：{meta.folder} · 当前版本：{meta.version_name or '未知'} "
            f"(DataVersion {meta.data_version})"
        )
        if not self.target_combo.currentText().strip():
            self._sync_data_version(meta.version_name)

    def _sync_data_version(self, text: str) -> None:
        info = saves_tools.resolve_target(text) if str(text or "").strip() else {}
        value = int(info.get("data_version") or 0) if info else 0
        if value > 0:
            self.data_version_spin.setValue(value)

    def _convert(self) -> None:
        meta = self._meta
        if meta is None:
            return
        target = self.target_combo.currentText().strip()
        if not target:
            QMessageBox.information(self, "请填写目标版本", "目标版本不能为空，例如 1.20.1。")
            return
        if self.data_version_spin.value() <= 0:
            answer = QMessageBox.question(
                self,
                "确认清除 DataVersion",
                "DataVersion 为 0 会清除版本标记，仅适用于 1.9 以前的旧版本。\n"
                "如果你要转换到 1.9 及以上版本，请填写对应的 DataVersion。是否继续？",
            )
            if answer != QMessageBox.Yes:
                return
        answer = QMessageBox.question(
            self,
            "确认转换",
            f"将把世界「{meta.name}」的版本标记从 "
            f"{meta.version_name or '未知'} 改为 {target}。\n"
            "转换前会自动备份 level.dat，但整份世界仍建议另外备份。是否继续？",
        )
        if answer != QMessageBox.Yes:
            return
        try:
            result = saves_tools.convert_world(
                meta.path,
                target,
                data_version=self.data_version_spin.value(),
                snapshot=self.snapshot_check.isChecked(),
            )
        except saves_tools.SaveToolError as exc:
            QMessageBox.warning(self, "转换失败", str(exc))
            return
        before = result.get("before") or {}
        after = result.get("after") or {}
        QMessageBox.information(
            self,
            "转换完成",
            "版本标记已更新：\n"
            f"{before.get('version_name') or '未知'} (DataVersion {before.get('data_version')})\n"
            "→\n"
            f"{after.get('version_name')} (DataVersion {after.get('data_version')})\n\n"
            f"备份文件：{result.get('backup')}",
        )
        self._load_current()
