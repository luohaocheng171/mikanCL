"""多人联机页：集成陶瓦联机（Terracotta），房间码 P2P 联机。

Terracotta（AGPL-3.0，作者 Burning_TNT）以独立进程运行，本页通过其本地 HTTP 接口
读取房间状态并下发创建/加入指令，界面中保留了原项目的版权标识。
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import terracotta as tc
from ..context import AppContext
from .widgets import Card, card_title_row, hline, page_header

# 陶瓦联机返回的异常类型编号 → 可读原因（在 MultiplayerPage 内翻译）
_EXCEPTION_TEXT = {
    0: "无法找到房主的游戏，请确认房主已开启局域网世界。",
    1: "连接被重置，请稍后重试或更换网络。",
    2: "联机组件异常退出（访客端），请重试。",
    3: "联机组件异常退出（房主端），请重试。",
    4: "服务器连接被重置，请稍后重试。",
    5: "房间码无效或房间已关闭，请核对后重试。",
}


def normalize_room_code(text: str) -> str:
    """把用户输入的房间码规范成 U/XXXX-XXXX-XXXX-XXXX。"""
    raw = "".join(ch for ch in (text or "").upper() if ch.isalnum())
    if raw.startswith("U"):
        raw = raw[1:]
    raw = "".join(ch for ch in raw if ch.isalnum())[:16]
    groups = [raw[i : i + 4] for i in range(0, len(raw), 4)]
    return "U/" + "-".join(groups) if groups else ""


class SimpleWorker(QThread):
    """把耗时操作放到后台线程；func 接收自身以便发送进度。"""

    done = Signal(object)
    failed = Signal(str)
    progress = Signal(float, str)

    def __init__(self, func, parent=None):
        super().__init__(parent)
        self._func = func

    def run(self) -> None:
        try:
            self.done.emit(self._func(self))
        except Exception as exc:  # noqa: BLE001 - 统一回传可读原因
            self.failed.emit(str(exc))


class StatePoller(QThread):
    """每秒读取一次陶瓦本地状态。"""

    state_changed = Signal(object)

    def __init__(self, service: tc.Service, parent=None):
        super().__init__(parent)
        self.service = service
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.wait(1.2):
            try:
                state = self.service.state()
            except Exception as exc:  # noqa: BLE001
                state = {"state": "error", "message": str(exc)}
            self.state_changed.emit(state)

    def stop(self) -> None:
        self._stop.set()


class MultiplayerPage(QWidget):
    log_line = Signal(str)

    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self.service: tc.Service | None = None
        self.poller: StatePoller | None = None
        self.worker: SimpleWorker | None = None
        self._state: dict = {"state": "waiting"}
        self._starting = False
        self.log_line.connect(self._append_log)
        self._build()
        self._render()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        header, _ = page_header(
            self.tr("多人联机"),
            self.tr("陶瓦联机 · 房间码组网，无需端口映射或公网 IP"),
        )
        layout.addWidget(header)

        body = QHBoxLayout()
        body.setSpacing(14)

        # ---- 左：状态与操作 ----
        left = QVBoxLayout()
        left.setSpacing(14)
        status_card = Card()
        self.state_dot = QLabel("●")
        self.state_dot.setStyleSheet("color: #65d46e; font-size: 13px;")
        self.state_text = QLabel(self.tr("未安装"))
        self.state_text.setObjectName("CardTitle")
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(8)
        head.addWidget(self.state_dot)
        head.addWidget(self.state_text)
        head.addStretch(1)
        status_card.body.addLayout(head)
        self.detail_text = QLabel(self.tr("陶瓦联机尚未安装，点击下方按钮自动下载官方发行包。"))
        self.detail_text.setObjectName("Muted")
        self.detail_text.setWordWrap(True)
        status_card.body.addWidget(self.detail_text)

        self.room_label = QLabel("")
        self.room_label.setStyleSheet(
            "font-family: Consolas, 'Cascadia Mono', monospace; font-size: 22px;"
            " font-weight: 700; color: #9ff0a8; letter-spacing: 1px;"
        )
        self.room_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.room_label.setVisible(False)
        status_card.body.addWidget(self.room_label)

        room_row = QHBoxLayout()
        room_row.setContentsMargins(0, 0, 0, 0)
        room_row.setSpacing(8)
        self.copy_btn = QPushButton(self.tr("复制房间码"))
        self.copy_btn.setObjectName("Ghost")
        self.copy_btn.setVisible(False)
        self.copy_btn.clicked.connect(self._copy_room)
        room_row.addWidget(self.copy_btn)
        room_row.addStretch(1)
        status_card.body.addLayout(room_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress.setVisible(False)
        status_card.body.addWidget(self.progress)
        left.addWidget(status_card)

        action_card = Card()
        action_card.body.addWidget(
            card_title_row(
                self.tr("联机操作"), self.tr("房主创建房间，朋友输入房间码加入")
            )
        )
        action_card.body.addWidget(hline())

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)
        form.addWidget(QLabel(self.tr("你的名字")), 0, 0)
        self.name_edit = QLineEdit(self.ctx.config.player_name or "Steve")
        self.name_edit.setPlaceholderText(self.tr("游戏内显示名字"))
        form.addWidget(self.name_edit, 0, 1)

        form.addWidget(QLabel(self.tr("房间码")), 1, 0)
        self.room_edit = QLineEdit()
        self.room_edit.setPlaceholderText("U/XXXX-XXXX-XXXX-XXXX")
        form.addWidget(self.room_edit, 1, 1)
        action_card.body.addLayout(form)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.host_btn = QPushButton(self.tr("创建房间"))
        self.host_btn.setObjectName("Primary")
        self.host_btn.clicked.connect(self._host)
        self.join_btn = QPushButton(self.tr("加入房间"))
        self.join_btn.setObjectName("Primary")
        self.join_btn.clicked.connect(self._join)
        self.leave_btn = QPushButton(self.tr("结束联机"))
        self.leave_btn.setObjectName("Danger")
        self.leave_btn.clicked.connect(self._leave)
        self.install_btn = QPushButton(self.tr("下载并安装陶瓦联机"))
        self.install_btn.setObjectName("Primary")
        self.install_btn.clicked.connect(self._install)
        buttons.addWidget(self.host_btn)
        buttons.addWidget(self.join_btn)
        buttons.addWidget(self.leave_btn)
        buttons.addWidget(self.install_btn)
        buttons.addStretch(1)
        action_card.body.addLayout(buttons)
        left.addWidget(action_card)
        left.addStretch(1)

        # ---- 右：说明 + 日志 ----
        right = QVBoxLayout()
        right.setSpacing(14)
        help_card = Card()
        help_card.body.addWidget(card_title_row(self.tr("怎么玩"), self.tr("三步开局")))
        help_text = QLabel(
            self.tr(
                "1. 房主：进入单人存档 → Esc → 对局域网开放 → 回到本页点「创建房间」。\n"
                "2. 房主：把房间码发给朋友。\n"
                "3. 朋友：输入房间码点「加入房间」，然后在游戏「多人游戏」列表双击"
                "「陶瓦联机大厅」即可进入。\n\n"
                "房间基于 P2P 组网，免费、无需端口映射；网络质量取决于双方网络状况。"
            )
        )
        help_text.setObjectName("Muted")
        help_text.setWordWrap(True)
        help_card.body.addWidget(help_text)
        right.addWidget(help_card)

        log_card = Card()
        log_card.body.addWidget(card_title_row(self.tr("运行日志"), ""))
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("Console")
        self.log_view.setReadOnly(True)
        self.log_view.setFixedHeight(150)
        log_card.body.addWidget(self.log_view)
        credit = QLabel(
            self.tr(
                '联机能力来自开源项目 <a href="https://github.com/burningtnt/Terracotta" '
                'style="color:#65d46e;">Terracotta | 陶瓦联机</a>'
                "（AGPL-3.0，作者 Burning_TNT），本启动器仅调用其官方发行包。"
            )
        )
        credit.setObjectName("Tiny")
        credit.setOpenExternalLinks(True)
        credit.setWordWrap(True)
        log_card.body.addWidget(credit)
        right.addWidget(log_card)
        right.addStretch(1)

        body.addLayout(left, 3)
        body.addLayout(right, 2)
        layout.addLayout(body, 1)

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        if not tc.is_installed():
            self._state = {"state": "not-installed"}
            self._render()
            return
        self._ensure_service()

    def shutdown(self) -> None:
        if self.poller is not None:
            self.poller.stop()
            self.poller.wait(1500)
            self.poller = None
        if self.service is not None:
            self.service.stop()
            self.service = None

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    def _append_log(self, message: str) -> None:
        self.log_view.appendPlainText(message)

    def _player(self) -> str:
        name = self.name_edit.text().strip() or "Steve"
        return name

    def _ensure_service(self) -> None:
        if self._starting or (self.service is not None and self.service.running()):
            return
        self._starting = True
        self._set_state("starting", self.tr("正在启动联机组件…"))
        service = tc.Service(log=self.log_line.emit)

        def start(_worker: SimpleWorker) -> int:
            return service.start()

        worker = SimpleWorker(start, self)
        self.worker = worker
        worker.done.connect(lambda _port: self._on_started(service))
        worker.failed.connect(self._on_start_failed)
        worker.start()

    def _on_started(self, service: tc.Service) -> None:
        self._starting = False
        self.service = service
        self.poller = StatePoller(service, self)
        self.poller.state_changed.connect(self._on_state)
        self.poller.start()
        self._state = {"state": "waiting"}
        self._render()

    def _on_start_failed(self, message: str) -> None:
        self._starting = False
        self.service = None
        self._set_state("error", self.tr("联机组件启动失败：{0}").format(message))
        self.log_line.emit(self.tr("[陶瓦] 启动失败：{0}").format(message))

    def _set_state(self, state: str, detail: str = "") -> None:
        self._state = {"state": state, "detail": detail}
        self._render()

    def _on_state(self, state: dict) -> None:
        self._state = state
        self._render()

    def _copy_room(self) -> None:
        code = self.room_label.text().strip()
        if code:
            QApplication.clipboard().setText(code)
            self.ctx.bus.toast.emit(self.tr("房间码已复制到剪贴板"))

    # ------------------------------------------------------------------
    # 操作
    # ------------------------------------------------------------------
    def _install(self) -> None:
        self.install_btn.setEnabled(False)
        self.progress.setVisible(True)

        def task(worker: SimpleWorker) -> str:
            return str(
                tc.install(
                    log=self.log_line.emit,
                    progress=lambda ratio, detail: worker.progress.emit(ratio, detail),
                )
            )

        worker = SimpleWorker(task, self)
        self.worker = worker
        worker.progress.connect(self._on_install_progress)
        worker.done.connect(self._on_installed)
        worker.failed.connect(self._on_install_failed)
        worker.start()

    def _on_install_progress(self, ratio: float, detail: str) -> None:
        self.progress.setValue(int(max(0.0, min(1.0, ratio)) * 1000))
        self.detail_text.setText(self.tr("正在下载陶瓦联机… {0}").format(detail))

    def _on_installed(self, _path: str) -> None:
        self.install_btn.setEnabled(True)
        self.progress.setVisible(False)
        self.ctx.bus.toast.emit(self.tr("陶瓦联机安装完成"))
        self._ensure_service()

    def _on_install_failed(self, message: str) -> None:
        self.install_btn.setEnabled(True)
        self.progress.setVisible(False)
        self._set_state("error", self.tr("安装失败：{0}").format(message))
        QMessageBox.warning(self, self.tr("安装失败"), message)

    def _host(self) -> None:
        if self.service is None or not self.service.running():
            QMessageBox.information(
                self, self.tr("请稍候"), self.tr("联机组件还没就绪，请稍等几秒再试。")
            )
            return
        self._run_action(
            lambda: self.service.host(self._player()), self.tr("正在局域网内寻找你的世界…")
        )

    def _join(self) -> None:
        if self.service is None or not self.service.running():
            QMessageBox.information(
                self, self.tr("请稍候"), self.tr("联机组件还没就绪，请稍等几秒再试。")
            )
            return
        code = normalize_room_code(self.room_edit.text())
        if len(code) != 20:
            QMessageBox.information(
                self,
                self.tr("房间码无效"),
                self.tr("房间码格式应为 U/XXXX-XXXX-XXXX-XXXX，请检查后重试。"),
            )
            return
        self.room_edit.setText(code)
        self._run_action(
            lambda: self.service.join(code, self._player()),
            self.tr("正在连接房间 {0}…").format(code),
        )

    def _leave(self) -> None:
        if self.service is None:
            return
        try:
            self.service.idle()
        except tc.TerracottaError as exc:
            self.log_line.emit(self.tr("[陶瓦] 结束联机失败：{0}").format(exc))
        self.shutdown()
        self._state = {"state": "waiting"}
        self._render()

    def _run_action(self, action, hint: str) -> None:
        service = self.service
        self._set_state("busy", hint)

        def task(_worker: SimpleWorker):
            action()
            return True

        worker = SimpleWorker(task, self)
        self.worker = worker
        worker.done.connect(lambda _ok: self._on_state(service.state()))
        worker.failed.connect(lambda message: self._set_state("error", message))
        worker.start()

    # ------------------------------------------------------------------
    # 渲染
    # ------------------------------------------------------------------
    def _render(self) -> None:
        state = str(self._state.get("state") or "waiting")
        installed = tc.is_installed()
        room = str(self._state.get("room") or "")
        detail = ""
        color = "#65d46e"
        show_room = False
        busy = state in (
            "starting",
            "busy",
            "host-scanning",
            "host-starting",
            "guest-connecting",
            "guest-starting",
        )

        if state == "not-installed":
            title = self.tr("未安装")
            detail = self.tr("点击「下载并安装陶瓦联机」自动获取官方发行包（约 8 MB）。")
            color = "#e0b15c"
        elif state == "starting":
            title = self.tr("正在启动")
            detail = self.tr("首次运行会释放联机组件，请稍候…")
            color = "#e0b15c"
        elif state == "error":
            title = self.tr("出错了")
            detail = str(
                self._state.get("detail")
                or self._state.get("message")
                or self.tr("未知错误")
            )
            color = "#e8909a"
        elif state == "waiting":
            title = self.tr("空闲")
            detail = self.tr(
                "创建房间或输入房间码加入；房主需先在游戏中「对局域网开放」。"
            )
        elif state == "host-scanning":
            title = self.tr("等待局域网世界")
            detail = self.tr(
                "请在游戏中打开存档并选择「对局域网开放」，本页会自动完成创建。"
            )
            color = "#e0b15c"
        elif state == "host-starting":
            title = self.tr("正在创建房间")
            detail = self.tr("正在组网，请稍候…")
            show_room = bool(room)
            color = "#e0b15c"
        elif state == "host-ok":
            title = self.tr("房间已创建")
            profiles = self._state.get("profiles") or []
            detail = self.tr("已连接玩家 {0} 人 · 把房间码发给朋友即可加入。").format(
                len(profiles)
            )
            show_room = True
        elif state == "guest-connecting":
            title = self.tr("正在连接")
            detail = self.tr("正在请求房间 {0}…").format(room)
            color = "#e0b15c"
        elif state == "guest-starting":
            title = self.tr("正在建立连接")
            detail = self.tr("正在通过 P2P 组网，通常需要几秒到几十秒…")
            color = "#e0b15c"
        elif state == "guest-ok":
            title = self.tr("已进入房间")
            url = str(self._state.get("url") or "127.0.0.1")
            detail = self.tr(
                "服务器地址 {0} · 打开游戏「多人游戏」，双击「陶瓦联机大厅」即可进入。"
            ).format(url)
        elif state == "exception":
            kind = self._state.get("type")
            title = self.tr("联机失败")
            detail = self._exception_text(kind)
            color = "#e8909a"
        elif state == "busy":
            title = self.tr("处理中")
            detail = str(self._state.get("detail") or "")
            color = "#e0b15c"
        else:
            title = self.tr("空闲")
            detail = str(self._state.get("detail") or "")

        self.state_text.setText(title)
        self.detail_text.setText(detail)
        self.state_dot.setStyleSheet(f"color: {color}; font-size: 13px;")
        self.state_text.setStyleSheet(f"color: {color};")
        self.room_label.setVisible(show_room and bool(room))
        self.room_label.setText(room)
        self.copy_btn.setVisible(show_room and bool(room))
        if not installed:
            self.state_text.setText(self.tr("未安装"))
            self.detail_text.setText(
                self.tr("点击「下载并安装陶瓦联机」自动获取官方发行包（约 8 MB）。")
            )

        self.install_btn.setVisible(not installed)
        self.host_btn.setEnabled(installed and not busy)
        self.join_btn.setEnabled(installed and not busy)
        self.leave_btn.setEnabled(
            installed and state in ("host-ok", "guest-ok", "host-scanning", "guest-starting")
        )

    def _exception_text(self, kind) -> str:
        source = _EXCEPTION_TEXT.get(kind, "未知错误，请重试。")
        return self.tr(source)
