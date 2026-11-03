"""通用界面组件。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

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


def scroll_page(page: QWidget) -> QWidget:
    """把整页内容包进滚动容器。

    窗口高度不足时改为鼠标滚轮上下滚动，避免布局把卡片、表单硬压成薄片导致文字重叠。
    """
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    # 纵向始终允许滚轮；横向仅在页面比窗口更宽时出现，避免内容被硬裁切
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    # 关键：视口默认 WA_OpaquePaintEvent=True 且样式表 background: transparent，
    # 滚动/切页时不擦除旧像素，导致文字重影。设为 False 让 Qt 先清空再绘制。
    scroll.viewport().setAttribute(Qt.WA_OpaquePaintEvent, False)
    scroll.viewport().setAttribute(Qt.WA_StyledBackground, True)
    page.setAttribute(Qt.WA_StyledBackground, True)
    # 用 inline 样式表确保背景一定被绘制（普通 QWidget 默认不绘制应用级背景）。
    # 有自定义背景图时由 MainWindow._apply_appearance 统一改为 transparent。
    scroll.viewport().setStyleSheet("background-color: #0c1310;")
    page.setStyleSheet("background-color: #0c1310;")
    scroll.setWidget(page)
    return scroll


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


def ask_skin_model(parent=None, default: str = "classic", title: str = "") -> str | None:
    """询问皮肤手臂模型：Steve（经典）或 Alex（纤细）；取消返回 None。

    用户取消时调用方应中止后续打包。
    """
    from PySide6.QtWidgets import QInputDialog

    from ..i18n import t

    items = [t("SkinPack", "Steve（经典）"), t("SkinPack", "Alex（纤细）")]
    current = 1 if (default or "").lower() == "slim" else 0
    value, ok = QInputDialog.getItem(
        parent,
        title or t("SkinPack", "选择手臂模型"),
        t("SkinPack", "请选择这张皮肤的手臂模型（导入后会按此模型打包）："),
        items,
        current,
        False,
    )
    if not ok:
        return None
    return "slim" if value == items[1] else "classic"
