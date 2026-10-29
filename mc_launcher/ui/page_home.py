"""主页：账号、启动配置、版本列表与运行日志。"""

from __future__ import annotations

import os
import re
import shutil
import socket
import threading
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QThread, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QGuiApplication,
    QPixmap,
    QSyntaxHighlighter,
    QTextCharFormat,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME
from ..auth import AuthError, MicrosoftAuth, apply_local_skin, apply_skin_resourcepack, ensure_authlib_injector
from ..config import DATA_DIR, ISOLATION_LABELS, ServerEntry
from ..context import AppContext, wait_thread
from ..i18n import t
from ..installer import GameInstaller, Progress
from ..java import pick_java, probe_java
from ..launcher import (
    LaunchOptions,
    archive_crash_log,
    build_launch_plan,
    crash_hint,
    post_launch,
    prepare_isolated_dir,
    split_server,
    start_game,
    wait_early_exit,
)
from ..net import Cancelled, Http
from ..version import InstalledVersion, VersionError, load_version, scan_installed_versions
from .theme import make_avatar
from .widgets import Badge, Card, page_header


def _total_physical_memory_mb() -> int:
    """读取物理内存总量（MB）；非 Windows 或失败返回 0。"""
    if os.name != "nt":
        return 0
    try:
        import ctypes

        class _MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = _MemoryStatusEx()
        stat.dwLength = ctypes.sizeof(_MemoryStatusEx)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return int(stat.ullTotalPhys // (1024 * 1024))
    except Exception:  # noqa: BLE001
        pass
    return 0


def _integrated_gpu_name() -> str:
    """从注册表读取显卡描述；含集成显卡字样（Intel / AMD APU / 集成）时返回名称，否则空串。"""
    if os.name != "nt":
        return ""
    try:
        import winreg  # type: ignore
    except ImportError:
        return ""
    keywords = ("集成", "intel", "uhd graphics", "iris", "radeon(tm) graphics", "amd radeon graphics")
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Video") as root:
            count, _, _ = winreg.QueryInfoKey(root)
            for i in range(count):
                sub = winreg.EnumKey(root, i)
                try:
                    with winreg.OpenKey(root, sub) as key:
                        try:
                            name, _ = winreg.QueryValueEx(key, "Device Description")
                        except OSError:
                            try:
                                name, _ = winreg.QueryValueEx(key, "DriverDesc")
                            except OSError:
                                continue
                        lowered = str(name).lower()
                        if any(k in lowered for k in keywords):
                            return str(name)
                except OSError:
                    continue
    except OSError:
        return ""
    return ""


def _scan_mod_conflicts(game_dir: Path) -> list[str]:
    """防御式调用 content 的 Mod 冲突检测；返回冲突详情列表，空表示无冲突。"""
    try:
        from ..content import detect_mod_conflicts, scan_mod_metadata
    except ImportError:
        return []
    mods_dir = Path(game_dir) / "mods"
    if not mods_dir.is_dir():
        return []
    try:
        metadata = scan_mod_metadata(mods_dir)
        return [str(c.get("detail") or c.get("modid") or c.get("type") or "") for c in detect_mod_conflicts(metadata)]
    except Exception:  # noqa: BLE001
        return []


def _preflight(
    ctx: AppContext,
    version_id: str,
    game_dir: Path,
    memory_mb: int,
    log: Callable[[str], None],
) -> dict:
    """启动前 checklist 预检。返回 {"blocked": [...], "warnings": [...], "mod_conflicts": [...]}。

    blocked 为红标阻止项（由页面弹框让用户选择是否继续）；warnings 为黄标警告仅提示。
    """
    blocked: list[str] = []
    warnings: list[str] = []
    log("[预检] 开始启动前检查…")

    # 1) 内存 ≤ 物理内存 70%（仅警告）
    total_mb = _total_physical_memory_mb()
    used_mb = int(memory_mb or 0)
    if total_mb > 0:
        if used_mb > int(total_mb * 0.7):
            msg = f"[预检][警告] 分配内存 {used_mb} MB 超过物理内存 70%（共 {total_mb} MB），可能出现内存不足或卡顿。"
            warnings.append(msg)
            log(msg)
        else:
            log(f"[预检] 内存分配 {used_mb} MB，物理内存 {total_mb} MB（未超 70%）。")
    else:
        log("[预检] 无法读取物理内存信息，跳过内存检查。")

    # 2) 磁盘剩余 > 2GB（阻止）
    try:
        usage = shutil.disk_usage(game_dir)
        free_gb = usage.free / (1024**3)
        if free_gb <= 2.0:
            msg = f"[预检][阻止] 磁盘剩余空间不足：仅剩 {free_gb:.1f} GB（需大于 2 GB）。"
            blocked.append(msg)
            log(msg)
        else:
            log(f"[预检] 磁盘剩余 {free_gb:.1f} GB（OK）。")
    except OSError as exc:
        log(f"[预检] 无法读取磁盘空间：{exc}")

    # 3) Mods 冲突（阻止）
    mod_conflicts = _scan_mod_conflicts(game_dir)
    if mod_conflicts:
        msg = f"[预检][阻止] 检测到 {len(mod_conflicts)} 个 Mod 冲突：\n" + "\n".join(
            f"  - {text}" for text in mod_conflicts[:3]
        )
        blocked.append(msg)
        log(msg)
    else:
        log("[预检] Mod 冲突检查通过。")

    # 4) 显卡：集成显卡 + 开启光影（仅警告；读不到就跳过）
    shader_dir = Path(game_dir) / "shaderpacks"
    has_shaders = shader_dir.is_dir() and any(shader_dir.iterdir())
    gpu_name = _integrated_gpu_name()
    if gpu_name and has_shaders:
        msg = f"[预检][警告] 检测到集成显卡（{gpu_name}）且已启用光影包，游戏性能可能不足。"
        warnings.append(msg)
        log(msg)
    elif gpu_name:
        log(f"[预检] 显卡：{gpu_name}")

    log(f"[预检] 检查完成：{len(warnings)} 项警告，{len(blocked)} 项阻止。")
    return {"blocked": blocked, "warnings": warnings, "mod_conflicts": mod_conflicts}


class VersionRow(QFrame):
    selected = Signal(str)
    activated = Signal(str)
    settings_requested = Signal(str)

    def __init__(
        self,
        version: InstalledVersion,
        ctx: AppContext | None = None,
        game_dir: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.version = version
        self.ctx = ctx
        self.game_dir = game_dir
        self.setObjectName("VersionRow")
        self.setProperty("selected", False)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(72)
        self.setToolTip(str(version.path))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 12, 10)
        layout.setSpacing(10)

        texts = QVBoxLayout()
        texts.setSpacing(4)
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        name_label = QLabel(version.id)
        name_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #e6f1e9;")
        title_row.addWidget(name_label)

        loader_badge = Badge(version.loader, _loader_kind(version.loader))
        title_row.addWidget(loader_badge)
        if version.error:
            broken = Badge(t("HomePage", "损坏"), "orange")
            broken.setToolTip(version.error)
            title_row.addWidget(broken)
        title_row.addStretch(1)
        texts.addLayout(title_row)

        date = (
            datetime.fromtimestamp(version.modified).strftime("%Y-%m-%d %H:%M")
            if version.modified
            else t("HomePage", "未知时间")
        )
        meta_text = f"{version.display_type} · {date}"
        if version.base_version:
            meta_text += t("HomePage", "· 基于 {0}", version.base_version)
        meta = QLabel(meta_text)
        meta.setObjectName("Tiny")
        texts.addWidget(meta)
        layout.addLayout(texts, 1)

        launch_button = QPushButton(t("HomePage", "启动"))
        launch_button.setFixedWidth(66)
        launch_button.setEnabled(not version.error)
        launch_button.clicked.connect(lambda: self.activated.emit(self.version.id))
        layout.addWidget(launch_button)

    def set_selected(self, value: bool) -> None:
        self.setProperty("selected", value)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.selected.emit(self.version.id)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and not self.version.error:
            self.activated.emit(self.version.id)
        super().mouseDoubleClickEvent(event)

    # ------------------------------------------------------------------
    def _mods_dir(self) -> Path:
        root = Path(self.game_dir or (self.ctx.config.game_path if self.ctx else "."))
        mode = self.ctx.config.isolation_for(self.version.id) if self.ctx else "none"
        if mode in ("mods", "all"):
            return root / "versions" / self.version.id / "game" / "mods"
        return root / "mods"

    def contextMenuEvent(self, event) -> None:
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)
        launch = menu.addAction("启动游戏")
        launch.setEnabled(not self.version.error)
        launch.triggered.connect(lambda: self.activated.emit(self.version.id))
        menu.addSeparator()
        open_version = menu.addAction("打开版本文件夹")
        open_version.triggered.connect(self._open_version_dir)
        open_mods = menu.addAction("打开模组目录")
        open_mods.triggered.connect(self._open_mods_dir)
        settings = menu.addAction("编辑版本设置")
        settings.triggered.connect(lambda: self.settings_requested.emit(self.version.id))
        copy_id = menu.addAction("复制版本 ID")
        copy_id.triggered.connect(
            lambda: QGuiApplication.clipboard().setText(self.version.id)
        )
        menu.addSeparator()
        remove = menu.addAction("删除此版本")
        remove.triggered.connect(self._delete_version)
        menu.exec(event.globalPos())

    def _open_version_dir(self) -> None:
        folder = Path(self.version.path).parent
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _open_mods_dir(self) -> None:
        folder = self._mods_dir()
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _delete_version(self) -> None:
        if QMessageBox.question(
            self,
            APP_NAME,
            f"确定删除版本「{self.version.id}」吗？\n版本目录会一并删除，且不可恢复。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        folder = Path(self.version.path).parent
        try:
            shutil.rmtree(folder)
        except OSError as exc:
            QMessageBox.warning(self, APP_NAME, f"删除失败：{exc}")
            return
        if self.ctx is not None:
            self.ctx.bus.versions_changed.emit()
            self.ctx.bus.toast.emit(f"已删除版本 {self.version.id}")


def _loader_kind(loader: str) -> str:
    return {
        "原版": "gray",
        "Forge": "orange",
        "NeoForge": "green",
        "Fabric": "blue",
        "Quilt": "orange",
        "OptiFine": "blue",
        "损坏": "orange",
    }.get(loader, "gray")


class ServerPingWorker(QThread):
    """并发测试服务器延迟，并尝试读取在线人数。"""

    result = Signal(str, int, str)

    def __init__(self, servers: list[ServerEntry], parent=None):
        super().__init__(parent)
        self.servers = list(servers)

    def run(self) -> None:
        for entry in self.servers:
            latency = -1
            try:
                started = time.perf_counter()
                with socket.create_connection((entry.host, int(entry.port)), timeout=4):
                    pass
                latency = int((time.perf_counter() - started) * 1000)
            except OSError:
                self.result.emit(entry.id, -1, "无法连接")
                continue
            players = ""
            try:
                data = Http().get_json_url(
                    f"https://api.mcstatus.io/v2/status/java/{entry.host}:{int(entry.port)}",
                    timeout=6,
                )
                if isinstance(data, dict) and data.get("online"):
                    info = data.get("players") or {}
                    players = f"在线 {info.get('online', 0)}/{info.get('max', 0)}"
            except Exception:  # noqa: BLE001 - 在线人数仅作为附加信息
                players = ""
            self.result.emit(entry.id, latency, players)


class ServerDialog(QDialog):
    """服务器库：添加、删除与延迟测试。"""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self._ping_worker: ServerPingWorker | None = None
        self.setWindowTitle(t("HomePage", "服务器列表"))
        self.resize(660, 440)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            [
                t("HomePage", "名称"),
                t("HomePage", "地址"),
                t("HomePage", "状态"),
                t("HomePage", "备注"),
            ]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 160)
        self.table.setColumnWidth(1, 210)
        self.table.setColumnWidth(2, 150)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table, 1)

        form = QHBoxLayout()
        form.setSpacing(8)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(t("HomePage", "名称（可留空）"))
        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText(t("HomePage", "服务器地址，例如 play.example.com"))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(25565)
        add_button = QPushButton(t("HomePage", "添加"))
        add_button.setObjectName("Primary")
        add_button.clicked.connect(self._add_server)
        form.addWidget(self.name_edit)
        form.addWidget(self.host_edit, 1)
        form.addWidget(self.port_spin)
        form.addWidget(add_button)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        ping_button = QPushButton(t("HomePage", "测试延迟"))
        ping_button.clicked.connect(self._ping_all)
        remove_button = QPushButton(t("HomePage", "删除选中"))
        remove_button.setObjectName("Danger")
        remove_button.clicked.connect(self._remove_selected)
        close_button = QPushButton(t("HomePage", "关闭"))
        close_button.clicked.connect(self.accept)
        buttons.addWidget(ping_button)
        buttons.addWidget(remove_button)
        buttons.addStretch(1)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self._reload()

    def _reload(self) -> None:
        entries = self.ctx.config.servers
        self.table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            name_item = QTableWidgetItem(entry.name)
            name_item.setData(Qt.UserRole, entry.id)
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QTableWidgetItem(f"{entry.host}:{entry.port}"))
            self.table.setItem(row, 2, QTableWidgetItem("未测试"))
            self.table.setItem(row, 3, QTableWidgetItem(entry.note))

    def _add_server(self) -> None:
        host = self.host_edit.text().strip()
        if not host:
            QMessageBox.information(self, APP_NAME, "请输入服务器地址。")
            return
        parsed_host, parsed_port = split_server(host, self.port_spin.value())
        for entry in self.ctx.config.servers:
            if entry.host.lower() == parsed_host.lower() and int(entry.port) == int(parsed_port):
                QMessageBox.information(self, APP_NAME, "该服务器已在列表中。")
                return
        self.ctx.config.add_server(
            self.name_edit.text().strip() or parsed_host, parsed_host, parsed_port
        )
        self.name_edit.clear()
        self.host_edit.clear()
        self._reload()
        self.ctx.bus.config_changed.emit()

    def _remove_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 0)
        server_id = item.data(Qt.UserRole) if item else ""
        if self.ctx.config.remove_server(str(server_id)):
            self._reload()
            self.ctx.bus.config_changed.emit()

    def _ping_all(self) -> None:
        if self._ping_worker is not None and self._ping_worker.isRunning():
            return
        entries = list(self.ctx.config.servers)
        if not entries:
            return
        for row in range(self.table.rowCount()):
            self.table.setItem(row, 2, QTableWidgetItem("测试中…"))
        self._ping_worker = ServerPingWorker(entries, self)
        self._ping_worker.result.connect(self._on_ping_result)
        self._ping_worker.finished.connect(self._on_ping_done)
        self._ping_worker.start()

    def _on_ping_result(self, server_id: str, latency: int, players: str) -> None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is None or item.data(Qt.UserRole) != server_id:
                continue
            if latency >= 0:
                text = f"{latency} ms"
                if players:
                    text += f" · {players}"
            else:
                text = players or t("HomePage", "无法连接")
            self.table.setItem(row, 2, QTableWidgetItem(text))
            break

    def _on_ping_done(self) -> None:
        worker, self._ping_worker = self._ping_worker, None
        if worker is not None:
            worker.deleteLater()

    def shutdown(self) -> None:
        wait_thread(self._ping_worker)
        self._ping_worker = None


