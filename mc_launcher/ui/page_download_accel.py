"""下载加速：把任意直链交给启动器的多线程下载器（与其他下载共享 328 线程上限）。"""

from __future__ import annotations

import os
import re
import threading
import time
import urllib.parse
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..config import DATA_DIR
from ..context import AppContext
from ..downloads import DownloadTask
from ..net import MAX_DOWNLOAD_THREADS, Cancelled, Candidate, Http, probe_download_size
from .widgets import Card, card_title_row, page_header

_URL_PATTERN = re.compile(r"https?://[^\s\"'<>（）()]+", re.I)
_TRAILING = "，。；：！？、,.;:!?)]}）】》>"
_UNSAFE_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _format_size(value: float) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    index = 0
    while value >= 1024 and index < len(units) - 1:
        value /= 1024
        index += 1
    return f"{value:.1f} {units[index]}" if index else f"{int(value)} B"


def _filename_for(url: str) -> str:
    """从直链末尾取文件名，去掉查询参数与非法的 Windows 字符。"""
    path = urllib.parse.unquote(urllib.parse.urlparse(url).path)
    name = path.rsplit("/", 1)[-1]
    name = _UNSAFE_NAME.sub("_", name).strip(" .")
    return name[:180] or "download.bin"


def _unique_dest(directory: Path, name: str, reserved: set[str]) -> Path:
    """同名文件已存在（或已被进行中的任务占用）时追加序号，避免两次下载写同一个文件。"""

    def taken(path: Path) -> bool:
        return path.exists() or os.path.normcase(str(path)) in reserved

    dest = directory / name
    if not taken(dest):
        return dest
    stem, suffix = dest.stem, dest.suffix
    for index in range(1, 1000):
        candidate = directory / f"{stem} ({index}){suffix}"
        if not taken(candidate):
            return candidate
    return dest.with_name(f"{stem} ({time.time_ns()}){suffix}")


