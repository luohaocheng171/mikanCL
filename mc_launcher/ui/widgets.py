"""通用界面组件。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .theme import make_dot


class Card(QFrame):
    def __init__(self, parent: QWidget | None = None, margins: int = 18, spacing: int = 12):
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(margins, margins, margins, margins)
        self.body.setSpacing(spacing)


class Badge(QLabel):
    def __init__(self, text: str, kind: str = "gray", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setObjectName("Badge")
        self.set_kind(kind)
        self.setAlignment(Qt.AlignCenter)

    def set_kind(self, kind: str) -> None:
        self.setProperty("kind", kind)
        self.style().unpolish(self)
        self.style().polish(self)


class StatusDot(QWidget):
    def __init__(self, color: str = "#65d46e", size: int = 9, parent: QWidget | None = None):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)
        self._label = QLabel(self)
        pixmap = make_dot(color, size)
        self._label.setPixmap(pixmap)
        self._label.setGeometry(0, 0, size, size)


def hline() -> QFrame:
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet("background-color: #1e2d24; border: none;")
    return line


def card_title_row(title: str, subtitle: str = "", extra: QWidget | None = None) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)
    texts = QVBoxLayout()
    texts.setContentsMargins(0, 0, 0, 0)
    texts.setSpacing(2)
    label = QLabel(title)
    label.setObjectName("CardTitle")
    texts.addWidget(label)
    if subtitle:
        sub = QLabel(subtitle)
        sub.setObjectName("Tiny")
        texts.addWidget(sub)
    layout.addLayout(texts)
    layout.addStretch(1)
    if extra is not None:
        layout.addWidget(extra)
    return row


def page_header(title: str, subtitle: str) -> tuple[QWidget, QHBoxLayout]:
    wrapper = QWidget()
    layout = QHBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)
    texts = QVBoxLayout()
    texts.setContentsMargins(0, 0, 0, 0)
    texts.setSpacing(3)
    title_label = QLabel(title)
    title_label.setObjectName("PageTitle")
    sub_label = QLabel(subtitle)
    sub_label.setObjectName("PageSub")
    texts.addWidget(title_label)
    texts.addWidget(sub_label)
    layout.addLayout(texts)
    layout.addStretch(1)
    return wrapper, layout