class LaunchWorker(QThread):
    progress = Signal(object)
    log = Signal(str)
    started = Signal(object)
    failed = Signal(str)
    preflight_blocked = Signal(list)  # 预检阻止项列表，由页面弹框决定是否继续

    def __init__(
        self,
        ctx: AppContext,
        version_id: str,
        player_name: str,
        java,
        memory_mb: int,
        width: int,
        height: int,
        extra_jvm_args: str,
        extra_game_args: str = "",
        game_dir: Path | None = None,
        account=None,
        parent=None,
    ):
        super().__init__(parent)
        self.ctx = ctx
        self.version_id = version_id
        self.player_name = player_name
        self.java = java
        self.memory_mb = memory_mb
        self.width = width
        self.height = height
        self.extra_jvm_args = extra_jvm_args
        self.extra_game_args = extra_game_args
        self.game_dir = game_dir
        self.account = account
        self.cancel_event = threading.Event()
        self.installer: GameInstaller | None = None
        self.session = None

    def run(self) -> None:  # noqa: D401
        # ---- 启动前 checklist 预检：日志输出全部检查项；阻止项由页面弹框决定 ----
        root_dir = Path(self.game_dir or self.ctx.config.game_path)
        preflight = _preflight(
            self.ctx, self.version_id, root_dir, int(self.memory_mb), self.log.emit
        )
        if preflight["blocked"]:
            self._preflight_wait = threading.Event()
            self._preflight_continue = False
            self.preflight_blocked.emit(preflight["blocked"])
            if not self._preflight_wait.wait(120):
                self.log.emit("[预检] 等待用户确认超时，已中止启动。")
                return
            if not self._preflight_continue:
                return
        try:
            cfg = self.ctx.config
            root_dir = Path(self.game_dir or cfg.game_path)
            setting = cfg.version_setting(self.version_id)
            isolation = cfg.isolation_for(self.version_id)
            game_dir = prepare_isolated_dir(root_dir, self.version_id, isolation)
            if isolation != "none":
                self.log.emit(f"[隔离] 模式：{ISOLATION_LABELS.get(isolation, isolation)} → {game_dir}")
            account = self.account
            authlib_jar = ""
            auth_server = ""
            uuid = ""
            access_token = ""
            user_type = "legacy"
            if account is not None:
                self.player_name = account.name
                uuid = account.uuid
                access_token = account.access_token
                if account.type == "microsoft":
                    user_type = "msa"
                    if account.token_expired and account.refresh_token:
                        self.log.emit("[登录] 微软令牌已过期，正在自动刷新…")
                        try:
                            fresh = MicrosoftAuth(
                                self.ctx.config.microsoft_client_id
                            ).refresh(account, log=self.log.emit)
                            self.ctx.accounts.update(fresh)
                            account = fresh
                            self.account = fresh
                            uuid = fresh.uuid
                            access_token = fresh.access_token
                            self.ctx.bus.accounts_changed.emit()
                            self.log.emit("[登录] 令牌刷新完成。")
                        except AuthError as exc:
                            self.log.emit(f"[登录] {exc}")
                            raise AuthError(
                                f"{exc}\n请到账号页重新登录微软账号后再启动。"
                            ) from exc
                    elif not account.access_token:
                        raise AuthError("当前微软账号尚未登录，请到账号页完成登录。")
                elif account.type == "authlib":
                    auth_server = account.auth_server
                    try:
                        authlib_jar = str(
                            ensure_authlib_injector(self.ctx.config, log=self.log.emit)
                        )
                    except AuthError as exc:
                        self.log.emit(f"[外置登录] {exc}")
                        raise
                if account.type == "offline" and not access_token:
                    access_token = ""
                    uuid = account.uuid

            self.installer = GameInstaller(
                self.ctx.config,
                self.ctx.sources,
                progress_cb=self.progress.emit,
                log_cb=self.log.emit,
                cancel=self.cancel_event,
            )
            self.installer.config = self.ctx.config.with_game_dir(root_dir)
            merged = self.installer.ensure_version(self.version_id)
            if setting.auto_connect and setting.server.strip():
                server, port = split_server(setting.server, int(setting.port or 25565))
            elif cfg.active_server() is not None:
                active = cfg.active_server()
                server, port = split_server(active.host, int(active.port or 25565))
            else:
                server, port = split_server(
                    cfg.auto_connect_server if cfg.auto_connect_enabled else "",
                    int(cfg.auto_connect_port or 25565),
                )
            extra_jvm = " ".join(
                part for part in (self.extra_jvm_args, setting.extra_jvm_args) if part.strip()
            )
            extra_game = " ".join(
                part for part in (self.extra_game_args, setting.extra_game_args) if part.strip()
            )
            memory = int(setting.memory_mb) if setting.memory_mb else int(self.memory_mb)
            window_title = (setting.window_title or cfg.window_title or "").strip()
            priority = setting.priority or cfg.process_priority or "normal"
            proxy = cfg.effective_proxy if cfg.proxy_jvm else ""
            if account is not None and account.type == "offline":
                try:
                    applied = apply_local_skin(account, game_dir)
                    if applied:
                        self.log.emit(f"[皮肤] 已应用离线皮肤：{applied}")
                except Exception as exc:  # noqa: BLE001
                    self.log.emit(f"[皮肤] 离线皮肤应用失败：{exc}")
                try:
                    pack = apply_skin_resourcepack(account, game_dir)
                    if pack:
                        self.log.emit(f"[皮肤] 已生成离线皮肤资源包（单人模式生效）：{pack}")
                except Exception as exc:  # noqa: BLE001
                    self.log.emit(f"[皮肤] 皮肤资源包生成失败：{exc}")
            plan = build_launch_plan(
                LaunchOptions(
                    version=merged,
                    game_dir=game_dir,
                    root_dir=root_dir,
                    player_name=self.player_name,
                    java=self.java,
                    memory_mb=memory,
                    width=self.width,
                    height=self.height,
                    extra_jvm_args=extra_jvm,
                    extra_game_args=extra_game,
                    uuid=uuid,
                    access_token=access_token,
                    user_type=user_type,
                    authlib_jar=authlib_jar,
                    auth_server=auth_server,
                    auto_connect=bool(server),
                    server=server,
                    server_port=port,
                    proxy_url=proxy,
                    window_title=window_title,
                    priority=priority,
                    offline=(account is None or account.type == "offline"),
                )
            )
            for warning in plan.warnings:
                self.log.emit(f"[提示] {warning}")
            self.log.emit(f"[启动] Java：{self.java.path}")
            self.log.emit(f"[启动] 日志文件：{plan.log_path}")
            session = start_game(plan, on_line=self.log.emit)
            post_launch(session.process, priority=priority, title=window_title)
            self.session = session
            early, tail = wait_early_exit(session)
            if early:
                self.failed.emit(crash_hint(session.process.returncode or -1, tail))
                return
            self.started.emit(session)
            # QThread 到此结束；进程退出由守护线程监听，避免退出启动器时留下运行中的 QThread。
            threading.Thread(
                target=self._watch_session, args=(session,), name="mc-exit-watcher", daemon=True
            ).start()
        except Cancelled:
            self.failed.emit("启动已取消。")
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))

    def _watch_session(self, session) -> None:
        """守护线程只通过总线发信号，不引用 LaunchWorker，避免其已析构。"""
        try:
            code = int(session.process.wait() or 0)
            tail = "\n".join(session.lines()[-12:])
            self.ctx.bus.game_exited.emit(code, tail)
        except Exception:  # noqa: BLE001 - 启动器可能已经退出
            pass

    def cancel(self) -> None:
        self.cancel_event.set()
        if self.session is not None:
            self.session.stop()

    def stop_game(self) -> None:
        if self.session is not None:
            self.session.stop()


