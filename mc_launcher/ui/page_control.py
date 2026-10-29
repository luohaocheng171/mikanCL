"""版本设置页：单个实例/版本的概览、游戏设置、内容管理与版本维护。"""

from __future__ import annotations

import json
import re
import shutil
import time
import zipfile
from pathlib import Path

from PySide6.QtCore import QThread, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME
from ..config import ISOLATION_LABELS, PROCESS_PRIORITIES
from ..content import ContentError, ContentProject, ContentVersion
from ..context import AppContext
from ..version import InstalledVersion, VersionError, load_version, scan_installed_versions
from .widgets import Badge, Card, card_title_row, hline, page_header, scroll_page

NAV_ITEMS = ("概览", "游戏设置", "模组管理", "资源包管理", "光影包管理", "版本管理")

FILE_CATEGORIES = {
    "mods": {
        "label": "Mod",
        "suffixes": (".jar", ".zip"),
        "hint": "支持 .jar 与 .zip；禁用时会在原文件名后追加 .disabled 后缀。",
        "online": "在线添加 Mod",
    },
    "resourcepacks": {
        "label": "资源包",
        "suffixes": (".zip",),
        "hint": "支持 .zip 资源包；禁用时会在原文件名后追加 .disabled 后缀。",
        "online": "在线添加资源包",
    },
    "shaderpacks": {
        "label": "光影包",
        "suffixes": (".zip",),
        "hint": "支持 .zip 光影包；禁用时会在原文件名后追加 .disabled 后缀。",
        "online": "在线添加光影包",
    },
}

DISABLED_SUFFIX = ".disabled"

LOADER_API_KEYS = {
    "Forge": "forge",
    "NeoForge": "neoforge",
    "Fabric": "fabric",
    "Quilt": "quilt",
    "LiteLoader": "liteloader",
    "OptiFine": "optifine",
    "原版": "",
}

ISOLATED_KEYS = {
    "mods": {"mods"},
    "saves": {"saves"},
    "all": {"mods", "saves", "resourcepacks", "shaderpacks"},
}


class ModUpdateWorker(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, content, jars: list, game_version: str, loader: str, parent=None):
        super().__init__(parent)
        self.content = content
        self.jars = list(jars)
        self.game_version = game_version
        self.loader = loader

    def run(self) -> None:
        try:
            updates = self.content.check_mod_updates(
                self.jars, self.game_version, self.loader
            )
            self.done.emit(updates)
        except ContentError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"检查更新失败：{exc}")


class ModUpdateApplyWorker(QThread):
    progress = Signal(float, str)
    log = Signal(str)
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, ctx: AppContext, updates: list, game_dir: Path, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.updates = list(updates)
        self.game_dir = Path(game_dir)

    def run(self) -> None:
        total = max(1, len(self.updates))
        try:
            for index, (path, version) in enumerate(self.updates):
                self.progress.emit(index / total, f"更新 {path.name}…")
                project = ContentProject(
                    source="modrinth",
                    id=version.project_id,
                    title=path.stem,
                    project_type="mod",
                    slug=version.project_id,
                )
                self.ctx.content.install_content(
                    project, version, self.game_dir, log=self.log.emit
                )
                if path.exists():
                    try:
                        path.unlink()
                    except OSError as exc:
                        self.log.emit(f"[更新] 无法删除旧文件 {path.name}：{exc}")
            self.progress.emit(1.0, "更新完成")
            self.done.emit(f"已更新 {len(self.updates)} 个 Mod。")
        except ContentError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"更新失败：{exc}")