class LinkDownloadWorker(QThread):
    """单个直链的下载线程：进度回调转成信号，交给下载中心的任务卡片展示。"""

    done = Signal()
    failed = Signal(str)
    progress = Signal(float, float, str)  # 进度 0~1、字节/秒、明细文字

    def __init__(
        self,
        url: str,
        dest: Path,
        workers: int,
        cancel_event: threading.Event,
        pause_event: threading.Event,
        parent=None,
    ):
        super().__init__(parent)
        self.url = url
        self.dest = Path(dest)
        self.workers = max(1, min(int(workers), MAX_DOWNLOAD_THREADS))
        self.cancel_event = cancel_event
        self.pause_event = pause_event

    def run(self) -> None:
        total, ranged = probe_download_size(self.url)
        state = {"bytes": 0, "last_t": time.time(), "last_b": 0}

        def on_bytes(count: int) -> None:
            state["bytes"] += int(count)
            now = time.time()
            if now - state["last_t"] < 0.25:
                return
            dt = max(1e-6, now - state["last_t"])
            speed = (state["bytes"] - state["last_b"]) / dt
            state["last_t"], state["last_b"] = now, state["bytes"]
            percent = min(1.0, state["bytes"] / total) if total else 0.0
            if total:
                detail = f"已下载 {_format_size(state['bytes'])} / {_format_size(total)}"
            else:
                detail = f"已下载 {_format_size(state['bytes'])}"
            self.progress.emit(percent, speed, detail)

        try:
            Http().download(
                [Candidate(url=self.url, headers={}, source_name="用户链接")],
                self.dest,
                size=total or None,
                cancel=self.cancel_event,
                pause=self.pause_event,
                on_bytes=on_bytes,
                parallel=True,  # 用户主动走加速页：优先进分段下载，不支持 Range 会自动退回单流
                workers=self.workers,
            )
            self.done.emit()
        except Cancelled:
            pass  # 已由下载中心标记为取消
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class DownloadAccelPage(QWidget):
    """多行粘贴直链 → 提交到全局下载中心，用高线程数下载。"""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self._build()
        self._update_count()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(16)

        header, _ = page_header(
            "下载加速",
            "把任意下载链接丢给启动器：多线程分段下载，所有下载共享 328 线程上限。",
        )
        root.addWidget(header)

        input_card = Card(margins=20, spacing=10)
        input_card.body.addWidget(
            card_title_row(
                "下载链接",
                "每行一个链接；也可以直接粘贴整段网页文本，会自动提取 http/https 链接",
            )
        )
        self.url_edit = QPlainTextEdit()
        self.url_edit.setObjectName("Console")
        self.url_edit.setPlaceholderText(
            "https://example.com/file.zip\nhttps://example.com/another.iso"
        )
        self.url_edit.setMinimumHeight(150)
        self.url_edit.textChanged.connect(self._update_count)
        input_card.body.addWidget(self.url_edit)
        self.count_label = QLabel("")
        self.count_label.setObjectName("Tiny")
        input_card.body.addWidget(self.count_label)
        root.addWidget(input_card)

        target_card = Card(margins=20, spacing=10)
        target_card.body.addWidget(
            card_title_row("保存位置与线程", "线程数越高越快，但受全局 328 上限和服务器限速影响")
        )
        dir_row = QHBoxLayout()
        dir_row.setSpacing(8)
        self.dir_edit = QLineEdit(str(self._default_dir()))
        dir_row.addWidget(self.dir_edit, 1)
        browse = QPushButton("浏览")
        browse.setObjectName("Ghost")
        browse.clicked.connect(self._choose_dir)
        dir_row.addWidget(browse)
        open_btn = QPushButton("打开目录")
        open_btn.setObjectName("Ghost")
        open_btn.clicked.connect(self._open_dir)
        dir_row.addWidget(open_btn)
        target_card.body.addLayout(dir_row)

        thread_row = QHBoxLayout()
        thread_row.setSpacing(8)
        thread_row.addWidget(QLabel("下载线程数"))
        self.thread_spin = QSpinBox()
        self.thread_spin.setRange(1, MAX_DOWNLOAD_THREADS)
        self.thread_spin.setValue(self._default_threads())
        self.thread_spin.setSuffix(" 线程")
        self.thread_spin.setMinimumWidth(140)
        thread_row.addWidget(self.thread_spin)
        self.ranged_label = QLabel("是否分段由服务器 Range 支持情况自动决定")
        self.ranged_label.setObjectName("Tiny")
        thread_row.addWidget(self.ranged_label, 1)
        target_card.body.addLayout(thread_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        start_btn = QPushButton("开始下载")
        start_btn.setObjectName("PrimaryCompact")
        start_btn.setCursor(Qt.PointingHandCursor)
        start_btn.clicked.connect(self._start)
        action_row.addWidget(start_btn)
        center_btn = QPushButton("查看下载中心")
        center_btn.setObjectName("GhostCompact")
        center_btn.clicked.connect(lambda: self.ctx.bus.navigate.emit("downloads"))
        action_row.addWidget(center_btn)
        action_row.addStretch(1)
        target_card.body.addLayout(action_row)
        root.addWidget(target_card)

        hint = QLabel(
            "提示：任务与版本安装、Java 下载共用同一个线程预算，不会把电脑线程数打爆；"
            "暂停后已下载的分段会保留，继续时接着下。"
        )
        hint.setObjectName("Tiny")
        hint.setWordWrap(True)
        root.addWidget(hint)
        root.addStretch(1)

    # ------------------------------------------------------------------
    def _default_dir(self) -> Path:
        saved = (self.ctx.config.download_accel_dir or "").strip()
        if saved:
            return Path(saved)
        return DATA_DIR / "downloads"

    def _default_threads(self) -> int:
        # 加速页默认就开高线程（至少 64），仍受全局 328 上限约束
        configured = int(self.ctx.config.download_threads or 16)
        return max(1, min(MAX_DOWNLOAD_THREADS, max(64, configured)))

    def _choose_dir(self) -> None:
        current = self.dir_edit.text().strip() or str(self._default_dir())
        chosen = QFileDialog.getExistingDirectory(self, "选择保存目录", current)
        if chosen:
            self.dir_edit.setText(chosen)

    def _open_dir(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        path = Path(self.dir_edit.text().strip() or str(self._default_dir()))
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _parse_urls(self) -> list[str]:
        seen: set[str] = set()
        urls: list[str] = []
        for match in _URL_PATTERN.finditer(self.url_edit.toPlainText()):
            url = match.group(0).rstrip(_TRAILING)
            if len(url) <= len("https://"):
                continue
            if url not in seen:
                seen.add(url)
                urls.append(url)
        return urls

    def _update_count(self) -> None:
        count = len(self._parse_urls())
        self.count_label.setText(
            f"已识别 {count} 个链接" if count else "还没有可用链接（需要以 http:// 或 https:// 开头）"
        )

    def _start(self) -> None:
        urls = self._parse_urls()
        if not urls:
            QMessageBox.warning(
                self, "没有可用链接", "请先粘贴以 http:// 或 https:// 开头的下载链接。"
            )
            return
        directory = Path(self.dir_edit.text().strip() or str(self._default_dir()))
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "无法创建目录", f"{directory}\n{exc}")
            return
        self.dir_edit.setText(str(directory))
        self.ctx.config.download_accel_dir = str(directory)
        threads = int(self.thread_spin.value())
        # 进行中的任务已经占用了同名目标时也要跳过，避免两个 worker 同时写一个文件
        reserved = {
            os.path.normcase(str(Path(task.target_dir) / task.name))
            for task in self.ctx.downloads.tasks()
            if task.active and task.target_dir
        }
        for url in urls:
            dest = _unique_dest(directory, _filename_for(url), reserved)
            reserved.add(os.path.normcase(str(dest)))
            self._submit(url, dest, threads)
        self.ctx.bus.log.emit(f"[下载加速] 已提交 {len(urls)} 个链接，线程数 {threads}")
        self.ctx.bus.toast.emit(f"已提交 {len(urls)} 个下载任务，可在「下载中心」查看进度。")

    def _submit(self, url: str, dest: Path, threads: int) -> None:
        manager = self.ctx.downloads

        def factory(task: DownloadTask) -> QThread:
            # 每次（含重试）都新建事件，保证取消/暂停绑定到当前 worker
            cancel_event = threading.Event()
            pause_event = threading.Event()
            task.cancel = cancel_event.set
            task.pause_event = pause_event
            worker = LinkDownloadWorker(url, dest, threads, cancel_event, pause_event)
            worker.progress.connect(
                lambda percent, speed, detail, tid=task.id: manager.update(
                    tid, percent=percent, speed=speed, detail=detail, status="下载中"
                )
            )
            worker.done.connect(
                lambda tid=task.id: manager.finish(tid, True, "下载完成")
            )
            worker.failed.connect(
                lambda message, tid=task.id: manager.finish(tid, False, message)
            )
            return worker

        manager.submit(
            kind="加速下载",
            name=dest.name,
            factory=factory,
            rebuild=factory,
            target_dir=str(dest.parent),
            detail=url,
        )
