"""内置浏览器页：多标签访问 Minecraft Wiki、MC 百科与 Bilibili。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Qt
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


class WebPage(QWebEnginePage):
    def __init__(self, profile: QWebEngineProfile, owner: "BrowserPage", parent=None):
        super().__init__(profile, parent)
        self.owner = owner
        self.fullScreenRequested.connect(self._on_fullscreen)

    def createWindow(self, _window_type):  # noqa: N802
        view = self.owner.add_tab("about:blank", background=False)
        return view.page()

    def _on_fullscreen(self, request) -> None:
        """HTML5 视频进入/退出全屏：交给整个窗口切换，避免画面被裁剪。"""
        request.accept()
        view = self.view()
        if view is None:
            return
        window = view.window()
        if request.toggleOn():
            self._was_maximized = window.isMaximized()
            window.showFullScreen()
        else:
            if getattr(self, "_was_maximized", False):
                window.showMaximized()
            else:
                window.showNormal()


class WebView(QWebEngineView):
    def __init__(self, owner: "BrowserPage", profile: QWebEngineProfile, parent=None):
        super().__init__(parent)
        self.owner = owner
        page = WebPage(profile, owner, self)
        self.setPage(page)


class BrowserPage(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
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
        system_browser = QPushButton("🌐 系统浏览器")
        system_browser.setObjectName("Chip")
        system_browser.setToolTip("用系统默认浏览器打开当前页面（可播放 H.264 视频）")
        system_browser.clicked.connect(self._open_in_system_browser)
        quick_row.addWidget(system_browser)
        outer.addLayout(quick_row)

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
        # 显式从磁盘加载已保存的 cookie，保证 B 站等站点登录状态跨会话保留
        try:
            profile.cookieStore().loadAllCookies()
        except (AttributeError, RuntimeError):
            pass
        self.profile = profile

        self._new_shortcut = QShortcut(QKeySequence("Ctrl+T"), self)
        self._new_shortcut.activated.connect(lambda: self.add_tab(None))
        self._close_shortcut = QShortcut(QKeySequence("Ctrl+W"), self)
        self._close_shortcut.activated.connect(
            lambda: self._close_tab(self.tabs.currentIndex())
        )

    def _tool_button(self, text: str, tooltip: str, slot) -> QPushButton:
        button = QPushButton(text)
        button.setFixedSize(32, 32)
        button.setToolTip(tooltip)
        button.setStyleSheet("font-size: 16px; padding: 0;")
        button.clicked.connect(slot)
        return button

    # ------------------------------------------------------------------
    def add_tab(self, url: str | None = None, background: bool = False) -> WebView:
        view = WebView(self, self.profile, self)
        view.titleChanged.connect(lambda title, v=view: self._set_tab_title(v, title))
        view.urlChanged.connect(lambda qurl, v=view: self._on_url_changed(v, qurl))
        view.loadStarted.connect(lambda v=view: self._on_load_started(v))
        view.loadProgress.connect(lambda value, v=view: self._on_load_progress(v, value))
        view.loadFinished.connect(lambda ok, v=view: self._on_load_finished(v, ok))
        view.iconChanged.connect(lambda icon, v=view: self._set_tab_icon(v, icon))
        settings = view.page().settings()
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

        index = self.tabs.addTab(view, "新标签页")
        if url is None:
            view.setHtml(START_HTML, QUrl("https://mclite.local/"))
        elif url == "about:blank":
            view.setHtml(START_HTML, QUrl("https://mclite.local/"))
        else:
            view.setUrl(QUrl(url))
        self.tabs.setCurrentIndex(index)
        return view

    def _close_tab(self, index: int) -> None:
        view = self.tabs.widget(index)
        self.tabs.removeTab(index)
        if view is not None:
            view.deleteLater()
        if self.tabs.count() == 0:
            self.add_tab(None)

    def _set_tab_title(self, view: WebView, title: str) -> None:
        index = self.tabs.indexOf(view)
        if index < 0:
            return
        label = title.strip() or "新标签页"
        if label.startswith("MikanCL"):
            label = "新标签页"
        self.tabs.setTabText(index, label[:24])
        self.tabs.setTabToolTip(index, title)

    def _set_tab_icon(self, view: WebView, icon: QIcon) -> None:
        index = self.tabs.indexOf(view)
        if index >= 0 and not icon.isNull():
            self.tabs.setTabIcon(index, icon)

    def _on_url_changed(self, view: WebView, url: QUrl) -> None:
        if view is self.current_view():
            text = url.toString()
            if text.startswith("https://mclite.local/"):
                text = ""
            if not self.url_edit.hasFocus():
                self.url_edit.setText(text)
            self.status_url.setText(text)

    def _on_tab_changed(self, _index: int) -> None:
        view = self.current_view()
        if view is not None:
            url = view.url().toString()
            if url.startswith("https://mclite.local/"):
                url = ""
            self.url_edit.setText(url)
            self.status_url.setText(url)

    def _on_load_started(self, view: WebView) -> None:
        if view is self.current_view():
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            self.status_msg.setText("加载中…")

    def _on_load_progress(self, view: WebView, value: int) -> None:
        if view is self.current_view():
            self.progress_bar.setValue(value)

    def _on_load_finished(self, view: WebView, ok: bool) -> None:
        if view is self.current_view():
            self.progress_bar.setVisible(False)
            self.status_msg.setText("加载完成" if ok else "加载失败")

    # ------------------------------------------------------------------
    def current_view(self) -> WebView | None:
        view = self.tabs.currentWidget()
        return view if isinstance(view, WebView) else None

    def _open_in_system_browser(self) -> None:
        """内置内核缺少 H.264 解码，无法播放部分站点视频时改交给系统浏览器。"""
        view = self.current_view()
        url = view.url() if view is not None else QUrl()
        if url.scheme() not in ("http", "https"):
            raw = self.url_edit.text().strip()
            if raw:
                url = QUrl(self._clean_input(raw))
        if url.scheme() not in ("http", "https"):
            self.ctx.bus.toast.emit("当前没有可打开的网页地址")
            return
        QDesktopServices.openUrl(url)
        self.ctx.bus.toast.emit("已用系统浏览器打开当前页面")

    def _navigate(self) -> None:
        view = self.current_view()
        if view is None:
            return
        raw = self.url_edit.text().strip()
        view.setUrl(QUrl(self._clean_input(raw)))
        view.setFocus()

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
        view = self.current_view()
        if view:
            view.back()

    def _go_forward(self) -> None:
        view = self.current_view()
        if view:
            view.forward()

    def _reload(self) -> None:
        view = self.current_view()
        if view:
            view.reload()

    def _go_home(self) -> None:
        view = self.current_view()
        if view:
            view.setHtml(START_HTML, QUrl("https://mclite.local/"))
            self.url_edit.clear()

    def navigate_to(self, url: str) -> None:
        view = self.current_view()
        if view is None:
            view = self.add_tab(url)
        else:
            view.setUrl(QUrl(url))
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
            flush = getattr(self.profile.cookieStore(), "flushCookieStore", None)
            if callable(flush):
                flush()
        except (AttributeError, RuntimeError):
            pass
        while self.tabs.count():
            view = self.tabs.widget(0)
            self.tabs.removeTab(0)
            if view is not None:
                view.deleteLater()
