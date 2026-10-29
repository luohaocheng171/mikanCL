"""MikanCL 应用入口。"""

from __future__ import annotations

import os
import sys

os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--autoplay-policy=no-user-gesture-required --disable-features=RendererCodeIntegrity",
)

# QtWebEngine 要求在创建 QApplication 之前导入 WebEngineWidgets
from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401
from PySide6.QtCore import QCoreApplication, QSharedMemory, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from . import APP_NAME, APP_NAME_CN  # noqa: E402
from .auth import AccountStore  # noqa: E402
from .config import LOG_DIR, Config  # noqa: E402
from .content import ContentClient  # noqa: E402
from .context import AppBus, AppContext  # noqa: E402
from .i18n import Translator  # noqa: E402
from .net import SourceManager, apply_proxy  # noqa: E402
from .ui.main_window import MainWindow  # noqa: E402
from .ui.theme import STYLESHEET, apply_theme, make_block_icon  # noqa: E402


def _dark_palette() -> QPalette:
    palette = QPalette()
    colors = {
        QPalette.Window: "#0c1310",
        QPalette.WindowText: "#e8f1ea",
        QPalette.Base: "#0e1712",
        QPalette.AlternateBase: "#121d16",
        QPalette.ToolTipBase: "#121d16",
        QPalette.ToolTipText: "#e8f1ea",
        QPalette.Text: "#e8f1ea",
        QPalette.PlaceholderText: "#718a7a",
        QPalette.Button: "#18271e",
        QPalette.ButtonText: "#e8f1ea",
        QPalette.BrightText: "#ffffff",
        QPalette.Highlight: "#2f6b3a",
        QPalette.HighlightedText: "#ffffff",
        QPalette.Link: "#65d46e",
        QPalette.LinkVisited: "#4bae57",
    }
    for role, value in colors.items():
        palette.setColor(role, QColor(value))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, QColor("#5f7867"))
    return palette


def _install_log_sink(bus: AppBus) -> None:
    """把界面日志同步落盘到 data/logs/launcher.log（5MB × 3 轮转）。"""
    try:
        import logging
        from logging.handlers import RotatingFileHandler

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger(APP_NAME)
        logger.setLevel(logging.INFO)
        handler = RotatingFileHandler(
            LOG_DIR / "launcher.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s"))
        logger.addHandler(handler)
        bus.log.connect(lambda message: logger.info(message))
    except Exception:  # noqa: BLE001 - 日志落盘失败不应阻止启动
        pass


_SINGLE_INSTANCE: QSharedMemory | None = None


def _acquire_single_instance() -> QSharedMemory | None:
    """单实例保护：避免两个进程同时读写 config.json / accounts.json / 浏览器 profile。"""
    try:
        memory = QSharedMemory(f"{APP_NAME}-single-instance")
        if memory.attach():
            memory.detach()
            return None
        return memory if memory.create(1) else None
    except Exception:  # noqa: BLE001 - 单实例失败不应阻止启动
        return None


def release_single_instance() -> None:
    """释放单实例锁，供「立即重启」在拉起新进程前调用，否则新进程会误判为重复启动。"""
    global _SINGLE_INSTANCE
    memory = _SINGLE_INSTANCE
    _SINGLE_INSTANCE = None
    if memory is None:
        return
    try:
        memory.detach()
    except Exception:  # noqa: BLE001 - 释放失败只影响重启，不影响退出
        pass


def main() -> None:
    # PyInstaller 打包后：工作目录重定向到 exe 所在目录，数据文件也在此自动生成
    if getattr(sys, "frozen", False):
        try:
            os.chdir(os.path.dirname(sys.executable))
        except OSError:
            pass
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    # 显示名用于窗口标题后缀，保持中性以免在非中文界面出现中文
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setStyle("Fusion")
    app.setPalette(_dark_palette())
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyleSheet(STYLESHEET)
    app.setWindowIcon(make_block_icon(64))

    global _SINGLE_INSTANCE
    guard = _acquire_single_instance()
    if guard is None:
        QMessageBox.information(
            None,
            APP_NAME,
            f"{APP_NAME_CN} 已经在运行中。请切换到已打开的窗口，或先在托盘退出后再启动。",
        )
        return
    _SINGLE_INSTANCE = guard

    config = Config.load()
    # 主题色在配置加载后才能确定：重算样式表与高亮色
    apply_theme(app, config.accent_color)
    # 翻译器需在 QApplication 之后、MainWindow 之前安装；Translator 自身挂到 app 上防 GC
    Translator(app).load(config.language)
    apply_proxy(config.effective_proxy)
    context = AppContext(
        config=config,
        sources=SourceManager(config),
        bus=AppBus(),
        accounts=AccountStore(default_name=config.player_name),
        content=ContentClient(config),
    )
    _install_log_sink(context.bus)

    def final_save() -> None:
        """退出前兜底落盘，避免异常关闭时丢失配置与账号。"""
        # 取消尚未触发的防抖写盘，避免与同步 save() 争用同一个临时文件
        timer = getattr(context.config, "_save_timer", None)
        if timer is not None:
            timer.cancel()
        for store in (context.config, context.accounts):
            try:
                store.save()
            except Exception:  # noqa: BLE001 - 退出阶段不应该再抛异常
                pass

    window = MainWindow(context)
    app.aboutToQuit.connect(final_save)
    window.show()
    code = app.exec()
    # 跳过 Qt/Python 析构：退出时可能仍有后台线程在收尾，直接结束进程避免崩溃
    try:
        final_save()
        app.processEvents()
        sys.stdout.flush()
        sys.stderr.flush()
    finally:
        os._exit(code)


if __name__ == "__main__":
    main()