_LOG_ERROR_WORDS = ("[错误]", "error", "exception", "caused by", "fatal", "failed", "失败", "崩溃")
_LOG_WARN_WORDS = ("[警告]", "warn", "警告")


def _log_level(line: str) -> str:
    """粗略判断日志级别：error / warn / info，用于着色与过滤。"""
    lowered = line.lower()
    if any(word in lowered for word in _LOG_ERROR_WORDS):
        return "error"
    if any(word in lowered for word in _LOG_WARN_WORDS):
        return "warn"
    return "info"


class LogHighlighter(QSyntaxHighlighter):
    """给运行日志着色：错误红色、警告黄色。"""

    def __init__(self, document) -> None:
        super().__init__(document)
        self._error = QTextCharFormat()
        self._error.setForeground(QColor("#ff6b6b"))
        self._warn = QTextCharFormat()
        self._warn.setForeground(QColor("#e8c07a"))

    def highlightBlock(self, text: str) -> None:  # noqa: N802 - Qt 命名
        level = _log_level(text)
        if level == "error":
            self.setFormat(0, len(text), self._error)
        elif level == "warn":
            self.setFormat(0, len(text), self._warn)


class HomePage(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self._rows: dict[str, VersionRow] = {}
        self._selected_id = ""
        self._required_java = 21
        self._worker: LaunchWorker | None = None
        self._session = None
        self._launch_queue: list[str] = []
        self._queue_running = False
        self._queue_stop = False
        self._queue_total = 0
        self._server_ping: ServerPingWorker | None = None
        self._server_ping_cache: dict[str, tuple[float, int, str]] = {}
        self._log_lines: list[str] = []
        self._loaded_instance = self.ctx.config.selected_instance_id
        self._build()
        self._connect()
        self.refresh_versions()
        self.reload_config()
        # 等主窗口把 bus.log 接到控制台后再写入，保证日志既显示也落盘
        QTimer.singleShot(0, lambda: self._append_log(f"[{APP_NAME}] 启动器已就绪。双击版本即可启动游戏。"))

    # ------------------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(14)

        header, header_layout = page_header(
            self.tr("启动游戏"), self.tr("选择已安装的版本，一键进入 Minecraft")
        )
        self.dir_button = QPushButton(self.tr("打开游戏目录"))
        self.dir_button.setObjectName("Chip")
        self.dir_button.clicked.connect(self._open_game_dir)
        header_layout.addWidget(self.dir_button)
        settings_button = QPushButton(self.tr("游戏设置"))
        settings_button.setObjectName("Chip")
        settings_button.clicked.connect(lambda: self.ctx.bus.navigate.emit("settings"))
        header_layout.addWidget(settings_button)
        outer.addWidget(header)

        body = QHBoxLayout()
        body.setSpacing(16)
        outer.addLayout(body, 1)

        left = QWidget()
        left.setFixedWidth(320)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(14)
        body.addWidget(left)

        # 账号卡片
        account = Card()
        self.account_badge = Badge(self.tr("离线模式"), "green")
        manage_button = QPushButton(self.tr("管理账号"))
        manage_button.setObjectName("Ghost")
        manage_button.clicked.connect(lambda: self.ctx.bus.navigate.emit("accounts"))
        title_widget = self._card_title(
            self.tr("当前账号"),
            self.tr("支持离线 / 微软正版 / 外置登录"),
            self.account_badge,
        )
        account.body.addWidget(title_widget)
        account_row = QHBoxLayout()
        account_row.setSpacing(12)
        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(56, 56)
        self.avatar_label.setCursor(Qt.PointingHandCursor)
        self.avatar_label.setToolTip(self.tr("点击切换账号"))
        self.avatar_label.installEventFilter(self)
        account_row.addWidget(self.avatar_label)
        name_box = QVBoxLayout()
        name_box.setSpacing(6)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(self.tr("输入玩家昵称"))
        self.name_edit.setMaxLength(16)
        name_box.addWidget(self.name_edit)
        self.uuid_label = QLabel()
        self.uuid_label.setObjectName("Tiny")
        name_box.addWidget(self.uuid_label)
        account_row.addLayout(name_box, 1)
        account.body.addLayout(account_row)
        account.body.addWidget(manage_button, alignment=Qt.AlignRight)
        left_layout.addWidget(account)

        # 启动配置
        config_card = Card()
        config_card.body.addWidget(self._card_title(self.tr("启动配置"), self.tr("Java、内存与窗口")))
        java_head = QHBoxLayout()
        java_label = QLabel(self.tr("Java 运行时"))
        java_label.setObjectName("Muted")
        java_head.addWidget(java_label)
        java_head.addStretch(1)
        self.java_hint = QLabel("")
        self.java_hint.setObjectName("Tiny")
        java_head.addWidget(self.java_hint)
        config_card.body.addLayout(java_head)
        self.java_combo = QComboBox()
        config_card.body.addWidget(self.java_combo)

        memory_head = QHBoxLayout()
        memory_label = QLabel(self.tr("分配内存"))
        memory_label.setObjectName("Muted")
        memory_head.addWidget(memory_label)
        memory_head.addStretch(1)
        self.memory_value = QLabel("4.0 GB")
        self.memory_value.setStyleSheet("color: #8fe89b; font-weight: 600;")
        memory_head.addWidget(self.memory_value)
        config_card.body.addLayout(memory_head)
        self.memory_slider = QSlider(Qt.Horizontal)
        self.memory_slider.setRange(1024, 16384)
        self.memory_slider.setSingleStep(256)
        self.memory_slider.setPageStep(1024)
        config_card.body.addWidget(self.memory_slider)

        resolution_row = QHBoxLayout()
        self.resolution_check = QCheckBox(self.tr("自定义分辨率"))
        self.resolution_check.setToolTip(self.tr("勾选后使用下方宽高启动游戏"))
        resolution_row.addWidget(self.resolution_check)
        resolution_row.addStretch(1)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(320, 12000)
        self.width_spin.setFixedWidth(66)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(240, 12000)
        self.height_spin.setFixedWidth(66)
        resolution_row.addWidget(self.width_spin)
        resolution_row.addWidget(QLabel("×"))
        resolution_row.addWidget(self.height_spin)
        config_card.body.addLayout(resolution_row)
        left_layout.addWidget(config_card)

        # 启动按钮区
        launch_box = QWidget()
        launch_layout = QVBoxLayout(launch_box)
        launch_layout.setContentsMargins(0, 2, 0, 0)
        launch_layout.setSpacing(8)
        self.launch_info = QLabel(self.tr("未选择版本"))
        self.launch_info.setObjectName("Muted")
        launch_layout.addWidget(self.launch_info)

        server_row = QHBoxLayout()
        server_row.setSpacing(6)
        server_caption = QLabel(self.tr("连接服务器"))
        server_caption.setObjectName("Muted")
        server_row.addWidget(server_caption)
        self.server_combo = QComboBox()
        self.server_combo.setToolTip(
            self.tr("选择后在启动时自动进入该服务器（单人游戏不受影响）")
        )
        self.server_combo.currentIndexChanged.connect(self._on_server_changed)
        server_row.addWidget(self.server_combo, 1)
        self.server_manage_button = QPushButton(self.tr("管理"))
        self.server_manage_button.setObjectName("Ghost")
        self.server_manage_button.setFixedWidth(56)
        self.server_manage_button.clicked.connect(self._open_server_dialog)
        server_row.addWidget(self.server_manage_button)
        launch_layout.addLayout(server_row)

        self.launch_button = QPushButton(self.tr("启动游戏"))
        self.launch_button.setObjectName("Primary")
        self.launch_button.setMinimumHeight(48)
        self.launch_button.clicked.connect(self._on_launch_clicked)
        launch_layout.addWidget(self.launch_button)
        left_layout.addWidget(launch_box)

        # 进度卡片
        self.progress_card = Card(margins=14, spacing=8)
        self.progress_stage = QLabel(self.tr("准备启动"))
        self.progress_stage.setStyleSheet("font-weight: 600;")
        self.progress_card.body.addWidget(self.progress_stage)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setTextVisible(False)
        self.progress_card.body.addWidget(self.progress_bar)
        detail_row = QHBoxLayout()
        self.progress_detail = QLabel("")
        self.progress_detail.setObjectName("Tiny")
        detail_row.addWidget(self.progress_detail, 1)
        self.cancel_button = QPushButton(self.tr("取消"))
        self.cancel_button.setObjectName("Ghost")
        self.cancel_button.clicked.connect(self._cancel_launch)
        detail_row.addWidget(self.cancel_button)
        self.progress_card.body.addLayout(detail_row)
        self.progress_card.setVisible(False)
        left_layout.addWidget(self.progress_card)
        left_layout.addStretch(1)

        # 右侧版本列表
        right = QVBoxLayout()
        right.setSpacing(14)
        body.addLayout(right, 1)

        versions_card = Card()
        versions_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        versions_head = QVBoxLayout()
        versions_head.setSpacing(8)
        head_row = QHBoxLayout()
        head_row.setSpacing(8)
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_label = QLabel(self.tr("已安装版本"))
        title_label.setObjectName("CardTitle")
        title_box.addWidget(title_label)
        self.version_count = QLabel(self.tr("0 个版本"))
        self.version_count.setObjectName("Tiny")
        title_box.addWidget(self.version_count)
        head_row.addLayout(title_box)
        head_row.addStretch(1)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(self.tr("搜索版本…"))
        self.search_edit.setMinimumWidth(96)
        self.search_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        head_row.addWidget(self.search_edit, 1)

        # 实例切换与操作按钮放到第二行，窗口变窄时不会把右侧内容挤出卡片
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        instance_label = QLabel(self.tr("实例"))
        instance_label.setObjectName("Muted")
        action_row.addWidget(instance_label)
        self.instance_combo = QComboBox()
        self.instance_combo.setMinimumWidth(110)
        self.instance_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.instance_combo.setToolTip(self.tr("切换默认实例或整合包独立实例"))
        action_row.addWidget(self.instance_combo, 1)
        refresh_button = QPushButton(self.tr("刷新"))
        refresh_button.setObjectName("Ghost")
        refresh_button.clicked.connect(self.refresh_versions)
        action_row.addWidget(refresh_button)
        self.queue_launch_button = QPushButton(self.tr("多选启动"))
        self.queue_launch_button.setObjectName("Ghost")
        self.queue_launch_button.clicked.connect(self._open_queue_dialog)
        action_row.addWidget(self.queue_launch_button)
        self.queue_stop_button = QPushButton(self.tr("停止队列"))
        self.queue_stop_button.setObjectName("Ghost")
        self.queue_stop_button.setVisible(False)
        self.queue_stop_button.clicked.connect(self._stop_queue)
        action_row.addWidget(self.queue_stop_button)
        download_button = QPushButton(self.tr("安装新版本"))
        download_button.clicked.connect(lambda: self.ctx.bus.navigate.emit("download"))
        action_row.addWidget(download_button)
        versions_head.addLayout(head_row)
        versions_head.addLayout(action_row)
        versions_card.body.addLayout(versions_head)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.version_host = QWidget()
        self.version_layout = QVBoxLayout(self.version_host)
        self.version_layout.setContentsMargins(0, 0, 6, 0)
        self.version_layout.setSpacing(8)
        self.version_layout.addStretch(1)
        self.scroll.setWidget(self.version_host)
        versions_card.body.addWidget(self.scroll, 1)
        right.addWidget(versions_card, 1)

        console_card = Card()
        console_card.setFixedHeight(210)
        console_head = QHBoxLayout()
        console_title = QLabel(self.tr("运行日志"))
        console_title.setObjectName("CardTitle")
        console_head.addWidget(console_title)
        console_head.addStretch(1)
        self.console_filter = QComboBox()
        self.console_filter.addItem(self.tr("全部日志"), "all")
        self.console_filter.addItem(self.tr("仅错误与警告"), "problems")
        self.console_filter.setFixedWidth(130)
        self.console_filter.currentIndexChanged.connect(lambda _index: self._rebuild_console())
        console_head.addWidget(self.console_filter)
        clear_button = QPushButton(self.tr("清空"))
        clear_button.setObjectName("Ghost")
        clear_button.clicked.connect(self._clear_console)
        console_head.addWidget(clear_button)
        open_log_button = QPushButton(self.tr("日志目录"))
        open_log_button.setObjectName("Ghost")
        open_log_button.clicked.connect(self._open_log_dir)
        console_head.addWidget(open_log_button)
        console_card.body.addLayout(console_head)
        self.console = QTextEdit()
        self.console.setObjectName("Console")
        self.console.setReadOnly(True)
        self.console.document().setMaximumBlockCount(4000)
        self.console_highlighter = LogHighlighter(self.console.document())
        console_card.body.addWidget(self.console, 1)
        right.addWidget(console_card)

    @staticmethod
    def _card_title(title: str, subtitle: str, extra: QWidget | None = None) -> QWidget:
        from .widgets import card_title_row

        return card_title_row(title, subtitle, extra)

    def _connect(self) -> None:
        self.name_edit.editingFinished.connect(self._on_name_changed)
        self.java_combo.currentIndexChanged.connect(self._on_java_changed)
        self.memory_slider.valueChanged.connect(self._on_memory_preview)
        self.memory_slider.sliderReleased.connect(self._save_memory)
        self.resolution_check.toggled.connect(self._on_resolution_toggled)
        self.width_spin.valueChanged.connect(self._on_resolution_changed)
        self.height_spin.valueChanged.connect(self._on_resolution_changed)
        self.search_edit.textChanged.connect(self._apply_search)
        self.instance_combo.currentIndexChanged.connect(self._on_instance_changed)
        self.ctx.bus.config_changed.connect(self.reload_config)
        self.ctx.bus.javas_changed.connect(self.reload_config)
        self.ctx.bus.versions_changed.connect(self.refresh_versions)
        self.ctx.bus.accounts_changed.connect(self._refresh_account_card)
        self.ctx.bus.instances_changed.connect(self._reload_instances)
        self.ctx.bus.game_exited.connect(self._on_exited)

    # ------------------------------------------------------------------
    def _instance_dir(self) -> Path:
        return self.ctx.config.instance_path(self.ctx.config.selected_instance_id)

    def refresh_versions(self) -> None:
        game_dir = self._instance_dir()
        try:
            game_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._append_log(f"[错误] 游戏目录不可写：{exc}")
        versions = scan_installed_versions(game_dir)

        while self.version_layout.count():
            item = self.version_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._rows.clear()

        if not versions:
            empty = QWidget()
            empty_layout = QVBoxLayout(empty)
            empty_layout.setContentsMargins(20, 40, 20, 40)
            empty_layout.setSpacing(8)
            icon = QLabel()
            icon.setPixmap(make_avatar("Alex", 48))
            icon.setAlignment(Qt.AlignCenter)
            empty_layout.addWidget(icon)
            label = QLabel(self.tr("还没有安装任何版本"))
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("font-size: 15px; font-weight: 600;")
            empty_layout.addWidget(label)
            hint = QLabel(
                self.tr("前往下载页安装一个正式版，或用 HMCL 安装后指向同一个游戏目录。")
            )
            hint.setObjectName("Muted")
            hint.setAlignment(Qt.AlignCenter)
            hint.setWordWrap(True)
            empty_layout.addWidget(hint)
            button = QPushButton(self.tr("安装 Minecraft"))
            button.setObjectName("Primary")
            button.setMaximumWidth(180)
            button.clicked.connect(lambda: self.ctx.bus.navigate.emit("download"))
            empty_layout.addWidget(button, alignment=Qt.AlignHCenter)
            self.version_layout.addWidget(empty)
            self.version_layout.addStretch(1)
            self.version_count.setText(self.tr("0 个版本"))
            self._select_version("")
            return

        for version in versions:
            row = VersionRow(version, self.ctx, str(game_dir))
            row.selected.connect(self._select_version)
            row.activated.connect(self._launch_version)
            row.settings_requested.connect(self.ctx.bus.focus_version.emit)
            self.version_layout.insertWidget(self.version_layout.count() - 1, row)
            self._rows[version.id] = row

        self.version_count.setText(t("HomePage", "{0} 个版本", len(versions)))
        self._apply_search(self.search_edit.text())
        instance = self.ctx.config.selected_instance()
        if self._selected_id in self._rows:
            keep = self._selected_id
        elif instance.version_id and instance.version_id in self._rows:
            keep = instance.version_id
        else:
            keep = versions[0].id
        self._select_version(keep)

    def _apply_search(self, text: str) -> None:
        needle = (text or "").strip().lower()
        for version_id, row in self._rows.items():
            row.setVisible(not needle or needle in version_id.lower())

    def _select_version(self, version_id: str) -> None:
        self._selected_id = version_id
        for rid, row in self._rows.items():
            row.set_selected(rid == version_id)
        if not version_id:
            self.launch_info.setText(self.tr("未选择版本"))
            self.launch_button.setEnabled(False)
            self.java_hint.setText("")
            return
        row = self._rows.get(version_id)
        loader = row.version.loader if row else ""
        self.launch_info.setText(
            t("HomePage", "将启动：{0}", version_id) + (f" · {loader}" if loader else "")
        )
        self.launch_button.setEnabled(bool(row and not row.version.error))
        self._update_java_hint(version_id)

    def _update_java_hint(self, version_id: str) -> None:
        try:
            merged = load_version(self._instance_dir(), version_id)
            self._required_java = merged.java_major or 21
            self.java_hint.setText(t("HomePage", "需要 Java {0}", self._required_java))
        except (VersionError, OSError) as exc:
            self._required_java = 21
            self.java_hint.setText(self.tr("版本文件异常"))
            self.java_hint.setToolTip(str(exc))

    # ------------------------------------------------------------------
    def reload_config(self) -> None:
        config = self.ctx.config
        self._reload_instances()
        self._refresh_account_card()

        memory = max(1024, min(16384, int(config.memory_mb)))
        self.memory_slider.blockSignals(True)
        self.memory_slider.setValue(memory)
        self.memory_slider.blockSignals(False)
        self._on_memory_preview(memory)

        self.resolution_check.blockSignals(True)
        self.resolution_check.setChecked(bool(config.width and config.height))
        self.resolution_check.blockSignals(False)
        self.width_spin.blockSignals(True)
        self.height_spin.blockSignals(True)
        self.width_spin.setValue(config.width or 854)
        self.height_spin.setValue(config.height or 480)
        self.width_spin.blockSignals(False)
        self.height_spin.blockSignals(False)
        self.width_spin.setEnabled(self.resolution_check.isChecked())
        self.height_spin.setEnabled(self.resolution_check.isChecked())

        self._refresh_java_combo()
        self._refresh_servers()
        self.dir_button.setToolTip(str(self._instance_dir()))
        self._update_java_hint(self._selected_id) if self._selected_id else None

    def _refresh_servers(self) -> None:
        config = self.ctx.config
        self.server_combo.blockSignals(True)
        self.server_combo.clear()
        self.server_combo.addItem(t("HomePage", "不自动连接"), "")
        now = time.time()
        for entry in config.servers:
            label = f"{entry.name} · {entry.host}:{entry.port}"
            cached = self._server_ping_cache.get(entry.id)
            if cached is not None and now - cached[0] < 300:
                _age, latency, players = cached
                if latency < 0:
                    label += f" · {t('HomePage', '无法连接')}"
                else:
                    label += f" · {players or t('HomePage', '可连接')} · {latency}ms"
            self.server_combo.addItem(label, entry.id)
        index = self.server_combo.findData(config.active_server_id)
        self.server_combo.setCurrentIndex(index if index >= 0 else 0)
        self.server_combo.blockSignals(False)
        if self._loaded_instance != config.selected_instance_id:
            # 新导入/恢复的整合包实例会被自动选中，这里同步刷新版本列表
            self._loaded_instance = config.selected_instance_id
            self._selected_id = ""
            self.refresh_versions()
        self._ping_servers()

    def _ping_servers(self) -> None:
        """异步刷新主页服务器在线人数，结果缓存 5 分钟。"""
        if self._server_ping is not None and self._server_ping.isRunning():
            return
        now = time.time()
        pending = [
            entry
            for entry in self.ctx.config.servers
            if entry.id not in self._server_ping_cache
            or now - self._server_ping_cache[entry.id][0] >= 300
        ]
        if not pending:
            return
        worker = ServerPingWorker(pending, self)
        worker.result.connect(self._on_server_ping)
        worker.finished.connect(self._on_server_ping_finished)
        self._server_ping = worker
        worker.start()

    def _on_server_ping(self, server_id: str, latency: int, players: str) -> None:
        self._server_ping_cache[server_id] = (time.time(), latency, players)
        index = self.server_combo.findData(server_id)
        if index < 0:
            return
        entry = next((item for item in self.ctx.config.servers if item.id == server_id), None)
        if entry is None:
            return
        label = f"{entry.name} · {entry.host}:{entry.port}"
        if latency < 0:
            label += f" · {t('HomePage', '无法连接')}"
        else:
            label += f" · {players or t('HomePage', '可连接')} · {latency}ms"
        self.server_combo.setItemText(index, label)

    def _on_server_ping_finished(self) -> None:
        worker, self._server_ping = self._server_ping, None
        if worker is not None:
            worker.deleteLater()

    def _on_server_changed(self, index: int) -> None:
        server_id = str(self.server_combo.itemData(index) or "")
        if server_id == self.ctx.config.active_server_id:
            return
        self.ctx.config.active_server_id = server_id
        self.ctx.config.save()
        if server_id:
            entry = self.ctx.config.active_server()
            if entry is not None:
                self.ctx.bus.toast.emit(f"启动后将自动连接 {entry.name}")

    def _open_server_dialog(self) -> None:
        dialog = ServerDialog(self.ctx, self)
        dialog.exec()
        self._refresh_servers()

    def _reload_instances(self) -> None:
        current = self.ctx.config.selected_instance_id
        self.instance_combo.blockSignals(True)
        self.instance_combo.clear()
        for instance in self.ctx.config.instance_list():
            label = f"[整合包] {instance.name}" if instance.modpack else instance.name
            if instance.mc_version:
                label += f" · {instance.mc_version}"
            if instance.loader:
                label += f" · {instance.loader}"
            self.instance_combo.addItem(label, instance.id)
        index = self.instance_combo.findData(current)
        self.instance_combo.setCurrentIndex(index if index >= 0 else 0)
        self.instance_combo.blockSignals(False)

    def _on_instance_changed(self, index: int) -> None:
        instance_id = str(self.instance_combo.itemData(index) or "default")
        if instance_id == self.ctx.config.selected_instance_id:
            return
        self.ctx.config.select_instance(instance_id)
        self._selected_id = ""
        self.refresh_versions()
        self.reload_config()
        self.ctx.bus.toast.emit(f"已切换到实例：{self.instance_combo.currentText()}")

    def launch_instance_version(self, instance_id: str, version_id: str) -> bool:
        """供「整合包」页调用：切换到指定实例并直接启动版本。"""
        self.ctx.config.select_instance(instance_id)
        self._selected_id = ""
        self._loaded_instance = self.ctx.config.selected_instance_id
        self._reload_instances()
        self.refresh_versions()
        if version_id not in self._rows:
            return False
        self._select_version(version_id)
        self._start_launch()
        return True

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self.avatar_label and event.type() == QEvent.MouseButtonRelease:
            self._show_account_menu()
            return True
        return super().eventFilter(obj, event)

    def _show_account_menu(self) -> None:
        """点头像直接切换账号，无需进入账号页。"""
        menu = QMenu(self)
        current = self.ctx.current_account()
        current_id = current.id if current is not None else ""
        for account in list(self.ctx.accounts.accounts):
            action = menu.addAction(
                f"{account.name} · {t('HomePage', account.type_label)}"
            )
            action.setCheckable(True)
            action.setChecked(account.id == current_id)
            action.triggered.connect(
                lambda _checked=False, account_id=account.id: self._switch_account(account_id)
            )
        if not self.ctx.accounts.accounts:
            action = menu.addAction("暂无账号")
            action.setEnabled(False)
        menu.addSeparator()
        menu.addAction("管理账号…", lambda: self.ctx.bus.navigate.emit("accounts"))
        menu.exec(self.avatar_label.mapToGlobal(self.avatar_label.rect().bottomLeft()))

    def _switch_account(self, account_id: str) -> None:
        self.ctx.accounts.set_selected(account_id)
        self._refresh_account_card()
        self.ctx.bus.accounts_changed.emit()
        self.ctx.bus.toast.emit(f"已切换账号：{self.ctx.accounts.selected().name}")

    def _refresh_account_card(self) -> None:
        account = self.ctx.current_account()
        if account is None:
            return
        kinds = {"offline": "gray", "microsoft": "blue", "authlib": "orange"}
        self.account_badge.setText(t("HomePage", account.type_label))
        self.account_badge.set_kind(kinds.get(account.type, "gray"))
        self.avatar_label.setPixmap(make_avatar(account.name or "Steve", 56))
        if not self.name_edit.hasFocus():
            self.name_edit.blockSignals(True)
            self.name_edit.setText(account.name)
            self.name_edit.blockSignals(False)
        self.name_edit.setReadOnly(account.type != "offline")
        if account.uuid:
            self.uuid_label.setText(f"UUID: {account.uuid[:18]}…")
        else:
            self.uuid_label.setText(t("HomePage", "尚未完成登录"))
        tip = account.note or t("HomePage", account.type_label)
        if account.auth_server:
            tip += f" · {account.auth_server}"
        self.name_edit.setToolTip(tip)

    def _refresh_java_combo(self) -> None:
        current = self.ctx.config.java_path
        self.java_combo.blockSignals(True)
        self.java_combo.clear()
        self.java_combo.addItem(t("HomePage", "自动选择（按版本匹配）"), "")
        for java in self.ctx.javas:
            self.java_combo.addItem(f"{java.label}", java.path)
            self.java_combo.setItemData(
                self.java_combo.count() - 1, java.path, Qt.ToolTipRole
            )
        if current:
            index = self.java_combo.findData(current)
            if index < 0:
                info = probe_java(current)
                if info:
                    self.java_combo.addItem(info.label, info.path)
                    index = self.java_combo.count() - 1
                else:
                    self.java_combo.addItem(
                        t("HomePage", "无效的 Java：{0}", Path(current).name), current
                    )
                    index = self.java_combo.count() - 1
            self.java_combo.setCurrentIndex(index)
        else:
            self.java_combo.setCurrentIndex(0)
        self.java_combo.blockSignals(False)

    # ------------------------------------------------------------------
    def _on_name_changed(self) -> None:
        name = self.name_edit.text().strip() or "Steve"
        account = self.ctx.current_account()
        if account is not None and account.type == "offline":
            from ..launcher import offline_uuid

            if len(name) > 16:
                name = name[:16]
            account.name = name
            account.uuid = offline_uuid(name)
            self.ctx.accounts.update(account)
            self.ctx.bus.accounts_changed.emit()
        self.ctx.config.player_name = name
        self.ctx.config.save_debounced()
        self._refresh_account_card()

    def _on_java_changed(self, index: int) -> None:
        path = str(self.java_combo.itemData(index) or "")
        self.ctx.config.java_path = path
        self.ctx.config.save_debounced()
        self._update_java_hint(self._selected_id) if self._selected_id else None

    def _on_memory_preview(self, value: int) -> None:
        self.memory_value.setText(f"{value / 1024:.1f} GB")

    def _save_memory(self) -> None:
        self.ctx.config.memory_mb = int(self.memory_slider.value())
        self.ctx.config.save()

    def _on_resolution_toggled(self, checked: bool) -> None:
        self.width_spin.setEnabled(checked)
        self.height_spin.setEnabled(checked)
        if checked:
            self.ctx.config.width = int(self.width_spin.value())
            self.ctx.config.height = int(self.height_spin.value())
        else:
            self.ctx.config.width = 0
            self.ctx.config.height = 0
        self.ctx.config.save_debounced()

    def _on_resolution_changed(self) -> None:
        if self.resolution_check.isChecked():
            self.ctx.config.width = int(self.width_spin.value())
            self.ctx.config.height = int(self.height_spin.value())
            self.ctx.config.save_debounced()

    # ------------------------------------------------------------------
    def _launch_version(self, version_id: str) -> None:
        self._select_version(version_id)
        self._start_launch()

    def _on_launch_clicked(self) -> None:
        if self._queue_running:
            self.ctx.bus.toast.emit("多选启动队列进行中，请先点击“停止队列”。")
            return
        if self._session is not None:
            if self._session.process.poll() is None:
                self._append_log("[启动] 正在停止游戏…")
                self._session.stop()
            return
        if self._worker is not None and self._worker.isRunning():
            self._append_log("[启动] 取消启动流程…")
            self._worker.cancel()
            return
        self._start_launch()

    def _start_launch(self) -> None:
        version_id = self._selected_id
        if not version_id:
            QMessageBox.information(self, APP_NAME, "请先选择一个版本。")
            return
        row = self._rows.get(version_id)
        if row and row.version.error:
            QMessageBox.warning(self, "版本损坏", row.version.error)
            return
        account = self.ctx.current_account()
        name = account.name if account is not None else self.name_edit.text().strip()
        if account is None or account.type == "offline":
            name = self.name_edit.text().strip()
            if not name:
                QMessageBox.warning(self, "昵称不能为空", "请输入一个玩家昵称。")
                return
            if len(name) > 16 or not re.fullmatch(r"[\w\u4e00-\u9fff]+", name, re.UNICODE):
                QMessageBox.warning(self, "昵称不合法", "昵称需为 1-16 个字符，且不能包含空格或特殊符号。")
                return
        elif account.type == "microsoft" and not account.access_token:
            QMessageBox.warning(
                self, "账号未登录", "当前微软账号尚未完成登录，请到账号页重新登录。"
            )
            self.ctx.bus.navigate.emit("accounts")
            return

        game_dir = self._instance_dir()
        try:
            merged = load_version(game_dir, version_id)
            required = merged.java_major or 21
        except (VersionError, OSError) as exc:
            QMessageBox.critical(self, "无法读取版本", str(exc))
            return

        java, warning = pick_java(self.ctx.javas, required, self.ctx.config.java_path)
        if java is None:
            QMessageBox.warning(
                self,
                "未找到 Java",
                f"{warning}\n\n请先在设置页选择 Java，或安装 Java {required}。",
            )
            self.ctx.bus.navigate.emit("settings")
            return
        if warning:
            answer = QMessageBox.question(
                self,
                "Java 版本提示",
                f"{warning}\n\n仍要继续启动吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

        self._session = None
        self.progress_card.setVisible(True)
        self.progress_stage.setText(self.tr("准备启动"))
        self.progress_detail.setText("")
        self.progress_bar.setValue(0)
        self.launch_button.setText(self.tr("取消"))

        self._worker = LaunchWorker(
            self.ctx,
            version_id,
            name,
            java,
            self.ctx.config.memory_mb,
            self.ctx.config.width,
            self.ctx.config.height,
            self.ctx.config.extra_jvm_args,
            extra_game_args=self.ctx.config.extra_game_args,
            game_dir=game_dir,
            account=account,
            parent=self,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(self._on_log)
        self._worker.started.connect(self._on_started)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.preflight_blocked.connect(self._on_preflight_blocked)
        self._append_log(f"[启动] 准备启动 {version_id}，Java：{java.path}")
        self._worker.start()

    def _cancel_launch(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._append_log("[启动] 已请求取消。")

    def _on_progress(self, progress: Progress) -> None:
        self.progress_card.setVisible(True)
        self.progress_stage.setText(progress.stage)
        self.progress_bar.setValue(int(progress.percent * 1000))
        detail = progress.detail
        if progress.speed > 0 and progress.percent < 1:
            detail += f" · {progress.speed / 1048576:.1f} MB/s"
        self.progress_detail.setText(detail)

    def _on_log(self, line: str) -> None:
        self._append_log(line)

    def _append_log(self, line: str) -> None:
        # 统一走总线：主页渲染由 _write_console 完成，同时落盘到 data/logs/launcher.log
        self.ctx.bus.log.emit(line)

    def _write_console(self, line: str) -> None:
        self._log_lines.append(line)
        if len(self._log_lines) > 4000:
            del self._log_lines[:1000]
        if not self._matches_filter(line):
            return
        self.console.append(line)
        bar = self.console.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _matches_filter(self, line: str) -> bool:
        if self.console_filter.currentData() != "problems":
            return True
        return _log_level(line) != "info"

    def _clear_console(self) -> None:
        self._log_lines.clear()
        self.console.clear()

    def _rebuild_console(self) -> None:
        self.console.clear()
        for line in self._log_lines:
            if self._matches_filter(line):
                self.console.append(line)

    def _on_started(self, session) -> None:
        self._session = session
        self.progress_card.setVisible(False)
        self.launch_button.setText(self.tr("停止游戏"))
        self.launch_button.setEnabled(True)
        self.launch_info.setText(t("HomePage", "游戏运行中：{0}", self._selected_id))
        self._append_log("[启动] 游戏进程已启动。")
        action = self.ctx.config.after_launch_action
        if action == "hide":
            QTimer.singleShot(800, self.ctx.bus.hide_window.emit)
        elif action == "close":
            QTimer.singleShot(1200, lambda: self.window().close())

    def _on_failed(self, message: str) -> None:
        self._append_log(f"[错误] {message}")
        self._reset_launch_ui()
        if self._queue_running:
            self._append_log("[多选启动] 当前版本启动失败，继续队列中的下一个。")
            return  # 队列模式只记录，不弹框打断
        QMessageBox.critical(self, "启动失败", message)

    def _on_exited(self, code: int, tail: str) -> None:
        session, self._session = self._session, None
        duration = ""
        if session is not None and getattr(session, "started_at", 0):
            minutes = max(0, int((time.time() - session.started_at) / 60))
            duration = f"，运行 {minutes} 分钟"
        self._append_log(f"[启动] 游戏已退出（代码 {code}{duration}）。")
        self._reset_launch_ui()
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        if self._launch_queue:
            # 队列模式：只记录异常，不弹框打断，自动推进下一个
            if code != 0:
                self._append_log(
                    f"[多选启动] {self._selected_id} 异常退出（代码 {code}），继续下一个。"
                )
            QTimer.singleShot(0, self._maybe_advance_queue)
            return
        if code != 0:
            if session is not None:
                archived = archive_crash_log(session, code)
                if archived is not None:
                    self._append_log(f"[崩溃] 本次日志已归档：{archived}")
            hint = crash_hint(code, tail)
            self._append_log(hint)
            QMessageBox.warning(self, "游戏异常退出", hint)
        elif not self.ctx.config.keep_launcher_on_game_exit:
            QTimer.singleShot(200, lambda: self.window().close())

    def _reset_launch_ui(self) -> None:
        self.progress_card.setVisible(False)
        self.launch_button.setText(self.tr("启动游戏"))
        self.launch_button.setEnabled(bool(self._selected_id))
        if self._selected_id:
            row = self._rows.get(self._selected_id)
            loader = row.version.loader if row else ""
            self.launch_info.setText(
                t("HomePage", "将启动：{0}", self._selected_id)
                + (f" · {loader}" if loader else "")
            )
        else:
            self.launch_info.setText(self.tr("未选择版本"))

    def _on_worker_finished(self) -> None:
        # 进程仍在运行时保留 worker 引用，直到 exited 信号到达。
        if self._session is None and self._worker is not None:
            worker = self._worker
            self._worker = None
            worker.deleteLater()
        # 队列模式：worker 结束但游戏未启动（预检中止 / 启动失败）时推进队列
        if self._queue_running and self._launch_queue and self._session is None:
            QTimer.singleShot(0, self._maybe_advance_queue)

    def _on_preflight_blocked(self, blocked: list) -> None:
        """预检阻止项：弹框让用户选择仍要启动 / 中止。"""
        worker = self._worker
        if worker is None:
            return
        answer = QMessageBox.warning(
            self,
            "启动前预检未通过",
            "\n".join(str(line) for line in blocked) + "\n\n仍要启动吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        worker._preflight_continue = answer == QMessageBox.Yes
        worker._preflight_wait.set()
        if not worker._preflight_continue:
            self._append_log("[预检] 用户选择不启动，已中止。")
            self._reset_launch_ui()

    # ------------------------------------------------------------------
    # 多选启动队列
    # ------------------------------------------------------------------
    def _open_queue_dialog(self) -> None:
        if self._queue_running:
            self.ctx.bus.toast.emit("已有启动队列在进行中。")
            return
        if self._session is not None or (
            self._worker is not None and self._worker.isRunning()
        ):
            self.ctx.bus.toast.emit("当前已有游戏在运行，请先退出再使用多选启动。")
            return
        if not self._rows:
            QMessageBox.information(self, "多选启动", "当前没有可启动的版本。")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(t("HomePage", "多选启动"))
        dialog.setMinimumSize(360, 420)
        layout = QVBoxLayout(dialog)
        tip = QLabel(
            self.tr("按选择顺序依次启动；同一实例目录不能并行，需等前一个游戏退出。")
        )
        tip.setObjectName("Muted")
        tip.setWordWrap(True)
        layout.addWidget(tip)
        list_widget = QListWidget()
        list_widget.setSelectionMode(QAbstractItemView.MultiSelection)
        for version_id in self._rows:
            list_widget.addItem(version_id)
        layout.addWidget(list_widget, 1)
        buttons = QHBoxLayout()
        cancel_btn = QPushButton(self.tr("取消"))
        cancel_btn.clicked.connect(dialog.reject)
        launch_btn = QPushButton(self.tr("启动"))
        launch_btn.setObjectName("Primary")
        launch_btn.clicked.connect(dialog.accept)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(launch_btn)
        layout.addLayout(buttons)
        if dialog.exec() != QDialog.Accepted:
            return
        selected = [
            list_widget.item(i).text()
            for i in range(list_widget.count())
            if list_widget.item(i).isSelected()
        ]
        if not selected:
            return

        self._launch_queue = list(selected)
        self._queue_total = len(selected)
        self._queue_running = True
        self._queue_stop = False
        self.queue_stop_button.setVisible(True)
        self.queue_launch_button.setEnabled(False)
        self._append_log(f"[多选启动] 已加入队列：{'、'.join(selected)}")
        self._launch_queue_next()

    def _launch_queue_next(self) -> None:
        if not self._launch_queue:
            self._finish_queue()
            return
        if self._queue_stop:
            self._finish_queue("已停止队列。")
            return
        version_id = self._launch_queue.pop(0)
        self._append_log(
            f"[多选启动] 开始启动：{version_id}（队列剩余 {len(self._launch_queue)}）"
        )
        self._select_version(version_id)
        self._start_launch()
        # _start_launch 可能因 Java/账号问题提前返回（未创建 worker），交给下一轮推进
        if self._worker is None or not self._worker.isRunning():
            QTimer.singleShot(0, self._maybe_advance_queue)

    def _maybe_advance_queue(self) -> None:
        """队列推进的唯一入口：仅在无运行中游戏 / 无运行中 worker 时启动下一个。"""
        if not self._queue_running or not self._launch_queue:
            return
        if self._session is not None:
            return
        if self._worker is not None and self._worker.isRunning():
            return
        self._launch_queue_next()

    def _stop_queue(self) -> None:
        if not self._queue_running:
            return
        self._queue_stop = True
        self._append_log("[多选启动] 已请求停止队列：当前版本退出后不再继续。")
        self.ctx.bus.toast.emit("已请求停止队列。")

    def _finish_queue(self, message: str = "") -> None:
        total = self._queue_total
        self._launch_queue = []
        self._queue_running = False
        self._queue_stop = False
        self._queue_total = 0
        self.queue_stop_button.setVisible(False)
        self.queue_launch_button.setEnabled(True)
        if message:
            self._append_log(f"[多选启动] {message}")
            self.ctx.bus.toast.emit(message)
        elif total:
            self._append_log(f"[多选启动] 已依次启动 {total} 个版本。")
            self.ctx.bus.toast.emit(f"已依次启动 {total} 个版本。")

    # ------------------------------------------------------------------
    def _open_game_dir(self) -> None:
        path = self._instance_dir()
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _open_log_dir(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(DATA_DIR / "logs")))

    def shutdown(self) -> None:
        """关闭启动器时的清理：取消准备中的任务，但不强杀已启动的游戏。"""
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel_event.set()
            wait_thread(self._worker, 4000)
