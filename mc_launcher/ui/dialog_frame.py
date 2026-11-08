"""首次启动时的界面框架选择：经典 Qt / 美化 pywebview。

只做 Windows，所以美化版固定走 Edge WebView2（Chromium 内核），
不会加载 Qt 主窗口；选择结果写入 config.frame_mode。
两套框架共用同一套后端，可在设置页随时双向切换（重启后生效）。
"""

from __future__ import annotations

import os
import winreg
from pathlib import Path

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

_RUNTIME_GUID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"


def webview2_installed() -> bool:
    """轻量检测 WebView2 Runtime（不导入 pywebview，避免启动开销）。"""
    paths = [
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{_RUNTIME_GUID}"),
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{_RUNTIME_GUID}"),
        (winreg.HKEY_CURRENT_USER, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{_RUNTIME_GUID}"),
    ]
    for root, path in paths:
        try:
            with winreg.OpenKey(root, path) as key:
                version, _ = winreg.QueryValueEx(key, "pv")
        except OSError:
            continue
        if version and version != "0.0.0.0":
            return True
    for base in (
        os.environ.get("ProgramFiles(x86)", ""),
        os.environ.get("ProgramFiles", ""),
    ):
        if not base:
            continue
        folder = Path(base) / "Microsoft" / "EdgeWebView" / "Application"
        if folder.exists() and list(folder.glob("*/msedgewebview2.exe")):
            return True
    return False


class _FrameCard(QFrame):
    """可点选的框架卡片：标题 + 副标题 + 要点列表。"""

    def __init__(self, title: str, subtitle: str, points: list[str], parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ModeCard")
        self.setCursor(Qt.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(7)
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
        layout.addStretch(1)


class FrameModeDialog(QDialog):
    """确认后返回 `mode`（classic / webview）。"""

    MODE_CLASSIC = "classic"
    MODE_WEBVIEW = "webview"

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.mode = self.MODE_CLASSIC
        self.setWindowTitle(t("FrameModeDialog", "选择界面框架"))
        self.setMinimumWidth(720)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        title = QLabel(t("FrameModeDialog", "选择界面框架"))
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        intro = QLabel(
            t(
                "FrameModeDialog",
                "两套界面共用同一套启动、下载、账号与联机内核，功能完全对齐。"
                "只加载所选框架，未选中的模块不会占用内存。"
                "随时可在设置页双向切换，无需重新选择。",
            )
        )
        intro.setObjectName("Muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.classic_card = _FrameCard(
            t("FrameModeDialog", "经典版 · Qt"),
            t("FrameModeDialog", "稳定 · 省内存 · 功能完整"),
            [
                t("FrameModeDialog", "纯 Qt 绘制，不依赖任何浏览器运行时"),
                t("FrameModeDialog", "所有页面（下载、内容、联机、工具、设置）全部可用"),
                t("FrameModeDialog", "启动最快，适合 4 代 i5 / 核显等老机器"),
            ],
        )
        runtime_note = (
            t("FrameModeDialog", "已检测到 WebView2 Runtime")
            if webview2_installed()
            else t("FrameModeDialog", "未检测到 WebView2 Runtime（首次使用会引导安装）")
        )
        self.webview_card = _FrameCard(
            t("FrameModeDialog", "美化版 · pywebview"),
            t("FrameModeDialog", "Chromium 渲染 · 玻璃拟态 · 参考主流启动器"),
            [
                t("FrameModeDialog", "Edge WebView2（Chromium）渲染，CSS 动画与视觉上限更高"),
                t("FrameModeDialog", "下载、内容、账号、联机、工具、设置与经典版功能一致"),
                t("FrameModeDialog", "可随时在设置页切回经典版；缺少运行时按提示安装"),
                runtime_note,
            ],
        )
        for card, mode in (
            (self.classic_card, self.MODE_CLASSIC),
            (self.webview_card, self.MODE_WEBVIEW),
        ):
            card.mousePressEvent = lambda event, m=mode: self._choose(m)  # type: ignore[method-assign]
            cards.addWidget(card, 1)
        layout.addLayout(cards)

        note = QLabel(
            t(
                "FrameModeDialog",
                "美化版依赖 WebView2 Runtime。Win10/11 通常随 Edge 预装；缺失时启动器会引导下载并退出，"
                "也可把运行时解包到安装目录 webview2 文件夹使用内置版本。",
            )
        )
        note.setObjectName("Tiny")
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        confirm = QPushButton(t("FrameModeDialog", "使用此框架"))
        confirm.setObjectName("Primary")
        confirm.clicked.connect(self.accept)
        buttons.addWidget(confirm)
        layout.addLayout(buttons)

        self._choose(self.MODE_CLASSIC)

    def _choose(self, mode: str) -> None:
        self.mode = mode
        for card, value in (
            (self.classic_card, self.MODE_CLASSIC),
            (self.webview_card, self.MODE_WEBVIEW),
        ):
            card.setProperty("selected", value == mode)
            card.style().unpolish(card)
            card.style().polish(card)

    def accept(self) -> None:  # noqa: D401 - Qt 重写
        """未选择时默认经典版，保证一定能进入界面。"""
        if self.mode not in (self.MODE_CLASSIC, self.MODE_WEBVIEW):
            self.mode = self.MODE_CLASSIC
        super().accept()
