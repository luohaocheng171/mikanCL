"""主窗口：自绘标题栏、侧边栏导航、页面容器、拖拽导入、托盘与 Java 扫描。"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QSize, QThread, Qt, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QAction, QGuiApplication, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, APP_NAME_CN, APP_VERSION
from ..context import AppContext, wait_thread
from ..i18n import t
from ..java import detect_java_installed
from ..plugins import PluginManager, PluginPage
from .dropinstall import handle_dropped_paths
from .page_accounts import AccountsPage
from .page_bedrock import BedrockPage
from .page_browser import BrowserPage
from .page_content import ContentPage
from .page_control import ControlPage
from .page_download import DownloadPage
from .page_download_center import DownloadCenterPage
from .page_forbric import ForbricPage
from .page_modpack import ModpackPage
from .page_home import HomePage
from .page_java_center import JavaCenterPage
from .page_loaders import LoadersPage
from .page_multiplayer import MultiplayerPage
from .page_seed_terrain import SeedTerrainPage
from .page_settings import SettingsPage
from .page_skin_factory import SkinFactoryPage
from .page_wiki import WikiPage
from .covers import CoverLoader
from .theme import (
    acrylic_stylesheet,
    background_overlay_stylesheet,
    make_avatar,
    make_block_icon,
    make_nav_icon,
    make_skin_avatar,
    resolve_account_avatar,
)
from .widgets import scroll_page

# 无边框窗口的边缘缩放：Windows 命中测试消息与结果码
_WM_NCHITTEST = 0x0084
_RESIZE_MARGIN = 6
_HIT_TEST = {
    (True, False, True, False): 13,  # 左上
    (False, True, True, False): 14,  # 右上
    (True, False, False, True): 16,  # 左下
    (False, True, False, True): 17,  # 右下
    (True, False, False, False): 10,  # 左
    (False, True, False, False): 11,  # 右
    (False, False, True, False): 12,  # 上
    (False, False, False, True): 15,  # 下
}


def _cursor_point(lparam: int) -> QPoint:
    """从 WM_NCHITTEST 的 lParam 中取出屏幕坐标（有符号 16 位）。"""
    x = ctypes.c_short(lparam & 0xFFFF).value
    y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
    return QPoint(x, y)


class TitleBar(QFrame):
    """无边框窗口的自绘标题栏：拖动、双击最大化、最小化/最大化/关闭。"""

    def __init__(self, window: "MainWindow"):
        super().__init__(window)
        self.setObjectName("TitleBar")
        self.setFixedHeight(44)
        self._drag_offset: QPoint | None = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 8, 0)
        layout.setSpacing(10)

        icon = QLabel()
        icon.setPixmap(make_block_icon(20).pixmap(20, 20))
        layout.addWidget(icon)
        title = QLabel(f"{APP_NAME} · {t('MainWindow', 'Minecraft 启动器')}")
        title.setObjectName("TitleBarText")
        layout.addWidget(title)
        layout.addStretch(1)

        self.min_button = self._make_button("−", t("MainWindow", "最小化"))
        self.min_button.clicked.connect(window.showMinimized)
        layout.addWidget(self.min_button)
        self.max_button = self._make_button("□", t("MainWindow", "最大化 / 还原"))
        self.max_button.clicked.connect(window.toggle_maximized)
        layout.addWidget(self.max_button)
        close_button = self._make_button("✕", t("MainWindow", "关闭"), danger=True)
        close_button.clicked.connect(window.close)
        layout.addWidget(close_button)

    def _make_button(self, text: str, tip: str, danger: bool = False) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("WinClose" if danger else "WinButton")
        button.setToolTip(tip)
        button.setFixedSize(40, 30)
        button.setCursor(Qt.PointingHandCursor)
        return button

    # ---------- 拖动窗口 ----------
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is None or not (event.buttons() & Qt.LeftButton):
            return
        window = self.window()
        if window.isMaximized():
            window.showNormal()
            self._drag_offset = QPoint(int(window.width() / 2), int(self.height() / 2))
        window.move(event.globalPosition().toPoint() - self._drag_offset)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.window().toggle_maximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class JavaScanWorker(QThread):
    done = Signal(list)

    def run(self) -> None:
        self.done.emit(detect_java_installed())


class RootWidget(QWidget):
    """根容器：自定义背景图按窗口大小等比铺满并居中裁切，不会拉伸变形。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Root")
        self._source: QPixmap | None = None
        self._cache: QPixmap | None = None
        self._cache_size = QSize()

    def set_background(self, path: str) -> None:
        pixmap = QPixmap(path) if path else QPixmap()
        self._source = None if pixmap.isNull() else pixmap
        self._cache = None
        self._cache_size = QSize()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        if self._source is None or self.width() <= 0 or self.height() <= 0:
            super().paintEvent(event)
            return
        if self._cache is None or self._cache_size != self.size():
            self._cache = self._source.scaled(
                self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            self._cache_size = self.size()
        painter = QPainter(self)
        painter.drawPixmap(
            (self.width() - self._cache.width()) // 2,
            (self.height() - self._cache.height()) // 2,
            self._cache,
        )


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self._java_worker: JavaScanWorker | None = None
        self._plugin_pages: dict[int, QWidget] = {}
        self.plugin_manager: PluginManager | None = None
        self.setWindowTitle(f"{APP_NAME} · {self.tr('Minecraft 启动器')}")
        self.setWindowIcon(make_block_icon(64))
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAcceptDrops(True)
        self._apply_default_geometry()

        self._build()
        self._avatar_covers = CoverLoader(self)
        self._connect_bus()
        self._load_plugins()
        self._apply_appearance()
        self._start_java_scan()
        self._setup_tray()

    # ---------- 窗口尺寸 ----------
    def _apply_default_geometry(self) -> None:
        """默认尺寸贴近 PCL / HMCL（约 1080×680），并按屏幕可用区域自动收缩。"""
        width, height = 1080, 680
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            width = max(900, min(width, available.width() - 60))
            height = max(540, min(height, available.height() - 60))
        self.setMinimumSize(min(900, width), min(540, height))
        self.resize(width, height)
        if screen is not None:
            available = screen.availableGeometry()
            self.move(available.center() - self.rect().center())

    # ---------- 无边框窗口的边缘缩放 ----------
    def nativeEvent(self, eventType, message):  # noqa: N802
        """让无边框窗口也能像普通窗口一样拖动边缘改大小。"""
        if sys.platform == "win32" and eventType == b"windows_generic_MSG":
            try:
                msg = ctypes.wintypes.MSG.from_address(int(message))
            except (TypeError, ValueError):
                msg = None
            if msg is not None and msg.message == _WM_NCHITTEST and not self.isMaximized():
                point = self.mapFromGlobal(_cursor_point(msg.lParam))
                margin = _RESIZE_MARGIN
                hit = _HIT_TEST.get(
                    (
                        point.x() < margin,
                        point.x() > self.width() - margin,
                        point.y() < margin,
                        point.y() > self.height() - margin,
                    )
                )
                if hit:
                    return True, hit
        return super().nativeEvent(eventType, message)

    # ------------------------------------------------------------------
    def toggle_maximized(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        self._sync_window_buttons()

    def _sync_window_buttons(self) -> None:
        if not hasattr(self, "title_bar"):
            return
        self.title_bar.max_button.setText("❐" if self.isMaximized() else "□")

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._sync_window_buttons()

    # ---------- 拖拽导入 ----------
    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        paths: list[Path] = []
        for url in event.mimeData().urls():
            if url.isLocalFile():
                local = url.toLocalFile()
                if local:
                    paths.append(Path(local))
        if not paths:
            return
        event.acceptProposedAction()
        plugins = [p for p in paths if p.suffix.lower() == ".py" and p.is_file()]
        others = [p for p in paths if p not in plugins]
        if plugins:
            self._install_plugins(plugins)
        if others:
            handle_dropped_paths(self, self.ctx, others)

    def _install_plugins(self, paths: list[Path]) -> None:
        """拖入的 .py 文件当作插件：复制到 data/plugins 并立即加载。"""
        manager = self.plugin_manager
        if manager is None:
            return
        messages: list[str] = []
        success = 0
        for path in paths:
            ok, message = manager.install_file(path)
            messages.append(message)
            success += 1 if ok else 0
            self.ctx.bus.log.emit(f"[插件] {message}")
        if len(messages) == 1:
            self.statusBar().showMessage(messages[0], 8000)
        else:
            self.statusBar().showMessage(f"{success}/{len(paths)} 个插件已处理", 8000)
            QMessageBox.information(self, "插件安装", "\n".join(messages))

    # ------------------------------------------------------------------
    def _build(self) -> None:
        self.root = RootWidget()
        root = self.root
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.title_bar = TitleBar(self)
        outer.addWidget(self.title_bar)

        body = QWidget()
        outer.addWidget(body, 1)
        layout = QHBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(210)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 22, 16, 16)
        side.setSpacing(10)

        logo_row = QHBoxLayout()
        logo_row.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(make_block_icon(44).pixmap(44, 44))
        logo_row.addWidget(logo)
        logo_text = QVBoxLayout()
        logo_text.setSpacing(0)
        title = QLabel(APP_NAME)
        title.setObjectName("LogoTitle")
        sub = QLabel("MINECRAFT LAUNCHER")
        sub.setObjectName("LogoSub")
        logo_text.addWidget(title)
        logo_text.addWidget(sub)
        logo_row.addLayout(logo_text)
        logo_row.addStretch(1)
        side.addLayout(logo_row)
        side.addSpacing(18)

        self.nav_group = QButtonGroup(self)
        self.nav_buttons: list[QPushButton] = []
        nav_items = [
            ("home", self.tr("启动游戏")),
            ("download", self.tr("下载安装")),
            ("downloads", self.tr("下载中心")),
            ("content", self.tr("内容中心")),
            ("modpack", self.tr("整合包")),
            ("account", self.tr("账号管理")),
            ("control", self.tr("版本设置")),
            # theme.py 的 make_nav_icon 没有 "loaders" 分支，走默认图标（不要改 theme.py）
            ("loaders", self.tr("Mod 加载器")),
            # theme.py 的 make_nav_icon 没有 "multiplayer" 分支，走默认图标（不要改 theme.py）
            ("multiplayer", self.tr("多人联机")),
            ("browser", self.tr("内置浏览器")),
            # theme.py 的 make_nav_icon 没有 "forbric" 分支，走默认图标（不要改 theme.py）
            ("forbric", self.tr("Forbric")),
            ("java", self.tr("Java 中心")),
            ("wiki", self.tr("教程中心")),
            ("bedrock", self.tr("基岩版")),
            ("skin_factory", self.tr("皮肤工厂")),
            ("seed_terrain", self.tr("世界种子")),
            ("settings", self.tr("设置")),
        ]
        # 功能开关：被关闭的标签页不创建页面也不显示导航；设置页始终保留（否则无法再开回来）
        cfg = self.ctx.config
        nav_items = [
            (key, text)
            for key, text in nav_items
            if key == "settings" or cfg.feature_enabled(key)
        ]
        nav_host = QWidget()
        nav_host.setStyleSheet("background: transparent;")
        nav_layout = QVBoxLayout(nav_host)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(10)
        self.nav_layout = nav_layout
        for index, (key, text) in enumerate(nav_items):
            button = QPushButton(text)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setMinimumHeight(36)
            # 记录导航 key，供 _navigate_by_name 反查页码（避免手写数字映射错位）
            button._nav_key = key  # type: ignore[attr-defined]
            button.setIcon(make_nav_icon(key, 18, "#9fb6a7"))
            button.setIconSize(QSize(18, 18))
            button.clicked.connect(lambda checked=False, i=index: self.switch_page(i))
            self.nav_group.addButton(button, index)
            nav_layout.addWidget(button)
            self.nav_buttons.append(button)
        nav_layout.addStretch(1)
        self.nav_buttons[0].setChecked(True)

        # 侧边栏导航放进滚动容器：窗口变矮时用滚轮上下滑动，而不是把按钮压扁丢失文字
        nav_scroll = QScrollArea()
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setFrameShape(QFrame.NoFrame)
        nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        nav_scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        nav_scroll.setWidget(nav_host)
        side.addWidget(nav_scroll, 1)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background-color: #1b2920; border: none;")
        side.addWidget(divider)

        mini = QHBoxLayout()
        mini.setSpacing(8)
        self.sidebar_avatar = QLabel()
        self.sidebar_avatar.setPixmap(make_avatar("Steve", 34))
        mini.addWidget(self.sidebar_avatar)
        texts = QVBoxLayout()
        texts.setSpacing(1)
        self.sidebar_account = QLabel(self.tr("离线模式"))
        self.sidebar_account.setStyleSheet("font-size: 12px; font-weight: 600; color: #cfe3d5;")
        texts.addWidget(self.sidebar_account)
        self.sidebar_mode = QLabel(t("MainWindow", "v{0} · 正版 / 外置登录", APP_VERSION))
        self.sidebar_mode.setObjectName("Tiny")
        texts.addWidget(self.sidebar_mode)
        mini.addLayout(texts)
        mini.addStretch(1)
        side.addLayout(mini)
        layout.addWidget(sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        layout.addWidget(content, 1)

        self.pages = QStackedWidget()
        content_layout.addWidget(self.pages)

        # 被功能开关关闭的页面直接不创建（属性置 None），后台任务与网络请求也随之不会启动
        def _on(key: str) -> bool:
            return key == "settings" or cfg.feature_enabled(key)

        self.home_page = HomePage(self.ctx, self) if _on("home") else None
        self.download_page = DownloadPage(self.ctx, self) if _on("download") else None
        self.download_center_page = (
            DownloadCenterPage(self.ctx, self) if _on("downloads") else None
        )
        self.content_page = ContentPage(self.ctx, self) if _on("content") else None
        self.modpack_page = ModpackPage(self.ctx, self) if _on("modpack") else None
        self.accounts_page = AccountsPage(self.ctx, self) if _on("account") else None
        self.control_page = ControlPage(self.ctx, self) if _on("control") else None
        self.loaders_page = LoadersPage(self.ctx, self) if _on("loaders") else None
        self.multiplayer_page = MultiplayerPage(self.ctx, self) if _on("multiplayer") else None
        self.browser_page = BrowserPage(self.ctx, self) if _on("browser") else None
        self.forbric_page = ForbricPage(self.ctx, self) if _on("forbric") else None
        self.java_center_page = JavaCenterPage(self.ctx, self) if _on("java") else None
        self.wiki_page = WikiPage(self.ctx, self) if _on("wiki") else None
        self.bedrock_page = BedrockPage(self.ctx, self) if _on("bedrock") else None
        self.skin_factory_page = SkinFactoryPage(self.ctx, self) if _on("skin_factory") else None
        self.seed_terrain_page = SeedTerrainPage(self.ctx, self) if _on("seed_terrain") else None
        self.settings_page = SettingsPage(self.ctx, self)
        page_seq = (
            ("home", self.home_page),
            ("download", self.download_page),
            ("downloads", self.download_center_page),
            ("content", self.content_page),
            ("modpack", self.modpack_page),
            ("account", self.accounts_page),
            ("control", self.control_page),
            ("loaders", self.loaders_page),
            ("multiplayer", self.multiplayer_page),
            ("browser", self.browser_page),
            ("forbric", self.forbric_page),
            ("java", self.java_center_page),
            ("wiki", self.wiki_page),
            ("bedrock", self.bedrock_page),
            ("skin_factory", self.skin_factory_page),
            ("seed_terrain", self.seed_terrain_page),
            ("settings", self.settings_page),
        )
        # 切页时的刷新回调按 key 查找：页面可被开关隐藏后，页码不再固定，不能再用硬编码数字
        self._refresh_by_key: dict[str, object] = {}
        for key, page in page_seq:
            if page is None:
                continue
            # 浏览器页内含 WebEngine 视图，保持原样；其余页面在窗口变矮时改为滚轮滚动，
            # 避免布局把卡片、表单硬压成薄片导致文字重叠或内容显示不全。
            self.pages.addWidget(page if page is self.browser_page else scroll_page(page))
        refresh_candidates = (
            ("home", self.home_page, "refresh_versions"),
            ("download", self.download_page, "ensure_loaded"),
            ("downloads", self.download_center_page, "refresh"),
            ("content", self.content_page, "refresh"),
            ("modpack", self.modpack_page, "refresh"),
            ("account", self.accounts_page, "refresh"),
            ("control", self.control_page, "refresh"),
            ("loaders", self.loaders_page, "refresh"),
            ("multiplayer", self.multiplayer_page, "refresh"),
            ("forbric", self.forbric_page, "refresh"),
            ("java", self.java_center_page, "refresh"),
            ("wiki", self.wiki_page, "refresh"),
            ("bedrock", self.bedrock_page, "refresh"),
            ("skin_factory", self.skin_factory_page, None),
            ("seed_terrain", self.seed_terrain_page, None),
        )
        for key, page, method in refresh_candidates:
            if page is not None and method:
                self._refresh_by_key[key] = getattr(page, method)

        bar = self.statusBar()
        bar.setSizeGripEnabled(True)
        bar.showMessage(
            t(
                "MainWindow",
                "{0} {1} 已就绪 · 正版 / 外置登录 / 内容中心",
                APP_NAME,
                APP_VERSION,
            )
        )
        if self.modpack_page is not None:
            self.modpack_page.launch_requested.connect(self._launch_from_modpack)
        self._refresh_sidebar_account()

    def _launch_from_modpack(self, instance_id: str, version_id: str) -> None:
        """从「整合包」页直接启动：切换实例并拉起对应版本。"""
        if self.home_page is None:
            QMessageBox.warning(self, "无法启动", "「启动游戏」页已在功能开关中关闭，无法从整合包页启动。")
            return
        self.switch_page(0)
        if not self.home_page.launch_instance_version(instance_id, version_id):
            QMessageBox.warning(
                self,
                "无法启动",
                f"实例中找不到版本 {version_id}，请先在「整合包」页点击“修复”补全版本文件。",
            )

    def _connect_bus(self) -> None:
        bus = self.ctx.bus
        bus.navigate.connect(self._navigate_by_name)
        bus.open_browser.connect(self._open_browser)
        bus.toast.connect(lambda message: self.statusBar().showMessage(message, 6000))
        if self.home_page is not None:
            bus.log.connect(self.home_page._write_console)
        bus.hide_window.connect(self._hide_to_tray)
        bus.javas_changed.connect(self.settings_page._rebuild_java_table)
        bus.accounts_changed.connect(self._refresh_sidebar_account)
        bus.config_changed.connect(self._refresh_sidebar_account)
        bus.config_changed.connect(self._apply_appearance)
        self.pages.currentChanged.connect(self._on_page_changed)
        # 主页右键「编辑版本设置」：先由 ControlPage 选中版本，再切到该页（不重复 refresh）
        bus.focus_version.connect(self._show_version_settings)

    def _show_version_settings(self, _version_id: str = "") -> None:
        """切到「版本设置」页，但不再刷新，避免把刚选中的版本重置回实例默认版本。"""
        # 页面可被功能开关隐藏，按 key 反查而不是用固定页码
        for index, button in enumerate(self.nav_buttons):
            if getattr(button, "_nav_key", "") == "control":
                self.pages.setCurrentIndex(index)
                button.setChecked(True)
                return

    # ------------------------------------------------------------------
    # 插件
    def _load_plugins(self) -> None:
        self.plugin_manager = PluginManager(self.ctx)
        self.plugin_manager.on_page_added = self._add_plugin_page
        self.plugin_manager.load()
        if self.plugin_manager.errors:
            names = "、".join(plugin_id for plugin_id, _detail in self.plugin_manager.errors)
            self.statusBar().showMessage(f"插件加载失败：{names}，详见控制台日志", 10000)

    def _add_plugin_page(self, page: PluginPage) -> None:
        index = len(self.nav_buttons)
        widget = page.widget
        if not isinstance(widget, QScrollArea):
            widget = scroll_page(widget)
        self.pages.addWidget(widget)
        button = QPushButton(page.title)
        button.setObjectName("NavButton")
        button.setCheckable(True)
        button.setMinimumHeight(36)
        button.setIcon(make_nav_icon("content", 18, "#9fb6a7"))
        button.setIconSize(QSize(18, 18))
        button.clicked.connect(lambda checked=False, i=index: self.switch_page(i))
        self.nav_group.addButton(button, index)
        # 侧边栏末尾有 stretch，插件按钮插在它前面
        self.nav_layout.insertWidget(max(0, self.nav_layout.count() - 1), button)
        self.nav_buttons.append(button)
        self._plugin_pages[index] = page.widget

    # ------------------------------------------------------------------
    # 外观
    def _apply_appearance(self) -> None:
        image = (self.ctx.config.background_image or "").strip()
        has_image = bool(image) and Path(image).exists()
        self.root.set_background(image if has_image else "")
        stylesheet = background_overlay_stylesheet(has_image)
        if self.ctx.config.ui_acrylic:
            stylesheet += acrylic_stylesheet()
        self.setStyleSheet(stylesheet)
        self._apply_acrylic()

    def _apply_acrylic(self) -> None:
        """Windows 下通过 DWM SetWindowCompositionAttribute 实现毛玻璃（acrylic）。"""
        if sys.platform != "win32":
            return
        enabled = bool(self.ctx.config.ui_acrylic)
        self.setAttribute(Qt.WA_TranslucentBackground, enabled)
        try:
            import ctypes

            hwnd = int(self.winId())
            ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
            ACCENT_DISABLED = 0
            accent = ACCENT_ENABLE_ACRYLICBLURBEHIND if enabled else ACCENT_DISABLED
            # 0xAABBGGRR，低 alpha 让 DWM 模糊透出，深色基调
            gradient_color = 0x99201818 if enabled else 0

            class AccentPolicy(ctypes.Structure):
                _fields_ = [
                    ("AccentState", ctypes.c_int),
                    ("AccentFlags", ctypes.c_int),
                    ("GradientColor", ctypes.c_uint),
                    ("AnimationId", ctypes.c_int),
                ]

            class WindowCompositionAttributeData(ctypes.Structure):
                _fields_ = [
                    ("Attribute", ctypes.c_ulong),
                    ("Data", ctypes.POINTER(AccentPolicy)),
                    ("SizeOfData", ctypes.c_size_t),
                ]

            WCA_ACCENT_POLICY = 19
            policy = AccentPolicy(accent, 0, gradient_color, 0)
            data = WindowCompositionAttributeData(
                WCA_ACCENT_POLICY, ctypes.byref(policy), ctypes.sizeof(policy)
            )
            ctypes.windll.user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data))
        except Exception:
            # 不支持的系统静默回退到半透明深色背景
            pass

    def _on_page_changed(self, index: int) -> None:
        """页面切换淡入淡出动画；动画开关关闭时直接跳过以降低 GPU 占用。"""
        if not self.ctx.config.ui_animations:
            return
        widget = self.pages.currentWidget()
        if widget is None:
            return
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(180)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.finished.connect(lambda w=widget: self._clear_page_effect(w))
        animation.start(QPropertyAnimation.DeleteWhenStopped)

    @staticmethod
    def _clear_page_effect(widget: QWidget) -> None:
        try:
            widget.setGraphicsEffect(None)
        except RuntimeError:
            pass

    def _navigate_by_name(self, name: str) -> None:
        # 按导航项 key 反查页码：插件 / 外部跳转只需匹配 key，新增页面时不用再同步数字
        aliases = {
            "downloads": "downloads",
            "download_center": "downloads",
            "account": "account",
            "accounts": "account",
            "loader": "loaders",
            "loaders": "loaders",
            "multi": "multiplayer",
            "multiplayer": "multiplayer",
            "java": "java",
        }
        target = aliases.get(name, name)
        for index, button in enumerate(self.nav_buttons):
            if getattr(button, "_nav_key", "") == target:
                self.switch_page(index)
                return
        self.switch_page(0)

    def _refresh_sidebar_account(self) -> None:
        account = self.ctx.current_account()
        if account is None:
            return
        self.sidebar_avatar.setPixmap(resolve_account_avatar(account, 34))
        if getattr(account, "skin_url", "") and not getattr(account, "skin_path", ""):
            base = resolve_account_avatar(account, 34)
            self._avatar_covers.load(
                account.skin_url,
                lambda pm: self._on_sidebar_avatar(
                    make_skin_avatar(pm, 34)
                    if pm is not None and not pm.isNull()
                    else base
                ),
                QSize(34, 34),
            )
        type_label = t("AccountsPage", account.type_label)
        self.sidebar_account.setText(f"{account.name} · {type_label}")
        self.sidebar_account.setToolTip(account.note or type_label)

    def _on_sidebar_avatar(self, pixmap) -> None:
        try:
            self.sidebar_avatar.setPixmap(pixmap)
        except RuntimeError:
            pass

    def switch_page(self, index: int) -> None:
        if not (0 <= index < self.pages.count()):
            return
        self.pages.setCurrentIndex(index)
        self.nav_buttons[index].setChecked(True)
        # 页面可被功能开关隐藏，页码不固定：按导航 key 找刷新回调
        key = getattr(self.nav_buttons[index], "_nav_key", "")
        refresh = self._refresh_by_key.get(key)
        if callable(refresh):
            refresh()
        elif index in self._plugin_pages:
            # 插件页可选提供 refresh() 方法，切页时自动调用
            plugin_refresh = getattr(self._plugin_pages[index], "refresh", None)
            if callable(plugin_refresh):
                plugin_refresh()

    def _open_browser(self, url: str) -> None:
        if self.browser_page is None:
            # 内置浏览器被功能开关关闭时退化为系统浏览器打开
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices

            QDesktopServices.openUrl(QUrl(url))
            return
        for index, button in enumerate(self.nav_buttons):
            if getattr(button, "_nav_key", "") == "browser":
                self.switch_page(index)
                break
        self.browser_page.navigate_to(url)

    def _hide_to_tray(self) -> None:
        if self.tray.isVisible() and QSystemTrayIcon.isSystemTrayAvailable():
            self.hide()
            self.tray.showMessage(
                APP_NAME, "启动器已隐藏，点击托盘图标可恢复。", QSystemTrayIcon.Information, 2500
            )
        else:
            self.showMinimized()

    # ------------------------------------------------------------------
    def _start_java_scan(self) -> None:
        self._java_worker = JavaScanWorker(self)
        self._java_worker.done.connect(self._on_java_scanned)
        self._java_worker.start()

    def _on_java_scanned(self, javas: list) -> None:
        self.ctx.javas = javas
        self.ctx.bus.javas_changed.emit()
        self._java_worker = None
        if not javas:
            self.statusBar().showMessage("未检测到 Java，请到设置页手动指定 Java 路径。", 8000)
        else:
            self.statusBar().showMessage(f"已检测到 {len(javas)} 个 Java 运行时。", 5000)

    def _setup_tray(self) -> None:
        self.tray = QSystemTrayIcon(make_block_icon(32), self)
        self.tray.setToolTip(f"{APP_NAME} · {self.tr('Minecraft 启动器')}")
        menu = QMenu(self)
        show_action = QAction(self.tr("显示主界面"), self)
        show_action.triggered.connect(self._restore_window)
        menu.addAction(show_action)
        menu.addSeparator()
        quit_action = QAction(self.tr("退出启动器"), self)
        quit_action.triggered.connect(self._quit_app)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._restore_window()

    def _restore_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_app(self) -> None:
        self._force_quit = True
        self.close()

    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:
        if (
            self.ctx.config.close_to_tray
            and not getattr(self, "_force_quit", False)
            and self.tray.isVisible()
        ):
            event.ignore()
            self._hide_to_tray()
            return
        self.ctx.config.save()
        for page in (
            self.home_page,
            self.download_page,
            self.download_center_page,
            self.content_page,
            self.modpack_page,
            self.accounts_page,
            self.control_page,
            self.loaders_page,
            self.multiplayer_page,
            self.browser_page,
            self.forbric_page,
            self.java_center_page,
            self.wiki_page,
            self.bedrock_page,
            self.settings_page,
        ):
            if page is None:
                continue
            shutdown = getattr(page, "shutdown", None)
            if callable(shutdown):
                shutdown()
        self._avatar_covers.shutdown()
        if self.plugin_manager is not None:
            self.plugin_manager.shutdown()
        wait_thread(self._java_worker, 1500)
        self.tray.hide()
        event.accept()
