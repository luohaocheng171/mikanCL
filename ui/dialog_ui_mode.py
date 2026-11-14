"""首次启动时的界面运行模式选择。

两种模式共用同一套 Qt 渲染内核，区别只在动效与 Windows DWM 合成：
- 经典：纯 Qt 绘制、无系统毛玻璃，最低占用，适合低配机 / 远程桌面 / 多开。
- 视觉：调用 Windows 原生亚克力（DWM），磁贴导航 + 半透明层级，参考 iOS / BakaXL。

没有切换 Electron / Tauri / Flutter：它们的内存占用更高，且无法直接使用
Windows 原生亚克力，性价比不如现有 Qt 实现。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..i18n import t


class _ModeCard(QFrame):
    """一张可点选的模式卡片（标题 + 描述 + 占用提示）。"""

    def __init__(self, title: str, subtitle: str, points: list[str], parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ModeCard")
        self.setCursor(Qt.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)
        head = QLabel(title)
        head.setObjectName("ModeCardTitle")
        layout.addWidget(head)
        sub = QLabel(subtitle)
        sub.setObjectName("ModeCardSub")
        sub.setWordWrap(True)
        layout.addWidget(sub)
        for point in points:
            label = QLabel(f"· {point}")
            label.setObjectName("ModeCardPoint")
            label.setWordWrap(True)
            layout.addWidget(label)


class UiModeDialog(QDialog):
    """确认后返回 `mode`（classic / visual）。"""

    MODE_CLASSIC = "classic"
    MODE_VISUAL = "visual"

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.mode = self.MODE_CLASSIC
        self.setWindowTitle(t("UiModeDialog", "选择界面运行模式"))
        self.setMinimumWidth(640)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        title = QLabel(t("UiModeDialog", "选择界面运行模式"))
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        intro = QLabel(
            t(
                "UiModeDialog",
                "两种模式使用同一个 Qt 引擎，无需下载额外组件；之后可在「设置 → 界面效果」随时切换。"
                "低配电脑建议经典模式，想要毛玻璃与更强视觉层次则选视觉增强。",
            )
        )
        intro.setObjectName("Muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.classic_card = _ModeCard(
            t("UiModeDialog", "经典模式"),
            t("UiModeDialog", "稳定 · 低占用 · 快速启动"),
            [
                t("UiModeDialog", "纯 Qt 自绘，不启用系统毛玻璃合成"),
                t("UiModeDialog", "内存与 GPU 占用最低，适合低配机 / 远程桌面"),
                t("UiModeDialog", "侧边栏磁贴导航，深色磨砂质感"),
            ],
        )
        self.visual_card = _ModeCard(
            t("UiModeDialog", "视觉增强"),
            t("UiModeDialog", "毛玻璃 · 磁贴 · 参考 iOS / BakaXL"),
            [
                t("UiModeDialog", "调用 Windows 10/11 原生 DWM 亚克力，背景与按钮半透明"),
                t("UiModeDialog", "保留品牌绿色点缀，卡片层级更接近 iOS 控制中心"),
                t("UiModeDialog", "支持背景图 + 毛玻璃叠加，可随时关闭"),
            ],
        )
        for card, mode in (
            (self.classic_card, self.MODE_CLASSIC),
            (self.visual_card, self.MODE_VISUAL),
        ):
            card.mousePressEvent = lambda event, m=mode: self._choose(m)  # type: ignore[method-assign]
            cards.addWidget(card, 1)
        layout.addLayout(cards)

        note = QLabel(
            t(
                "UiModeDialog",
                "说明：没有改用 Electron / Tauri / Flutter —— 它们的内存占用更高，且无法直接调用"
                " Windows 原生亚克力。当前 Qt + DWM 方案更轻，效果也更接近系统原生。",
            )
        )
        note.setObjectName("Tiny")
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        back = QPushButton(t("UiModeDialog", "返回"))
        back.setObjectName("Ghost")
        back.clicked.connect(self.reject)
        buttons.addWidget(back)
        confirm = QPushButton(t("UiModeDialog", "使用此模式"))
        confirm.setObjectName("Primary")
        confirm.clicked.connect(self.accept)
        buttons.addWidget(confirm)
        layout.addLayout(buttons)

        self._choose(self.MODE_CLASSIC)

    def _choose(self, mode: str) -> None:
        self.mode = mode
        for card, value in (
            (self.classic_card, self.MODE_CLASSIC),
            (self.visual_card, self.MODE_VISUAL),
        ):
            card.setProperty("selected", value == mode)
            card.style().unpolish(card)
            card.style().polish(card)
