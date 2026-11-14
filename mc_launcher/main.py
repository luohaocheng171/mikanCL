"""MikanCL 应用入口。

启动路径按界面框架分成三条，未选中的框架不导入：
- classic：Qt Widgets 主窗口（功能完整，低占用）
- webview：pywebview + WebView2 美化版外壳（Chromium 渲染）
- electron：独立版，交给 Electron 产物自己启动，主程序直接退出

重模块（QtWebEngine、MainWindow、ContentClient、Net 等）全部放到函数内惰性导入，
避免美化版启动时白等几百毫秒。
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--autoplay-policy=no-user-gesture-required --disable-features=RendererCodeIntegrity",
)

from . import APP_NAME, APP_NAME_CN
from .config import LOG_DIR, Config

_SINGLE_INSTANCE = None
_FAULT_HANDLE = None


def _dark_palette():
    from PySide6.QtGui import QColor, QPalette

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


def _install_log_sink(bus) -> None:
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


def _enable_fault_handler() -> None:
    """崩溃现场捕获：仅调试模式开启，把 C 层崩溃栈写进 data/logs/faulthandler.log。"""
    if os.environ.get("MIKAN_DEBUG_STARTUP") != "1":
        return
    global _FAULT_HANDLE
    try:
        import faulthandler

        from .config import LOG_DIR

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        _FAULT_HANDLE = open(LOG_DIR / "faulthandler.log", "a", encoding="utf-8")
        faulthandler.enable(_FAULT_HANDLE, all_threads=True)
    except Exception:  # noqa: BLE001 - 调试设施失败不影响启动
        _FAULT_HANDLE = None


def _acquire_single_instance():
    """单实例保护：避免两个进程同时读写 config.json / accounts.json / 浏览器 profile。"""
    from PySide6.QtCore import QSharedMemory

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


def _run_webview(config) -> bool:
    """运行美化版；返回 True 表示正常结束。"""
    from .ui_web import shell

    code = shell.run(config)
    if code != 0:
        return False
    try:
        config.cancel_debounced_save()
        config.save()
    except Exception:  # noqa: BLE001 - 退出阶段不再抛异常
        pass
    return True


def _message_box(text: str) -> None:
    """还没有 QApplication 时的兜底提示（只在 Windows 上有实际效果）。"""
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, text, APP_NAME, 0x00000030)
    except Exception:  # noqa: BLE001 - 提示失败不影响退出
        pass


def _run_electron(config) -> bool:
    """独立版：拉起 Electron 产物并退出主程序；返回 True 表示已经交接。"""
    from .electron_launcher import launch_electron

    if launch_electron():
        try:
            config.cancel_debounced_save()
            config.save()
        except Exception:  # noqa: BLE001
            pass
        return True
    _message_box(
        f"未找到 {APP_NAME_CN} 独立版（Electron）。\n\n"
        "独立版是单独的构建产物，需要先运行 build_electron.py 生成；\n"
        "也可以在「设置 → 外观 → 界面框架」里切回美化版或经典版。"
    )
    return False


def _log_line(message: str) -> None:
    """把启动阶段的关键决策写进 data/logs/launcher.log（与界面日志同一文件）。"""
    import time

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_DIR / "launcher.log", "a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  [框架] {message}\n")
    except OSError:
        pass


def main() -> None:
    from ._trace import trace as _startup_trace

    _enable_fault_handler()
    _startup_trace("enter main")
    # 打包后：工作目录重定向到 exe 所在目录，数据文件也在此自动生成
    if getattr(sys, "frozen", False) or "__compiled__" in globals():
        from .config import APP_ROOT

        try:
            os.chdir(APP_ROOT)
        except OSError:
            pass
    _startup_trace("after chdir")

    config = Config.load()
    _startup_trace("after config load")

    # 独立版：主程序只做交接，不初始化 Qt，也不碰 WebView2
    if config.frame_mode_asked and config.frame_mode == "electron":
        if _run_electron(config):
            _startup_trace("electron handed over")
            return
        # 产物缺失：提示后按经典版继续，避免卡在无法进入的界面
        config.frame_mode = "classic"
        config.frame_locked = False
        try:
            config.save()
        except OSError:
            pass

    # 已选定美化版时不再导入 QtWebEngine；经典版仍需在 QApplication 之前导入
    if not (config.frame_mode_asked and config.frame_mode == "webview"):
        from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
    _startup_trace("after qtwebengine")

    from PySide6.QtCore import QCoreApplication, Qt
    from PySide6.QtGui import QFont, QGuiApplication
    from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

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

    from .ui.theme import STYLESHEET, apply_theme, make_block_icon

    app.setStyleSheet(STYLESHEET)
    app.setWindowIcon(make_block_icon(64))
    apply_theme(app, config.accent_color, config.theme_name)
    _startup_trace("after QApplication")

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
    _startup_trace("after single instance")

    # 翻译器需在 QApplication 之后、MainWindow 之前安装；Translator 自身挂到 app 上防 GC
    from .i18n import Translator

    Translator(app).load(config.language)
    _startup_trace("after translator")

    # 首次启动：先选界面框架（经典 Qt / 美化 pywebview）；之后可在设置页双向切换
    if not config.frame_mode_asked:
        from .ui.dialog_frame import FrameModeDialog

        frame_dialog = FrameModeDialog()
        result = frame_dialog.exec()
        config.frame_mode = frame_dialog.mode
        config.frame_mode_asked = True
        config.frame_locked = False
        config.save()
        # 记一笔，方便排查「选了一个框架却进了另一个」这类问题
        _log_line(
            "首次选择界面框架：{}（{}）".format(
                config.frame_mode,
                "已点使用此框架" if result == QDialog.Accepted else "直接关闭对话框，沿用高亮项",
            )
        )
    _startup_trace(f"frame mode: {config.frame_mode}")

    # 首次就选了独立版：拉起 Electron 后立刻退出，不进入 Qt / WebView2 流程
    if config.frame_mode == "electron":
        if _run_electron(config):
            guard.detach()
            _SINGLE_INSTANCE = None
            # 正常返回让 PyInstaller 清理临时解包目录，避免每次切换残留上百 MB
            return
        from .ui.dialog_frame import webview2_installed as _webview2_ok

        config.frame_mode = "webview" if _webview2_ok() else "classic"
        config.frame_locked = False
        try:
            config.save()
        except OSError:
            pass
        _startup_trace(f"electron missing, fallback: {config.frame_mode}")

    _log_line(f"进入界面框架：{config.frame_mode}")

    # 经典版首次启动再选「界面运行模式」（毛玻璃程度），美化版不需要
    if config.frame_mode == "classic" and not config.ui_mode_asked:
        from .ui.dialog_ui_mode import UiModeDialog

        mode_dialog = UiModeDialog()
        mode_dialog.exec()
        config.ui_mode = mode_dialog.mode
        config.ui_acrylic = mode_dialog.mode == UiModeDialog.MODE_VISUAL
        config.ui_mode_asked = True
        config.save()

    # 用户协议门禁：经典版用 Qt 对话框；美化版在网页内展示同一份协议文本
    from . import agreement

    if config.frame_mode == "classic" and agreement.needs_prompt(config):
        from .ui.dialog_agreement import AgreementDialog

        dialog = AgreementDialog(config.language)
        if dialog.exec() != QDialog.Accepted:
            # 不同意：立刻结束进程，绝不进入主界面
            guard.detach()
            _SINGLE_INSTANCE = None
            os._exit(0)
        agreement.accept(config)
    _startup_trace("after dialogs")

    if config.frame_mode == "webview":
        _startup_trace("before webview shell")
        if _run_webview(config):
            _startup_trace("webview closed")
            os._exit(0)
        # 美化版启动失败：询问是否自动切回经典版，避免用户被卡死在无法使用的框架
        guard.detach()
        _SINGLE_INSTANCE = None
        answer = QMessageBox.question(
            None,
            APP_NAME,
            "美化版无法启动（缺少 WebView2 Runtime 或渲染器初始化失败）。\n\n"
            "请安装 Microsoft Edge WebView2 Runtime 后重试；也可以把运行时解包到安装目录的 "
            "webview2 文件夹使用内置版本。\n\n"
            "是否立即切回经典版（Qt）？切换后重新启动启动器即可进入经典版。\n\n"
            "详细错误已写入 data/logs/webview_error.log。",
        )
        if answer == QMessageBox.Yes:
            config.frame_mode = "classic"
            config.frame_locked = False
            try:
                config.save()
            except OSError:
                pass
            QMessageBox.information(None, APP_NAME, "已切回经典版，请重新启动启动器。")
        os._exit(2)

    # ---- 经典 Qt 界面 ----
    from .auth import AccountStore
    from .content import ContentClient
    from .context import AppBus, AppContext
    from .net import SourceManager, apply_proxy
    from .ui.main_window import MainWindow

    apply_proxy(config.effective_proxy)
    context = AppContext(
        config=config,
        sources=SourceManager(config),
        bus=AppBus(),
        accounts=AccountStore(default_name=config.player_name),
        content=ContentClient(config),
    )
    _install_log_sink(context.bus)
    _startup_trace("after log sink")

    def final_save() -> None:
        """退出前兜底落盘，避免异常关闭时丢失配置与账号。"""
        # 取消尚未触发的防抖写盘，避免与同步 save() 争用同一个临时文件
        context.config.cancel_debounced_save()
        for store in (context.config, context.accounts):
            try:
                store.save()
            except Exception:  # noqa: BLE001 - 退出阶段不应该再抛异常
                pass

    window = MainWindow(context)
    _startup_trace("after MainWindow")
    app.aboutToQuit.connect(final_save)
    window.show()
    _startup_trace("after show")
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
