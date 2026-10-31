"""内置浏览器页：多标签访问 Minecraft Wiki、MC 百科与 Bilibili。

默认使用系统自带的 Edge WebView2 内核（完整 Chromium，自带 H.264/AAC），B 站等
站点的视频可以在启动器里直接播放，不需要切到系统浏览器；只有系统缺失 WebView2
运行时的时候，才回退到 QtWebEngine 并提示「视频可能无法播放」。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices, QIcon, QKeySequence, QShortcut
from PySide6.QtWebEngineCore import (
    QWebEngineDownloadRequest,
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import BROWSER_DIR, DATA_DIR
from ..context import AppContext
from ..net import USER_AGENT
from .webview2 import WebView2View, webview2_available

QUICK_LINKS = [
    ("Minecraft Wiki", "https://zh.minecraft.wiki/"),
    ("MC 百科", "https://www.mcmod.cn/"),
    ("B 站 MC", "https://search.bilibili.com/all?keyword=我的世界"),
    ("Minecraft.net", "https://www.minecraft.net/zh-hans"),
]

START_HTML = """
<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>新标签页</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { color-scheme: dark; }
  body { margin:0; background:#0c1310; color:#e8f1ea; font-family:"Microsoft YaHei UI",system-ui,sans-serif; }
  .wrap { max-width:760px; margin:0 auto; padding:80px 32px; }
  h1 { font-size:30px; margin:0 0 8px; letter-spacing:1px; }
  p.sub { color:#8aa192; margin:0 0 40px; }
  .grid { display:grid; grid-template-columns:repeat(2,1fr); gap:14px; }
  a.card { display:block; padding:20px; border:1px solid #23352a; border-radius:14px;
           background:#121d16; color:#e8f1ea; text-decoration:none; transition:border-color .15s; }
  a.card:hover { border-color:#4f9a5f; background:#16241b; }
  .name { font-size:16px; font-weight:600; margin-bottom:6px; }
  .desc { font-size:12px; color:#8aa192; }
  .foot { margin-top:36px; font-size:12px; color:#62796c; }
</style></head><body>
<div class="wrap">
  <h1>MikanCL 内置浏览器</h1>
  <p class="sub">查 Wiki、看教程、逛 B 站，都无需切换到系统浏览器。</p>
  <div class="grid">
    <a class="card" href="https://zh.minecraft.wiki/"><div class="name">Minecraft 中文 Wiki</div>
      <div class="desc">方块、合成、机制与版本资料</div></a>
    <a class="card" href="https://www.mcmod.cn/"><div class="name">MC 百科</div>
      <div class="desc">模组、整合包与教程索引</div></a>
    <a class="card" href="https://search.bilibili.com/all?keyword=我的世界"><div class="name">哔哩哔哩</div>
      <div class="desc">实况、红石与模组视频</div></a>
    <a class="card" href="https://www.minecraft.net/zh-hans"><div class="name">Minecraft 官网</div>
      <div class="desc">新闻、正版账号与社区</div></a>
  </div>
  <div class="foot">提示：Ctrl+T 新建标签，Ctrl+W 关闭标签。</div>
</div>
</body></html>
"""

HOME_BASE = "https://mclite.local/"


class _QtPage(QWebEnginePage):
    """QtWebEngine 回退内核的页面：处理弹窗与视频全屏。"""

    def __init__(self, profile: QWebEngineProfile, host: "QtHost"):
        super().__init__(profile, host)
        self.host = host
        self.fullScreenRequested.connect(self._on_fullscreen)

    def createWindow(self, _window_type):  # noqa: N802
        browser = self.host.browser
        if browser is None:
            return None
        new_host = browser.add_tab(None)
        return new_host.view.page() if new_host is not None else None

    def _on_fullscreen(self, request) -> None:
        request.accept()
        self.host.fullscreenChanged.emit(bool(request.toggleOn()))


class QtHost(QWidget):
    """QtWebEngine 标签页（回退用），对外接口与 WebView2View 保持一致。"""

    titleChanged = Signal(str)
    urlChanged = Signal(str)
    loadProgress = Signal(int)
    loadFinished = Signal(bool)
    newWindowRequested = Signal(str)
    fullscreenChanged = Signal(bool)
    closeRequested = Signal()
    newTabShortcut = Signal()
    closeTabShortcut = Signal()
    failed = Signal(str)

    def __init__(self, browser: "BrowserPage", profile: QWebEngineProfile, parent=None):
        super().__init__(parent)
        self.browser = browser
        self._icon = QIcon()
        self.view = QWebEngineView(self)
        self.view.setPage(_QtPage(profile, self))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)

        settings = self.view.page().settings()
        # HTML5 媒体播放：允许脚本自动播放、支持视频全屏、允许播放器弹窗
        for attribute, value in (
            ("PlaybackRequiresUserGesture", False),
            ("FullScreenSupportEnabled", True),
            ("JavascriptCanOpenWindows", True),
            ("DarkMode", True),
        ):
            flag = getattr(QWebEngineSettings.WebAttribute, attribute, None)
            if flag is not None:
                settings.setAttribute(flag, value)

        self.view.titleChanged.connect(self.titleChanged.emit)
        self.view.urlChanged.connect(lambda url: self.urlChanged.emit(url.toString()))
        self.view.loadStarted.connect(lambda: self.loadProgress.emit(0))
        self.view.loadProgress.connect(self.loadProgress.emit)
        self.view.loadFinished.connect(self.loadFinished.emit)
        self.view.iconChanged.connect(self._on_icon)

    def _on_icon(self, icon: QIcon) -> None:
        if not icon.isNull():
            self._icon = icon

    def icon(self) -> QIcon:
        return self._icon

    def load(self, url: str) -> None:
        self.view.setUrl(QUrl(url))

    def set_html(self, html: str) -> None:
        self.view.setHtml(html, QUrl(HOME_BASE))

    def url(self) -> str:
        return self.view.url().toString()

    def title(self) -> str:
        return self.view.title()

    def back(self) -> None:
        self.view.back()

    def forward(self) -> None:
        self.view.forward()

    def reload(self) -> None:
        self.view.reload()

    def stop(self) -> None:
        self.view.stop()

    def focus_in(self) -> None:
        self.view.setFocus()

    def shutdown(self) -> None:
        self.view.stop()


class BrowserPage(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        # WebView2 可用就走 Chromium，视频可以直接播放；否则回退 QtWebEngine
        self.engine = "webview2" if webview2_available() else "qt"
        self.profile: QWebEngineProfile | None = None
        self._was_maximized = False
        # 用户手动收起 H.264 提示条后置为 True，下次页面变化时复位
        self._video_hint_dismissed = False
        self._build()
        self.add_tab(None)

    # ------------------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 10)
        outer.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self.back_button = self._tool_button("←", "后退", self._go_back)
        toolbar.addWidget(self.back_button)
        self.forward_button = self._tool_button("→", "前进", self._go_forward)
        toolbar.addWidget(self.forward_button)
        self.reload_button = self._tool_button("↻", "刷新", self._reload)
        toolbar.addWidget(self.reload_button)
        self.home_button = self._tool_button("⌂", "主页", self._go_home)
        toolbar.addWidget(self.home_button)

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("输入网址或搜索内容…")
        self.url_edit.returnPressed.connect(self._navigate)
        toolbar.addWidget(self.url_edit, 1)
        go_button = QPushButton("前往")
        go_button.clicked.connect(self._navigate)
        toolbar.addWidget(go_button)
        outer.addLayout(toolbar)

        quick_row = QHBoxLayout()
        quick_row.setSpacing(6)
        quick_label = QLabel("快捷访问")
        quick_label.setObjectName("Tiny")
        quick_row.addWidget(quick_label)
        for name, url in QUICK_LINKS:
            button = QPushButton(name)
            button.setObjectName("Chip")
            button.clicked.connect(lambda _=False, u=url: self.navigate_to(u))
            quick_row.addWidget(button)
        quick_row.addStretch(1)
        new_tab = QPushButton("＋ 新标签")
        new_tab.setObjectName("Chip")
        new_tab.clicked.connect(lambda: self.add_tab(None))
        quick_row.addWidget(new_tab)
        self.system_browser_button = QPushButton("🌐 系统浏览器")
        self.system_browser_button.setObjectName("Chip")
        self.system_browser_button.setToolTip("用系统默认浏览器打开当前页面")
        self.system_browser_button.clicked.connect(self._open_in_system_browser)
        quick_row.addWidget(self.system_browser_button)
        outer.addLayout(quick_row)

        # H.264 提示条：WebView2 内核自带解码器，这条提示只在回退内核里才可能出现
        self.video_hint_bar = QWidget()
        self.video_hint_bar.setObjectName("VideoHint")
        self.video_hint_bar.setStyleSheet(
            "QWidget#VideoHint { background: #241d10; border: 1px solid #6b5a2a;"
            " border-radius: 8px; }"
        )
        hint_layout = QHBoxLayout(self.video_hint_bar)
        hint_layout.setContentsMargins(10, 6, 8, 6)
        hint_layout.setSpacing(8)
        self.video_hint_label = QLabel("内置浏览器缺少 H.264 / AAC 解码器，视频可能无法播放。")
        hint_layout.addWidget(self.video_hint_label, 1)
        self.video_hint_button = QPushButton("用系统浏览器打开本页")
        self.video_hint_button.setObjectName("Chip")
        self.video_hint_button.clicked.connect(self._open_in_system_browser)
        hint_layout.addWidget(self.video_hint_button)
        self.video_hint_close = QPushButton("×")
        self.video_hint_close.setObjectName("Chip")
        self.video_hint_close.setFixedSize(28, 24)
        self.video_hint_close.setToolTip("知道了，先收起这条提示")
        self.video_hint_close.clicked.connect(self._dismiss_video_hint)
        hint_layout.addWidget(self.video_hint_close)
        self.video_hint_bar.setVisible(False)
        outer.addWidget(self.video_hint_bar)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        outer.addWidget(self.tabs, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedSize(160, 4)
        self.progress_bar.setVisible(False)
        footer.addWidget(self.progress_bar)
        self.status_url = QLabel("")
        self.status_url.setObjectName("Tiny")
        self.status_url.setStyleSheet("color: #6e8778;")
        footer.addWidget(self.status_url, 1)
        self.status_msg = QLabel("")
        self.status_msg.setObjectName("Tiny")
        footer.addWidget(self.status_msg)
        outer.addLayout(footer)

        # WebView2 自带解码器，「系统浏览器」按钮在这里属于多余操作，直接隐藏
        self.system_browser_button.setVisible(self.engine != "webview2")

        self._new_shortcut = QShortcut(QKeySequence("Ctrl+T"), self)
        self._new_shortcut.activated.connect(lambda: self.add_tab(None))
        self._close_shortcut = QShortcut(QKeySequence("Ctrl+W"), self)
        self._close_shortcut.activated.connect(
            lambda: self._close_tab(self.tabs.currentIndex())
        )

    def _ensure_profile(self) -> QWebEngineProfile:
        """回退内核的 profile 按需创建，避免走 WebView2 时白启一套 Chromium 进程。"""
        if self.profile is not None:
            return self.profile
        profile = QWebEngineProfile("MikanCL", self)
        storage = BROWSER_DIR / "storage"
        cache = BROWSER_DIR / "cache"
        storage.mkdir(parents=True, exist_ok=True)
        cache.mkdir(parents=True, exist_ok=True)
        profile.setPersistentStoragePath(str(storage))
        profile.setCachePath(str(cache))
        profile.setHttpUserAgent(USER_AGENT)
        profile.setSpellCheckEnabled(False)
        profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
        )
        profile.downloadRequested.connect(self._on_download)
        try:
            profile.cookieStore().loadAllCookies()
        except (AttributeError, RuntimeError):
            pass
        self.profile = profile
        return profile

    def _tool_button(self, text: str, tooltip: str, slot) -> QPushButton:
        button = QPushButton(text)
        button.setFixedSize(32, 32)
        button.setToolTip(tooltip)
        button.setStyleSheet("font-size: 16px; padding: 0;")
        button.clicked.connect(slot)
        return button

    # ------------------------------------------------------------------
    def add_tab(self, url: str | None = None, background: bool = False):
        if self.engine == "webview2":
            host = WebView2View(self)
            host.newTabShortcut.connect(lambda: self.add_tab(None))
            host.closeTabShortcut.connect(
                lambda h=host: self._close_tab(self.tabs.indexOf(h))
            )
            host.failed.connect(self._fallback_to_qt)
        else:
            host = QtHost(self, self._ensure_profile(), self)

        host.titleChanged.connect(lambda title, h=host: self._set_tab_title(h, title))
        host.urlChanged.connect(lambda url, h=host: self._on_url_changed(h, url))
        host.loadProgress.connect(lambda value, h=host: self._on_load_progress(h, value))
        host.loadFinished.connect(lambda ok, h=host: self._on_load_finished(h, ok))
        host.newWindowRequested.connect(self._on_new_window_requested)
        host.fullscreenChanged.connect(self._on_fullscreen_changed)
        host.closeRequested.connect(lambda h=host: self._close_tab(self.tabs.indexOf(h)))

        index = self.tabs.addTab(host, "新标签页")
        if url is None or url == "about:blank":
            host.set_html(START_HTML)
        else:
            host.load(url)
        self.tabs.setCurrentIndex(index)
        if background:
            self.tabs.setCurrentIndex(max(0, index - 1))
        return host

    def _dispose(self, host) -> None:
        host.shutdown()
        host.deleteLater()

    def _close_tab(self, index: int) -> None:
        if index < 0:
            return
        host = self.tabs.widget(index)
        self.tabs.removeTab(index)
        if host is not None:
            self._dispose(host)
        if self.tabs.count() == 0:
            self.add_tab(None)

    def _fallback_to_qt(self, message: str) -> None:
        """WebView2 起不来时整体切回 QtWebEngine，并把所有标签页重建一次。"""
        self.ctx.bus.log.emit(f"[浏览器] {message}")
        if self.engine != "webview2":
            return
        self.engine = "qt"
        self._ensure_profile()
        self.system_browser_button.setVisible(True)
        while self.tabs.count():
            host = self.tabs.widget(0)
            self.tabs.removeTab(0)
            if host is not None:
                self._dispose(host)
        self.add_tab(None)
        # 回退内核缺少 H.264 解码，直接把已有的提示条亮出来，不再额外弹窗打扰
        self.video_hint_bar.setVisible(True)

    def _on_new_window_requested(self, url: str) -> None:
        self.add_tab(url or None)

    def _on_fullscreen_changed(self, enter: bool) -> None:
        window = self.window()
        if window is None:
            return
        if enter:
            self._was_maximized = window.isMaximized()
            window.showFullScreen()
        elif self._was_maximized:
            window.showMaximized()
        else:
            window.showNormal()

    def _set_tab_title(self, host, title: str) -> None:
        index = self.tabs.indexOf(host)
        if index < 0:
            return
        label = title.strip() or "新标签页"
        if label.startswith("MikanCL"):
            label = "新标签页"
        self.tabs.setTabText(index, label[:24])
        self.tabs.setTabToolTip(index, title)
        icon = getattr(host, "icon", None)
        if callable(icon):
            icon = icon()
            if isinstance(icon, QIcon) and not icon.isNull():
                self.tabs.setTabIcon(index, icon)

    def _on_url_changed(self, host, url: str) -> None:
        if host is self.current_host():
            text = url or ""
            if text.startswith(HOME_BASE) or text in ("about:blank", "about:srcdoc"):
                text = ""
            if not self.url_edit.hasFocus():
                self.url_edit.setText(text)
            self.status_url.setText(text)

    def _on_tab_changed(self, _index: int) -> None:
        host = self.current_host()
        # 切走页面时先收起上一条提示，再按新页面重新探测
        self.video_hint_bar.setVisible(False)
        self._video_hint_dismissed = False
        if host is None:
            return
        self.url_edit.setText(self._display_url(host.url()))
        self.status_url.setText(self._display_url(host.url()))
        if isinstance(host, WebView2View):
            host.focus_in()
        else:
            self._probe_h264(host)

    @staticmethod
    def _display_url(url: str) -> str:
        if url.startswith(HOME_BASE) or url in ("about:blank", "about:srcdoc"):
            return ""
        return url

    def _on_load_progress(self, host, value: int) -> None:
        if host is self.current_host():
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(value)
            if value > 0:
                self.status_msg.setText("加载中…")

    def _on_load_finished(self, host, ok: bool) -> None:
        if host is not self.current_host():
            return
        self.progress_bar.setVisible(False)
        self.status_msg.setText("加载完成" if ok else "加载失败")
        if not isinstance(host, WebView2View):
            self._probe_h264(host)

    # ------------------------------------------------------------------
    def _probe_h264(self, host) -> None:
        """回退内核才需要探测：页面有 video 且内核不支持 H.264 时提示换系统浏览器。"""
        if not isinstance(host, QtHost):
            return
        script = """
        (function () {
            try {
                var probe = document.createElement('video');
                var support = probe.canPlayType('video/mp4; codecs="avc1.42E01E"');
                var count = document.querySelectorAll('video').length;
                return (!support && count > 0) ? 1 : 0;
            } catch (e) {
                return 0;
            }
        })();
        """
        host.view.page().runJavaScript(script, self._on_h264_probe)

    def _on_h264_probe(self, result) -> None:
        if result and not self._video_hint_dismissed and self.engine == "qt":
            self.video_hint_bar.setVisible(True)
        elif not result:
            self.video_hint_bar.setVisible(False)

    def _dismiss_video_hint(self) -> None:
        """手动收起提示条，直到下次页面切换或重新加载再重新判断。"""
        self._video_hint_dismissed = True
        self.video_hint_bar.setVisible(False)

    # ------------------------------------------------------------------
    def current_host(self):
        widget = self.tabs.currentWidget()
        return widget if isinstance(widget, (WebView2View, QtHost)) else None

    def _open_in_system_browser(self) -> None:
        host = self.current_host()
        url = host.url() if host is not None else ""
        if not url.startswith(("http://", "https://")):
            raw = self.url_edit.text().strip()
            if raw:
                url = self._clean_input(raw)
        if not url.startswith(("http://", "https://")):
            self.ctx.bus.toast.emit("当前没有可打开的网页地址")
            return
        QDesktopServices.openUrl(QUrl(url))
        self.ctx.bus.toast.emit("已用系统浏览器打开当前页面")

    def _navigate(self) -> None:
        host = self.current_host()
        if host is None:
            return
        host.load(self._clean_input(self.url_edit.text().strip()))
        host.focus_in()

    @staticmethod
    def _clean_input(raw: str) -> str:
        if not raw:
            return "https://zh.minecraft.wiki/"
        lower = raw.lower()
        if lower.startswith(("http://", "https://")):
            return raw
        if "." in raw and " " not in raw:
            return "https://" + raw
        from urllib.parse import quote_plus

        return f"https://search.bilibili.com/all?keyword={quote_plus(raw)}"

    def _go_back(self) -> None:
        host = self.current_host()
        if host:
            host.back()

    def _go_forward(self) -> None:
        host = self.current_host()
        if host:
            host.forward()

    def _reload(self) -> None:
        host = self.current_host()
        if host:
            host.reload()

    def _go_home(self) -> None:
        host = self.current_host()
        if host:
            host.set_html(START_HTML)
            self.url_edit.clear()

    def navigate_to(self, url: str) -> None:
        host = self.current_host()
        if host is None:
            self.add_tab(url)
        else:
            host.load(url)
        self.url_edit.setText(url)

    # ------------------------------------------------------------------
    def _on_download(self, item: QWebEngineDownloadRequest) -> None:
        downloads = Path.home() / "Downloads"
        if not downloads.is_dir():
            downloads = DATA_DIR / "downloads"
            downloads.mkdir(parents=True, exist_ok=True)
        name = item.suggestedFileName() or "download.bin"
        item.setDownloadDirectory(str(downloads))
        item.setDownloadFileName(name)
        item.accept()
        self.ctx.bus.log.emit(f"[浏览器] 正在下载 {name} 到 {downloads}")
        self.ctx.bus.toast.emit(f"已开始下载：{name}")

    def shutdown(self) -> None:
        # 退出前把内存中的 cookie 落盘，确保下次启动仍保持登录状态
        try:
            flush = getattr(self.profile.cookieStore(), "flushCookieStore", None) if self.profile else None
            if callable(flush):
                flush()
        except (AttributeError, RuntimeError):
            pass
        while self.tabs.count():
            host = self.tabs.widget(0)
            self.tabs.removeTab(0)
            if host is not None:
                self._dispose(host)