def _human_size(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


class ExportPackWorker(QThread):
    progress = Signal(float, str)
    done = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        version,
        folders: list[tuple[Path, str]],
        target: Path,
        instance_meta: dict | None = None,
        extra_files: list[tuple[Path, str]] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.version = version
        self.folders = list(folders)
        self.target = Path(target)
        self.instance_meta = instance_meta
        self.extra_files = list(extra_files or [])

    def _manifest(self) -> dict:
        loader_key = LOADER_API_KEYS.get(self.version.loader, "")
        loader_id = ""
        if loader_key:
            match = re.search(
                rf"{loader_key}(?:-loader)?[-_]?(\d+\.\d+(?:\.\d+)?)",
                self.version.id,
                re.IGNORECASE,
            )
            loader_id = f"{loader_key}-{match.group(1)}" if match else loader_key
        return {
            "minecraft": {
                "version": self.version.base_version or "",
                "modLoaders": (
                    [{"id": loader_id, "primary": True}] if loader_id else []
                ),
            },
            "manifestType": "minecraftModpack",
            "manifestVersion": 1,
            "name": f"{self.version.id} 整合包",
            "author": "MikanCL",
            "version": "1.0.0",
            "files": [],
        }

    def run(self) -> None:
        try:
            self.target.parent.mkdir(parents=True, exist_ok=True)
            if self.target.exists():
                self.target.unlink()
            items: list[tuple[Path, str]] = []
            for folder, prefix in self.folders:
                if not folder.is_dir():
                    continue
                for path in folder.rglob("*"):
                    if path.is_file():
                        items.append((path, f"{prefix}/{path.relative_to(folder).as_posix()}"))
            for path, arcname in self.extra_files:
                if path.is_file():
                    items.append((path, arcname))
            total = max(1, len(items))
            with zipfile.ZipFile(self.target, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr(
                    "manifest.json",
                    json.dumps(self._manifest(), ensure_ascii=False, indent=2),
                )
                if self.instance_meta is not None:
                    # 让 MikanCL 能识别并恢复原实例（版本、加载器、内存、窗口标题等）
                    archive.writestr(
                        "instance.json",
                        json.dumps(
                            {"format": "mikan/1", "instance": self.instance_meta},
                            ensure_ascii=False,
                            indent=2,
                        ),
                    )
                for index, (path, arcname) in enumerate(items):
                    self.progress.emit(index / total, f"打包 {arcname}")
                    archive.write(path, f"overrides/{arcname}")
            self.progress.emit(1.0, "打包完成")
            self.done.emit(str(self.target))
        except (OSError, ValueError) as exc:
            self.failed.emit(str(exc))


class ControlPage(QWidget):
    """单个 Minecraft 版本/实例的设置页。"""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self._refreshing = False
        self._versions: dict[str, InstalledVersion] = {}
        self._file_tables: dict[str, QTableWidget] = {}
        self._file_empty_labels: dict[str, QLabel] = {}
        self._file_count_labels: dict[str, QLabel] = {}
        self._file_conflict_labels: dict[str, QLabel] = {}
        self._mod_updates: dict[str, ContentVersion] = {}
        self._mod_update_worker: ModUpdateWorker | None = None
        self._mod_apply_worker: ModUpdateApplyWorker | None = None
        self._export_worker: ExportPackWorker | None = None
        self.overview_labels: dict[str, QLabel] = {}
        self.manage_labels: dict[str, QLabel] = {}
        self._build()
        self.ctx.bus.versions_changed.connect(self.refresh)
        self.ctx.bus.instances_changed.connect(self.refresh)
        self.ctx.bus.config_changed.connect(self._reload_game_settings)
        self.ctx.bus.javas_changed.connect(self._reload_game_settings)
        self.ctx.bus.focus_version.connect(self._focus_version)
        self.refresh()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 20, 26, 20)
        outer.setSpacing(14)

        header, header_layout = page_header(
            "版本设置", "管理当前版本的 Mod、资源包、光影包与启动参数"
        )
        self.open_dir_button = QPushButton("打开游戏目录")
        self.open_dir_button.setObjectName("Ghost")
        self.open_dir_button.clicked.connect(self._open_game_dir)
        header_layout.addWidget(self.open_dir_button)
        outer.addWidget(header)

        select_card = Card(margins=14, spacing=10)
        row = QHBoxLayout()
        row.setSpacing(10)
        caption = QLabel("实例")
        caption.setObjectName("Muted")
        row.addWidget(caption)
        self.instance_combo = QComboBox()
        self.instance_combo.setFixedWidth(210)
        self.instance_combo.currentIndexChanged.connect(self._on_instance_changed)
        row.addWidget(self.instance_combo)
        caption = QLabel("版本")
        caption.setObjectName("Muted")
        row.addWidget(caption)
        self.version_combo = QComboBox()
        self.version_combo.setMinimumWidth(240)
        self.version_combo.currentIndexChanged.connect(self._on_version_changed)
        row.addWidget(self.version_combo)
        self.path_label = QLabel("")
        self.path_label.setObjectName("Tiny")
        row.addWidget(self.path_label, 1)
        select_card.body.addLayout(row)
        outer.addWidget(select_card)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        outer.addWidget(splitter, 1)

        self.nav_list = QListWidget()
        self.nav_list.setObjectName("SettingsNav")
        self.nav_list.setFixedWidth(184)
        for text in NAV_ITEMS:
            self.nav_list.addItem(text)
        splitter.addWidget(self.nav_list)

        self.stack = QStackedWidget()
        splitter.addWidget(self.stack)

        self.stack.addWidget(scroll_page(self._build_overview_page()))
        self.stack.addWidget(scroll_page(self._build_game_page()))
        for key in ("mods", "resourcepacks", "shaderpacks"):
            self.stack.addWidget(self._build_files_page(key))
        self.stack.addWidget(scroll_page(self._build_manage_page()))

        self.nav_list.currentRowChanged.connect(self._on_nav_changed)
        self.nav_list.setCurrentRow(0)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

    def _build_overview_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        card = Card(margins=20, spacing=12)
        self.overview_badge = Badge("未选择", "gray")
        card.body.addWidget(
            card_title_row("版本概览", "当前所选版本的基本信息", self.overview_badge)
        )

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignTrailing)
        for key, text in (
            ("id", "版本 ID"),
            ("type", "版本类型"),
            ("loader", "加载器"),
            ("path", "所在目录"),
            ("java", "Java 要求"),
            ("modified", "文件修改时间"),
        ):
            label = QLabel("—")
            label.setWordWrap(True)
            self.overview_labels[key] = label
            form.addRow(text, label)
        card.body.addLayout(form)
        card.body.addWidget(hline())

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        launch = QPushButton("启动游戏")
        launch.setObjectName("Primary")
        launch.clicked.connect(lambda: self.ctx.bus.navigate.emit("home"))
        buttons.addWidget(launch)
        open_version = QPushButton("打开版本文件夹")
        open_version.clicked.connect(self._open_version_dir)
        buttons.addWidget(open_version)
        buttons.addStretch(1)
        remove_version = QPushButton("删除此版本")
        remove_version.setObjectName("Danger")
        remove_version.clicked.connect(self._delete_version_dir)
        buttons.addWidget(remove_version)
        card.body.addLayout(buttons)
        layout.addWidget(card)

        hint = QLabel("删除版本会连同 versions/<版本 ID> 目录一并移除，绑定该版本的实例记录也会被清理。")
        hint.setObjectName("Tiny")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)
        return page

    def _build_game_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        card = Card(margins=20, spacing=10)
        card.body.addWidget(
            card_title_row("游戏设置", "以下配置为全局设置，对所有实例和版本生效")
        )

        form = QFormLayout()
        form.setSpacing(9)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignTrailing)

        self.java_combo = QComboBox()
        form.addRow("Java 运行时", self.java_combo)

        self.memory_spin = QSpinBox()
        self.memory_spin.setRange(512, 65536)
        self.memory_spin.setSingleStep(512)
        self.memory_spin.setSuffix(" MB")
        form.addRow("最大内存", self.memory_spin)

        resolution = QHBoxLayout()
        resolution.setSpacing(6)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(0, 7680)
        self.width_spin.setSpecialValueText("默认")
        self.height_spin = QSpinBox()
        self.height_spin.setRange(0, 4320)
        self.height_spin.setSpecialValueText("默认")
        resolution.addWidget(self.width_spin)
        resolution.addWidget(QLabel("×"))
        resolution.addWidget(self.height_spin)
        resolution.addStretch(1)
        form.addRow("窗口分辨率", resolution)

        self.jvm_args = QPlainTextEdit()
        self.jvm_args.setFixedHeight(58)
        self.jvm_args.setPlaceholderText("-XX:+UseG1GC -XX:MaxGCPauseMillis=100")
        form.addRow("额外 JVM 参数", self.jvm_args)

        self.game_args = QPlainTextEdit()
        self.game_args.setFixedHeight(58)
        self.game_args.setPlaceholderText("--fullscreen --lang zh_CN")
        form.addRow("额外游戏参数", self.game_args)
        card.body.addLayout(form)

        card.body.addWidget(hline())

        server_row = QHBoxLayout()
        server_row.setSpacing(8)
        self.auto_server_check = QCheckBox("自动连接服务器")
        self.auto_server_check.toggled.connect(self._on_auto_server_toggled)
        server_row.addWidget(self.auto_server_check)
        self.server_edit = QLineEdit()
        self.server_edit.setPlaceholderText("play.example.com")
        server_row.addWidget(self.server_edit, 1)
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(25565)
        server_row.addWidget(self.port_spin)
        card.body.addLayout(server_row)

        self.hide_check = QCheckBox("启动游戏后隐藏启动器（可从托盘恢复）")
        card.body.addWidget(self.hide_check)

        save_row = QHBoxLayout()
        save = QPushButton("保存设置")
        save.setObjectName("Primary")
        save.clicked.connect(self._save_game_settings)
        save_row.addWidget(save)
        save_row.addStretch(1)
        card.body.addLayout(save_row)

        hint = QLabel("JVM 参数与游戏参数按空格分隔；自动连接等同于向游戏传入 --server 与 --port。")
        hint.setObjectName("Tiny")
        hint.setWordWrap(True)
        card.body.addWidget(hint)
        layout.addWidget(card)

        version_card = Card(margins=20, spacing=10)
        version_card.body.addWidget(
            card_title_row("当前版本设置", "仅对下方选中的版本生效，留空或 0 表示跟随全局")
        )
        self.version_note = QLabel("当前版本：未选择")
        self.version_note.setObjectName("Muted")
        version_card.body.addWidget(self.version_note)

        version_form = QFormLayout()
        version_form.setSpacing(9)
        version_form.setLabelAlignment(Qt.AlignRight | Qt.AlignTrailing)

        self.ver_isolation = QComboBox()
        self.ver_isolation.addItem("跟随全局", "")
        for key, label in ISOLATION_LABELS.items():
            self.ver_isolation.addItem(label, key)
        version_form.addRow("版本隔离", self.ver_isolation)

        self.ver_memory = QSpinBox()
        self.ver_memory.setRange(0, 65536)
        self.ver_memory.setSingleStep(512)
        self.ver_memory.setSpecialValueText("跟随全局")
        self.ver_memory.setSuffix(" MB")
        version_form.addRow("最大内存", self.ver_memory)

        self.ver_priority = QComboBox()
        self.ver_priority.addItem("跟随全局", "")
        for key, label in PROCESS_PRIORITIES.items():
            self.ver_priority.addItem(label, key)
        version_form.addRow("进程优先级", self.ver_priority)

        self.ver_title = QLineEdit()
        self.ver_title.setPlaceholderText("留空则跟随全局设置")
        version_form.addRow("游戏窗口标题", self.ver_title)

        self.ver_jvm = QPlainTextEdit()
        self.ver_jvm.setFixedHeight(52)
        self.ver_jvm.setPlaceholderText("追加到全局 JVM 参数之后")
        version_form.addRow("额外 JVM 参数", self.ver_jvm)

        self.ver_game = QPlainTextEdit()
        self.ver_game.setFixedHeight(52)
        self.ver_game.setPlaceholderText("追加到全局游戏参数之后，例如 --fullscreen")
        version_form.addRow("额外游戏参数", self.ver_game)
        version_card.body.addLayout(version_form)

        self.ver_server_check = QCheckBox("启动后自动连接指定服务器")
        self.ver_server_check.toggled.connect(self._on_ver_server_toggled)
        version_card.body.addWidget(self.ver_server_check)

        ver_server_row = QHBoxLayout()
        ver_server_row.setSpacing(8)
        self.ver_server_edit = QLineEdit()
        self.ver_server_edit.setPlaceholderText("play.example.com")
        ver_server_row.addWidget(self.ver_server_edit, 1)
        self.ver_port_spin = QSpinBox()
        self.ver_port_spin.setRange(1, 65535)
        self.ver_port_spin.setValue(25565)
        ver_server_row.addWidget(self.ver_port_spin)
        version_card.body.addLayout(ver_server_row)

        ver_save_row = QHBoxLayout()
        ver_save = QPushButton("保存当前版本设置")
        ver_save.setObjectName("Primary")
        ver_save.clicked.connect(self._save_version_settings)
        ver_save_row.addWidget(ver_save)
        ver_save_row.addStretch(1)
        version_card.body.addLayout(ver_save_row)
        layout.addWidget(version_card)
        layout.addStretch(1)
        return page

    def _build_files_page(self, key: str) -> QWidget:
        spec = FILE_CATEGORIES[key]
        label = str(spec["label"])
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        card = Card(margins=14, spacing=10)
        card.body.addWidget(card_title_row(f"{label}管理", str(spec["hint"])))

        if key == "mods":
            self._conflict_label = QLabel("")
            self._conflict_label.setStyleSheet("color: #ff6b6b; font-weight: 600;")
            self._conflict_label.setWordWrap(True)
            self._conflict_label.setVisible(False)
            card.body.addWidget(self._conflict_label)
            self._file_conflict_labels[key] = self._conflict_label

        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(["文件名", "大小", "状态"])
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.ExtendedSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(True)
        table.setColumnWidth(0, 340)
        table.setColumnWidth(1, 100)
        table.doubleClicked.connect(lambda _index, k=key: self._toggle_selected(k))
        card.body.addWidget(table, 1)
        self._file_tables[key] = table

        empty_label = QLabel("")
        empty_label.setObjectName("Tiny")
        empty_label.setWordWrap(True)
        card.body.addWidget(empty_label)
        self._file_empty_labels[key] = empty_label

        card.body.addWidget(hline())

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        enable = QPushButton("启用")
        enable.clicked.connect(lambda _checked=False, k=key: self._set_enabled(k, True))
        buttons.addWidget(enable)
        disable = QPushButton("禁用")
        disable.clicked.connect(lambda _checked=False, k=key: self._set_enabled(k, False))
        buttons.addWidget(disable)
        if key == "resourcepacks":
            up = QPushButton("上移")
            up.setObjectName("Ghost")
            up.clicked.connect(lambda _checked=False: self._move_resource_pack(-1))
            buttons.addWidget(up)
            down = QPushButton("下移")
            down.setObjectName("Ghost")
            down.clicked.connect(lambda _checked=False: self._move_resource_pack(1))
            buttons.addWidget(down)
        remove = QPushButton("删除")
        remove.setObjectName("Danger")
        remove.clicked.connect(lambda _checked=False, k=key: self._delete_selected(k))
        buttons.addWidget(remove)
        add = QPushButton("添加文件")
        add.setObjectName("Primary")
        add.clicked.connect(lambda _checked=False, k=key: self._add_files(k))
        buttons.addWidget(add)
        folder = QPushButton("打开文件夹")
        folder.setObjectName("Ghost")
        folder.clicked.connect(lambda _checked=False, k=key: self._open_folder(k))
        buttons.addWidget(folder)
        online = QPushButton(str(spec["online"]))
        online.setObjectName("Ghost")
        online.clicked.connect(lambda: self.ctx.bus.navigate.emit("content"))
        buttons.addWidget(online)
        if key == "mods":
            self.mod_update_button = QPushButton("检查更新")
            self.mod_update_button.setObjectName("Ghost")
            self.mod_update_button.clicked.connect(self._check_mod_updates)
            buttons.addWidget(self.mod_update_button)
            self.mod_apply_button = QPushButton("安装更新")
            self.mod_apply_button.setEnabled(False)
            self.mod_apply_button.clicked.connect(self._install_mod_updates)
            buttons.addWidget(self.mod_apply_button)
        buttons.addStretch(1)
        count_label = QLabel("")
        count_label.setObjectName("Tiny")
        buttons.addWidget(count_label)
        self._file_count_labels[key] = count_label
        card.body.addLayout(buttons)

        layout.addWidget(card, 1)
        return page

    def _build_manage_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        card = Card(margins=20, spacing=12)
        self.manage_badge = Badge("普通实例", "gray")
        card.body.addWidget(
            card_title_row("实例信息", "当前实例与版本的绑定关系及文件位置", self.manage_badge)
        )

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignTrailing)
        for key, text in (
            ("name", "名称"),
            ("dir", "目录"),
            ("version", "绑定版本"),
            ("loader", "加载器"),
            ("modpack", "是否整合包"),
        ):
            label = QLabel("—")
            label.setWordWrap(True)
            self.manage_labels[key] = label
            form.addRow(text, label)
        card.body.addLayout(form)
        card.body.addWidget(hline())

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        rename = QPushButton("重命名实例")
        rename.clicked.connect(self._rename_instance)
        buttons.addWidget(rename)
        open_dir = QPushButton("打开目录")
        open_dir.clicked.connect(self._open_game_dir)
        buttons.addWidget(open_dir)
        import_world = QPushButton("导入世界存档…")
        import_world.clicked.connect(self._import_world_archive)
        buttons.addWidget(import_world)
        export_pack = QPushButton("导出为整合包…")
        export_pack.clicked.connect(self._export_modpack)
        buttons.addWidget(export_pack)
        buttons.addStretch(1)
        remove_version = QPushButton("删除版本目录")
        remove_version.setObjectName("Danger")
        remove_version.clicked.connect(self._delete_version_dir)
        buttons.addWidget(remove_version)
        remove_instance = QPushButton("移除实例记录")
        remove_instance.setObjectName("Danger")
        remove_instance.clicked.connect(self._remove_instance_record)
        buttons.addWidget(remove_instance)
        card.body.addLayout(buttons)
        layout.addWidget(card)

        hint = QLabel(
            "移除实例记录只删除启动器中的实例配置，磁盘上的游戏文件会保留；"
            "删除版本目录会永久删除 versions/<版本 ID> 及其中的全部文件。默认实例不可改名或移除。"
        )
        hint.setObjectName("Tiny")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)
        return page

    def _import_world_archive(self) -> None:
        version = self._current_version()
        if version is None:
            QMessageBox.information(self, APP_NAME, "请先选择一个版本。")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "选择世界存档", str(Path.home()), "世界存档压缩包 (*.zip)"
        )
        if not path:
            return
        from ..content import ContentError
        from .dropinstall import install_file

        target = {"game_dir": str(self._instance_dir()), "version_id": version.id}
        try:
            destination = install_file(self.ctx, Path(path), "world", target)
        except ContentError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        self.ctx.bus.toast.emit(f"世界存档已导入：{destination}")
        self.ctx.bus.log.emit(f"[存档] 已导入到 {destination}")

    def _export_modpack(self) -> None:
        version = self._current_version()
        if version is None:
            QMessageBox.information(self, APP_NAME, "请先选择一个版本。")
            return
        if self._export_worker is not None and self._export_worker.isRunning():
            self.ctx.bus.toast.emit("已有整合包导出任务在进行中。")
            return
        target, _ = QFileDialog.getSaveFileName(
            self,
            "导出为整合包 / 实例备份",
            str(Path.home() / f"{version.id}-整合包.mikan"),
            "MikanCL 实例备份 (*.mikan);;CurseForge 整合包 (*.zip)",
        )
        if not target:
            return
        if not Path(target).suffix:
            target += ".mikan"
        folders: list[tuple[Path, str]] = []
        for key, prefix in (
            ("mods", "mods"),
            ("resourcepacks", "resourcepacks"),
            ("shaderpacks", "shaderpacks"),
        ):
            folder = self._files_dir(key)
            if folder.is_dir():
                folders.append((folder, prefix))
        config_dir = self._instance_dir() / "config"
        if config_dir.is_dir():
            folders.append((config_dir, "config"))
        extra_files: list[tuple[Path, str]] = []
        options = self._files_dir("resourcepacks").parent / "options.txt"
        if options.is_file():
            extra_files.append((options, "options.txt"))

        instance = self.ctx.config.get_instance(self._current_instance_id())
        if instance is not None:
            instance_meta = instance.to_dict()
        else:
            instance_meta = {
                "name": version.id,
                "version_id": version.id,
                "loader": version.loader or "",
                "mc_version": version.base_version or "",
                "modpack": "",
                "loader_version": "",
                "memory_mb": 0,
                "window_title": "",
                "extra_jvm_args": "",
            }

        self._export_worker = ExportPackWorker(
            version, folders, Path(target), instance_meta, extra_files, self
        )
        self._export_worker.progress.connect(
            lambda _value, detail: self.ctx.bus.toast.emit(detail)
        )
        self._export_worker.done.connect(self._on_export_done)
        self._export_worker.failed.connect(
            lambda message: QMessageBox.warning(self, APP_NAME, f"导出失败：{message}")
        )
        self._export_worker.start()
        self.ctx.bus.toast.emit("正在打包当前版本…")

    def _on_export_done(self, path: str) -> None:
        self.ctx.bus.toast.emit(f"整合包已导出：{path}")
        box = QMessageBox(self)
        box.setWindowTitle(APP_NAME)
        box.setText(f"整合包已导出到：\n{path}")
        box.setInformativeText(
            "包含 mods、资源包、光影包、config 与 instance.json；"
            "可在 MikanCL 中拖入直接恢复原实例，也可在其他启动器中作为整合包导入。"
        )
        open_button = box.addButton("打开所在文件夹", QMessageBox.ActionRole)
        box.addButton("关闭", QMessageBox.AcceptRole)
        box.exec()
        if box.clickedButton() is open_button:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        try:
            self._reload_instances()
            self._reload_versions()
            self._reload_game_settings()
            self._reload_overview()
            self._reload_manage()
            for key in FILE_CATEGORIES:
                self._reload_files(key)
        finally:
            self._refreshing = False

    def shutdown(self) -> None:
        for worker in (self._mod_update_worker, self._mod_apply_worker, self._export_worker):
            if worker is not None and worker.isRunning():
                worker.requestInterruption()
                worker.wait(2000)
        self._mod_update_worker = None
        self._mod_apply_worker = None
        self._export_worker = None

    # ------------------------------------------------------------------
    def _current_instance_id(self) -> str:
        return str(self.instance_combo.currentData() or "default")

    def _instance_dir(self) -> Path:
        return self.ctx.config.instance_path(self._current_instance_id())

    def _files_dir(self, key: str) -> Path:
        base = self._instance_dir()
        version = self._current_version()
        mode = self.ctx.config.isolation_for(version.id) if version else "none"
        if key == "mods" and "mods" in ISOLATED_KEYS.get(mode, set()):
            return base / "versions" / version.id / "game" / key
        if key in ("saves",) and "saves" in ISOLATED_KEYS.get(mode, set()):
            return base / "versions" / version.id / "game" / key
        if key in ("resourcepacks", "shaderpacks") and mode == "all":
            return base / "versions" / version.id / "game" / key
        return base / key

    def _current_version(self) -> InstalledVersion | None:
        version_id = str(self.version_combo.currentData() or "")
        return self._versions.get(version_id)

    def _on_nav_changed(self, index: int) -> None:
        if 0 <= index < self.stack.count():
            self.stack.setCurrentIndex(index)

    def _reload_instances(self) -> None:
        current = self.ctx.config.selected_instance_id
        self.instance_combo.blockSignals(True)
        self.instance_combo.clear()
        for instance in self.ctx.config.instance_list():
            label = instance.name
            if instance.version_id:
                label += f" · {instance.version_id}"
            self.instance_combo.addItem(label, instance.id)
        index = self.instance_combo.findData(current)
        self.instance_combo.setCurrentIndex(index if index >= 0 else 0)
        self.instance_combo.blockSignals(False)

    def _reload_versions(self) -> None:
        game_dir = self._instance_dir()
        versions = scan_installed_versions(game_dir)
        self._versions = {version.id: version for version in versions}
        instance = self.ctx.config.get_instance(self._current_instance_id())
        preferred = instance.version_id if instance is not None else ""

        self.version_combo.blockSignals(True)
        self.version_combo.clear()
        for version in versions:
            self.version_combo.addItem(f"{version.id} · {version.loader}", version.id)
        index = self.version_combo.findData(preferred)
        self.version_combo.setCurrentIndex(index if index >= 0 else (0 if versions else -1))
        self.version_combo.blockSignals(False)

        version = self._current_version()
        folder = version.path.parent if version is not None else game_dir
        self.path_label.setText(str(folder))
        self.path_label.setToolTip(str(folder))

    def _on_instance_changed(self, _index: int) -> None:
        if self._refreshing:
            return
        instance_id = self._current_instance_id()
        if instance_id == self.ctx.config.selected_instance_id:
            return
        self.ctx.config.select_instance(instance_id)
        self.ctx.bus.instances_changed.emit()

    def _on_version_changed(self, _index: int) -> None:
        if self._refreshing:
            return
        version_id = str(self.version_combo.currentData() or "")
        if not version_id:
            return
        self._reload_version_settings()
        instance_id = self._current_instance_id()
        if instance_id == "default":
            if self.ctx.config.default_version_id == version_id:
                return
            self.ctx.config.default_version_id = version_id
            self.ctx.config.save()
        else:
            instance = self.ctx.config.get_instance(instance_id)
            if instance is None or instance.version_id == version_id:
                return
            instance.version_id = version_id
            self.ctx.config.save()
        self.ctx.bus.instances_changed.emit()

    def _focus_version(self, version_id: str) -> None:
        """从主页右键菜单跳转过来时，选中对应版本并切到游戏设置。"""
        self.refresh()
        index = self.version_combo.findData(version_id)
        if index >= 0:
            self.version_combo.setCurrentIndex(index)
        self.nav_list.setCurrentRow(1)
        self.stack.setCurrentIndex(1)
        self._reload_version_settings()

    # ------------------------------------------------------------------
    def _reload_overview(self) -> None:
        version = self._current_version()
        if version is None:
            for label in self.overview_labels.values():
                label.setText("—")
            self.overview_badge.setText("未选择")
            self.overview_badge.set_kind("gray")
            return

        self.overview_labels["id"].setText(version.id)
        self.overview_labels["type"].setText(version.display_type)
        self.overview_labels["loader"].setText(version.loader)
        self.overview_labels["path"].setText(str(version.path.parent))

        java_text = "—"
        try:
            major = load_version(self._instance_dir(), version.id).java_major
        except (OSError, TypeError, ValueError, VersionError):
            major = None
        if major:
            java_text = f"Java {major}"
        self.overview_labels["java"].setText(java_text)

        if version.modified:
            stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(version.modified))
            self.overview_labels["modified"].setText(stamp)
        else:
            self.overview_labels["modified"].setText("—")

        if version.type == "broken":
            self.overview_badge.setText("损坏")
            self.overview_badge.set_kind("orange")
        elif version.loader and version.loader != "原版":
            self.overview_badge.setText(version.loader)
            self.overview_badge.set_kind("green")
        else:
            self.overview_badge.setText(version.loader or "原版")
            self.overview_badge.set_kind("blue")

    def _reload_manage(self) -> None:
        instance = self.ctx.config.get_instance(self._current_instance_id())
        if instance is None:
            for label in self.manage_labels.values():
                label.setText("—")
            self.manage_badge.setText("未知")
            self.manage_badge.set_kind("gray")
            return
        self.manage_labels["name"].setText(instance.name)
        self.manage_labels["dir"].setText(str(self.ctx.config.instance_path(instance.id)))
        self.manage_labels["version"].setText(instance.version_id or "未绑定")
        self.manage_labels["loader"].setText(instance.loader or "—")
        if instance.modpack:
            self.manage_labels["modpack"].setText(f"是（{instance.modpack}）")
            self.manage_badge.setText("整合包")
            self.manage_badge.set_kind("green")
        else:
            self.manage_labels["modpack"].setText("否")
            self.manage_badge.setText("普通实例")
            self.manage_badge.set_kind("gray")

    # ------------------------------------------------------------------
    def _reload_game_settings(self) -> None:
        config = self.ctx.config
        self._rebuild_java_combo()

        self.memory_spin.blockSignals(True)
        self.memory_spin.setValue(max(512, min(65536, int(config.memory_mb))))
        self.memory_spin.blockSignals(False)

        self.width_spin.blockSignals(True)
        self.width_spin.setValue(max(0, min(7680, int(config.width))))
        self.width_spin.blockSignals(False)

        self.height_spin.blockSignals(True)
        self.height_spin.setValue(max(0, min(4320, int(config.height))))
        self.height_spin.blockSignals(False)

        for widget, value in (
            (self.jvm_args, config.extra_jvm_args),
            (self.game_args, config.extra_game_args),
        ):
            widget.blockSignals(True)
            widget.setPlainText(str(value or ""))
            widget.blockSignals(False)

        self.auto_server_check.blockSignals(True)
        self.auto_server_check.setChecked(bool(config.auto_connect_enabled))
        self.auto_server_check.blockSignals(False)

        self.server_edit.blockSignals(True)
        self.server_edit.setText(str(config.auto_connect_server or ""))
        self.server_edit.blockSignals(False)

        self.port_spin.blockSignals(True)
        self.port_spin.setValue(max(1, min(65535, int(config.auto_connect_port or 25565))))
        self.port_spin.blockSignals(False)

        self.hide_check.blockSignals(True)
        self.hide_check.setChecked(config.after_launch_action == "hide")
        self.hide_check.blockSignals(False)

        self._on_auto_server_toggled(self.auto_server_check.isChecked())
        self._reload_version_settings()

    def _reload_version_settings(self) -> None:
        version = self._current_version()
        if version is None:
            self.version_note.setText("当前版本：未选择")
            for widget in (
                self.ver_isolation,
                self.ver_memory,
                self.ver_priority,
                self.ver_title,
                self.ver_jvm,
                self.ver_game,
                self.ver_server_check,
                self.ver_server_edit,
                self.ver_port_spin,
            ):
                widget.blockSignals(True)
            self.ver_isolation.setCurrentIndex(0)
            self.ver_memory.setValue(0)
            self.ver_priority.setCurrentIndex(0)
            self.ver_title.clear()
            self.ver_jvm.setPlainText("")
            self.ver_game.setPlainText("")
            self.ver_server_check.setChecked(False)
            self.ver_server_edit.clear()
            self.ver_port_spin.setValue(25565)
            for widget in (
                self.ver_isolation,
                self.ver_memory,
                self.ver_priority,
                self.ver_title,
                self.ver_jvm,
                self.ver_game,
                self.ver_server_check,
                self.ver_server_edit,
                self.ver_port_spin,
            ):
                widget.blockSignals(False)
            return
        setting = self.ctx.config.version_setting(version.id)
        loader = version.loader or "原版"
        self.version_note.setText(f"当前版本：{version.id} · {loader}")
        self.ver_isolation.blockSignals(True)
        index = self.ver_isolation.findData(setting.isolation)
        self.ver_isolation.setCurrentIndex(index if index >= 0 else 0)
        self.ver_isolation.blockSignals(False)
        self.ver_memory.blockSignals(True)
        self.ver_memory.setValue(max(0, int(setting.memory_mb)))
        self.ver_memory.blockSignals(False)
        self.ver_priority.blockSignals(True)
        index = self.ver_priority.findData(setting.priority)
        self.ver_priority.setCurrentIndex(index if index >= 0 else 0)
        self.ver_priority.blockSignals(False)
        self.ver_title.blockSignals(True)
        self.ver_title.setText(setting.window_title)
        self.ver_title.blockSignals(False)
        self.ver_jvm.blockSignals(True)
        self.ver_jvm.setPlainText(setting.extra_jvm_args)
        self.ver_jvm.blockSignals(False)
        self.ver_game.blockSignals(True)
        self.ver_game.setPlainText(setting.extra_game_args)
        self.ver_game.blockSignals(False)
        self.ver_server_check.blockSignals(True)
        self.ver_server_check.setChecked(bool(setting.auto_connect))
        self.ver_server_check.blockSignals(False)
        self.ver_server_edit.blockSignals(True)
        self.ver_server_edit.setText(setting.server)
        self.ver_server_edit.blockSignals(False)
        self.ver_port_spin.blockSignals(True)
        self.ver_port_spin.setValue(max(1, min(65535, int(setting.port or 25565))))
        self.ver_port_spin.blockSignals(False)
        self._on_ver_server_toggled(bool(setting.auto_connect))

    def _on_ver_server_toggled(self, checked: bool) -> None:
        self.ver_server_edit.setEnabled(checked)
        self.ver_port_spin.setEnabled(checked)

    def _rebuild_java_combo(self) -> None:
        current = str(self.ctx.config.java_path or "")
        self.java_combo.blockSignals(True)
        self.java_combo.clear()
        self.java_combo.addItem("自动选择（按版本匹配）", "")
        index = -1
        for java in self.ctx.javas:
            self.java_combo.addItem(java.label, java.path)
            if current and java.path == current:
                index = self.java_combo.count() - 1
        if current and index < 0:
            self.java_combo.addItem(f"{current}（手动指定）", current)
            index = self.java_combo.count() - 1
        self.java_combo.setCurrentIndex(index if index >= 0 else 0)
        self.java_combo.blockSignals(False)

    def _on_auto_server_toggled(self, checked: bool) -> None:
        self.server_edit.setEnabled(checked)
        self.port_spin.setEnabled(checked)

    def _save_game_settings(self) -> None:
        config = self.ctx.config
        config.java_path = str(self.java_combo.currentData() or "")
        config.memory_mb = max(512, min(65536, int(self.memory_spin.value())))
        config.width = int(self.width_spin.value())
        config.height = int(self.height_spin.value())
        config.extra_jvm_args = self.jvm_args.toPlainText().strip()
        config.extra_game_args = self.game_args.toPlainText().strip()
        config.auto_connect_enabled = self.auto_server_check.isChecked()
        config.auto_connect_server = self.server_edit.text().strip()
        config.auto_connect_port = int(self.port_spin.value())
        if self.hide_check.isChecked():
            config.after_launch_action = "hide"
        elif config.after_launch_action == "hide":
            config.after_launch_action = "nothing"
        config.hide_after_launch = config.after_launch_action == "hide"
        if config.auto_connect_enabled and not config.auto_connect_server:
            QMessageBox.warning(self, APP_NAME, "已启用自动连接，但服务器地址为空。")
            return
        config.save()
        self.ctx.bus.config_changed.emit()
        self.ctx.bus.toast.emit("游戏设置已保存。")

    def _save_version_settings(self) -> None:
        version = self._current_version()
        if version is None:
            QMessageBox.information(self, APP_NAME, "请先在版本列表中选择一个版本。")
            return
        config = self.ctx.config
        setting = config.ensure_version_setting(version.id)
        setting.isolation = str(self.ver_isolation.currentData() or "")
        setting.memory_mb = max(0, min(65536, int(self.ver_memory.value())))
        setting.priority = str(self.ver_priority.currentData() or "")
        setting.window_title = self.ver_title.text().strip()
        setting.extra_jvm_args = self.ver_jvm.toPlainText().strip()
        setting.extra_game_args = self.ver_game.toPlainText().strip()
        setting.auto_connect = self.ver_server_check.isChecked()
        setting.server = self.ver_server_edit.text().strip()
        setting.port = int(self.ver_port_spin.value())
        if setting.auto_connect and not setting.server:
            QMessageBox.warning(self, APP_NAME, "已启用自动连接，但服务器地址为空。")
            return
        config.save()
        self.ctx.bus.config_changed.emit()
        self.ctx.bus.toast.emit(f"{version.id} 的版本设置已保存。")

    # ------------------------------------------------------------------
    def _is_content_file(self, path: Path, key: str) -> bool:
        name = path.name.lower()
        if name.endswith(DISABLED_SUFFIX):
            name = name[: -len(DISABLED_SUFFIX)]
        return any(name.endswith(str(suffix)) for suffix in FILE_CATEGORIES[key]["suffixes"])

    def _display_name(self, path: Path) -> str:
        name = path.name
        if name.endswith(DISABLED_SUFFIX):
            name = name[: -len(DISABLED_SUFFIX)]
        return name

    # ------------------------------------------------------------------
    def _check_mod_updates(self) -> None:
        version = self._current_version()
        if version is None:
            QMessageBox.information(self, APP_NAME, "请先选择一个版本。")
            return
        if self._mod_update_worker is not None and self._mod_update_worker.isRunning():
            return
        folder = self._files_dir("mods")
        try:
            jars = [
                path
                for path in folder.iterdir()
                if path.is_file()
                and path.suffix.lower() == ".jar"
                and not path.name.endswith(DISABLED_SUFFIX)
            ]
        except OSError:
            jars = []
        if not jars:
            self.ctx.bus.toast.emit("没有可检查更新的 Mod 文件。")
            return
        loader = LOADER_API_KEYS.get(version.loader, "")
        self.mod_update_button.setEnabled(False)
        self.mod_update_button.setText("检查中…")
        self._mod_update_worker = ModUpdateWorker(
            self.ctx.content, jars, version.base_version or "", loader, self
        )
        self._mod_update_worker.done.connect(self._on_mod_updates)
        self._mod_update_worker.failed.connect(self._on_mod_updates_failed)
        self._mod_update_worker.finished.connect(self._restore_update_button)
        self._mod_update_worker.start()

    def _restore_update_button(self) -> None:
        self.mod_update_button.setEnabled(True)
        self.mod_update_button.setText("检查更新")

    def _on_mod_updates(self, updates: list) -> None:
        self._mod_updates = {str(path): version for path, version in updates}
        self.mod_apply_button.setEnabled(bool(self._mod_updates))
        self._reload_files("mods")
        if self._mod_updates:
            self.ctx.bus.toast.emit(f"发现 {len(self._mod_updates)} 个可更新的 Mod")
        else:
            self.ctx.bus.toast.emit("所有 Mod 都已是 Modrinth 上的最新兼容版本")

    def _on_mod_updates_failed(self, message: str) -> None:
        QMessageBox.warning(self, APP_NAME, message)

    def _install_mod_updates(self) -> None:
        if not self._mod_updates:
            return
        if self._mod_apply_worker is not None and self._mod_apply_worker.isRunning():
            return
        updates = [(Path(path), version) for path, version in self._mod_updates.items()]
        game_root = self._files_dir("mods").parent
        self.mod_apply_button.setEnabled(False)
        self.mod_update_button.setEnabled(False)
        self._mod_apply_worker = ModUpdateApplyWorker(self.ctx, updates, game_root, self)
        self._mod_apply_worker.progress.connect(
            lambda _value, detail: self.ctx.bus.toast.emit(detail)
        )
        self._mod_apply_worker.log.connect(self.ctx.bus.log.emit)
        self._mod_apply_worker.done.connect(self._on_mod_apply_done)
        self._mod_apply_worker.failed.connect(self._on_mod_apply_failed)
        self._mod_apply_worker.start()

    def _on_mod_apply_done(self, message: str) -> None:
        self._mod_updates.clear()
        self.mod_update_button.setEnabled(True)
        self.mod_apply_button.setEnabled(False)
        self.ctx.bus.toast.emit(message)
        self._reload_files("mods")

    def _on_mod_apply_failed(self, message: str) -> None:
        self.mod_update_button.setEnabled(True)
        self.mod_apply_button.setEnabled(bool(self._mod_updates))
        QMessageBox.warning(self, APP_NAME, message)

    def _reload_files(self, key: str) -> None:
        table = self._file_tables.get(key)
        if table is None:
            return
        folder = self._files_dir(key)
        entries: list[Path] = []
        if folder.is_dir():
            try:
                entries = sorted(
                    (p for p in folder.iterdir() if p.is_file() and self._is_content_file(p, key)),
                    key=lambda p: p.name.lower(),
                )
            except OSError:
                entries = []
        if key == "resourcepacks":
            # 启用中的资源包按 options.txt 的加载顺序排列，其余按名称
            order = [name.lower() for name in self._resource_pack_order()]
            ranked = {name: index for index, name in enumerate(order)}
            entries.sort(key=lambda p: (ranked.get(p.name.lower(), len(ranked)), p.name.lower()))
        current_shader = self._current_shaderpack() if key == "shaderpacks" else ""

        table.setRowCount(len(entries))
        enabled = 0
        for row, path in enumerate(entries):
            disabled = path.name.endswith(DISABLED_SUFFIX)
            if not disabled:
                enabled += 1
            name_item = QTableWidgetItem(self._display_name(path))
            name_item.setData(Qt.UserRole, str(path))
            name_item.setToolTip(str(path))
            table.setItem(row, 0, name_item)
            try:
                size = path.stat().st_size
            except OSError:
                size = 0
            size_item = QTableWidgetItem(_human_size(size))
            size_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 1, size_item)
            status_item = QTableWidgetItem("已禁用" if disabled else "已启用")
            if disabled:
                status_item.setForeground(Qt.gray)
            elif key == "shaderpacks" and current_shader == self._display_name(path).lower():
                status_item.setText("已启用 · 当前使用")
                status_item.setForeground(Qt.GlobalColor.green)
            else:
                pending = self._mod_updates.get(str(path)) if key == "mods" else None
                if pending is not None:
                    status_item.setText(f"可更新 → {pending.version_number or pending.name}")
                    status_item.setToolTip("使用“安装更新”按钮更新到该版本")
                    status_item.setForeground(Qt.GlobalColor.green)
            table.setItem(row, 2, status_item)

        empty_label = self._file_empty_labels.get(key)
        if empty_label is not None:
            if not folder.is_dir():
                empty_label.setText(f"目录不存在：{folder}")
                empty_label.setVisible(True)
            elif not entries:
                empty_label.setText("该目录中暂无文件，可使用“添加文件”导入。")
                empty_label.setVisible(True)
            else:
                empty_label.setText("")
                empty_label.setVisible(False)

        count_label = self._file_count_labels.get(key)
        if count_label is not None:
            count_label.setText(f"{enabled} 已启用 / {len(entries)} 个文件" if entries else "")

        if key == "mods":
            self._scan_mod_conflicts(key)

    def _scan_mod_conflicts(self, key: str) -> None:
        """防御式调用 content 的 Mod 元数据扫描，标红冲突行并给出提示。"""
        table = self._file_tables.get(key)
        label = self._file_conflict_labels.get(key)
        if label is not None:
            label.setVisible(False)
        try:
            from ..content import detect_mod_conflicts, scan_mod_metadata
        except ImportError:
            return  # 并行开发中：content 的扫描函数尚未就绪，静默跳过
        mods_dir = self._files_dir("mods")
        if not mods_dir.is_dir():
            return
        try:
            metadata = scan_mod_metadata(mods_dir)
            conflicts = detect_mod_conflicts(metadata)
        except Exception as exc:  # noqa: BLE001
            if label is not None:
                label.setText(f"Mod 冲突检测失败：{exc}")
                label.setVisible(True)
            return
        if not conflicts:
            return

        row_index: dict[str, int] = {}
        if table is not None:
            for row in range(table.rowCount()):
                item = table.item(row, 0)
                if item is not None:
                    row_index[str(item.data(Qt.UserRole) or "")] = row

        def _detail(conflict: dict) -> str:
            detail = str(conflict.get("detail") or "")
            if detail:
                return detail
            ctype = str(conflict.get("type") or "")
            modid = str(conflict.get("modid") or "")
            if ctype == "duplicate_modid":
                return f"Mod ID 重复：{modid}，请禁用其中一个"
            if ctype == "missing_dependency":
                return f"缺少前置依赖：{modid}"
            return ctype or "未知冲突"

        touched: set[int] = set()
        first_detail = ""
        for conflict in conflicts:
            detail = _detail(conflict)
            if not first_detail:
                first_detail = detail
            for raw in conflict.get("files") or []:
                row = row_index.get(str(raw))
                if row is None or row in touched:
                    continue
                touched.add(row)
                name_item = table.item(row, 0) if table is not None else None
                status_item = table.item(row, 2) if table is not None else None
                if name_item is not None:
                    name_item.setForeground(Qt.GlobalColor.red)
                    name_item.setToolTip(detail)
                if status_item is not None:
                    status_item.setForeground(Qt.GlobalColor.red)
                    status_item.setToolTip(detail)

        if label is not None and conflicts:
            label.setText(f"发现 {len(conflicts)} 个冲突：{first_detail}")
            label.setVisible(True)

    def _selected_paths(self, table: QTableWidget) -> list[Path]:
        rows = sorted({index.row() for index in table.selectedIndexes()})
        result: list[Path] = []
        for row in rows:
            item = table.item(row, 0)
            if item is None:
                continue
            raw = str(item.data(Qt.UserRole) or "")
            if raw:
                result.append(Path(raw))
        return result

    def _toggle_selected(self, key: str) -> None:
        table = self._file_tables.get(key)
        if table is None:
            return
        paths = self._selected_paths(table)
        if not paths:
            return
        changed = 0
        for path in paths:
            if path.name.endswith(DISABLED_SUFFIX):
                target = path.with_name(self._display_name(path))
            else:
                target = path.with_name(path.name + DISABLED_SUFFIX)
            if target.exists():
                continue
            try:
                path.rename(target)
                changed += 1
            except OSError as exc:
                QMessageBox.warning(self, APP_NAME, f"操作 {path.name} 失败：{exc}")
        if changed:
            self._reload_files(key)
            self.ctx.bus.toast.emit(f"已切换 {changed} 个文件的状态。")

    def _set_enabled(self, key: str, enabled: bool) -> None:
        table = self._file_tables.get(key)
        if table is None:
            return
        paths = self._selected_paths(table)
        if not paths:
            return
        changed = 0
        failed: list[str] = []
        for path in paths:
            disabled = path.name.endswith(DISABLED_SUFFIX)
            if disabled == (not enabled):
                continue
            target = path.with_name(self._display_name(path) if enabled else path.name + DISABLED_SUFFIX)
            if target.exists():
                failed.append(path.name)
                continue
            try:
                path.rename(target)
                changed += 1
            except OSError:
                failed.append(path.name)
        if failed:
            QMessageBox.warning(
                self, APP_NAME, "以下文件无法修改状态（目标文件已存在或没有权限）：\n" + "\n".join(failed)
            )
        if changed:
            self._reload_files(key)
            self.ctx.bus.toast.emit(f"已{'启用' if enabled else '禁用'} {changed} 个文件。")

    def _delete_selected(self, key: str) -> None:
        table = self._file_tables.get(key)
        if table is None:
            return
        paths = self._selected_paths(table)
        if not paths:
            return
        answer = QMessageBox.question(
            self,
            "删除文件",
            f"确定删除选中的 {len(paths)} 个文件吗？此操作不可恢复。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        deleted = 0
        failed: list[str] = []
        for path in paths:
            try:
                path.unlink()
                deleted += 1
            except OSError:
                failed.append(path.name)
        if failed:
            QMessageBox.warning(self, APP_NAME, "以下文件删除失败：\n" + "\n".join(failed))
        if deleted:
            self._reload_files(key)
            self.ctx.bus.toast.emit(f"已删除 {deleted} 个文件。")

    def _add_files(self, key: str) -> None:
        folder = self._files_dir(key)
        if key == "mods":
            filters = "Mod 文件 (*.jar *.zip);;所有文件 (*.*)"
        else:
            filters = "压缩包 (*.zip);;所有文件 (*.*)"
        files, _selected = QFileDialog.getOpenFileNames(self, "添加文件", "", filters)
        if not files:
            return
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, APP_NAME, f"无法创建目录 {folder}：{exc}")
            return
        copied = 0
        for raw in files:
            source = Path(raw)
            target = folder / source.name
            if target.exists():
                answer = QMessageBox.question(
                    self,
                    "文件已存在",
                    f"{source.name} 已存在，是否覆盖？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if answer != QMessageBox.Yes:
                    continue
            try:
                shutil.copy2(source, target)
                copied += 1
            except OSError as exc:
                QMessageBox.warning(self, APP_NAME, f"复制 {source.name} 失败：{exc}")
        if copied:
            self._reload_files(key)
            self.ctx.bus.toast.emit(f"已添加 {copied} 个文件。")

    def _current_shaderpack(self) -> str:
        """读取 Iris / OptiFine 配置，返回当前选中的光影包文件名（小写）。"""
        base = self._files_dir("shaderpacks").parent
        for relative in ("config/iris.properties", "optionsshaders.txt"):
            try:
                text = (base / relative).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line in text.splitlines():
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                if key.strip().lower() != "shaderpack":
                    continue
                name = value.strip().strip('"')
                if name.lower() in ("", "off", "(internal)", "none"):
                    return ""
                return name.lower()
        return ""

    def _resource_pack_order(self) -> list[str]:
        """读取 options.txt 中已启用资源包的加载顺序。"""
        options = self._files_dir("resourcepacks").parent / "options.txt"
        try:
            text = options.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        for line in text.splitlines():
            if line.startswith("resourcePacks:"):
                values = re.findall(r'"([^"]*)"', line)
                return [
                    value[5:] if value.lower().startswith("file/") else value
                    for value in values
                ]
        return []

    def _write_resource_pack_order(self, names: list[str]) -> None:
        options = self._files_dir("resourcepacks").parent / "options.txt"
        try:
            text = options.read_text(encoding="utf-8", errors="replace") if options.is_file() else ""
        except OSError:
            text = ""
        builtin = {"vanilla", "programmer_art", "high_contrast"}
        values = [
            name if name.lower() in builtin else f"file/{name}" for name in names
        ]
        line = "resourcePacks:[" + ",".join(f'"{value}"' for value in values) + "]"
        lines = text.splitlines()
        for index, existing in enumerate(lines):
            if existing.startswith("resourcePacks:"):
                lines[index] = line
                break
        else:
            lines.append(line)
        try:
            options.parent.mkdir(parents=True, exist_ok=True)
            options.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError as exc:
            self.ctx.bus.toast.emit(f"写入 options.txt 失败：{exc}")

    def _move_resource_pack(self, delta: int) -> None:
        """上移/下移启用中的资源包，并同步写回 options.txt。"""
        table = self._file_tables.get("resourcepacks")
        if table is None:
            return
        row = table.currentRow()
        if row < 0:
            self.ctx.bus.toast.emit("请先选择一个资源包。")
            return
        item = table.item(row, 0)
        if item is None:
            return
        name = Path(str(item.data(Qt.UserRole))).name
        order = self._resource_pack_order()
        lowered = [entry.lower() for entry in order]
        if name.lower() not in lowered:
            self.ctx.bus.toast.emit("该资源包当前未启用，请先启用后再调整顺序。")
            return
        index = lowered.index(name.lower())
        target = index + delta
        if target < 0 or target >= len(order):
            return
        order[index], order[target] = order[target], order[index]
        self._write_resource_pack_order(order)
        self._reload_files("resourcepacks")
        for candidate in range(table.rowCount()):
            cell = table.item(candidate, 0)
            if cell is not None and Path(str(cell.data(Qt.UserRole))).name.lower() == name.lower():
                table.selectRow(candidate)
                break
        self.ctx.bus.toast.emit(f"已调整资源包顺序：{name}")

    def _open_folder(self, key: str) -> None:
        folder = self._files_dir(key)
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, APP_NAME, f"无法创建目录 {folder}：{exc}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _open_game_dir(self) -> None:
        folder = self._instance_dir()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _open_version_dir(self) -> None:
        version = self._current_version()
        if version is None:
            self.ctx.bus.toast.emit("当前没有选中的版本。")
            return
        folder = version.path.parent
        if not folder.is_dir():
            self.ctx.bus.toast.emit(f"版本目录不存在：{folder}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    # ------------------------------------------------------------------
    def _delete_version_dir(self) -> None:
        version = self._current_version()
        if version is None:
            self.ctx.bus.toast.emit("当前没有可删除的版本。")
            return
        folder = version.path.parent
        answer = QMessageBox.warning(
            self,
            "删除版本",
            f"确定删除版本「{version.id}」吗？\n目录 {folder} 及其中的全部文件将被永久删除。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            shutil.rmtree(folder)
        except FileNotFoundError:
            pass
        except OSError as exc:
            QMessageBox.warning(self, APP_NAME, f"无法删除版本目录：{exc}")
            return

        config = self.ctx.config
        for instance in list(config.instances):
            if instance.version_id == version.id:
                config.remove_instance(instance.id)
        if config.default_version_id == version.id:
            config.default_version_id = ""
            config.save()

        self.refresh()
        self.ctx.bus.versions_changed.emit()
        self.ctx.bus.instances_changed.emit()
        self.ctx.bus.toast.emit(f"已删除版本：{version.id}")

    def _rename_instance(self) -> None:
        instance = self.ctx.config.get_instance(self._current_instance_id())
        if instance is None:
            return
        if instance.id == "default":
            QMessageBox.information(self, APP_NAME, "默认实例不能重命名。")
            return
        name, ok = QInputDialog.getText(self, "重命名实例", "新的实例名称：", text=instance.name)
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        instance.name = name
        self.ctx.config.save()
        self.refresh()
        self.ctx.bus.instances_changed.emit()
        self.ctx.bus.toast.emit(f"实例已重命名为：{name}")

    def _remove_instance_record(self) -> None:
        instance = self.ctx.config.get_instance(self._current_instance_id())
        if instance is None:
            return
        if instance.id == "default":
            QMessageBox.information(self, APP_NAME, "默认实例不能被移除。")
            return
        answer = QMessageBox.question(
            self,
            "移除实例",
            f"确定移除实例「{instance.name}」的记录吗？\n磁盘上的游戏文件会保留。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.ctx.config.remove_instance(instance.id)
        self.refresh()
        self.ctx.bus.instances_changed.emit()
        self.ctx.bus.toast.emit(f"已移除实例：{instance.name}")
