"""首次启动时的界面框架选择：默认推荐美化版（pywebview）。

三套框架：
- 经典版：PySide6 / Qt 自绘，最省内存；
- 美化版：pywebview + Edge WebView2（Chromium），默认推荐；
- 独立版：Electron 自带 Chromium，不依赖 WebView2，代价是占用较高。

三套共用同一套后端，选择结果写入 config.frame_mode，可在设置页随时切换（重启后生效）。
独立版需要单独的构建产物，缺失时不会阻塞启动，会退回美化版 / 经典版。
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

from ..electron_launcher import electron_installed
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
        self.title_text = title
        self._handler = None
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
        labels = [head, sub]
        for point in points:
            label = QLabel(f"· {point}")
            label.setObjectName("ModeCardPoint")
            label.setWordWrap(True)
            layout.addWidget(label)
            labels.append(label)
        # 卡片内所有文字都不吃鼠标事件，点在文字上也等同于点整张卡片
        for label in labels:
            label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addStretch(1)

    def set_handler(self, handler) -> None:
        self._handler = handler

    def mouseReleaseEvent(self, event) -> None:  # noqa: D401 - Qt 重写
        inside = self.rect().contains(event.position().toPoint())
        if event.button() == Qt.LeftButton and inside and self._handler is not None:
            self._handler()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class FrameModeDialog(QDialog):
    """确认后返回 `mode`（classic / webview / electron）。"""

    MODE_CLASSIC = "classic"
    MODE_WEBVIEW = "webview"
    MODE_ELECTRON = "electron"

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.mode = self.MODE_WEBVIEW if webview2_installed() else self.MODE_CLASSIC
        self.setObjectName("FrameModeDialog")
        self.setWindowTitle(t("FrameModeDialog", "选择界面框架"))
        self.setMinimumWidth(960)
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
                "默认推荐美化版：Chromium 渲染，视觉与动画更完整；经典版更省内存；"
                "独立版自带 Chromium，完全不依赖系统组件，但占用更高。"
                "三套界面共用同一套启动、下载、账号与联机内核，随时可在设置页切换。",
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
            t("FrameModeDialog", "美化版 · pywebview（推荐）"),
            t("FrameModeDialog", "Chromium 渲染 · 玻璃拟态 · 参考主流启动器"),
            [
                t("FrameModeDialog", "Edge WebView2（Chromium）渲染，CSS 动画与视觉上限更高"),
                t("FrameModeDialog", "下载、内容、账号、联机、工具、设置与经典版功能一致"),
                t("FrameModeDialog", "可随时在设置页切回经典版；缺少运行时按提示安装"),
                runtime_note,
            ],
        )
        electron_note = (
            t("FrameModeDialog", "独立版已内置，首次切换会自动释放")
            if electron_installed()
            else t("FrameModeDialog", "未检测到独立版（源码运行需先构建，缺失时自动退回）")
        )
        self.electron_card = _FrameCard(
            t("FrameModeDialog", "独立版 · Electron"),
            t("FrameModeDialog", "脱离依赖 · 自带 Chromium · 占用较高"),
            [
                t("FrameModeDialog", "自带 Chromium 内核，不依赖 WebView2，装不上运行时的电脑也能用"),
                t("FrameModeDialog", "界面与美化版完全一致，共用同一套 HTML / CSS / JS"),
                t("FrameModeDialog", "缺点：安装包与内存占用都比前两种更高"),
                electron_note,
            ],
        )
        for card, mode in (
            (self.webview_card, self.MODE_WEBVIEW),
            (self.classic_card, self.MODE_CLASSIC),
            (self.electron_card, self.MODE_ELECTRON),
        ):
            card.set_handler(lambda m=mode: self._choose(m))
            cards.addWidget(card, 1)
        layout.addLayout(cards)

        note = QLabel(
            t(
                "FrameModeDialog",
                "美化版依赖 WebView2 Runtime。Win10/11 通常随 Edge 预装；缺失时启动器会引导下载并退出，"
                "也可把运行时解包到安装目录 webview2 文件夹使用内置版本。"
                "独立版不需要 WebView2。单文件版已内置独立版，选中后会释放到 data/electron/app，之后直接复用。",
            )
        )
        note.setObjectName("Tiny")
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QHBoxLayout()
        # 明确显示「点确定后会进哪一版」，避免高亮看不出来导致选错
        self.selection = QLabel()
        self.selection.setObjectName("Muted")
        buttons.addWidget(self.selection)
        buttons.addStretch(1)
        confirm = QPushButton(t("FrameModeDialog", "使用此框架"))
        confirm.setObjectName("Primary")
        confirm.clicked.connect(self.accept)
        buttons.addWidget(confirm)
        layout.addLayout(buttons)

        self._choose(self.mode)

    def _choose(self, mode: str) -> None:
        self.mode = mode
        chosen = None
        for card, value in (
            (self.classic_card, self.MODE_CLASSIC),
            (self.webview_card, self.MODE_WEBVIEW),
            (self.electron_card, self.MODE_ELECTRON),
        ):
            card.setProperty("selected", value == mode)
            card.style().unpolish(card)
            card.style().polish(card)
            if value == mode:
                chosen = card
        if chosen is not None:
            self.selection.setText(f"✓  {chosen.title_text}")

    def accept(self) -> None:  # noqa: D401 - Qt 重写
        """未选择时默认推荐美化版；运行时缺失则回退经典版保证能进入界面。"""
        if self.mode not in (self.MODE_CLASSIC, self.MODE_WEBVIEW, self.MODE_ELECTRON):
            self.mode = self.MODE_WEBVIEW if webview2_installed() else self.MODE_CLASSIC
        super().accept()
