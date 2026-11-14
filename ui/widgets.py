"""通用界面组件。"""

from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..config import DATA_DIR
from .theme import make_dot

RECENT_PAGES_PATH = DATA_DIR / "recent_pages.json"


def load_recent_pages(limit: int = 5) -> list[dict]:
    """读取「最近使用」记录；文件损坏或不存在时返回空列表。"""
    try:
        payload = json.loads(RECENT_PAGES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(payload, list):
        return []
    items: list[dict] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("key") or "")
        label = str(entry.get("label") or "")
        if key and label:
            items.append({"key": key, "label": label})
    return items[:limit]


def save_recent_pages(items: list[dict], limit: int = 5) -> None:
    """持久化「最近使用」记录；写入失败不影响界面。"""
    try:
        RECENT_PAGES_PATH.write_text(
            json.dumps(items[:limit], ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        pass


# 功能页底部的「你可能还需要」映射：(唯一键, 按钮文案, 目标页面 key)
RELATED_FEATURES = (
    ("nbt", "NBT 编辑器", "control"),
    ("seed", "世界种子预览", "seed_terrain"),
    ("saves", "存档备份", "control"),
    ("gallery", "截图图库", "gallery"),
    ("crash", "崩溃报告", "crash"),
    ("modgraph", "Mod 关系图", "modgraph"),
    ("deps", "依赖补全", "deps"),
)


def related_features_row(ctx, current_key: str = "") -> QWidget:
    """生成「你可能还需要：…」快捷入口行；当前页对应的功能自动省略。"""
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    caption = QLabel("你可能还需要：")
    caption.setObjectName("Tiny")
    layout.addWidget(caption)
    count = 0
    for key, title, target in RELATED_FEATURES:
        if target == current_key:
            continue
        button = QPushButton(title)
        button.setObjectName("Chip")
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(
            lambda _checked=False, page=target: ctx.bus.navigate.emit(page)
        )
        layout.addWidget(button)
        count += 1
    layout.addStretch(1)
    row.setVisible(bool(count))
    return row


class ModpackInstallModeDialog(QDialog):
    """整合包安装方式：下载全新版本，或附加到已安装的版本。"""

    def __init__(
        self,
        versions: list[dict],
        title: str = "安装整合包",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.mode = "new"
        self.selected: dict | None = None
        self.setObjectName("Root")
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        heading = QLabel("选择整合包的安装方式")
        heading.setObjectName("CardTitle")
        layout.addWidget(heading)

        box = QGroupBox("安装方式")
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(12, 8, 12, 8)
        box_layout.setSpacing(6)
        self.mode_new = QRadioButton("下载全新版本安装（推荐，整合包互不影响）")
        self.mode_new.setChecked(True)
        self.mode_attach = QRadioButton("附加到已有版本（不下载原版、不新建实例）")
        box_layout.addWidget(self.mode_new)
        box_layout.addWidget(self.mode_attach)

        self.version_combo = QComboBox()
        for target in versions:
            self.version_combo.addItem(str(target.get("label") or "未命名版本"), target)
        self.version_combo.setEnabled(False)
        box_layout.addWidget(self.version_combo)
        layout.addWidget(box)

        if versions:
            hint_text = (
                "附加模式会把整合包内容直接写入所选版本的游戏目录，不安装原版与加载器；"
                "所选版本的 Minecraft 版本与加载器必须和整合包一致。"
            )
        else:
            hint_text = "尚未安装任何游戏版本，只能选择「下载全新版本安装」。"
        hint = QLabel(hint_text)
        hint.setObjectName("Tiny")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        if not versions:
            self.mode_attach.setEnabled(False)

        layout.addStretch(1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("取消")
        cancel.setObjectName("Ghost")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        confirm = QPushButton("继续")
        confirm.setObjectName("Primary")
        confirm.clicked.connect(self._accept)
        buttons.addWidget(confirm)
        layout.addLayout(buttons)

        self.mode_attach.toggled.connect(
            lambda checked: self.version_combo.setEnabled(bool(checked) and bool(versions))
        )

    def _accept(self) -> None:
        if self.mode_attach.isChecked():
            target = self.version_combo.currentData()
            if not isinstance(target, dict) or not target.get("version_id"):
                QMessageBox.information(self, "请选择版本", "请选择一个已安装的游戏版本。")
                return
            self.mode = "attach"
            self.selected = dict(target)
        self.accept()


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
    # 底色统一由 theme.py 的全局规则 QScrollArea > QWidget / > QWidget > QWidget 负责，
    # 不再为每个页面单独 inline setStyleSheet；自定义背景图时全局规则会改成 transparent。
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
