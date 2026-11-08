"""主窗口：自绘标题栏、侧边栏导航、页面容器、拖拽导入、托盘与 Java 扫描。"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import shutil
import socket
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QSize, QThread, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QGuiApplication,
    QIcon,
    QMovie,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, APP_NAME_CN, APP_VERSION, skins
from ..auth import AuthError, validate_skin_file
from ..config import DATA_DIR
from .._trace import trace as _trace
from ..context import AppContext, wait_thread
from ..i18n import t
from ..java import detect_java_installed, merge_java_lists, preload_jvm
from ..net import set_default_download_workers, set_download_speed_limit
from ..plugins import PluginManager, PluginPage
from .dropinstall import handle_dropped_paths
from .page_accounts import AccountsPage
from .page_bedrock import BedrockPage
from .page_browser import BrowserPage
from .page_content import ContentPage
from .page_control import ControlPage
from .page_crash import CrashReportPage
from .page_dependencies import DependenciesPage
from .page_download import DownloadPage
from .page_download_accel import DownloadAccelPage
from .page_download_center import DownloadCenterPage
from .page_forbric import ForbricPage
from .page_gallery import GalleryPage
from .page_modpack import ModpackPage
from .page_modgraph import ModGraphPage
from .page_home import HomePage
from .page_java_center import JavaCenterPage
from .page_loaders import LoadersPage
from .page_multiplayer import MultiplayerPage
from .page_seed_terrain import SeedTerrainPage
from .page_settings import SettingsPage
from .page_skin_factory import SkinFactoryPage
from .page_skin_pack import SkinPackPage
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
from .widgets import ask_skin_model, scroll_page

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

# 侧边栏导航板块：22 个磁贴平铺太杂乱，用标签切换只显示当前板块的磁贴。
# 这里的 key 必须覆盖全部导航项；未列出的 key（如插件页）统一归到「工具」板块。
NAV_GROUPS = (
    ("launch", "启动", ("home", "control")),
    ("download", "下载", ("download", "downloads", "download_accel", "modpack")),
    ("content", "内容", ("content", "loaders", "forbric", "deps", "modgraph")),
    ("online", "联机", ("account", "multiplayer", "bedrock", "browser")),
    (
        "tools",
        "工具",
        (
            "java",
            "wiki",
            "crash",
            "seed_terrain",
            "skin_factory",
            "skin_pack",
            "gallery",
        ),
    ),
    ("system", "设置", ("settings",)),
)


class _ClickLabel(QLabel):
    """可点击的标签：侧栏头像用它弹出「最近皮肤」菜单。"""

    clicked = Signal()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt 事件名
        if event.button() == Qt.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


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
        self.menu_button = self._make_button("☰", t("MainWindow", "Minecraft 菜单"))
        self.menu_button.setFixedSize(36, 30)
        self.menu_button.clicked.connect(lambda: window.show_game_menu(self.menu_button))
        layout.addWidget(self.menu_button)
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


class JvmPreloadWorker(QThread):
    done = Signal(bool, str)

    def __init__(self, java_path: str, parent=None):
        super().__init__(parent)
        self.java_path = java_path

    def run(self) -> None:
        _trace("thread: jvm preload start")
        ok, message = preload_jvm(self.java_path)
        _trace(f"thread: jvm preload done ({ok})")
        self.done.emit(ok, message)


class JavaScanWorker(QThread):
    done = Signal(list)

    def __init__(self, extra_paths: list[str] | None = None, parent=None):
        super().__init__(parent)
        self.extra_paths = list(extra_paths or [])

    def run(self) -> None:
        _trace("thread: java scan start")
        result = detect_java_installed(self.extra_paths)
        _trace(f"thread: java scan done ({len(result)})")
        self.done.emit(result)


class RootWidget(QWidget):
    """根容器：自定义背景图按窗口大小等比铺满并居中裁切，不会拉伸变形。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Root")
        self._source: QPixmap | None = None
        self._cache: QPixmap | None = None
        self._cache_size = QSize()
        self._movie: QMovie | None = None
        # 窗口底色（毛玻璃模式下带透明度）。必须用 Source 方式整块填充，
        # 否则半透明底色会与上一帧内容叠加：滚轮滚动 / 局部重绘时旧文字会残留成重影。
        self._base_color = QColor("#0c1310")

    def set_base_color(self, color: QColor) -> None:
        if color != self._base_color:
            self._base_color = color
            self.update()

    def _stop_movie(self) -> None:
        if self._movie is not None:
            self._movie.stop()
            self._movie = None

    def _on_movie_frame(self, _frame: int) -> None:
        if self._movie is not None:
            self._source = self._movie.currentPixmap()
            self._cache = None
            self._cache_size = QSize()
            self.update()

    def set_background(self, path: str) -> None:
        """支持静态图片与 GIF / WebP 动图；动图逐帧重绘并按窗口等比铺满。"""
        self._stop_movie()
        suffix = Path(path).suffix.lower() if path else ""
        if suffix in {".gif", ".webp"}:
            movie = QMovie(path)
            if movie.isValid():
                movie.setCacheMode(QMovie.CacheAll)
                movie.frameChanged.connect(self._on_movie_frame)
                self._movie = movie
                movie.start()
                self._source = movie.currentPixmap()
                self._cache = None
                self._cache_size = QSize()
                self.update()
                return
        pixmap = QPixmap(path) if path else QPixmap()
        self._source = None if pixmap.isNull() else pixmap
        self._cache = None
        self._cache_size = QSize()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        if self._source is None or self.width() <= 0 or self.height() <= 0:
            # Source 组合模式：直接用底色覆盖脏区，彻底清掉上一帧的残留像素
            painter.setCompositionMode(QPainter.CompositionMode_Source)
            painter.fillRect(event.rect(), self._base_color)
            return
        if self._cache is None or self._cache_size != self.size():
            self._cache = self._source.scaled(
                self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            self._cache_size = self.size()
        painter.drawPixmap(
            (self.width() - self._cache.width()) // 2,
            (self.height() - self._cache.height()) // 2,
            self._cache,
        )


class NetworkCheckWorker(QThread):
    """启动时探测能否访问版本清单/镜像源，用于离线能力自检。"""

    done = Signal(bool)

    def run(self) -> None:
        ok = False
        for host in ("launchermeta.mojang.com", "bmclapi2.bangbang93.com"):
            try:
                with socket.create_connection((host, 443), timeout=4):
                    ok = True
                    break
            except OSError:
                continue
        self.done.emit(ok)


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        set_default_download_workers(ctx.config.download_threads)
        set_download_speed_limit(ctx.config.download_speed_limit)
        self._java_worker: JavaScanWorker | None = None
        self._preload_worker: JvmPreloadWorker | None = None
        self._preload_started = False
        # 上一次应用外观时的（背景图, 毛玻璃）组合；没变化就不再重复刷全窗口样式
        self._appearance_state: tuple[str, bool, int] | None = None
        self._applied_stylesheet = ""
        self._plugin_pages: dict[int, QWidget] = {}
        self.plugin_manager: PluginManager | None = None
        # 页面跳转历史：右下角下载悬浮按钮右键回到上一页
        self._nav_history: list[str] = []
        self._current_nav_key = ""
        self._nav_skip_record = False
        self.setWindowTitle(f"{APP_NAME} · {self.tr('Minecraft 启动器')}")
        _trace("mw: after setWindowTitle")
        self.setWindowIcon(make_block_icon(64))
        _trace("mw: after setWindowIcon")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        # 必须在窗口创建（show）之前设置：运行中再切换该属性需要重建原生窗口，
        # 这也是旧版毛玻璃“开启后不生效 / 文字发虚”的根因。关闭毛玻璃时由根容器
        # 绘制不透明底色，效果与不透明窗口一致。
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAcceptDrops(True)
        _trace("mw: after flags/attrs")
        self._apply_default_geometry()
        _trace("mw: after geometry")

        self._build()
        _trace("mw: after _build")
        self._avatar_covers = CoverLoader(self)
        _trace("mw: after CoverLoader")
        self._connect_bus()
        _trace("mw: after _connect_bus")
        self._load_plugins()
        _trace("mw: after _load_plugins")
        self._apply_appearance()
        _trace("mw: after _apply_appearance")
        self._start_java_scan()
        _trace("mw: after _start_java_scan")
        self._setup_tray()
        _trace("mw: after _setup_tray")
        self._network_worker: NetworkCheckWorker | None = None
        QTimer.singleShot(1200, self._start_network_check)

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
        self.title_bar.max_button.setText("▣" if self.isMaximized() else "□")

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
        _trace("build: after central widget")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.title_bar = TitleBar(self)
        outer.addWidget(self.title_bar)
        _trace("build: after titlebar")

        body = QWidget()
        outer.addWidget(body, 1)
        layout = QHBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        # 图标栏模式：侧栏收窄，默认只显示图标，悬停用 ToolTip 显示功能名
        sidebar.setFixedWidth(84)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(8, 16, 8, 12)
        side.setSpacing(8)

        logo_row = QVBoxLayout()
        logo_row.setSpacing(0)
        logo = QLabel()
        logo.setPixmap(make_block_icon(40).pixmap(40, 40))
        logo_row.addWidget(logo, 0, Qt.AlignHCenter)
        # 保留标题控件但默认隐藏，避免其它逻辑按对象名查找时缺失
        title = QLabel(APP_NAME)
        title.setObjectName("LogoTitle")
        title.setVisible(False)
        sub = QLabel("MINECRAFT LAUNCHER")
        sub.setObjectName("LogoSub")
        sub.setVisible(False)
        logo_row.addWidget(title)
        logo_row.addWidget(sub)
        side.addLayout(logo_row)
        side.addSpacing(10)
        _trace("build: after logo")

        self.nav_group = QButtonGroup(self)
        self.nav_buttons: list[QPushButton] = []
        self.nav_keys: list[str] = []
        nav_items = [
            ("home", self.tr("启动游戏"), self.tr("启动")),
            ("download", self.tr("下载安装"), self.tr("下载")),
            ("downloads", self.tr("下载中心"), self.tr("任务")),
            ("download_accel", self.tr("下载加速"), self.tr("加速")),
            ("content", self.tr("内容中心"), self.tr("内容")),
            ("modpack", self.tr("整合包"), self.tr("整合包")),
            ("account", self.tr("账号管理"), self.tr("账号")),
            ("control", self.tr("版本设置"), self.tr("版本")),
            # theme.py 的 make_nav_icon 没有 "loaders" 分支，走默认图标（不要改 theme.py）
            ("loaders", self.tr("Mod 加载器"), self.tr("加载器")),
            # theme.py 的 make_nav_icon 没有 "multiplayer" 分支，走默认图标（不要改 theme.py）
            ("multiplayer", self.tr("多人联机"), self.tr("联机")),
            ("browser", self.tr("内置浏览器"), self.tr("浏览器")),
            # theme.py 的 make_nav_icon 没有 "forbric" 分支，走默认图标（不要改 theme.py）
            ("forbric", self.tr("Forbric"), "Forbric"),
            ("java", self.tr("Java 中心"), "Java"),
            ("deps", self.tr("依赖补全"), self.tr("依赖")),
            ("modgraph", self.tr("Mod 关系网"), self.tr("关系网")),
            ("wiki", self.tr("教程中心"), self.tr("教程")),
            ("bedrock", self.tr("基岩版"), self.tr("基岩版")),
            ("skin_factory", self.tr("皮肤工厂"), self.tr("皮肤厂")),
            ("skin_pack", self.tr("皮肤包"), self.tr("皮肤包")),
            ("seed_terrain", self.tr("世界种子"), self.tr("种子")),
            ("gallery", self.tr("截图图库"), self.tr("截图")),
            ("crash", self.tr("崩溃报告"), self.tr("崩溃")),
            ("settings", self.tr("设置"), self.tr("设置")),
        ]
        # 功能开关：被关闭的标签页不创建页面也不显示导航；设置页始终保留（否则无法再开回来）
        cfg = self.ctx.config
        nav_items = [
            (key, text, short)
            for key, text, short in nav_items
            if key == "settings" or cfg.feature_enabled(key)
        ]
        nav_host = QWidget()
        nav_host.setStyleSheet("background: transparent;")
        nav_layout = QVBoxLayout(nav_host)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(6)
        self.nav_layout = nav_layout

        # 导航改成单列竖排：3 列磁贴 + 横向板块标签会把「设置」等标签挤出 244px 侧栏。
        # 按钮创建顺序仍是 nav_items 顺序（页面索引依赖它），只把按钮插进对应板块的布局。
        self.nav_group_layouts: dict[str, QVBoxLayout] = {}
        self.nav_group_titles: dict[str, QLabel] = {}
        group_of = {
            key: group_key for group_key, _label, keys in NAV_GROUPS for key in keys
        }
        for group_key, label, _group_keys in NAV_GROUPS:
            title = QLabel(self.tr(label))
            title.setObjectName("NavGroupLabel")
            title.setAlignment(Qt.AlignHCenter)
            nav_layout.addWidget(title)
            group_layout = QVBoxLayout()
            group_layout.setContentsMargins(0, 0, 0, 4)
            group_layout.setSpacing(4)
            nav_layout.addLayout(group_layout)
            self.nav_group_titles[group_key] = title
            self.nav_group_layouts[group_key] = group_layout

        for index, (key, text, short) in enumerate(nav_items):
            button = QToolButton()
            button.setObjectName("NavTileRow")
            button.setText(text)
            button.setToolTip(text)
            button.setCheckable(True)
            # 只显示图标；鼠标停留时由 ToolTip 显示功能名
            button.setToolButtonStyle(Qt.ToolButtonIconOnly)
            button.setFixedSize(48, 48)
            button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            button.setCursor(Qt.PointingHandCursor)
            # 记录导航 key，供 _navigate_by_name 反查页码（避免手写数字映射错位）
            button._nav_key = key  # type: ignore[attr-defined]
            button.setIcon(make_nav_icon(key, 22, "#9fb6a7"))
            button.setIconSize(QSize(22, 22))
            button.clicked.connect(lambda checked=False, i=index: self.switch_page(i))
            self.nav_group.addButton(button, index)
            group_key = group_of.get(key, "tools")
            button._nav_group = group_key  # type: ignore[attr-defined]
            self.nav_group_layouts[group_key].addWidget(button, 0, Qt.AlignHCenter)
            self.nav_buttons.append(button)
            self.nav_keys.append(key)
        # 功能开关关闭后可能整组为空：连板块小标题一起隐藏
        for group_key, group_layout in self.nav_group_layouts.items():
            if group_layout.count() == 0:
                self.nav_group_titles[group_key].setVisible(False)
        nav_layout.addStretch(1)
        self.nav_buttons[0].setChecked(True)
        self._show_nav_group(getattr(self.nav_buttons[0], "_nav_group", "launch"))
        _trace(f"build: after nav rows ({len(self.nav_buttons)})")

        # 侧边栏导航放进滚动容器：窗口变矮时用滚轮上下滑动，而不是把按钮压扁丢失文字
        self.nav_scroll = nav_scroll = QScrollArea()
        nav_scroll.setObjectName("SidebarScroll")
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setFrameShape(QFrame.NoFrame)
        nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # 侧边栏滚动区底色由 theme.py 的 QScrollArea#SidebarScroll 规则统一控制
        nav_scroll.viewport().setAttribute(Qt.WA_OpaquePaintEvent, False)
        nav_scroll.viewport().setAttribute(Qt.WA_StyledBackground, True)
        nav_scroll.setWidget(nav_host)
        side.addWidget(nav_scroll, 1)
        _trace("build: after nav scroll")

        self.offline_banner = QLabel(
            self.tr("当前无网络\n只能启动已安装版本，联网功能已置灰")
        )
        self.offline_banner.setObjectName("OfflineBanner")
        self.offline_banner.setWordWrap(True)
        self.offline_banner.setVisible(False)
        side.addWidget(self.offline_banner)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background-color: #1b2920; border: none;")
        side.addWidget(divider)

        mini = QVBoxLayout()
        mini.setSpacing(4)
        self.sidebar_avatar = _ClickLabel()
        self.sidebar_avatar.setCursor(Qt.PointingHandCursor)
        self.sidebar_avatar.setToolTip(self.tr("点击快速切换皮肤"))
        self.sidebar_avatar.clicked.connect(self._show_skin_menu)
        self.sidebar_avatar.setPixmap(make_avatar("Steve", 38))
        mini.addWidget(self.sidebar_avatar, 0, Qt.AlignHCenter)
        # 账号文字保留但隐藏，保证其它更新逻辑仍可写入
        self.sidebar_account = QLabel(self.tr("离线模式"))
        self.sidebar_account.setStyleSheet("font-size: 12px; font-weight: 600; color: #cfe3d5;")
        self.sidebar_account.setVisible(False)
        self.sidebar_mode = QLabel(t("MainWindow", "v{0} · 正版 / 外置登录", APP_VERSION))
        self.sidebar_mode.setObjectName("Tiny")
        self.sidebar_mode.setVisible(False)
        mini.addWidget(self.sidebar_account)
        mini.addWidget(self.sidebar_mode)
        side.addLayout(mini)
        layout.addWidget(sidebar)
        _trace("build: after sidebar")

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
        self.download_accel_page = (
            DownloadAccelPage(self.ctx, self) if _on("download_accel") else None
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
        self.dependencies_page = DependenciesPage(self.ctx, self) if _on("deps") else None
        self.modgraph_page = ModGraphPage(self.ctx, self) if _on("modgraph") else None
        self.wiki_page = WikiPage(self.ctx, self) if _on("wiki") else None
        self.bedrock_page = BedrockPage(self.ctx, self) if _on("bedrock") else None
        self.skin_factory_page = SkinFactoryPage(self.ctx, self) if _on("skin_factory") else None
        self.skin_pack_page = SkinPackPage(self.ctx, self) if _on("skin_pack") else None
        self.seed_terrain_page = SeedTerrainPage(self.ctx, self) if _on("seed_terrain") else None
        self.gallery_page = GalleryPage(self.ctx, self) if _on("gallery") else None
        self.crash_page = CrashReportPage(self.ctx, self) if _on("crash") else None
        _trace("build: before settings page")
        self.settings_page = SettingsPage(self.ctx, self)
        _trace("build: after pages created")
        page_seq = (
            ("home", self.home_page),
            ("download", self.download_page),
            ("downloads", self.download_center_page),
            ("download_accel", self.download_accel_page),
            ("content", self.content_page),
            ("modpack", self.modpack_page),
            ("account", self.accounts_page),
            ("control", self.control_page),
            ("loaders", self.loaders_page),
            ("multiplayer", self.multiplayer_page),
            ("browser", self.browser_page),
            ("forbric", self.forbric_page),
            ("java", self.java_center_page),
            ("deps", self.dependencies_page),
            ("modgraph", self.modgraph_page),
            ("wiki", self.wiki_page),
            ("bedrock", self.bedrock_page),
            ("skin_factory", self.skin_factory_page),
            ("skin_pack", self.skin_pack_page),
            ("seed_terrain", self.seed_terrain_page),
            ("gallery", self.gallery_page),
            ("crash", self.crash_page),
            ("settings", self.settings_page),
        )
        # 切页时的刷新回调按 key 查找：页面可被开关隐藏后，页码不再固定，不能再用硬编码数字
        self._refresh_by_key: dict[str, object] = {}
        for key, page in page_seq:
            if page is None:
                continue
            # 浏览器页内含 WebEngine 视图、关系网页是自绘大画布，都不能塞进滚动容器
            self.pages.addWidget(
                page
                if page is self.browser_page or page is self.modgraph_page
                else scroll_page(page)
            )
            _trace(f"build: page added {key}")
        _trace("build: after pages added")
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
            ("deps", self.dependencies_page, "refresh"),
            ("modgraph", self.modgraph_page, "refresh"),
            ("wiki", self.wiki_page, "refresh"),
            ("bedrock", self.bedrock_page, "refresh"),
            ("skin_factory", self.skin_factory_page, None),
            ("skin_pack", self.skin_pack_page, "refresh"),
            ("seed_terrain", self.seed_terrain_page, None),
            ("gallery", self.gallery_page, "refresh"),
            ("crash", self.crash_page, "refresh"),
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

        # 右下角圆形下载悬浮按钮：只有存在下载任务时才显示
        self.download_fab = QPushButton("↓", root)
        self.download_fab.setObjectName("DownloadFab")
        self.download_fab.setFixedSize(52, 52)
        self.download_fab.setCursor(Qt.PointingHandCursor)
        self.download_fab.setToolTip(
            self.tr("有下载任务进行中 · 左键前往下载中心，右键返回上一页")
        )
        self.download_fab.setVisible(False)
        self.download_fab.clicked.connect(lambda: self._navigate_by_name("downloads"))
        self.download_fab.setContextMenuPolicy(Qt.CustomContextMenu)
        self.download_fab.customContextMenuRequested.connect(
            lambda _pos: self._back_to_previous_page()
        )
        self._refresh_sidebar_account()
        _trace("build: done")

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
        self.ctx.downloads.changed.connect(self._update_download_fab)
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
                self._show_nav_group(getattr(button, "_nav_group", ""))
                return

    # ------------------------------------------------------------------
    # 离线自检
    _NETWORK_KEYS = {
        "download",
        "download_accel",
        "content",
        "modpack",
        "java",
        "deps",
        "browser",
        "multiplayer",
        "bedrock",
    }

    def _start_network_check(self) -> None:
        worker = NetworkCheckWorker(self)
        self._network_worker = worker
        worker.done.connect(self._on_network_checked)
        worker.start()

    def _on_network_checked(self, online: bool) -> None:
        self.ctx.online = bool(online)
        self.offline_banner.setVisible(not online)
        for button, key in zip(self.nav_buttons, self.nav_keys):
            if key in self._NETWORK_KEYS:
                button.setEnabled(online)
                if not online:
                    button.setToolTip(self.tr("当前无网络，联网功能已暂时置灰"))
        if not online:
            self.statusBar().showMessage(
                self.tr("当前无网络：只能启动已安装版本，联网功能已置灰。"), 15000
            )

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
        button = QToolButton()
        button.setObjectName("NavTileRow")
        button.setText(page.title)
        button.setToolTip(page.title)
        button.setCheckable(True)
        button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        button.setFixedHeight(40)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        button.setCursor(Qt.PointingHandCursor)
        button.setIcon(make_nav_icon("content", 20, "#9fb6a7"))
        button.setIconSize(QSize(20, 20))
        button.clicked.connect(lambda checked=False, i=index: self.switch_page(i))
        self.nav_group.addButton(button, index)
        group_key = "tools"
        button._nav_group = group_key  # type: ignore[attr-defined]
        self.nav_group_layouts[group_key].addWidget(button)
        self.nav_buttons.append(button)
        self.nav_keys.append("plugin")
        self._plugin_pages[index] = page.widget

    # ------------------------------------------------------------------
    # 外观
    def _apply_appearance(self) -> None:
        image = (self.ctx.config.background_image or "").strip()
        dynamic = (self.ctx.config.dynamic_wallpaper or "").strip()
        # 动态壁纸优先：GIF / WebP 由 QMovie 逐帧播放；视频壁纸只在美化版可用
        if dynamic and Path(dynamic).is_file() and Path(dynamic).suffix.lower() in {".gif", ".webp"}:
            image = dynamic
        has_image = bool(image) and Path(image).exists()
        acrylic = bool(self.ctx.config.ui_acrylic)
        strength = max(0, min(100, int(getattr(self.ctx.config, "glass_strength", 62) or 0)))
        # 启动/切换配置时都会调用本方法：状态没变就直接返回，避免对整个窗口做全量重排样式
        state = (image if has_image else "", acrylic, strength if acrylic else 0)
        if state == self._appearance_state:
            return
        self._appearance_state = state
        self.root.set_background(image if has_image else "")
        stylesheet = background_overlay_stylesheet(has_image)
        if acrylic:
            stylesheet += acrylic_stylesheet()
        # 滚动区 / 堆叠页的底色统一由 theme.py 的应用级样式表控制，
        # 这里只保留一层窗口级覆盖（无背景图且无毛玻璃时为空字符串）。
        # setStyleSheet 会触发整棵控件树重新计算样式，内容没变就不要重复调用。
        if stylesheet != self._applied_stylesheet:
            self._applied_stylesheet = stylesheet
            self.setStyleSheet(stylesheet)
        self._apply_acrylic()

    def _apply_acrylic(self) -> None:
        """开启 / 关闭毛玻璃。

        Windows 11 走 DWM 系统亚克力（DWMWA_SYSTEMBACKDROP_TYPE = 3）：模糊发生在
        窗口背后的合成层，窗口内文字仍正常由 GPU 合成，不会像旧版 Accent 那样发虚。
        Windows 10 回退到 Accent BlurBehind（3），而不是 AcrylicBlurBehind（4）——
        后者在 Win10 上掉帧且明显糊字。
        """
        enabled = bool(self.ctx.config.ui_acrylic)
        strength = max(0, min(100, int(getattr(self.ctx.config, "glass_strength", 62) or 62)))
        # 强度决定染色深浅：0 近乎全透明，100 才接近实心；默认 62 仍能看到桌面
        alpha = max(12, min(150, 12 + int(strength * 0.9)))
        self.root.set_base_color(
            QColor(12, 19, 16, alpha) if enabled else QColor("#0c1310")
        )
        if sys.platform != "win32":
            return
        try:
            hwnd = int(self.winId())
        except Exception:
            return
        if enabled:
            if not self._set_win11_backdrop(hwnd, 3):
                self._set_legacy_accent(hwnd, 3, strength)
        else:
            self._set_win11_backdrop(hwnd, 1)
            self._set_legacy_accent(hwnd, 0, strength)

    @staticmethod
    def _set_win11_backdrop(hwnd: int, value: int) -> bool:
        """DWMWA_SYSTEMBACKDROP_TYPE：0 自动 / 1 无 / 2 Mica / 3 亚克力 / 4 云母。"""
        try:
            data = ctypes.c_int(value)
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.wintypes.HWND(hwnd), 38, ctypes.byref(data), ctypes.sizeof(data)
            )
            if value == 3:
                dark = ctypes.c_int(1)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    ctypes.wintypes.HWND(hwnd), 20, ctypes.byref(dark), ctypes.sizeof(dark)
                )
            return result == 0
        except Exception:
            return False

    @staticmethod
    def _set_legacy_accent(hwnd: int, state: int, strength: int = 62) -> None:
        """Win10 回退方案：SetWindowCompositionAttribute，强度控制染色浓度。"""
        try:
            # 0xAABBGGRR，与主题底色 #0c1310 同色调，低 alpha 让 DWM 模糊透出
            alpha = max(6, min(90, 6 + int(strength * 0.45)))

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

            policy = AccentPolicy(state, 0, gradient_color, 0)
            data = WindowCompositionAttributeData(
                19, ctypes.byref(policy), ctypes.sizeof(policy)
            )
            ctypes.windll.user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data))
        except Exception:
            # 不支持的系统静默回退到半透明深色背景
            pass

    def _on_page_changed(self, index: int) -> None:
        """页面切换动画。

        注意：不要给 QScrollArea 加 QGraphicsOpacityEffect。那会把整页离屏栅格化，
        既造成明显卡顿，也会让文字重新采样后发虚；毛玻璃模式下尤其严重。
        """

    def _clear_page_effect(self, widget: QWidget) -> None:
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

    def show_game_menu(self, anchor: QWidget) -> None:
        """标题栏的 Minecraft 风格菜单：沿用游戏内的菜单命名。"""
        menu = QMenu(self)
        entries = (
            (self.tr("单人游戏（存档管理）"), "control"),
            (self.tr("多人游戏（服务器列表）"), "multiplayer"),
            (self.tr("资源包 / 光影包"), "control"),
            (self.tr("截图图库"), "gallery"),
            (self.tr("崩溃报告"), "crash"),
            (self.tr("选项…（设置）"), "settings"),
            (self.tr("Java 与运行环境"), "java"),
        )
        for label, key in entries:
            action = menu.addAction(label)
            action.triggered.connect(lambda _checked=False, k=key: self._navigate_by_name(k))
        menu.addSeparator()
        quit_action = menu.addAction(self.tr("退出启动器"))
        quit_action.triggered.connect(self.close)
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

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

    # ---------- 皮肤快速切换 ----------
    def _show_skin_menu(self) -> None:
        """点击侧栏头像：列出最近用过的皮肤，一键切换。"""
        menu = QMenu(self)
        items = skins.entries(limit=8)
        account = self.ctx.current_account()
        current = Path(account.skin_path) if account and account.skin_path else None
        if items:
            for entry in items:
                pix = QPixmap(entry.path)
                icon = QIcon(make_skin_avatar(pix, 22)) if not pix.isNull() else QIcon()
                label = entry.name or Path(entry.path).stem
                if Path(entry.path) == current:
                    label = f"✓ {label}"
                action = menu.addAction(icon, label)
                action.triggered.connect(
                    lambda _checked=False, e=entry: self._apply_skin_entry(e)
                )
        else:
            menu.addAction(self.tr("还没有历史皮肤")).setEnabled(False)
        menu.addSeparator()
        menu.addAction(self.tr("导入新皮肤…"), self._import_skin_from_menu)
        menu.addAction(
            self.tr("打开皮肤库"),
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(skins.LIBRARY_DIR))
            ),
        )
        menu.exec(self.sidebar_avatar.mapToGlobal(self.sidebar_avatar.rect().bottomLeft()))

    def _apply_skin_entry(self, entry: skins.SkinEntry) -> None:
        account = self.ctx.current_account()
        if account is None:
            return
        skin_dir = DATA_DIR / "skins"
        skin_dir.mkdir(parents=True, exist_ok=True)
        target = skin_dir / f"{account.name}.png"
        try:
            shutil.copy2(entry.path, target)
        except OSError as exc:
            QMessageBox.warning(self, APP_NAME, f"应用皮肤失败：{exc}")
            return
        account.skin_path = str(target)
        account.skin_model = entry.model or "classic"
        self.ctx.accounts.update(account)
        skins.touch(entry)
        self.ctx.bus.accounts_changed.emit()
        applied = self._apply_skin_to_versions(account)
        if applied:
            self.ctx.bus.toast.emit(
                f"已切换到皮肤「{entry.name or Path(entry.path).stem}」，并适配 {applied} 个游戏目录"
            )
        else:
            self.ctx.bus.toast.emit(f"已切换到皮肤「{entry.name or Path(entry.path).stem}」")

    def _apply_skin_to_versions(self, account) -> int:
        """自动检测已安装版本，把当前皮肤覆盖式写入每个版本的隔离目录。

        直接使用 skinpack 写入（不再依赖 import_offline_skin），这样正版 / 外置
        登录账号也能生效，并按各版本 pack_format 与 1.19.4+ 的 9 套默认皮肤名
        生成能真正命中的资源包。
        """
        from ..skinpack import SkinPackError, apply_player_skin_bytes, purge_old_packs
        from ..version import scan_installed_versions

        skin_path = str(getattr(account, "skin_path", "") or "")
        if not skin_path or not Path(skin_path).is_file():
            return 0
        try:
            image = Path(skin_path).read_bytes()
        except OSError:
            return 0
        try:
            installed = scan_installed_versions(self.ctx.config.game_path)
        except OSError:
            return 0
        model = getattr(account, "skin_model", "") or "classic"
        applied = 0
        for item in installed:
            try:
                targets = self.ctx.config.resolve_game_dirs(item.id).skin_targets()
            except Exception:  # noqa: BLE001
                targets = [self.ctx.config.game_path]
            for game_dir in targets:
                try:
                    purge_old_packs(Path(game_dir))
                    apply_player_skin_bytes(
                        image,
                        account.name,
                        model,
                        Path(game_dir),
                        item.id,
                        install_pack=True,
                        enable_pack=True,
                    )
                    applied += 1
                except (SkinPackError, OSError):  # 单个版本失败不影响其它版本
                    continue
        return applied

    def _import_skin_from_menu(self) -> None:
        account = self.ctx.current_account()
        if account is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("选择本地皮肤"), str(Path.home()), "PNG 图片 (*.png)"
        )
        if not path:
            return
        try:
            validate_skin_file(path)
        except (AuthError, OSError) as exc:
            QMessageBox.warning(self, APP_NAME, f"读取皮肤失败：{exc}")
            return
        model = ask_skin_model(self, account.skin_model or "classic")
        if model is None:
            return
        self._apply_skin_entry(skins.remember(path, model))

    # ---------- 侧边栏板块 ----------
    def _show_nav_group(self, group_key: str) -> None:
        """把侧边栏滚动到指定板块（单列竖排导航，只影响显示不改页面）。"""
        title = getattr(self, "nav_group_titles", {}).get(group_key)
        scroll = getattr(self, "nav_scroll", None)
        if title is None or scroll is None or not title.isVisible():
            return
        scroll.ensureWidgetVisible(title, 0, 16)

    def _show_nav_group_for_key(self, nav_key: str) -> None:
        """按页面 key 自动切到对应板块（跳转后用户能看到当前磁贴）。"""
        for button in self.nav_buttons:
            if getattr(button, "_nav_key", "") == nav_key:
                self._show_nav_group(getattr(button, "_nav_group", ""))
                return

    def switch_page(self, index: int) -> None:
        if not (0 <= index < self.pages.count()):
            return
        changed = index != self.pages.currentIndex()
        self.pages.setCurrentIndex(index)
        self.nav_buttons[index].setChecked(True)
        self._show_nav_group(getattr(self.nav_buttons[index], "_nav_group", ""))
        # 页面可被功能开关隐藏，页码不固定：按导航 key 找刷新回调
        key = getattr(self.nav_buttons[index], "_nav_key", "")
        if key != self._current_nav_key and not self._nav_skip_record:
            if self._current_nav_key:
                self._nav_history.append(self._current_nav_key)
                del self._nav_history[:-20]
        self._current_nav_key = key
        # 重复点击当前磁贴不重复刷新；真正切页时把刷新延后到事件循环空闲，
        # 先让页面完成一次绘制，避免磁盘扫描 / 网络请求阻塞切换动画
        if not changed:
            return
        refresh = self._refresh_by_key.get(key)
        if callable(refresh):
            QTimer.singleShot(0, refresh)
        elif index in self._plugin_pages:
            # 插件页可选提供 refresh() 方法，切页时自动调用
            plugin_refresh = getattr(self._plugin_pages[index], "refresh", None)
            if callable(plugin_refresh):
                QTimer.singleShot(0, plugin_refresh)

    # ---------- 下载悬浮按钮 ----------
    def _update_download_fab(self) -> None:
        if not hasattr(self, "download_fab"):
            return
        active = any(task.active for task in self.ctx.downloads.tasks())
        if active and not self.download_fab.isVisible():
            self.download_fab.setVisible(True)
            self._place_download_fab()
            self.download_fab.raise_()
        elif not active and self.download_fab.isVisible():
            self.download_fab.setVisible(False)

    def _place_download_fab(self) -> None:
        if not hasattr(self, "download_fab"):
            return
        fab = self.download_fab
        root = self.root
        fab.move(
            max(0, root.width() - fab.width() - 24),
            max(0, root.height() - fab.height() - 24),
        )

    def _back_to_previous_page(self) -> None:
        """悬浮按钮右键：回到进入当前页之前的那一页。"""
        while self._nav_history:
            key = self._nav_history.pop()
            if key and key != self._current_nav_key:
                # switch_page 会把当前页再压入历史，这次回退要跳过记录，否则会来回跳
                self._nav_skip_record = True
                try:
                    self._navigate_by_name(key)
                finally:
                    self._nav_skip_record = False
                return

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._place_download_fab()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._place_download_fab()
        self._update_download_fab()

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
        self._java_worker = JavaScanWorker(self.ctx.config.java_scan_paths(), self)
        self._java_worker.done.connect(self._on_java_scanned)
        self._java_worker.finished.connect(self._release_java_worker)
        self._java_worker.start()

    def _release_java_worker(self) -> None:
        """run() 结束后再释放线程对象，避免在 done 信号里析构仍在运行的 QThread。"""
        self._java_worker = None

    def _on_java_scanned(self, javas: list) -> None:
        merged = merge_java_lists(self.ctx.javas, javas)
        self.ctx.javas = merged
        self.ctx.config.remember_java_paths(java.path for java in merged)
        self.ctx.bus.javas_changed.emit()
        if not merged:
            self.statusBar().showMessage("未检测到 Java，请到设置页手动指定 Java 路径。", 8000)
        else:
            self.statusBar().showMessage(f"已检测到 {len(merged)} 个 Java 运行时。", 5000)
            self._start_jvm_preload(merged)

    def _start_jvm_preload(self, javas: list) -> None:
        """实验性 JVM 预加载：每次启动启动器只预热一次，全部在后台线程执行。"""
        if not self.ctx.config.preload_jvm or self._preload_started or not javas:
            return
        preferred = self.ctx.config.preload_java_path
        target = None
        if preferred:
            key = os.path.normcase(os.path.normpath(preferred))
            target = next(
                (j for j in javas if os.path.normcase(os.path.normpath(j.path)) == key), None
            )
        if target is None:
            target = javas[0]
        self._preload_started = True
        self._preload_worker = JvmPreloadWorker(target.path, self)
        self._preload_worker.done.connect(self._on_jvm_preloaded)
        self._preload_worker.finished.connect(self._release_preload_worker)
        self._preload_worker.start()
        self.ctx.bus.log.emit(f"[预加载] 正在预热 Java {target.major}：{target.path}")

    def _release_preload_worker(self) -> None:
        """run() 结束后再释放线程对象，避免在 done 信号里析构仍在运行的 QThread。"""
        self._preload_worker = None

    def _on_jvm_preloaded(self, ok: bool, message: str) -> None:
        if ok:
            self.ctx.bus.log.emit("[预加载] JVM 预热完成，后续启动游戏可更快进入")
        else:
            self.ctx.bus.log.emit(f"[预加载] JVM 预热失败：{message}")

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
        active = self._active_download_count()
        if active > 0:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Question)
            box.setWindowTitle(self.tr("正在下载"))
            box.setText(
                self.tr(
                    "还有 {0} 个下载 / 安装任务未完成。\n"
                    "直接关闭会立即中断它们（已完成的文件会保留，下次可继续下载）。"
                ).format(active)
            )
            close_button = box.addButton(self.tr("关闭（中断下载）"), QMessageBox.AcceptRole)
            cancel_button = box.addButton(self.tr("手滑了"), QMessageBox.RejectRole)
            box.setDefaultButton(cancel_button)
            box.exec()
            if box.clickedButton() is not cancel_button:
                self._fast_quit()
            event.ignore()
            return
        self._fast_quit()
        event.ignore()

    # ------------------------------------------------------------------
    def _active_download_count(self) -> int:
        try:
            return int(self.ctx.downloads.active_count)
        except Exception:  # noqa: BLE001 - 关闭流程不允许再抛异常
            return 0

    def _fast_quit(self) -> None:
        """直接截断进程：不等待线程池 / 页面析构，保存配置后立即退出。"""
        self._force_quit = True
        try:
            self.ctx.config.save()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.tray.hide()
        except Exception:  # noqa: BLE001
            pass
        # 跳过 QApplication 的慢速析构（QtWebEngine / 线程池等待可能耗时数秒）
        os._exit(0)
