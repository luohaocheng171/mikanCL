"""应用上下文与跨页面信号总线。"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QObject, Signal

from .auth import AccountStore
from .config import Config
from .content import ContentClient
from .downloads import DownloadManager
from .java import JavaInfo
from .net import SourceManager


class AppBus(QObject):
    log = Signal(str)
    versions_changed = Signal()
    instances_changed = Signal()
    accounts_changed = Signal()
    config_changed = Signal()
    javas_changed = Signal()
    open_browser = Signal(str)
    navigate = Signal(str)
    toast = Signal(str)
    hide_window = Signal()
    focus_version = Signal(str)
    # 游戏进程退出由守护线程通过总线转发，避免引用可能已析构的 QThread
    game_exited = Signal(int, str)


@dataclass
class AppContext:
    config: Config
    sources: SourceManager
    bus: AppBus
    accounts: AccountStore
    content: ContentClient
    javas: list[JavaInfo] = field(default_factory=list)
    downloads: DownloadManager = field(default_factory=DownloadManager)

    def current_account(self):
        return self.accounts.selected()


_ORPHAN_THREADS: list[QObject] = []


def wait_thread(worker: QObject | None, timeout_ms: int = 3000) -> None:
    """等待后台线程退出；若超时则解除父子关系，避免 Qt 销毁仍在运行的 QThread。"""
    if worker is None:
        return
    is_running = getattr(worker, "isRunning", None)
    if callable(is_running) and not is_running():
        return
    if worker.wait(timeout_ms):
        return
    worker.setParent(None)
    _ORPHAN_THREADS.append(worker)
