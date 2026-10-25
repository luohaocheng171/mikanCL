"""封面图片异步加载：内存缓存 + 磁盘缓存，避免阻塞界面。"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QSize, Qt, QUrl
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from .. import USER_AGENT
from ..config import CACHE_DIR

COVER_DIR = CACHE_DIR / "covers"
COVER_DIR.mkdir(parents=True, exist_ok=True)

_PALETTE = ("#2f6b3d", "#31556b", "#6b5731", "#5a316b", "#316b5e", "#6b3138")


def make_placeholder(size: QSize, text: str = "") -> QPixmap:
    """生成渐变占位封面，中心显示首字母。"""
    pixmap = QPixmap(size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    seed = sum(ord(c) for c in text) if text else 0
    first = QColor(_PALETTE[seed % len(_PALETTE)])
    second = first.darker(150)
    gradient = QLinearGradient(0, 0, size.width(), size.height())
    gradient.setColorAt(0.0, first)
    gradient.setColorAt(1.0, second)
    painter.fillRect(0, 0, size.width(), size.height(), gradient)
    if text:
        painter.setPen(QColor(255, 255, 255, 200))
        font = painter.font()
        font.setPixelSize(max(14, int(size.height() * 0.42)))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, text.strip()[:1].upper())
    painter.end()
    return pixmap


def _cache_path(url: str) -> Path:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return COVER_DIR / f"{digest}.img"


class CoverLoader(QObject):
    """按 URL 异步下载封面并缓存；回调始终在主线程执行。"""

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        self._cache: dict[str, QPixmap] = {}
        self._pending: dict[str, list[Callable[[QPixmap], None]]] = {}
        self._replies: dict[str, QNetworkReply] = {}

    def load(self, url: str, callback: Callable[[QPixmap], None], size: QSize) -> None:
        if not url:
            callback(make_placeholder(size, ""))
            return
        cached = self._cache.get(url)
        if cached is not None and not cached.isNull():
            callback(cached)
            return
        if url in self._pending:
            self._pending[url].append(callback)
            return
        self._pending[url] = [callback]
        disk = _cache_path(url)
        if disk.exists():
            pixmap = QPixmap(str(disk))
            if not pixmap.isNull():
                self._cache[url] = pixmap
                self._flush(url, pixmap)
                return
        request = QNetworkRequest(QUrl(url))
        request.setRawHeader(b"User-Agent", USER_AGENT.encode("utf-8"))
        reply = self._manager.get(request)
        self._replies[url] = reply
        reply.finished.connect(lambda u=url, r=reply: self._on_finished(u, r))

    def _on_finished(self, url: str, reply: QNetworkReply) -> None:
        self._replies.pop(url, None)
        data = reply.readAll()
        reply.deleteLater()
        pixmap = QPixmap()
        if data:
            pixmap.loadFromData(data)
        if pixmap.isNull():
            self._flush(url, None)
            return
        self._cache[url] = pixmap
        try:
            _cache_path(url).write_bytes(bytes(data))
        except OSError:
            pass
        self._flush(url, pixmap)

    def _flush(self, url: str, pixmap: QPixmap | None) -> None:
        callbacks = self._pending.pop(url, [])
        for callback in callbacks:
            try:
                callback(pixmap)
            except RuntimeError:
                # 目标控件已被销毁，忽略即可
                continue

    def shutdown(self) -> None:
        for reply in list(self._replies.values()):
            reply.abort()
        self._replies.clear()
        self._pending.clear()
