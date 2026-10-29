"""账号管理页：离线账号、微软正版设备码登录、第三方外置登录。"""

from __future__ import annotations

import shutil
import threading
import time
import urllib.parse
from pathlib import Path

from PySide6.QtCore import QThread, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices, QImage
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from PySide6.QtWebEngineWidgets import QWebEngineView

from .. import APP_NAME, USER_AGENT, auth
from ..config import DATA_DIR
from ..auth import (
    MS_LEGACY_REDIRECT,
    Account,
    AuthError,
    DeviceFlow,
    MicrosoftAuth,
    authlib_login,
)
from ..context import AppContext, wait_thread
from ..i18n import t
from .skin_view import SkinPreview3D
from .theme import make_avatar
from .widgets import Badge, Card, card_title_row, page_header


class DeviceCodeWorker(QThread):
    ok = Signal(object)
    failed = Signal(str)

    def __init__(self, client_id: str, parent=None):
        super().__init__(parent)
        self.client_id = client_id

    def run(self) -> None:
        try:
            self.ok.emit(MicrosoftAuth(self.client_id).start_device_flow())
        except AuthError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"发起微软登录失败：{exc}")


class MicrosoftPollWorker(QThread):
    ok = Signal(object)
    failed = Signal(str)
    status = Signal(str)

    def __init__(self, client_id: str, flow: DeviceFlow, cancel: threading.Event, parent=None):
        super().__init__(parent)
        self.client_id = client_id
        self.flow = flow
        self.cancel_event = cancel

    def run(self) -> None:
        try:
            account = MicrosoftAuth(self.client_id).poll(
                self.flow, cancel=self.cancel_event, log=self.status.emit
            )
            self.ok.emit(account)
        except AuthError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"微软登录失败：{exc}")


class MicrosoftLoginDialog(QDialog):
    def __init__(self, client_id: str, parent=None):
        super().__init__(parent)
        self.client_id = client_id
        self.cancel_event = threading.Event()
        self.account: Account | None = None
        self._flow: DeviceFlow | None = None
        self._code_worker: DeviceCodeWorker | None = None
        self._poll_worker: MicrosoftPollWorker | None = None
        self.setWindowTitle("微软正版登录")
        self.setModal(True)
        self.setMinimumWidth(470)
        self._build()
        self._start_code()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(12)
        title = QLabel("使用微软账号登录")
        title.setObjectName("CardTitle")
        layout.addWidget(title)
        hint = QLabel(
            "点击下方按钮打开微软登录页面，输入下面的设备码并授权。\n"
            "授权完成后此窗口会自动关闭，登录令牌将保存在本地。"
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.code_label = QLabel("正在获取设备码…")
        self.code_label.setAlignment(Qt.AlignCenter)
        self.code_label.setStyleSheet(
            "font-size: 28px; font-weight: 700; color: #8fe89b; letter-spacing: 4px;"
            "background-color: #0e1712; border: 1px solid #24362b; border-radius: 10px; padding: 14px;"
        )
        self.code_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.code_label)

        self.status_label = QLabel("准备连接微软登录服务…")
        self.status_label.setObjectName("Tiny")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        row = QHBoxLayout()
        self.open_button = QPushButton("打开登录页面")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self._open_page)
        row.addWidget(self.open_button)
        self.copy_button = QPushButton("复制设备码")
        self.copy_button.setObjectName("Ghost")
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self._copy_code)
        row.addWidget(self.copy_button)
        row.addStretch(1)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setObjectName("Ghost")
        self.cancel_button.clicked.connect(self.reject)
        row.addWidget(self.cancel_button)
        layout.addLayout(row)

    def _start_code(self) -> None:
        self._code_worker = DeviceCodeWorker(self.client_id, self)
        self._code_worker.ok.connect(self._on_flow)
        self._code_worker.failed.connect(self._on_failed)
        self._code_worker.start()

    def _on_flow(self, flow: DeviceFlow) -> None:
        self._flow = flow
        self.code_label.setText(flow.user_code or "--------")
        self.open_button.setEnabled(True)
        self.copy_button.setEnabled(True)
        self.status_label.setText(
            f"请在浏览器中访问 {flow.verification_uri} 并输入设备码。正在等待授权…"
        )
        self._poll_worker = MicrosoftPollWorker(self.client_id, flow, self.cancel_event, self)
        self._poll_worker.ok.connect(self._on_account)
        self._poll_worker.failed.connect(self._on_failed)
        self._poll_worker.status.connect(self.status_label.setText)
        self._poll_worker.start()
        self._open_page()

    def _open_page(self) -> None:
        if self._flow is not None:
            QDesktopServices.openUrl(QUrl(self._flow.verification_uri))

    def _copy_code(self) -> None:
        if self._flow is not None:
            QApplication.clipboard().setText(self._flow.user_code)
            self.status_label.setText("设备码已复制，请粘贴到微软登录页面。")

    def _on_account(self, account: Account) -> None:
        self.account = account
        self.accept()

    def _on_failed(self, message: str) -> None:
        if self._poll_worker is None:
            message = (
                f"{message}\n\n"
                "若提示应用不存在或无权限，说明当前 Client ID 不可用于设备码登录。\n"
                "可在“设置 → 账号与登录”填写自己注册的 Azure 应用 Client ID，\n"
                "或改用账号页的“浏览器登录”兼容模式。"
            )
        self.status_label.setText(message)
        if self._poll_worker is None:
            QMessageBox.warning(self, APP_NAME, message)

    def reject(self) -> None:
        self.cancel_event.set()
        super().reject()


