"""设置页：下载源管理（自定义源 + API Key）、游戏设置与 Java 管理。"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QProcess, QThread, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, APP_VERSION
from ..config import (
    AFTER_LAUNCH_ACTIONS,
    CACHE_DIR,
    DATA_DIR,
    ISOLATION_LABELS,
    PROCESS_PRIORITIES,
    SOURCE_MAPPINGS,
    DownloadSource,
)
from ..context import AppContext, wait_thread
from ..i18n import SUPPORTED_LANGUAGES, t
from ..java import detect_java_installed, download_java, java_key
from ..net import Cancelled, apply_proxy, test_source
from . import theme
from .widgets import Card, card_title_row, page_header, scroll_page


class TestSourceWorker(QThread):
    done = Signal(str, bool, str)

    def __init__(self, source: DownloadSource, parent=None):
        super().__init__(parent)
        self.source = DownloadSource.from_dict(source.to_dict())

    def run(self) -> None:
        ok, message = test_source(self.source)
        self.done.emit(self.source.name, ok, message)


class JavaDownloadWorker(QThread):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(float, float)  # 0~1 进度, 字节/秒

    def __init__(
        self,
        major: int,
        dest_root: Path,
        task_id: str = "",
        cancel_event: threading.Event | None = None,
        pause_event: threading.Event | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.major = int(major)
        self.dest_root = Path(dest_root)
        self.task_id = task_id
        self.cancel_event = cancel_event or threading.Event()
        self.pause_event = pause_event or threading.Event()

    def run(self) -> None:
        state = {"total": 0, "bytes": 0, "last_t": time.time(), "last_b": 0}

        def on_total(total: int) -> None:
            state["total"] = int(total)

        def on_bytes(n: int) -> None:
            # 限频上报进度与速度，避免高频刷新下载中心表格
            state["bytes"] += n
            now = time.time()
            if now - state["last_t"] < 0.25:
                return
            dt = now - state["last_t"]
            speed = (state["bytes"] - state["last_b"]) / dt if dt > 0 else 0.0
            state["last_t"], state["last_b"] = now, state["bytes"]
            total = state["total"]
            percent = min(1.0, state["bytes"] / total) if total else 0.0
            self.progress.emit(percent, speed)

        try:
            info = download_java(
                self.major,
                self.dest_root,
                log=lambda text: None,
                on_bytes=on_bytes,
                cancel=self.cancel_event,
                pause=self.pause_event,
                on_total=on_total,
            )
            self.done.emit(info)
        except Cancelled:
            pass  # 已由下载中心标记为取消
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class RescanJavaWorker(QThread):
    done = Signal(list)

    def run(self) -> None:
        self.done.emit(detect_java_installed())


class SourceDialog(QDialog):
    def __init__(self, source: DownloadSource, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"编辑下载源 · {source.name}")
        self.setMinimumWidth(520)
        self.source = source

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        self.name_edit = QLineEdit(source.name)
        self.manifest_edit = QLineEdit(source.manifest_url)
        self.manifest_edit.setPlaceholderText("https://example.com/mc/game/version_manifest_v2.json")
        self.mapping_combo = QComboBox()
        for key, text in SOURCE_MAPPINGS.items():
            self.mapping_combo.addItem(text, key)
        index = self.mapping_combo.findData(source.mapping)
        self.mapping_combo.setCurrentIndex(max(0, index))
        self.base_edit = QLineEdit(source.download_base)
        self.base_edit.setPlaceholderText("如 https://bmclapi2.bangbang93.com")
        self.header_edit = QLineEdit(source.api_key_header or "X-API-Key")
        self.header_edit.setPlaceholderText("X-API-Key")
        self.key_edit = QLineEdit(source.api_key)
        self.key_edit.setEchoMode(QLineEdit.PasswordEchoOnEdit)
        self.key_edit.setPlaceholderText("可留空")

        form.addRow("源名称", self.name_edit)
        form.addRow("版本清单地址", self.manifest_edit)
        form.addRow("资源映射方式", self.mapping_combo)
        form.addRow("镜像根地址", self.base_edit)
        form.addRow("API Key 请求头名", self.header_edit)
        form.addRow("API Key", self.key_edit)
        layout.addLayout(form)

        tip = QLabel(
            "BMCLAPI 兼容：把 Mojang 域名替换为镜像根地址并适配 /assets、/maven 路径。\n"
            "同路径镜像：仅替换域名，路径保持不变。\n"
            "若映射方式为“不重写”，资源仍从官方地址下载，仅清单从该源获取。"
        )
        tip.setObjectName("Tiny")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate(self) -> None:
        name = self.name_edit.text().strip()
        manifest = self.manifest_edit.text().strip()
        mapping = str(self.mapping_combo.currentData())
        base = self.base_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "信息不完整", "请填写源名称。")
            return
        if not manifest.startswith(("http://", "https://")):
            if base.startswith(("http://", "https://")):
                manifest = base.rstrip("/") + "/mc/game/version_manifest_v2.json"
            else:
                QMessageBox.warning(
                    self, "信息不完整", "请填写有效的版本清单地址（http/https）。"
                )
                return
        if mapping != "none" and not base.startswith(("http://", "https://")):
            QMessageBox.warning(
                self, "信息不完整", "该映射方式需要填写有效的镜像根地址（http/https）。"
            )
            return
        self.source.name = name
        self.source.manifest_url = manifest
        self.source.mapping = mapping
        self.source.download_base = base
        self.source.api_key_header = self.header_edit.text().strip() or "X-API-Key"
        self.source.api_key = self.key_edit.text()
        self.accept()


class SettingsPage(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self._test_worker: TestSourceWorker | None = None
        self._rescan_worker: RescanJavaWorker | None = None
        self._java_download_worker: JavaDownloadWorker | None = None
        self._build()
        self._connect()
        self._sync_ui_from_config()
        self._rebuild_source_table()
        self._rebuild_java_table()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 20, 26, 20)
        outer.setSpacing(16)
        header, _ = page_header(
            self.tr("设置"), self.tr("下载源、游戏配置与 Java 运行时管理")
        )
        outer.addWidget(header)

        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)
        self.tabs.insertTab(0, scroll_page(self._build_general_tab()), self.tr("通用"))
        self.tabs.insertTab(1, scroll_page(self._build_appearance_tab()), self.tr("外观"))
        self.tabs.addTab(self._build_sources_tab(), self.tr("下载源"))
        self.tabs.addTab(scroll_page(self._build_content_tab()), self.tr("内容源与镜像"))
        self.tabs.addTab(scroll_page(self._build_auth_tab()), self.tr("账号与登录"))
        self.tabs.addTab(scroll_page(self._build_game_tab()), self.tr("游戏设置"))
        self.tabs.addTab(self._build_java_tab(), self.tr("Java 运行时"))
        self.tabs.addTab(scroll_page(self._build_about_tab()), self.tr("关于"))

    def _build_general_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 14, 0, 0)
        layout.setSpacing(12)

        card = Card(margins=20, spacing=12)
        form = QFormLayout()
        form.setSpacing(11)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignTrailing)

        self.tray_check = QCheckBox(self.tr("关闭窗口时最小化到托盘（可从托盘恢复）"))
        form.addRow("", self.tray_check)

        self.language_combo = QComboBox()
        for code, name in SUPPORTED_LANGUAGES.items():
            self.language_combo.addItem(name, code)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        restart = QPushButton(self.tr("立即重启"))
        restart.setObjectName("Ghost")
        restart.clicked.connect(self._restart_launcher)
        language_row = QHBoxLayout()
        language_row.setSpacing(8)
        language_row.addWidget(self.language_combo, 1)
        language_row.addWidget(restart)
        form.addRow(self.tr("界面语言"), language_row)

        self.general_memory_spin = QSpinBox()
        self.general_memory_spin.setRange(512, 65536)
        self.general_memory_spin.setSingleStep(512)
        self.general_memory_spin.setSuffix(" MB")
        form.addRow(self.tr("默认最大内存"), self.general_memory_spin)

        self.general_threads_spin = QSpinBox()
        self.general_threads_spin.setRange(1, 328)
        self.general_threads_spin.setSuffix(f" {t('SettingsPage', '线程')}")
        form.addRow(self.tr("下载线程数"), self.general_threads_spin)

        self.general_hide_check = QCheckBox(self.tr("启动游戏后隐藏启动器（可从托盘恢复）"))
        form.addRow("", self.general_hide_check)

        self.start_anim_check = QCheckBox(self.tr("启动游戏时显示启动动画"))
        form.addRow("", self.start_anim_check)

        card.body.addLayout(form)
        buttons = QHBoxLayout()
        save = QPushButton(self.tr("保存通用设置"))
        save.setObjectName("Primary")
        save.clicked.connect(self._save_general_settings)
        buttons.addWidget(save)
        buttons.addStretch(1)
        card.body.addLayout(buttons)
        hint = QLabel(
            self.tr(
                "通用设置修改后需点击“保存通用设置”生效；内存与下载线程数同时影响全局配置。"
            )
        )
        hint.setObjectName("Tiny")
        hint.setWordWrap(True)
        card.body.addWidget(hint)
        layout.addWidget(card)

        paths_card = Card(margins=20, spacing=12)
        paths_card.body.addWidget(
            card_title_row(
                self.tr("目录与缓存"), self.tr("打开数据/游戏目录，或清理下载与封面缓存")
            )
        )
        self.data_dir_label = QLabel(t("SettingsPage", "数据目录：{0}", DATA_DIR))
        self.data_dir_label.setObjectName("Tiny")
        self.data_dir_label.setWordWrap(True)
        self.data_dir_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.version_label = QLabel(
            t("SettingsPage", "当前版本：{0} v{1}", APP_NAME, APP_VERSION)
        )
        self.version_label.setObjectName("Tiny")
        paths_card.body.addWidget(self.data_dir_label)
        paths_card.body.addWidget(self.version_label)

        open_row = QHBoxLayout()
        open_data = QPushButton(self.tr("打开数据目录"))
        open_data.clicked.connect(lambda: self._open_directory(DATA_DIR))
        open_row.addWidget(open_data)
        open_game = QPushButton(self.tr("打开游戏目录"))
        open_game.clicked.connect(lambda: self._open_directory(self.ctx.config.game_path))
        open_row.addWidget(open_game)
        open_plugins = QPushButton(self.tr("打开插件目录"))
        open_plugins.clicked.connect(lambda: self._open_directory(DATA_DIR / "plugins"))
        open_row.addWidget(open_plugins)
        open_row.addStretch(1)
        paths_card.body.addLayout(open_row)

        clear_row = QHBoxLayout()
        clear_covers = QPushButton(self.tr("清理封面缓存"))
        clear_covers.clicked.connect(
            lambda: self._clear_cache(["covers"], "封面缓存")
        )
        clear_row.addWidget(clear_covers)
        clear_downloads = QPushButton(self.tr("清理下载缓存"))
        clear_downloads.clicked.connect(
            lambda: self._clear_cache(["modpacks", "loaders"], "下载缓存")
        )
        clear_row.addWidget(clear_downloads)
        clear_row.addStretch(1)
        paths_card.body.addLayout(clear_row)

        path_hint = QLabel(
            t(
                "SettingsPage",
                "缓存目录位于 {0}；清理后已下载的整合包与加载器需要重新下载。",
                CACHE_DIR,
            )
        )
        path_hint.setObjectName("Tiny")
        path_hint.setWordWrap(True)
        paths_card.body.addWidget(path_hint)
        layout.addWidget(paths_card)
        layout.addStretch(1)
        return page

    def _build_appearance_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 14, 0, 0)
        layout.setSpacing(12)

        card = Card(margins=20, spacing=12)
        card.body.addWidget(
            card_title_row(
                self.tr("主题色与背景"),
                self.tr("主题色即时生效；背景图按窗口大小等比铺满并居中裁切，不会拉伸变形"),
            )
        )

        accent_row = QHBoxLayout()
        accent_row.setSpacing(8)
        self.accent_buttons: dict[str, QPushButton] = {}
        for name, color in theme.ACCENT_PRESETS.items():
            chip = QPushButton(name)
            chip.setObjectName("Chip")
            chip.setCheckable(True)
            chip.setCursor(Qt.PointingHandCursor)
            chip.setStyleSheet(
                "QPushButton#Chip:checked {"
                f" background-color: {color}; border-color: {color}; color: #08200e;"
                " font-weight: 600; }"
            )
            chip.clicked.connect(lambda checked=False, c=color: self._apply_accent(c))
            accent_row.addWidget(chip)
            self.accent_buttons[color.lower()] = chip
        custom = QPushButton(self.tr("自定义颜色…"))
        custom.setObjectName("Ghost")
        custom.clicked.connect(self._pick_accent)
        accent_row.addWidget(custom)
        accent_row.addStretch(1)
        card.body.addWidget(QLabel(self.tr("主题色")))
        card.body.addLayout(accent_row)

        self.background_label = QLabel("未设置（使用默认深色背景）")
        self.background_label.setObjectName("Tiny")
        self.background_label.setWordWrap(True)
        self.background_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        card.body.addWidget(QLabel(self.tr("启动器背景图")))
        card.body.addWidget(self.background_label)

        background_row = QHBoxLayout()
        pick_bg = QPushButton(self.tr("选择图片…"))
        pick_bg.clicked.connect(self._pick_background)
        background_row.addWidget(pick_bg)
        clear_bg = QPushButton(self.tr("清除背景"))
        clear_bg.setObjectName("Ghost")
        clear_bg.clicked.connect(self._clear_background)
        background_row.addWidget(clear_bg)
        background_row.addStretch(1)
        card.body.addLayout(background_row)

        hint = QLabel(
            self.tr(
                "背景图会随窗口缩放自动适配：窗口比例与图片不同时按「铺满 + 居中裁切」处理，"
                "侧边栏与标题栏会自动半透明，保证文字可读。"
            )
        )
        hint.setObjectName("Tiny")
        hint.setWordWrap(True)
        card.body.addWidget(hint)
        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _apply_accent(self, color: str) -> None:
        cfg = self.ctx.config
        cfg.accent_color = color
        cfg.save()
        app = QApplication.instance()
        if isinstance(app, QApplication):
            theme.apply_theme(app, color)
        for key, chip in self.accent_buttons.items():
            chip.setChecked(key == color.lower())
        self.ctx.bus.toast.emit(f"主题色已切换为 {color}")

    def _pick_accent(self) -> None:
        current = self.ctx.config.accent_color or theme.ACCENT
        color = QColorDialog.getColor(current, self, self.tr("选择主题色"))
        if color.isValid():
            self._apply_accent(color.name())

    def _pick_background(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("选择启动器背景图"),
            str(DATA_DIR),
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if not path:
            return
        cfg = self.ctx.config
        cfg.background_image = path
        cfg.save()
        self._sync_appearance()
        self.ctx.bus.config_changed.emit()
        self.ctx.bus.toast.emit("背景图已更新。")

    def _clear_background(self) -> None:
        cfg = self.ctx.config
        if not cfg.background_image:
            return
        cfg.background_image = ""
        cfg.save()
        self._sync_appearance()
        self.ctx.bus.config_changed.emit()
        self.ctx.bus.toast.emit("已恢复默认背景。")

    def _sync_appearance(self) -> None:
        cfg = self.ctx.config
        accent = (cfg.accent_color or theme.ACCENT).lower()
        for key, chip in self.accent_buttons.items():
            chip.setChecked(key == accent)
        image = cfg.background_image
        if image and Path(image).exists():
            self.background_label.setText(image)
        elif image:
            self.background_label.setText(f"{image}（文件不存在）")
        else:
            self.background_label.setText("未设置（使用默认深色背景）")

    def _build_sources_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 14, 0, 0)
        layout.setSpacing(12)

        card = Card(margins=16, spacing=10)
        top = QHBoxLayout()
        desc = QLabel(
            self.tr(
                "支持官方源、BMCLAPI 镜像、自定义镜像与 API Key。下载时会按列表顺序自动回退。"
            )
        )
        desc.setObjectName("Muted")
        top.addWidget(desc, 1)
        add = QPushButton(self.tr("＋ 添加自定义源"))
        add.clicked.connect(self._add_source)
        top.addWidget(add)
        test = QPushButton(self.tr("测试当前源"))
        test.clicked.connect(self._test_selected_source)
        top.addWidget(test)
        card.body.addLayout(top)

        self.source_table = QTableWidget(0, 6)
        self.source_table.setHorizontalHeaderLabels(
            [
                self.tr("名称"),
                self.tr("版本清单地址"),
                self.tr("映射方式"),
                self.tr("API Key"),
                self.tr("启用"),
                self.tr("操作"),
            ]
        )
        self.source_table.verticalHeader().setVisible(False)
        self.source_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.source_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        header = self.source_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        self.source_table.setColumnWidth(5, 214)
        self.source_table.verticalHeader().setDefaultSectionSize(38)
        card.body.addWidget(self.source_table, 1)

        hint = QLabel(
            "API Key 会作为请求头附加到该源的清单与资源请求。内置源不可删除，但可以禁用或编辑 API Key。\n"
            "自定义源排在内置源之后作为备用；下载失败会自动尝试下一个源。"
        )
        hint.setObjectName("Tiny")
        hint.setWordWrap(True)
        card.body.addWidget(hint)
        layout.addWidget(card, 1)
        return page

    def _build_content_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 14, 0, 0)
        layout.setSpacing(12)
        card = Card(margins=20, spacing=12)
        form = QFormLayout()
        form.setSpacing(11)
        self.modrinth_edit = QLineEdit()
        self.modrinth_edit.setPlaceholderText("https://api.modrinth.com/v2")
        self.modrinth_mirror_edit = QLineEdit()
        self.modrinth_mirror_edit.setPlaceholderText(
            self.tr("留空使用官方 CDN；可填自建镜像根地址")
        )
        self.cf_edit = QLineEdit()
        self.cf_edit.setPlaceholderText("https://api.curseforge.com/v1")
        self.cf_key_edit = QLineEdit()
        self.cf_key_edit.setEchoMode(QLineEdit.PasswordEchoOnEdit)
        self.cf_key_edit.setPlaceholderText(self.tr("CurseForge API Key（必填）"))
        self.cf_mirror_edit = QLineEdit()
        self.cf_mirror_edit.setPlaceholderText(
            self.tr("留空使用官方 CDN；如 https://mediafilez.forgecdn.net")
        )
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, 328)
        self.threads_spin.setSuffix(f" {t('SettingsPage', '线程')}")
        form.addRow("Modrinth API", self.modrinth_edit)
        form.addRow(self.tr("Modrinth CDN 镜像"), self.modrinth_mirror_edit)
        form.addRow("CurseForge API", self.cf_edit)
        form.addRow("CurseForge API Key", self.cf_key_edit)
        form.addRow(self.tr("CurseForge CDN 镜像"), self.cf_mirror_edit)
        form.addRow(self.tr("并行下载线程"), self.threads_spin)
        card.body.addLayout(form)
        buttons = QHBoxLayout()
        save = QPushButton(self.tr("保存内容源设置"))
        save.setObjectName("Primary")
        save.clicked.connect(self._save_content_settings)
        buttons.addWidget(save)
        buttons.addStretch(1)
        card.body.addLayout(buttons)
        hint = QLabel(
            "Modrinth 与 CurseForge 提供 Mod、整合包、资源包与光影包。\n"
            "CDN 镜像仅替换下载地址的域名，不影响 API 请求。CurseForge 的 API Key 默认已内置，"
            "如失效请到 curseforge.com 开发者控制台申请后填入。"
        )
        hint.setObjectName("Tiny")
        hint.setWordWrap(True)
        card.body.addWidget(hint)
        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _build_auth_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 14, 0, 0)
        layout.setSpacing(12)
        card = Card(margins=20, spacing=12)
        form = QFormLayout()
        form.setSpacing(11)
        self.ms_client_edit = QLineEdit()
        self.ms_client_edit.setPlaceholderText(self.tr("微软 OAuth 客户端 ID"))
        self.authlib_url_edit = QLineEdit()
        self.authlib_url_edit.setPlaceholderText(
            self.tr("authlib-injector latest.json 地址")
        )
        form.addRow(self.tr("微软 Client ID"), self.ms_client_edit)
        form.addRow(self.tr("authlib-injector 源"), self.authlib_url_edit)
        card.body.addLayout(form)
        path_row = QHBoxLayout()
        self.authlib_path_label = QLabel("")
        self.authlib_path_label.setObjectName("Tiny")
        self.authlib_path_label.setWordWrap(True)
        path_row.addWidget(self.authlib_path_label, 1)
        clear = QPushButton(self.tr("清除缓存"))
        clear.setObjectName("Ghost")
        clear.clicked.connect(self._clear_authlib)
        path_row.addWidget(clear)
        card.body.addLayout(path_row)
        buttons = QHBoxLayout()
        save = QPushButton(self.tr("保存登录设置"))
        save.setObjectName("Primary")
        save.clicked.connect(self._save_auth_settings)
        buttons.addWidget(save)
        accounts = QPushButton(self.tr("前往账号管理"))
        accounts.clicked.connect(lambda: self.ctx.bus.navigate.emit("accounts"))
        buttons.addWidget(accounts)
        buttons.addStretch(1)
        card.body.addLayout(buttons)
        hint = QLabel(
            "微软正版登录采用 OAuth 设备码，不会保存密码。第三方外置登录会在启动时自动下载 "
            "authlib-injector 并以 javaagent 注入游戏；账号页可为每个账号单独指定验证服务器。\n"
            "所有登录令牌保存在 data/accounts.json，请勿将该文件分享给他人。"
        )
        hint.setObjectName("Tiny")
        hint.setWordWrap(True)
        card.body.addWidget(hint)
        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _build_game_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 14, 0, 0)
        layout.setSpacing(12)
        card = Card(margins=20, spacing=12)
        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignTrailing)

        self.game_dir_combo = QComboBox()
        self.game_dir_combo.setMinimumWidth(360)
        self.game_dir_combo.currentIndexChanged.connect(self._on_game_dir_selected)
        game_dir_row = QHBoxLayout()
        game_dir_row.setSpacing(8)
        game_dir_row.addWidget(self.game_dir_combo, 1)
        add_game = QPushButton(self.tr("添加…"))
        add_game.clicked.connect(self._add_game_dir)
        game_dir_row.addWidget(add_game)
        remove_game = QPushButton(self.tr("移除"))
        remove_game.setObjectName("Ghost")
        remove_game.clicked.connect(self._remove_game_dir)
        game_dir_row.addWidget(remove_game)
        open_game = QPushButton(self.tr("打开"))
        open_game.setObjectName("Ghost")
        open_game.clicked.connect(self._open_game_dir)
        game_dir_row.addWidget(open_game)
        form.addRow(self.tr("数据目录"), game_dir_row)

        self.isolation_combo = QComboBox()
        for key, label in ISOLATION_LABELS.items():
            self.isolation_combo.addItem(self.tr(label), key)
        self.isolation_combo.setToolTip(self.tr("按版本隔离模组或存档，可避免不同版本互相干扰"))
        self.isolation_combo.currentIndexChanged.connect(self._on_isolation_changed)
        form.addRow(self.tr("版本隔离"), self.isolation_combo)

        self.priority_combo = QComboBox()
        for key, label in PROCESS_PRIORITIES.items():
            self.priority_combo.addItem(self.tr(label), key)
        self.priority_combo.currentIndexChanged.connect(self._on_priority_changed)
        form.addRow(self.tr("游戏进程优先级"), self.priority_combo)

        self.after_launch_combo = QComboBox()
        for key, label in AFTER_LAUNCH_ACTIONS.items():
            self.after_launch_combo.addItem(self.tr(label), key)
        self.after_launch_combo.currentIndexChanged.connect(self._on_after_launch_changed)
        form.addRow(self.tr("启动后动作"), self.after_launch_combo)

        self.window_title_edit = QLineEdit()
        self.window_title_edit.setPlaceholderText(self.tr("留空则使用游戏默认标题"))
        self.window_title_edit.editingFinished.connect(self._on_window_title_changed)
        form.addRow(self.tr("游戏窗口标题"), self.window_title_edit)

        proxy_row = QHBoxLayout()
        proxy_row.setSpacing(8)
        self.proxy_check = QCheckBox(self.tr("启用代理"))
        self.proxy_check.toggled.connect(self._on_proxy_changed)
        proxy_row.addWidget(self.proxy_check)
        self.proxy_edit = QLineEdit()
        self.proxy_edit.setPlaceholderText("http://127.0.0.1:7890")
        self.proxy_edit.editingFinished.connect(self._on_proxy_changed)
        proxy_row.addWidget(self.proxy_edit, 1)
        self.proxy_jvm_check = QCheckBox(self.tr("游戏也走代理"))
        self.proxy_jvm_check.toggled.connect(self._on_proxy_changed)
        proxy_row.addWidget(self.proxy_jvm_check)
        form.addRow(self.tr("网络代理"), proxy_row)

        self.java_path_edit = QLineEdit()
        self.java_path_edit.setPlaceholderText(self.tr("留空则自动按版本选择"))
        self.java_path_edit.editingFinished.connect(self._on_java_path_changed)
        java_row = QHBoxLayout()
        java_row.addWidget(self.java_path_edit, 1)
        browse_java = QPushButton(self.tr("选择…"))
        browse_java.clicked.connect(self._browse_java)
        java_row.addWidget(browse_java)
        form.addRow(self.tr("Java 路径"), java_row)

        self.memory_spin = QSpinBox()
        self.memory_spin.setRange(512, 65536)
        self.memory_spin.setSingleStep(512)
        self.memory_spin.setSuffix(" MB")
        self.memory_spin.valueChanged.connect(self._on_memory_changed)
        form.addRow(self.tr("分配内存"), self.memory_spin)

        self.jvm_edit = QLineEdit()
        self.jvm_edit.setPlaceholderText("如 -Dfile.encoding=UTF-8 -XX:+UseG1GC")
        self.jvm_edit.editingFinished.connect(self._on_jvm_changed)
        form.addRow(self.tr("额外 JVM 参数"), self.jvm_edit)

        self.keep_check = QCheckBox(self.tr("游戏退出后保持启动器窗口打开"))
        self.keep_check.toggled.connect(self._on_keep_changed)
        form.addRow("", self.keep_check)

        card.body.addLayout(form)
        note = QLabel(
            "内存建议：原版 2–4 GB，整合包 4–8 GB。内存分配过大反而会拖慢系统。\n"
            "数据目录可添加多个 .minecraft 目录并用下拉框快速切换；版本隔离可在“版本设置”中按版本覆盖。\n"
            "自定义窗口标题与进程优先级通过系统 API 在游戏启动后自动应用。"
        )
        note.setObjectName("Tiny")
        note.setWordWrap(True)
        card.body.addWidget(note)
        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _build_java_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 14, 0, 0)
        layout.setSpacing(12)
        card = Card(margins=16, spacing=10)
        top = QHBoxLayout()
        desc = QLabel(
            self.tr(
                "启动器会自动扫描系统与常见启动器目录。Java 8 → 1.16，Java 17 → 1.17–1.20.4，Java 21 → 1.20.5+"
            )
        )
        desc.setObjectName("Muted")
        desc.setWordWrap(True)
        top.addWidget(desc, 1)
        rescan = QPushButton(self.tr("重新扫描"))
        rescan.clicked.connect(self._rescan_java)
        top.addWidget(rescan)
        self.java_download_button = QPushButton(self.tr("下载 Java…"))
        self.java_download_button.clicked.connect(self._download_java)
        top.addWidget(self.java_download_button)
        java_center = QPushButton(self.tr("Java 中心"))
        java_center.setObjectName("Ghost")
        java_center.clicked.connect(self._open_java_center)
        top.addWidget(java_center)
        card.body.addLayout(top)

        self.java_table = QTableWidget(0, 3)
        self.java_table.setHorizontalHeaderLabels(
            [self.tr("Java 版本"), self.tr("位数"), self.tr("路径")]
        )
        self.java_table.verticalHeader().setVisible(False)
        self.java_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.java_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.java_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.java_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.java_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.java_table.verticalHeader().setDefaultSectionSize(32)
        self.java_table.doubleClicked.connect(self._use_selected_java)
        card.body.addWidget(self.java_table, 1)
        tip = QLabel(
            self.tr(
                "双击一行可将其设为默认 Java。若未检测到合适的 Java，请安装对应版本后在游戏设置中手动指定。"
            )
        )
        tip.setObjectName("Tiny")
        card.body.addWidget(tip)
        layout.addWidget(card, 1)
        return page

    def _build_about_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 14, 0, 0)
        layout.setSpacing(12)
        card = Card(margins=24, spacing=12)
        title = QLabel(f"{APP_NAME} <span style='color:#65d46e'>v{APP_VERSION}</span>")
        title.setTextFormat(Qt.RichText)
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        card.body.addWidget(title)
        desc = QLabel(
            "MikanCL 是一款参考 HMCL / PCL 设计实现的全能 Minecraft 启动器。\n\n"
            "· 正版微软登录（设备码）、外置登录（authlib-injector）与离线账号并存\n"
            "· 兼容标准 .minecraft 目录与 inheritsFrom 继承版本（Forge / NeoForge / Fabric / Quilt / LiteLoader / OptiFine）\n"
            "· 一键安装 Forge、NeoForge、Fabric、Quilt、LiteLoader 加载器\n"
            "· 内容中心接入 Modrinth 与 CurseForge：Mod、整合包、资源包、光影包搜索与多线程下载\n"
            "· 整合包自动创建独立实例，独立配置版本、内存、参数与自动连服\n"
            "· 控制面板：实例切换、Mod 启用/禁用/删除、启动参数与自动连服配置\n"
            "· 内置 Mojang 官方源、BMCLAPI 镜像、自定义源与 API Key，内容 CDN 可配镜像\n"
            "· 内置 Chromium 浏览器，可直接访问 Minecraft Wiki、MC 百科与 Bilibili"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #b3c8b9; line-height: 1.6;")
        card.body.addWidget(desc)
        links = QHBoxLayout()
        wiki = QPushButton(self.tr("打开 Minecraft Wiki"))
        wiki.clicked.connect(
            lambda: self.ctx.bus.open_browser.emit("https://zh.minecraft.wiki/")
        )
        links.addWidget(wiki)
        bili = QPushButton(self.tr("打开 Bilibili"))
        bili.clicked.connect(
            lambda: self.ctx.bus.open_browser.emit(
                "https://search.bilibili.com/all?keyword=我的世界"
            )
        )
        links.addWidget(bili)
        links.addStretch(1)
        card.body.addLayout(links)
        note = QLabel(
            "免责声明：本启动器与 Mojang Studios、Microsoft、Bilibili、Minecraft Wiki 无隶属关系；"
            "Minecraft 是 Mojang Studios 的商标。请通过官方渠道支持正版游戏。"
        )
        note.setObjectName("Tiny")
        note.setWordWrap(True)
        card.body.addWidget(note)
        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _connect(self) -> None:
        self.ctx.bus.config_changed.connect(self._sync_ui_from_config)
        self.ctx.bus.javas_changed.connect(self._rebuild_java_table)

    # ------------------------------------------------------------------
    def _rebuild_source_table(self) -> None:
        config = self.ctx.config
        self.source_table.setRowCount(0)
        for row, source in enumerate(config.sources):
            self.source_table.insertRow(row)
            name_item = QTableWidgetItem(
                source.name + (t("SettingsPage", "（内置）") if source.builtin else "")
            )
            name_item.setData(Qt.UserRole, source.id)
            self.source_table.setItem(row, 0, name_item)
            self.source_table.setItem(row, 1, QTableWidgetItem(source.manifest_url))
            self.source_table.setItem(
                row,
                2,
                QTableWidgetItem(
                    t(
                        "SettingsPage",
                        SOURCE_MAPPINGS.get(source.mapping, source.mapping),
                    )
                ),
            )
            self.source_table.setItem(
                row,
                3,
                QTableWidgetItem(
                    t("SettingsPage", "已配置") if source.api_key.strip() else t("SettingsPage", "未设置")
                ),
            )
            self.source_table.setItem(
                row, 4, QTableWidgetItem(t("SettingsPage", "启用") if source.enabled else t("SettingsPage", "禁用"))
            )

            ops = QHBoxLayout()
            ops.setContentsMargins(0, 0, 0, 0)
            ops.setSpacing(4)
            edit = QPushButton(t("SettingsPage", "编辑"))
            edit.setStyleSheet("padding: 2px 8px; font-size: 11px;")
            edit.clicked.connect(lambda _=False, sid=source.id: self._edit_source(sid))
            ops.addWidget(edit)
            test = QPushButton(t("SettingsPage", "测试"))
            test.setStyleSheet("padding: 2px 8px; font-size: 11px;")
            test.clicked.connect(lambda _=False, sid=source.id: self._test_source(sid))
            ops.addWidget(test)
            toggle = QPushButton(
                t("SettingsPage", "禁用") if source.enabled else t("SettingsPage", "启用")
            )
            toggle.setStyleSheet("padding: 2px 8px; font-size: 11px;")
            toggle.clicked.connect(lambda _=False, sid=source.id: self._toggle_source(sid))
            ops.addWidget(toggle)
            if not source.builtin:
                delete = QPushButton(t("SettingsPage", "删除"))
                delete.setObjectName("Danger")
                delete.setStyleSheet("padding: 2px 8px; font-size: 11px;")
                delete.clicked.connect(lambda _=False, sid=source.id: self._delete_source(sid))
                ops.addWidget(delete)
            wrapper = QWidget()
            wrapper.setLayout(ops)
            self.source_table.setCellWidget(row, 5, wrapper)

    def _selected_source(self) -> DownloadSource | None:
        row = self.source_table.currentRow()
        if row < 0:
            return None
        item = self.source_table.item(row, 0)
        if item is None:
            return None
        return self.ctx.config.get_source(str(item.data(Qt.UserRole)))

    def _add_source(self) -> None:
        source = DownloadSource(
            id=self.ctx.config.new_source_id(),
            name=f"自定义源 {len(self.ctx.config.sources) + 1}",
            manifest_url="",
            mapping="bmclapi",
            download_base="",
            api_key_header="X-API-Key",
            api_key="",
            enabled=True,
            priority=90,
            builtin=False,
        )
        dialog = SourceDialog(source, self)
        if dialog.exec() != QDialog.Accepted:
            return
        self.ctx.config.sources.append(source)
        self._ctx_save()
        self.ctx.bus.toast.emit(f"已添加下载源：{source.name}")

    def _edit_source(self, source_id: str) -> None:
        source = self.ctx.config.get_source(source_id)
        if not source:
            return
        dialog = SourceDialog(source, self)
        if dialog.exec() != QDialog.Accepted:
            return
        self._ctx_save()
        self.ctx.bus.toast.emit(f"已保存下载源：{source.name}")
        if source.id == self.ctx.config.selected_source_id:
            self.ctx.bus.toast.emit("当前清单源已更新，可在下载页刷新清单。")

    def _delete_source(self, source_id: str) -> None:
        source = self.ctx.config.get_source(source_id)
        if not source or source.builtin:
            return
        answer = QMessageBox.question(
            self,
            "删除下载源",
            f"确定删除“{source.name}”吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.ctx.config.sources = [s for s in self.ctx.config.sources if s.id != source_id]
        if self.ctx.config.selected_source_id == source_id:
            remaining = [s for s in self.ctx.config.sources if s.enabled]
            self.ctx.config.selected_source_id = remaining[0].id if remaining else "official"
        self._ctx_save()
        self.ctx.bus.toast.emit(f"已删除下载源：{source.name}")

    def _toggle_source(self, source_id: str) -> None:
        source = self.ctx.config.get_source(source_id)
        if not source:
            return
        if source.enabled and len([s for s in self.ctx.config.sources if s.enabled]) <= 1:
            QMessageBox.warning(self, "无法禁用", "至少需要保留一个启用的下载源。")
            return
        source.enabled = not source.enabled
        self._ctx_save()
        self.ctx.bus.toast.emit(f"下载源已{'启用' if source.enabled else '禁用'}：{source.name}")

    def _test_source(self, source_id: str) -> None:
        source = self.ctx.config.get_source(source_id)
        if not source:
            return
        if self._test_worker is not None and self._test_worker.isRunning():
            self.ctx.bus.toast.emit("正在测试其他源，请稍候…")
            return
        self.ctx.bus.toast.emit(f"正在测试源：{source.name}")
        self._test_worker = TestSourceWorker(source, self)
        self._test_worker.done.connect(self._on_tested)
        self._test_worker.finished.connect(self._on_test_finished)
        self._test_worker.start()

    def _test_selected_source(self) -> None:
        source = self._selected_source()
        if source:
            self._test_source(source.id)
        else:
            self._test_source(self.ctx.config.selected_source_id)

    def _on_tested(self, name: str, ok: bool, message: str) -> None:
        self.ctx.bus.log.emit(f"[源测试] {name}：{message}")
        if ok:
            QMessageBox.information(self, "测试通过", f"「{name}」\n{message}")
        else:
            QMessageBox.warning(self, "测试失败", f"「{name}」\n{message}")

    def _on_test_finished(self) -> None:
        worker = self._test_worker
        self._test_worker = None
        if worker is not None:
            worker.deleteLater()

    # ------------------------------------------------------------------
    def _sync_ui_from_config(self) -> None:
        cfg = self.ctx.config
        self._rebuild_game_dir_combo()
        for widget, value in (
            (self.java_path_edit, str(cfg.java_path)),
            (self.jvm_edit, str(cfg.extra_jvm_args)),
            (self.window_title_edit, str(cfg.window_title)),
        ):
            if widget.hasFocus():
                continue
            widget.blockSignals(True)
            widget.setText(value)
            widget.blockSignals(False)
        for combo, value in (
            (self.isolation_combo, cfg.isolation_mode),
            (self.priority_combo, cfg.process_priority),
            (self.after_launch_combo, cfg.after_launch_action),
        ):
            combo.blockSignals(True)
            index = combo.findData(value)
            combo.setCurrentIndex(index if index >= 0 else 0)
            combo.blockSignals(False)
        proxy_widgets = (self.proxy_check, self.proxy_edit, self.proxy_jvm_check)
        for widget in proxy_widgets:
            widget.blockSignals(True)
        self.proxy_check.setChecked(bool(cfg.proxy_enabled))
        self.proxy_edit.setText(str(cfg.proxy_url))
        self.proxy_edit.setEnabled(bool(cfg.proxy_enabled))
        self.proxy_jvm_check.setChecked(bool(cfg.proxy_jvm))
        for widget in proxy_widgets:
            widget.blockSignals(False)
        self.memory_spin.blockSignals(True)
        self.memory_spin.setValue(max(512, int(cfg.memory_mb)))
        self.memory_spin.blockSignals(False)
        self.keep_check.blockSignals(True)
        self.keep_check.setChecked(bool(cfg.keep_launcher_on_game_exit))
        self.keep_check.blockSignals(False)
        self._rebuild_source_table()

        for widget, value in (
            (self.modrinth_edit, cfg.modrinth_api_base),
            (self.modrinth_mirror_edit, cfg.modrinth_cdn_mirror),
            (self.cf_edit, cfg.curseforge_api_base),
            (self.cf_key_edit, cfg.curseforge_api_key),
            (self.cf_mirror_edit, cfg.curseforge_cdn_mirror),
            (self.ms_client_edit, cfg.microsoft_client_id),
            (self.authlib_url_edit, cfg.authlib_injector_url),
        ):
            if widget.hasFocus():
                continue
            widget.blockSignals(True)
            widget.setText(str(value or ""))
            widget.blockSignals(False)
        self.threads_spin.blockSignals(True)
        self.threads_spin.setValue(max(1, min(328, int(cfg.download_threads))))
        self.threads_spin.blockSignals(False)
        for check, value in (
            (self.tray_check, cfg.close_to_tray),
            (self.general_hide_check, cfg.after_launch_action == "hide"),
            (self.start_anim_check, cfg.start_animation),
        ):
            check.blockSignals(True)
            check.setChecked(bool(value))
            check.blockSignals(False)
        self.general_memory_spin.blockSignals(True)
        self.general_memory_spin.setValue(max(512, int(cfg.memory_mb)))
        self.general_memory_spin.blockSignals(False)
        self.general_threads_spin.blockSignals(True)
        self.general_threads_spin.setValue(max(1, min(328, int(cfg.download_threads))))
        self.general_threads_spin.blockSignals(False)
        self.language_combo.blockSignals(True)
        index = self.language_combo.findData(cfg.language)
        self.language_combo.setCurrentIndex(index if index >= 0 else 0)
        self.language_combo.blockSignals(False)
        self._sync_appearance()
        self.authlib_path_label.setText(self._authlib_path_text())

    def _authlib_path_text(self) -> str:
        from ..auth import injector_jar_path

        path = Path(self.ctx.config.authlib_injector_path) if self.ctx.config.authlib_injector_path else injector_jar_path()
        if path.exists():
            size = path.stat().st_size / 1024
            return t("SettingsPage", "authlib-injector 缓存：{0}（{1} KB）", path, f"{size:.0f}")
        return t(
            "SettingsPage",
            "authlib-injector 缓存：{0}（尚未下载，首次使用外置登录时自动获取）",
            path,
        )

    def _on_language_changed(self, index: int) -> None:
        code = str(self.language_combo.itemData(index) or "zh_CN")
        cfg = self.ctx.config
        if code == cfg.language:
            return
        cfg.language = code
        cfg.save()
        QMessageBox.information(self, APP_NAME, self.tr("语言已保存，重启启动器后生效"))

    def _restart_launcher(self) -> None:
        # 必须先释放单实例锁，否则新进程会 attach 成功并判定为「已经在运行中」而直接退出
        from ..main import release_single_instance

        # 源码运行时 sys.argv[0] 是脚本路径（python run.py），必须带上；打包后 sys.argv[0] 是 exe 自身
        if getattr(sys, "frozen", False):
            args = sys.argv[1:]
            cwd = str(Path(sys.executable).parent)
        else:
            script = Path(sys.argv[0]).resolve()
            args = [str(script), *sys.argv[1:]]
            cwd = str(script.parent)
        release_single_instance()
        # PyInstaller onefile 用环境变量把解包目录传给子进程；若被新实例继承，
        # 新实例会复用旧临时目录，旧进程退出时清理失败并弹出警告框，因此临时清除。
        inherited = {}
        for key in ("_MEIPASS", "_PYI_PARENT_PROCESS_LEVEL", "_PYI_ARCHIVE_FILE"):
            if key in os.environ:
                inherited[key] = os.environ.pop(key)
        try:
            QProcess.startDetached(sys.executable, args, cwd)
        finally:
            os.environ.update(inherited)
        QApplication.quit()

    def _save_general_settings(self) -> None:
        cfg = self.ctx.config
        cfg.close_to_tray = self.tray_check.isChecked()
        cfg.start_animation = self.start_anim_check.isChecked()
        cfg.memory_mb = int(self.general_memory_spin.value())
        cfg.download_threads = int(self.general_threads_spin.value())
        if self.general_hide_check.isChecked():
            if cfg.after_launch_action != "hide":
                cfg.after_launch_action = "hide"
        elif cfg.after_launch_action == "hide":
            cfg.after_launch_action = "nothing"
        cfg.hide_after_launch = cfg.after_launch_action == "hide"
        self.after_launch_combo.blockSignals(True)
        index = self.after_launch_combo.findData(cfg.after_launch_action)
        self.after_launch_combo.setCurrentIndex(index if index >= 0 else 0)
        self.after_launch_combo.blockSignals(False)
        self._ctx_save()
        self.ctx.bus.toast.emit("通用设置已保存。")

    def _open_directory(self, path) -> None:
        target = Path(path)
        if not target.exists():
            QMessageBox.warning(self, "目录不存在", f"目录尚不存在：\n{target}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def _clear_cache(self, names: list[str], label: str) -> None:
        removed = 0
        failed = 0
        for name in names:
            folder = CACHE_DIR / name
            if not folder.is_dir():
                continue
            for item in folder.iterdir():
                try:
                    if item.is_file() or item.is_symlink():
                        item.unlink()
                        removed += 1
                except OSError:
                    failed += 1
        message = f"已清理{label}：{removed} 个文件。"
        if failed:
            message += f"（{failed} 个文件无法删除）"
        self.ctx.bus.toast.emit(message)

    def _save_content_settings(self) -> None:
        cfg = self.ctx.config
        cfg.modrinth_api_base = self.modrinth_edit.text().strip() or cfg.modrinth_api_base
        cfg.modrinth_cdn_mirror = self.modrinth_mirror_edit.text().strip()
        cfg.curseforge_api_base = self.cf_edit.text().strip() or cfg.curseforge_api_base
        cfg.curseforge_api_key = self.cf_key_edit.text().strip()
        cfg.curseforge_cdn_mirror = self.cf_mirror_edit.text().strip()
        cfg.download_threads = int(self.threads_spin.value())
        self._ctx_save()
        self.ctx.bus.toast.emit("内容源设置已保存。")

    def _save_auth_settings(self) -> None:
        cfg = self.ctx.config
        cfg.microsoft_client_id = self.ms_client_edit.text().strip() or cfg.microsoft_client_id
        cfg.authlib_injector_url = (
            self.authlib_url_edit.text().strip() or cfg.authlib_injector_url
        )
        self._ctx_save()
        self.authlib_path_label.setText(self._authlib_path_text())
        self.ctx.bus.toast.emit("登录设置已保存。")

    def _clear_authlib(self) -> None:
        from ..auth import injector_jar_path

        path = (
            Path(self.ctx.config.authlib_injector_path)
            if self.ctx.config.authlib_injector_path
            else injector_jar_path()
        )
        if not path.exists():
            self.ctx.bus.toast.emit("authlib-injector 缓存已为空。")
            return
        try:
            path.unlink()
        except OSError as exc:
            QMessageBox.warning(self, "删除失败", f"无法删除缓存文件：\n{exc}")
            return
        self.authlib_path_label.setText(self._authlib_path_text())
        self.ctx.bus.toast.emit("authlib-injector 缓存已清除，下次使用时会重新下载。")

    def _rebuild_game_dir_combo(self) -> None:
        cfg = self.ctx.config
        combo = self.game_dir_combo
        combo.blockSignals(True)
        combo.clear()
        for entry in cfg.game_dirs:
            combo.addItem(f"{entry.name} · {entry.path}", entry.id)
        index = combo.findData(cfg.active_game_dir)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def _on_game_dir_selected(self, index: int) -> None:
        dir_id = str(self.game_dir_combo.itemData(index) or "")
        cfg = self.ctx.config
        if not dir_id or dir_id == cfg.active_game_dir:
            return
        if cfg.select_game_dir(dir_id):
            self.ctx.bus.config_changed.emit()
            self.ctx.bus.versions_changed.emit()
            entry = cfg.active_game_entry()
            self.ctx.bus.toast.emit(f"已切换到数据目录：{entry.name}")

    def _add_game_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "选择要添加的数据目录", str(self.ctx.config.game_path)
        )
        if not path:
            return
        cfg = self.ctx.config
        existing = next(
            (entry for entry in cfg.game_dirs if Path(entry.path) == Path(path)), None
        )
        if existing is not None:
            cfg.select_game_dir(existing.id)
            message = f"已切换到数据目录：{existing.name}"
        else:
            entry = cfg.add_game_dir(Path(path).name or "新目录", path)
            cfg.select_game_dir(entry.id)
            message = f"已添加数据目录：{entry.name}"
        self.ctx.bus.config_changed.emit()
        self.ctx.bus.versions_changed.emit()
        self._rebuild_game_dir_combo()
        self.ctx.bus.toast.emit(message)

    def _remove_game_dir(self) -> None:
        cfg = self.ctx.config
        dir_id = str(self.game_dir_combo.currentData() or cfg.active_game_dir)
        if not cfg.remove_game_dir(dir_id):
            QMessageBox.information(self, "无法移除", "至少需要保留一个数据目录。")
            return
        self.ctx.bus.config_changed.emit()
        self.ctx.bus.versions_changed.emit()
        self._rebuild_game_dir_combo()
        self.ctx.bus.toast.emit("数据目录已移除。")

    def _open_game_dir(self) -> None:
        path = self.ctx.config.game_path
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _on_isolation_changed(self, index: int) -> None:
        self.ctx.config.isolation_mode = str(self.isolation_combo.itemData(index) or "none")
        self._ctx_save()

    def _on_priority_changed(self, index: int) -> None:
        self.ctx.config.process_priority = str(self.priority_combo.itemData(index) or "normal")
        self._ctx_save()

    def _on_after_launch_changed(self, index: int) -> None:
        value = str(self.after_launch_combo.itemData(index) or "nothing")
        self.ctx.config.after_launch_action = value
        self.ctx.config.hide_after_launch = value == "hide"
        self._ctx_save()

    def _on_window_title_changed(self) -> None:
        self.ctx.config.window_title = self.window_title_edit.text().strip()
        self._ctx_save()

    def _on_proxy_changed(self, *_args) -> None:
        cfg = self.ctx.config
        cfg.proxy_enabled = self.proxy_check.isChecked()
        cfg.proxy_url = self.proxy_edit.text().strip()
        cfg.proxy_jvm = self.proxy_jvm_check.isChecked()
        self.proxy_edit.setEnabled(cfg.proxy_enabled)
        apply_proxy(cfg.effective_proxy)
        self._ctx_save()

    def _on_java_path_changed(self) -> None:
        self.ctx.config.java_path = self.java_path_edit.text().strip()
        self._ctx_save()

    def _browse_java(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 javaw.exe 或 java.exe",
            str(Path(self.ctx.config.java_path).parent) if self.ctx.config.java_path else str(Path.home()),
            "Java 可执行文件 (javaw.exe java.exe);;所有文件 (*)",
        )
        if path:
            self.java_path_edit.setText(path)
            self._on_java_path_changed()

    def _java_task_active(self) -> bool:
        return any(t.kind == "Java" and t.active for t in self.ctx.downloads.tasks())

    def _download_java(self) -> None:
        if self._java_task_active():
            self.ctx.bus.toast.emit("已有 Java 下载任务在进行中。")
            return
        major, ok = QInputDialog.getInt(
            self, "下载 Java", "要下载的 Java 大版本（8 / 17 / 21）：", 21, 8, 30, 1
        )
        if not ok:
            return
        cancel_event = threading.Event()
        pause_event = threading.Event()

        def factory(_task) -> QThread:
            worker = JavaDownloadWorker(
                major, DATA_DIR / "runtime", _task.id, cancel_event, pause_event, self
            )
            worker.progress.connect(
                lambda p, s, tid=_task.id: self.ctx.downloads.update(
                    tid, percent=p, speed=s
                )
            )
            worker.done.connect(self._on_java_downloaded)
            worker.failed.connect(
                lambda msg, tid=_task.id: self._on_java_download_failed(tid, msg)
            )
            worker.finished.connect(self._restore_java_button)
            self._java_download_worker = worker
            return worker

        self.ctx.downloads.submit(
            kind="Java",
            name=f"Java {major}",
            factory=factory,
            cancel=cancel_event.set,
            pause=pause_event,
            rebuild=factory,
            target_dir=str(DATA_DIR / "runtime"),
            detail=f"Adoptium JRE · Java {major}",
        )
        self.java_download_button.setEnabled(False)
        self.java_download_button.setText("下载中…")
        self.ctx.bus.toast.emit(f"已加入下载中心：Java {major}（Adoptium）")

    def _restore_java_button(self) -> None:
        self._java_download_worker = None
        self.java_download_button.setEnabled(True)
        self.java_download_button.setText("下载 Java…")

    def _on_java_downloaded(self, info) -> None:
        self.ctx.javas = detect_java_installed()
        if info is not None and all(
            java_key(j.path) != java_key(info.path) for j in self.ctx.javas
        ):
            self.ctx.javas.append(info)
        self.ctx.bus.javas_changed.emit()
        self.ctx.bus.toast.emit(f"Java 已就绪：{getattr(info, 'version', '')}")
        self._rebuild_java_table()

    def _on_java_download_failed(self, task_id: str, message: str) -> None:
        self.ctx.downloads.finish(task_id, ok=False, message=message)
        QMessageBox.warning(self, APP_NAME, f"Java 下载失败：{message}")

    def _open_java_center(self) -> None:
        """以对话框形式打开 Java 中心，关闭时回收其后台 worker。"""
        from .page_java_center import JavaCenterPage

        dialog = QDialog(self)
        dialog.setWindowTitle("Java 中心")
        dialog.resize(900, 540)
        page = JavaCenterPage(self.ctx, dialog)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(page)
        dialog.finished.connect(page.shutdown)
        dialog.exec()

    def _rescan_java(self) -> None:
        if self._rescan_worker is not None and self._rescan_worker.isRunning():
            return
        self.ctx.bus.toast.emit("正在扫描 Java 运行时…")
        self._rescan_worker = RescanJavaWorker(self)
        self._rescan_worker.done.connect(self._on_java_rescanned)
        self._rescan_worker.start()

    def _on_java_rescanned(self, javas: list) -> None:
        self.ctx.javas = javas
        self.ctx.bus.javas_changed.emit()
        self.ctx.bus.toast.emit(f"扫描完成，共找到 {len(javas)} 个 Java 运行时。")

    def _rebuild_java_table(self) -> None:
        self.java_table.setRowCount(0)
        for row, java in enumerate(self.ctx.javas):
            self.java_table.insertRow(row)
            version_item = QTableWidgetItem(f"Java {java.major}  ({java.version})")
            version_item.setData(Qt.UserRole, java.path)
            self.java_table.setItem(row, 0, version_item)
            bits_item = QTableWidgetItem(f"{java.bits} 位")
            bits_item.setTextAlignment(Qt.AlignCenter)
            self.java_table.setItem(row, 1, bits_item)
            self.java_table.setItem(row, 2, QTableWidgetItem(java.path))

    def _use_selected_java(self) -> None:
        row = self.java_table.currentRow()
        if row < 0:
            return
        item = self.java_table.item(row, 0)
        if item is None:
            return
        path = str(item.data(Qt.UserRole) or "")
        if path:
            self.java_path_edit.setText(path)
            self._on_java_path_changed()
            self.ctx.bus.toast.emit(f"默认 Java 已设置为 Java {self.java_table.item(row, 0).text()}")

    def _on_memory_changed(self, value: int) -> None:
        self.ctx.config.memory_mb = int(value)
        self._ctx_save()

    def _on_jvm_changed(self) -> None:
        self.ctx.config.extra_jvm_args = self.jvm_edit.text()
        self._ctx_save()

    def _on_keep_changed(self, checked: bool) -> None:
        self.ctx.config.keep_launcher_on_game_exit = bool(checked)
        self._ctx_save()

    def _ctx_save(self) -> None:
        self.ctx.config.save_debounced()
        self.ctx.bus.config_changed.emit()

    def shutdown(self) -> None:
        for worker in (self._test_worker, self._rescan_worker, self._java_download_worker):
            wait_thread(worker, 2000)
