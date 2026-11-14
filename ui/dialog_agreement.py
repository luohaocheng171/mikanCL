"""用户协议确认对话框：标签页展示全部条款，必须勾选后才能继续。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .. import agreement
from .widgets import Card


class AgreementDialog(QDialog):
    """协议确认框：不同意则对话框返回 Rejected，调用方据此直接退出程序。"""

    def __init__(
        self, language: str, parent: QWidget | None = None, view_only: bool = False
    ):
        super().__init__(parent)
        data = agreement.texts(language)
        self.view_only = view_only
        self.setWindowTitle(data["title"])
        self.setModal(True)
        self.setMinimumSize(820, 620)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        title = QLabel(data["title"])
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        root.addWidget(title)

        intro = QLabel(data["intro"])
        intro.setWordWrap(True)
        intro.setObjectName("Tiny")
        if not view_only:
            root.addWidget(intro)

        # 所有条款以标签页形式并列展示，确认区固定在标签页下方
        self.tabs = QTabWidget()
        for name, body in data["sections"]:
            browser = QTextBrowser()
            browser.setOpenExternalLinks(False)
            browser.setPlainText(body)
            browser.setStyleSheet("border: none; background: transparent; padding: 6px;")
            self.tabs.addTab(browser, name)
        root.addWidget(self.tabs, 1)

        footer = Card(margins=14, spacing=10)
        if view_only:
            buttons = QHBoxLayout()
            buttons.addStretch(1)
            close_button = QPushButton(data["close"])
            close_button.setObjectName("PrimaryCompact")
            close_button.setFixedHeight(34)
            close_button.clicked.connect(self.accept)
            buttons.addWidget(close_button)
            footer.body.addLayout(buttons)
            root.addWidget(footer)
            return

        self.confirm_check = QCheckBox(data["checkbox"])
        self.confirm_check.stateChanged.connect(self._sync_button)
        footer.body.addWidget(self.confirm_check)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.decline_button = QPushButton(data["decline"])
        self.decline_button.setObjectName("GhostCompact")
        self.decline_button.setFixedHeight(34)
        self.decline_button.clicked.connect(self.reject)
        buttons.addWidget(self.decline_button)

        self.accept_button = QPushButton(data["accept"])
        self.accept_button.setObjectName("PrimaryCompact")
        self.accept_button.setFixedHeight(34)
        self.accept_button.setEnabled(False)
        self.accept_button.clicked.connect(self.accept)
        buttons.addWidget(self.accept_button)
        footer.body.addLayout(buttons)
        root.addWidget(footer)

        # 未勾选时禁止同意；关闭窗口（Esc / 右上角）等同于不同意
        self.setWindowFlag(Qt.WindowCloseButtonHint, True)

    def _sync_button(self, _state: int = 0) -> None:
        self.accept_button.setEnabled(self.confirm_check.isChecked())


__all__ = ["AgreementDialog"]