class BrowserLoginWorker(QThread):
    ok = Signal(object)
    failed = Signal(str)

    def __init__(self, access_token: str, refresh_token: str, parent=None):
        super().__init__(parent)
        self.access_token = access_token
        self.refresh_token = refresh_token

    def run(self) -> None:
        try:
            self.ok.emit(
                MicrosoftAuth().login_with_live_tokens(self.access_token, self.refresh_token)
            )
        except AuthError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"微软登录失败：{exc}")


class BrowserMicrosoftDialog(QDialog):
    """旧版 Live Connect 浏览器登录：兼容所有个人微软账号，无需自备 Client ID。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.account: Account | None = None
        self._worker: BrowserLoginWorker | None = None
        self.setWindowTitle("微软正版登录 · 浏览器")
        self.resize(520, 720)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 12)
        layout.setSpacing(8)
        hint = QLabel("在下方页面登录微软账号并授权，完成后窗口会自动关闭。")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.view = QWebEngineView(self)
        self.view.urlChanged.connect(self._on_url_changed)
        self.view.load(QUrl(MicrosoftAuth.legacy_authorize_url()))
        layout.addWidget(self.view, 1)
        self.status_label = QLabel("等待登录授权…")
        self.status_label.setObjectName("Tiny")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("取消")
        cancel.setObjectName("Ghost")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        layout.addLayout(row)

    def _on_url_changed(self, url: QUrl) -> None:
        text = url.toString()
        if not text.startswith(MS_LEGACY_REDIRECT):
            return
        fragment = dict(
            urllib.parse.parse_qsl(urllib.parse.urlsplit(text).fragment, keep_blank_values=True)
        )
        access_token = str(fragment.get("access_token") or "")
        if not access_token:
            error = fragment.get("error_description") or fragment.get("error") or "未返回访问令牌"
            self.status_label.setText(f"登录失败：{error}")
            return
        self.status_label.setText("授权成功，正在获取 Minecraft 档案…")
        self._worker = BrowserLoginWorker(
            access_token, str(fragment.get("refresh_token") or ""), self
        )
        self._worker.ok.connect(self._on_account)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_account(self, account: Account) -> None:
        self.account = account
        self.accept()

    def _on_failed(self, message: str) -> None:
        self.status_label.setText(message)

    def reject(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(800)
        super().reject()


class AuthlibLoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.account: Account | None = None
        self._worker: AuthlibWorker | None = None
        self.setWindowTitle("第三方外置登录")
        self.setModal(True)
        self.setMinimumWidth(460)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(12)
        title = QLabel("登录第三方验证服务器")
        title.setObjectName("CardTitle")
        layout.addWidget(title)
        hint = QLabel(
            "填写你的外置登录服务器（Yggdrasil API 根地址，例如 "
            "https://littleskin.cn/api/yggdrasil）。启动时会自动下载 authlib-injector 注入游戏。"
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()
        form.setSpacing(10)
        self.server_edit = QLineEdit()
        self.server_edit.setPlaceholderText("https://littleskin.cn/api/yggdrasil")
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("邮箱或用户名")
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText("密码")
        form.addRow("服务器地址", self.server_edit)
        form.addRow("账号", self.username_edit)
        form.addRow("密码", self.password_edit)
        layout.addLayout(form)

        self.status_label = QLabel("")
        self.status_label.setObjectName("Tiny")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        buttons = QDialogButtonBox()
        self.login_button = buttons.addButton("登录", QDialogButtonBox.AcceptRole)
        buttons.addButton("取消", QDialogButtonBox.RejectRole)
        self.login_button.clicked.connect(self._login)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _login(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        server = self.server_edit.text().strip()
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        if not server or not username:
            QMessageBox.warning(self, APP_NAME, "请填写服务器地址和账号。")
            return
        self.login_button.setEnabled(False)
        self.status_label.setText("正在登录，请稍候…")
        self._worker = AuthlibWorker(server, username, password, self)
        self._worker.ok.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_done(self, account: Account) -> None:
        self.account = account
        self.accept()

    def _on_failed(self, message: str) -> None:
        self.login_button.setEnabled(True)
        self.status_label.setText(message)

    def reject(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(200)
        super().reject()


class AuthlibWorker(QThread):
    ok = Signal(object)
    failed = Signal(str)

    def __init__(self, server: str, username: str, password: str, parent=None):
        super().__init__(parent)
        self.server = server
        self.username = username
        self.password = password

    def run(self) -> None:
        try:
            self.ok.emit(authlib_login(self.server, self.username, self.password))
        except AuthError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"外置登录失败：{exc}")


class RefreshWorker(QThread):
    ok = Signal(object)
    failed = Signal(str)

    def __init__(self, client_id: str, account: Account, parent=None):
        super().__init__(parent)
        self.client_id = client_id
        self.account = account

    def run(self) -> None:
        try:
            self.ok.emit(MicrosoftAuth(self.client_id).refresh(self.account))
        except AuthError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"刷新失败：{exc}")


class SkinUploadWorker(QThread):
    ok = Signal(str)
    failed = Signal(str)

    def __init__(self, account: Account, path: str, slim: bool, log=None, parent=None):
        super().__init__(parent)
        self.account = account
        self.path = path
        self.slim = slim
        self._log = log

    def run(self) -> None:
        try:
            auth.validate_skin_file(self.path)
            skin_url = auth.upload_skin(
                self.account, self.path, slim=self.slim, log=self._log
            )
            self.ok.emit(skin_url or "")
        except AuthError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"上传皮肤失败：{exc}")


class SkinLookupWorker(QThread):
    """通过正版账号名查询皮肤并下载到本地。"""

    ok = Signal(dict)
    failed = Signal(str)

    def __init__(self, name: str, dest_dir: Path, parent=None):
        super().__init__(parent)
        self.name = name
        self.dest_dir = dest_dir

    def run(self) -> None:
        try:
            info = auth.lookup_skin_by_name(self.name)
            url = str(info.get("skin_url") or "")
            if url:
                destination = self.dest_dir / f"{info.get('name') or self.name}.png"
                auth.download_skin_image(url, destination)
                info["local_path"] = str(destination)
            self.ok.emit(info)
        except AuthError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"查询皮肤失败：{exc}")


class AccountsPage(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self._workers: list[QThread] = []
        self._skin_manager = QNetworkAccessManager(self)
        self._skin_reply: QNetworkReply | None = None
        self._skin_url = ""
        self._skin_image: QImage | None = None
        self._skin_upload_worker: SkinUploadWorker | None = None
        self._skin_lookup_worker: SkinLookupWorker | None = None
        self._skin_uploading = False
        self._build()
        self.ctx.bus.accounts_changed.connect(self.refresh)
        self.refresh()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 20, 26, 20)
        outer.setSpacing(16)
        header, header_layout = page_header(
            self.tr("账号管理"),
            self.tr("离线账号、微软正版账号与第三方外置登录，登录信息仅保存在本地"),
        )
        add_offline = QPushButton(self.tr("添加离线账号"))
        add_offline.clicked.connect(self._add_offline)
        header_layout.addWidget(add_offline)
        add_ms = QPushButton(self.tr("微软正版登录"))
        add_ms.setObjectName("Primary")
        add_ms.setToolTip(self.tr("内置浏览器登录微软账号，兼容所有个人账号"))
        add_ms.clicked.connect(self._login_microsoft_browser)
        header_layout.addWidget(add_ms)
        add_ms_code = QPushButton(self.tr("设备码登录"))
        add_ms_code.setObjectName("Chip")
        add_ms_code.setToolTip(self.tr("设备码流程需要可用的 Azure Client ID，可在设置中配置"))
        add_ms_code.clicked.connect(self._login_microsoft)
        header_layout.addWidget(add_ms_code)
        add_authlib = QPushButton(self.tr("第三方外置登录"))
        add_authlib.setObjectName("Chip")
        add_authlib.clicked.connect(self._login_authlib)
        header_layout.addWidget(add_authlib)
        outer.addWidget(header)

        body = QHBoxLayout()
        body.setSpacing(16)
        outer.addLayout(body, 1)

        list_card = Card()
        list_card.body.addWidget(
            card_title_row(self.tr("账号列表"), self.tr("双击账号可设为当前账号"))
        )
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(
            [self.tr("账号"), self.tr("类型"), self.tr("状态")]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 180)
        self.table.setColumnWidth(1, 100)
        self.table.itemSelectionChanged.connect(self._show_selected)
        self.table.doubleClicked.connect(lambda _index: self._set_current())
        list_card.body.addWidget(self.table, 1)
        body.addWidget(list_card, 2)

        detail_card = Card()
        detail_card.setFixedWidth(360)
        detail_card.body.addWidget(
            card_title_row(self.tr("账号详情"), self.tr("当前账号将用于启动游戏"))
        )
        self.avatar = QLabel()
        self.avatar.setFixedSize(72, 72)
        detail_card.body.addWidget(self.avatar, alignment=Qt.AlignHCenter)
        self.name_label = QLabel(self.tr("未选择账号"))
        self.name_label.setAlignment(Qt.AlignHCenter)
        self.name_label.setStyleSheet("font-size: 18px; font-weight: 700;")
        detail_card.body.addWidget(self.name_label)
        self.type_badge = Badge(self.tr("离线模式"), "gray")
        detail_card.body.addWidget(self.type_badge, alignment=Qt.AlignHCenter)
        self.uuid_label = QLabel("")
        self.uuid_label.setObjectName("Tiny")
        self.uuid_label.setWordWrap(True)
        detail_card.body.addWidget(self.uuid_label)
        self.server_label = QLabel("")
        self.server_label.setObjectName("Tiny")
        self.server_label.setWordWrap(True)
        detail_card.body.addWidget(self.server_label)
        self.expire_label = QLabel("")
        self.expire_label.setObjectName("Tiny")
        detail_card.body.addWidget(self.expire_label)
        detail_card.body.addStretch(1)

        self.use_button = QPushButton(self.tr("设为当前账号"))
        self.use_button.setObjectName("Primary")
        self.use_button.clicked.connect(self._set_current)
        detail_card.body.addWidget(self.use_button)
        self.refresh_button = QPushButton(self.tr("刷新登录令牌"))
        self.refresh_button.clicked.connect(self._refresh_token)
        detail_card.body.addWidget(self.refresh_button)
        self.delete_button = QPushButton(self.tr("删除账号"))
        self.delete_button.setObjectName("Danger")
        self.delete_button.clicked.connect(self._delete)
        detail_card.body.addWidget(self.delete_button)

        skin_card = Card()
        skin_card.setFixedWidth(360)
        skin_card.body.addWidget(
            card_title_row(self.tr("皮肤"), self.tr("微软正版账号可上传自定义皮肤"))
        )
        self.skin_preview = SkinPreview3D()
        skin_card.body.addWidget(self.skin_preview, alignment=Qt.AlignHCenter)
        self.skin_status = QLabel(self.tr("未选择账号"))
        self.skin_status.setObjectName("Tiny")
        self.skin_status.setAlignment(Qt.AlignHCenter)
        self.skin_status.setWordWrap(True)
        skin_card.body.addWidget(self.skin_status)
        self.skin_hint = QLabel(
            self.tr("仅微软正版账号可上传皮肤；离线/外置账号请到对应皮肤站修改。")
        )
        self.skin_hint.setObjectName("Muted")
        self.skin_hint.setWordWrap(True)
        skin_card.body.addWidget(self.skin_hint)

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel(self.tr("皮肤模型")))
        self.skin_model_combo = QComboBox()
        self.skin_model_combo.addItem(self.tr("经典（Classic）"), "classic")
        self.skin_model_combo.addItem(self.tr("纤细（Slim / Alex）"), "slim")
        self.skin_model_combo.currentIndexChanged.connect(self._on_skin_model_changed)
        model_row.addWidget(self.skin_model_combo, 1)
        skin_card.body.addLayout(model_row)
        self.skin_preview.set_model("classic")

        self.skin_upload_button = QPushButton(self.tr("上传皮肤…"))
        self.skin_upload_button.setEnabled(False)
        self.skin_upload_button.clicked.connect(self._choose_skin_file)
        skin_card.body.addWidget(self.skin_upload_button)

        skin_tools = QHBoxLayout()
        skin_tools.setSpacing(8)
        self.skin_local_button = QPushButton(self.tr("使用本地皮肤…"))
        self.skin_local_button.setObjectName("Ghost")
        self.skin_local_button.clicked.connect(self._choose_local_skin)
        skin_tools.addWidget(self.skin_local_button)
        self.skin_search_button = QPushButton(self.tr("搜索正版皮肤…"))
        self.skin_search_button.setObjectName("Ghost")
        self.skin_search_button.clicked.connect(self._search_premium_skin)
        skin_tools.addWidget(self.skin_search_button)
        skin_card.body.addLayout(skin_tools)
        skin_note = QLabel(
            self.tr(
                "本地上传支持 64×64 / 64×32 PNG（≤24 KB）。离线账号的本地皮肤会写入 "
                "CustomSkinLoader/LocalSkin，需安装该 Mod 才能在游戏内显示。"
            )
        )
        skin_note.setObjectName("Tiny")
        skin_note.setWordWrap(True)
        skin_card.body.addWidget(skin_note)

        right_column = QWidget()
        right_layout = QVBoxLayout(right_column)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(16)
        right_layout.addWidget(detail_card, alignment=Qt.AlignHCenter)
        right_layout.addWidget(skin_card, alignment=Qt.AlignHCenter)
        right_layout.addStretch(1)
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        right_scroll.setFixedWidth(382)
        right_scroll.setWidget(right_column)
        body.addWidget(right_scroll)

        tip = QLabel(
            self.tr(
                "提示：微软正版登录采用设备码流程，不会接触你的密码；第三方登录需要填写服务器地址与密码，"
                "密码不会保存，只保存登录令牌。"
            )
        )
        tip.setObjectName("Muted")
        tip.setWordWrap(True)
        outer.addWidget(tip)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        accounts = self.ctx.accounts.accounts
        selected_id = self.ctx.accounts.selected_id
        self.table.blockSignals(True)
        self.table.setRowCount(len(accounts))
        for row, account in enumerate(accounts):
            name_item = QTableWidgetItem(account.name or t("AccountsPage", "未命名"))
            name_item.setData(Qt.UserRole, account.id)
            if account.id == selected_id:
                font = name_item.font()
                font.setBold(True)
                name_item.setFont(font)
                name_item.setToolTip(t("AccountsPage", "当前账号"))
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QTableWidgetItem(t("AccountsPage", account.type_label)))
            status = t("AccountsPage", "已登录") if account.type == "offline" else (
                t("AccountsPage", "令牌有效")
                if account.access_token and not account.token_expired
                else t("AccountsPage", "需要重新登录")
            )
            self.table.setItem(row, 2, QTableWidgetItem(status))
            if account.id == selected_id:
                self.table.selectRow(row)
        self.table.blockSignals(False)
        if self.table.currentRow() < 0 and accounts:
            self.table.selectRow(0)
        self._show_selected()

    def _current_account_id(self) -> str:
        row = self.table.currentRow()
        if row < 0:
            return ""
        item = self.table.item(row, 0)
        return str(item.data(Qt.UserRole) or "") if item else ""

    def _show_selected(self) -> None:
        account = self.ctx.accounts.get(self._current_account_id())
        if account is None:
            self.name_label.setText(self.tr("未选择账号"))
            self.avatar.clear()
            self.uuid_label.setText("")
            self.server_label.setText("")
            self.expire_label.setText("")
            self.use_button.setEnabled(False)
            self.refresh_button.setEnabled(False)
            self.delete_button.setEnabled(False)
            self._update_skin_card(None)
            return
        self.avatar.setPixmap(make_avatar(account.name or "Steve", 72))
        suffix = t("AccountsPage", "（当前）") if account.id == self.ctx.accounts.selected_id else ""
        self.name_label.setText(account.name + suffix)
        kinds = {"offline": "gray", "microsoft": "blue", "authlib": "orange"}
        self.type_badge.setText(t("AccountsPage", account.type_label))
        self.type_badge.set_kind(kinds.get(account.type, "gray"))
        self.uuid_label.setText(
            t(
                "AccountsPage",
                "UUID：{0}",
                account.uuid or t("AccountsPage", "未绑定"),
            )
        )
        self.server_label.setText(
            t("AccountsPage", "验证服务器：{0}", account.auth_server)
            if account.auth_server
            else ""
        )
        self.expire_label.setText(self._token_validity_text(account))
        self.use_button.setEnabled(account.id != self.ctx.accounts.selected_id)
        self.refresh_button.setEnabled(account.type == "microsoft" and bool(account.refresh_token))
        self.delete_button.setEnabled(len(self.ctx.accounts.accounts) > 1)
        self._update_skin_card(account)

    def _token_validity_text(self, account: Account) -> str:
        """微软账号的令牌刷新时间与剩余有效期。"""
        if account.type != "microsoft":
            return ""
        parts: list[str] = []
        if account.last_refresh:
            parts.append(
                t("AccountsPage", "上次刷新：")
                + time.strftime("%Y-%m-%d %H:%M", time.localtime(account.last_refresh))
            )
        if account.expires_at:
            remain = account.expires_at - time.time()
            if remain <= 0:
                state = t("AccountsPage", "已过期")
            elif remain >= 3600:
                state = t(
                    "AccountsPage",
                    "剩余 {0} 小时 {1} 分",
                    int(remain // 3600),
                    int(remain % 3600 // 60),
                )
            else:
                state = t("AccountsPage", "剩余 {0} 分钟", max(1, int(remain // 60)))
            parts.append(
                t(
                    "AccountsPage",
                    "有效期至 {0}（{1}）",
                    time.strftime("%m-%d %H:%M", time.localtime(account.expires_at)),
                    state,
                )
            )
        return " · ".join(parts)

    # ------------------------------------------------------------------
    # 皮肤
    # ------------------------------------------------------------------
    def _update_skin_card(self, account: Account | None) -> None:
        microsoft = bool(
            account is not None and account.type == "microsoft" and account.access_token
        )
        self._sync_skin_controls(account, microsoft)
        self._sync_skin_preview(account, microsoft)

    def _sync_skin_controls(self, account: Account | None, microsoft: bool) -> None:
        """只负责按钮可用状态与账号类型提示，不碰预览与皮肤地址。"""
        editable = microsoft and not self._skin_uploading
        self.skin_upload_button.setEnabled(editable)
        self.skin_model_combo.setEnabled(editable)
        self.skin_local_button.setEnabled(account is not None and not self._skin_uploading)
        self.skin_search_button.setEnabled(not self._skin_uploading)
        self.skin_hint.setText(
            self.tr("仅微软正版账号可上传皮肤；离线/外置账号请到对应皮肤站修改。")
        )
        if account is None:
            self.skin_status.setText(self.tr("未选择账号"))
        elif account.type != "microsoft":
            self.skin_status.setText(self.tr("当前账号类型不支持上传皮肤"))
        elif not account.access_token:
            self.skin_status.setText(self.tr("登录状态已失效，请刷新登录令牌"))

    def _sync_skin_preview(self, account: Account | None, microsoft: bool) -> None:
        """只负责预览图与本地/远程皮肤状态文案。"""
        if account is None:
            self._stop_skin_preview()
            self._skin_url = ""
            self._skin_image = None
            self.skin_preview.clear_skin()
            return
        local_path = Path(account.skin_path) if account.skin_path else None
        if local_path is not None and local_path.is_file():
            image = QImage(str(local_path))
            if not image.isNull():
                self._stop_skin_preview()
                self._skin_url = ""
                self._skin_image = image
                self.skin_preview.set_skin(image)
                self.skin_status.setText(self.tr("本地皮肤 · 启动时自动应用"))
                self.skin_hint.setText(
                    "本地皮肤会写入 CustomSkinLoader/LocalSkin，需安装 CustomSkinLoader 才能在游戏内显示。"
                )
                return

        url = account.skin_url or ""
        if not url:
            self._stop_skin_preview()
            self._skin_url = ""
            self._skin_image = None
            self.skin_preview.clear_skin()
            if microsoft:
                self.skin_status.setText(self.tr("尚未设置自定义皮肤"))
            return
        if url != self._skin_url:
            self._start_skin_preview(url)
        elif self._skin_image is not None:
            self.skin_preview.set_skin(self._skin_image)
            if microsoft:
                self.skin_status.setText(self.tr("皮肤预览已加载"))

    def _on_skin_model_changed(self) -> None:
        self.skin_preview.set_model(str(self.skin_model_combo.currentData() or "classic"))

    def _stop_skin_preview(self) -> None:
        if self._skin_reply is not None:
            reply = self._skin_reply
            self._skin_reply = None
            reply.abort()
            reply.deleteLater()

    def _start_skin_preview(self, url: str) -> None:
        self._stop_skin_preview()
        self._skin_url = url
        self._skin_image = None
        self.skin_preview.clear_skin()
        self.skin_status.setText(self.tr("正在加载皮肤预览…"))
        if not url.lower().startswith(("http://", "https://")):
            self.skin_status.setText(self.tr("皮肤地址无效"))
            return
        request = QNetworkRequest(QUrl(url))
        request.setRawHeader(b"User-Agent", USER_AGENT.encode("utf-8"))
        reply = self._skin_manager.get(request)
        self._skin_reply = reply
        reply.finished.connect(lambda r=reply: self._on_skin_downloaded(r))

    def _on_skin_downloaded(self, reply: QNetworkReply) -> None:
        if reply is not self._skin_reply:
            reply.deleteLater()
            return
        self._skin_reply = None
        data = bytes(reply.readAll())
        failed = reply.error() != QNetworkReply.NetworkError.NoError
        reply.deleteLater()
        image = QImage()
        if failed or not data or not image.loadFromData(data, "PNG") or image.isNull():
            self._skin_image = None
            self.skin_preview.clear_skin()
            self.skin_status.setText(self.tr("皮肤预览下载失败"))
            return
        self._skin_image = image
        self.skin_preview.set_skin(image)
        self.skin_status.setText(self.tr("皮肤预览已加载"))

    def _choose_skin_file(self) -> None:
        account = self.ctx.accounts.get(self._current_account_id())
        if account is None or account.type != "microsoft" or not account.access_token:
            QMessageBox.warning(
                self, APP_NAME, self.tr("只有已登录的微软正版账号可以上传皮肤。")
            )
            return
        if self._skin_uploading:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("选择皮肤文件"), str(Path.home()), "PNG 图片 (*.png)"
        )
        if not path:
            return
        slim = str(self.skin_model_combo.currentData()) == "slim"
        self._skin_uploading = True
        self.skin_upload_button.setEnabled(False)
        self.skin_model_combo.setEnabled(False)
        self.skin_upload_button.setText(self.tr("正在上传…"))
        self.skin_status.setText(self.tr("正在上传皮肤，请稍候…"))
        worker = SkinUploadWorker(account, path, slim, self.ctx.bus.log.emit, self)
        worker.ok.connect(self._on_skin_uploaded)
        worker.failed.connect(self._on_skin_upload_failed)
        worker.finished.connect(self._on_skin_upload_finished)
        self._skin_upload_worker = worker
        worker.start()

    def _on_skin_uploaded(self, skin_url: str) -> None:
        worker = self._skin_upload_worker
        if worker is not None and skin_url:
            worker.account.skin_url = skin_url
            self.ctx.accounts.update(worker.account)
            self.ctx.bus.accounts_changed.emit()
        QMessageBox.information(self, APP_NAME, self.tr("皮肤已上传，重新进入游戏生效。"))

    def _on_skin_upload_failed(self, message: str) -> None:
        self.skin_status.setText(self.tr("皮肤上传失败"))
        QMessageBox.warning(self, APP_NAME, message)

    def _on_skin_upload_finished(self) -> None:
        worker = self._skin_upload_worker
        self._skin_upload_worker = None
        if worker is not None:
            worker.deleteLater()
        self._skin_uploading = False
        self.skin_upload_button.setText(self.tr("上传皮肤…"))
        self._update_skin_card(self.ctx.accounts.get(self._current_account_id()))

    # ---------- 本地皮肤 / 正版皮肤搜索 ----------
    def _choose_local_skin(self) -> None:
        account = self.ctx.accounts.get(self._current_account_id())
        if account is None:
            QMessageBox.information(self, APP_NAME, "请先选择或创建一个账号。")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("选择本地皮肤"), str(Path.home()), "PNG 图片 (*.png)"
        )
        if not path:
            return
        try:
            auth.validate_skin_file(path)
        except AuthError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        skins_dir = DATA_DIR / "skins"
        skins_dir.mkdir(parents=True, exist_ok=True)
        target = skins_dir / f"{account.name}.png"
        try:
            shutil.copy2(path, target)
        except OSError as exc:
            QMessageBox.warning(self, APP_NAME, f"保存皮肤失败：{exc}")
            return
        account.skin_path = str(target)
        self.ctx.accounts.update(account)
        self.ctx.bus.accounts_changed.emit()
        self.ctx.bus.toast.emit("本地皮肤已保存，启动游戏时会自动应用。")

    def _search_premium_skin(self) -> None:
        if self._skin_lookup_worker is not None and self._skin_lookup_worker.isRunning():
            return
        account = self.ctx.accounts.get(self._current_account_id())
        default = account.name if account is not None else ""
        name, ok = QInputDialog.getText(
            self,
            self.tr("搜索正版皮肤"),
            self.tr("输入正版账号名："),
            QLineEdit.Normal,
            default,
        )
        if not ok or not name.strip():
            return
        self.skin_status.setText(t("AccountsPage", "正在查询 {0} 的皮肤…", name.strip()))
        self.skin_search_button.setEnabled(False)
        worker = SkinLookupWorker(name.strip(), DATA_DIR / "skins", self)
        self._skin_lookup_worker = worker
        worker.ok.connect(self._on_skin_lookup)
        worker.failed.connect(self._on_skin_lookup_failed)
        worker.finished.connect(self._on_skin_lookup_finished)
        worker.start()

    def _on_skin_lookup(self, info: dict) -> None:
        local = str(info.get("local_path") or "")
        name = str(info.get("name") or "")
        if not local:
            QMessageBox.information(self, APP_NAME, f"账号 {name} 没有设置自定义皮肤。")
            return
        account = self.ctx.accounts.get(self._current_account_id())
        model = "纤细（Slim）" if info.get("model") == "slim" else "经典（Classic）"
        if account is None:
            QMessageBox.information(
                self, APP_NAME, f"已保存 {name} 的皮肤（{model}）到：\n{local}\n请先选择账号后再应用。"
            )
            return
        answer = QMessageBox.question(
            self,
            self.tr("应用皮肤"),
            t(
                "AccountsPage",
                "已获取 {0} 的皮肤（{1}）。\n是否保存到当前账号「{2}」作为本地皮肤？",
                name,
                model,
                account.name,
            ),
        )
        if answer != QMessageBox.Yes:
            return
        account.skin_path = local
        self.ctx.accounts.update(account)
        self.ctx.bus.accounts_changed.emit()
        self.ctx.bus.toast.emit("正版皮肤已保存为本地皮肤。")

    def _on_skin_lookup_failed(self, message: str) -> None:
        self.skin_status.setText("皮肤查询失败")
        QMessageBox.warning(self, APP_NAME, message)

    def _on_skin_lookup_finished(self) -> None:
        worker = self._skin_lookup_worker
        self._skin_lookup_worker = None
        if worker is not None:
            worker.deleteLater()
        self.skin_search_button.setEnabled(True)
        self._update_skin_card(self.ctx.accounts.get(self._current_account_id()))

    # ------------------------------------------------------------------
    def _add_offline(self) -> None:
        name, ok = QInputDialog.getText(
            self, "添加离线账号", "玩家昵称（1-16 个字符）：", QLineEdit.Normal, "Steve"
        )
        if not ok:
            return
        try:
            account = self.ctx.accounts.make_offline(name.strip())
        except AuthError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        self.ctx.accounts.add(account)
        self._sync_current()
        self.ctx.bus.accounts_changed.emit()
        self.ctx.bus.toast.emit(f"已添加离线账号：{account.name}")

    def _login_microsoft(self) -> None:
        dialog = MicrosoftLoginDialog(self.ctx.config.microsoft_client_id, self)
        if dialog.exec() == QDialog.Accepted and dialog.account is not None:
            self.ctx.accounts.add(dialog.account)
            self._sync_current()
            self.ctx.bus.accounts_changed.emit()
            self.ctx.bus.toast.emit(f"微软账号登录成功：{dialog.account.name}")

    def _login_microsoft_browser(self) -> None:
        dialog = BrowserMicrosoftDialog(self)
        if dialog.exec() == QDialog.Accepted and dialog.account is not None:
            self.ctx.accounts.add(dialog.account)
            self._sync_current()
            self.ctx.bus.accounts_changed.emit()
            self.ctx.bus.toast.emit(f"微软账号登录成功：{dialog.account.name}")

    def _login_authlib(self) -> None:
        dialog = AuthlibLoginDialog(self)
        if dialog.exec() == QDialog.Accepted and dialog.account is not None:
            self.ctx.accounts.add(dialog.account)
            self._sync_current()
            self.ctx.bus.accounts_changed.emit()
            self.ctx.bus.toast.emit(f"外置登录成功：{dialog.account.name}")

    def _set_current(self) -> None:
        account_id = self._current_account_id()
        if not account_id:
            return
        self.ctx.accounts.set_selected(account_id)
        self._sync_current()
        self.ctx.bus.accounts_changed.emit()
        account = self.ctx.accounts.selected()
        self.ctx.bus.toast.emit(
            f"当前账号：{account.name}（{t('AccountsPage', account.type_label)}）"
        )

    def _sync_current(self) -> None:
        account = self.ctx.accounts.selected()
        self.ctx.config.selected_account_id = account.id
        if account.type == "offline":
            self.ctx.config.player_name = account.name
        self.ctx.config.save()
        self.refresh()
        self.ctx.bus.config_changed.emit()

    def _refresh_token(self) -> None:
        account = self.ctx.accounts.get(self._current_account_id())
        if account is None or account.type != "microsoft":
            return
        worker = RefreshWorker(self.ctx.config.microsoft_client_id, account, self)
        worker.ok.connect(self._on_refreshed)
        worker.failed.connect(lambda message: QMessageBox.warning(self, APP_NAME, message))
        worker.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)
        self._workers.append(worker)
        worker.start()
        self.ctx.bus.toast.emit("正在刷新微软登录令牌…")

    def _on_refreshed(self, account: Account) -> None:
        self.ctx.accounts.update(account)
        self.ctx.bus.accounts_changed.emit()
        self.ctx.bus.toast.emit("登录令牌已刷新。")

    def _delete(self) -> None:
        account = self.ctx.accounts.get(self._current_account_id())
        if account is None:
            return
        answer = QMessageBox.question(
            self,
            "删除账号",
            f"确定删除账号「{account.name}」吗？本地保存的登录令牌也会被移除。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self.ctx.accounts.remove(account.id)
        except AuthError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        self._sync_current()
        self.ctx.bus.accounts_changed.emit()
        self.ctx.bus.toast.emit(f"已删除账号：{account.name}")

    def shutdown(self) -> None:
        self._stop_skin_preview()
        wait_thread(self._skin_upload_worker, 5000)
        self._skin_upload_worker = None
        wait_thread(self._skin_lookup_worker, 5000)
        self._skin_lookup_worker = None
        for worker in list(self._workers):
            if worker.isRunning():
                worker.wait(1000)
        wait_thread(None)
