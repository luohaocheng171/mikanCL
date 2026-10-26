"""下载页：版本列表 → 版本详情 → 原版与 Mod 加载器串行安装。"""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

from PySide6.QtCore import QStandardPaths, QThread, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME
from ..content import ContentError, pick_best_version
from ..context import AppContext, wait_thread
from ..installer import GameInstaller, Progress
from ..java import pick_java
from ..modloader import (
    LOADER_LABELS,
    LoaderError,
    install_loader,
    java_for_mc,
    list_loader_versions,
)
from ..net import Cancelled, DownloadError, Http
from ..version import (
    CATEGORY_LABELS,
    VersionError,
    scan_installed_versions,
    version_category,
)
from .widgets import Badge, Card, hline, page_header

# 分类筛选：键为 version_category 的返回值，all 表示不过滤
_CATEGORY_FILTERS = [
    ("all", "全部"),
    ("release", "正式版"),
    ("snapshot", "快照"),
    ("april", "愚人节版本"),
    ("old", "远古版本"),
]

_LOADER_ORDER = ("forge", "neoforge", "fabric", "quilt", "liteloader")

_LOADER_DESCRIPTIONS = {
    "forge": "老牌加载器，兼容大量整合包",
    "neoforge": "Forge 分支，面向 1.20.1+",
    "fabric": "轻量快速，自动附带 Fabric API",
    "quilt": "Fabric 衍生，兼容其 Mod",
    "liteloader": "仅支持 1.12.2 及更早版本",
}

_ORIGINAL = ""


def _safe_filename(text: str, fallback: str = "file") -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\s]+', "-", str(text or "")).strip(".-")
    return cleaned or fallback


def _download_dir() -> Path:
    try:
        locations = QStandardPaths.standardLocations(QStandardPaths.DownloadLocation)
        if locations:
            return Path(locations[0])
    except Exception:  # noqa: BLE001 - 取不到标准目录时退回用户目录
        pass
    return Path.home() / "Downloads"


def _repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


# ---------------------------------------------------------------------------
# 后台任务
# ---------------------------------------------------------------------------
class ManifestWorker(QThread):
    """加载版本清单（网络请求，避免阻塞界面）。"""

    loaded = Signal(object, object, bool)
    failed = Signal(str)

    def __init__(self, ctx: AppContext, force: bool, preferred_id: str, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.force = force
        self.preferred_id = preferred_id

    def run(self) -> None:
        try:
            payload, source_name, cached = self.ctx.sources.get_manifest(
                force=self.force, preferred_id=self.preferred_id
            )
            self.loaded.emit(payload.get("data") or {}, source_name, cached)
        except DownloadError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class ClientJarSaveWorker(QThread):
    """仅下载某个版本的客户端 Jar，不写入游戏目录。"""

    progress = Signal(float, float, str)
    log = Signal(str)
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, ctx: AppContext, entry: dict, dest: Path, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.entry = dict(entry)
        self.dest = Path(dest)
        self.cancel_event = threading.Event()
        self.pause_event = threading.Event()

    @staticmethod
    def _client_of(raw) -> dict | None:
        downloads = raw.get("downloads") if isinstance(raw, dict) else None
        client = downloads.get("client") if isinstance(downloads, dict) else None
        return client if isinstance(client, dict) else None

    def _client_info(self, version_id: str) -> dict:
        """优先读本地版本 JSON，其次按清单地址在线获取。"""
        local = self.ctx.config.game_path / "versions" / version_id / f"{version_id}.json"
        if local.is_file():
            try:
                raw = json.loads(local.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise VersionError(f"本地版本 JSON 无法解析：{local}\n{exc}") from exc
            client = self._client_of(raw)
            if client is not None and str(client.get("url") or ""):
                self.log.emit(f"[下载] 使用本地版本信息：{local.name}")
                return client
        url = str(self.entry.get("url") or "")
        if not url:
            raise VersionError(f"版本 {version_id} 缺少版本 JSON 地址，无法获取客户端信息。")
        errors: list[str] = []
        fetched = False
        for candidate in self.ctx.sources.resource_candidates(url):
            try:
                raw = Http(timeout=30).get_json(candidate)
            except DownloadError as exc:
                errors.append(f"{candidate.source_name}: {exc}")
                continue
            fetched = True
            client = self._client_of(raw)
            if client is not None and str(client.get("url") or ""):
                return client
        if fetched:
            raise VersionError(
                f"版本 {version_id} 的版本 JSON 中没有 downloads.client"
                "（可能是旧版本或自定义版本），无法仅下载客户端 Jar。"
            )
        raise DownloadError(
            f"无法获取版本 {version_id} 的版本 JSON：\n" + "\n".join(errors[-3:])
        )

    def run(self) -> None:
        try:
            version_id = str(self.entry.get("id") or "")
            client = self._client_info(version_id)
            url = str(client.get("url") or "")
            if not url:
                raise VersionError(
                    f"版本 {version_id} 缺少 downloads.client，无法仅下载客户端 Jar。"
                )
            total = int(client.get("size") or 0)
            self.dest.parent.mkdir(parents=True, exist_ok=True)
            self.log.emit(f"[下载] {version_id} 客户端 → {self.dest}")
            state = {"bytes": 0, "time": time.monotonic(), "sent": 0}

            def report(count: int) -> None:
                state["bytes"] += count
                now = time.monotonic()
                elapsed = now - state["time"]
                if elapsed < 0.3:
                    return
                speed = (state["bytes"] - state["sent"]) / elapsed
                state["time"] = now
                state["sent"] = state["bytes"]
                percent = state["bytes"] / total if total > 0 else 0.0
                detail = f"{state['bytes'] / 1048576:.1f} MB"
                if total > 0:
                    detail += f" / {total / 1048576:.1f} MB"
                self.progress.emit(min(0.99, percent), speed, detail)

            Http(timeout=60).download_to_path(
                self.ctx.sources.resource_candidates(url),
                self.dest,
                size=total,
                sha1=str(client.get("sha1") or ""),
                cancel=self.cancel_event,
                pause=self.pause_event,
                log=self.log.emit,
                on_bytes=report,
            )
            self.progress.emit(1.0, 0.0, "下载完成")
            self.done.emit(str(self.dest))
        except Cancelled:
            self.failed.emit("下载已取消。")
        except (DownloadError, VersionError, OSError) as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - 统一回传可读原因
            self.failed.emit(f"保存失败：{exc}")

    def cancel(self) -> None:
        self.cancel_event.set()


class LoaderScanWorker(QThread):
    """依次检测 5 种加载器针对该 MC 版本的可用版本。"""

    result = Signal(str, object)
    failed = Signal(str, str)

    def __init__(self, mc_version: str, parent=None):
        super().__init__(parent)
        self.mc_version = mc_version
        self._cancelled = threading.Event()

    def run(self) -> None:
        for kind in _LOADER_ORDER:
            if self._cancelled.is_set():
                return
            try:
                versions = list_loader_versions(kind, self.mc_version)
                self.result.emit(kind, list(versions or []))
            except LoaderError as exc:
                self.failed.emit(kind, str(exc))
            except Exception as exc:  # noqa: BLE001
                self.failed.emit(kind, str(exc))

    def cancel(self) -> None:
        self._cancelled.set()


class ChainInstallWorker(QThread):
    """串行执行：安装原版 → 安装加载器 →（Fabric）安装 Fabric API。"""

    progress = Signal(object)
    log = Signal(str)
    done = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        ctx: AppContext,
        entry: dict,
        kind: str,
        loader_version: str,
        pause: threading.Event | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.ctx = ctx
        self.entry = entry
        self.kind = kind
        self.loader_version = loader_version
        self.cancel_event = threading.Event()
        self.pause_event = pause or threading.Event()

    def run(self) -> None:
        try:
            config = self.ctx.config
            game_dir = config.game_path
            mc_version = str(self.entry.get("id") or "")
            installer = GameInstaller(
                config,
                self.ctx.sources,
                progress_cb=self.progress.emit,
                log_cb=self.log.emit,
                cancel=self.cancel_event,
                pause=self.pause_event,
            )
            json_path = game_dir / "versions" / mc_version / f"{mc_version}.json"
            if json_path.exists():
                self.log.emit(f"[安装] 原版 {mc_version} 已存在，跳过下载。")
                self.progress.emit(Progress("检查原版", 0.05, mc_version))
            else:
                self.log.emit(f"[安装] 开始安装原版 {mc_version}")
                installer.install_version(self.entry)
            if self.cancel_event.is_set():
                raise Cancelled()

            final_id = mc_version
            if self.kind:
                java, hint = pick_java(
                    self.ctx.javas,
                    java_for_mc(mc_version),
                    str(config.java_path or ""),
                )
                if java is None:
                    raise LoaderError(
                        hint or "未找到可用的 Java，请前往设置页指定 Java 后再安装加载器。"
                    )
                if hint:
                    self.log.emit(f"[加载器] {hint}")
                label = LOADER_LABELS.get(self.kind, self.kind)
                self.progress.emit(
                    Progress("安装加载器", 0.6, f"{label} {self.loader_version}".strip())
                )
                final_id = install_loader(
                    installer,
                    self.kind,
                    mc_version,
                    self.loader_version,
                    java.path,
                    self.log.emit,
                    self.cancel_event,
                )
                if self.kind == "fabric":
                    self._install_fabric_api(mc_version)

            self.progress.emit(Progress("安装完成", 1.0, final_id))
            self.done.emit(final_id)
        except Cancelled:
            self.failed.emit("安装已取消。")
        except (VersionError, DownloadError, LoaderError, ContentError, OSError) as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))

    def _install_fabric_api(self, mc_version: str) -> None:
        """Fabric 安装完成后自动附带 Fabric API；失败仅记录警告。"""
        try:
            self.progress.emit(Progress("安装 Fabric API", 0.9, "正在查找项目"))
            self.log.emit("[内容] 正在查找 Fabric API…")
            projects = self.ctx.content.search(
                "modrinth", "mod", "fabric api", mc_version, "fabric", 0, 10
            )
            project = next((p for p in projects if p.slug == "fabric-api"), None)
            if project is None:
                self.log.emit("[内容] 未找到 Fabric API 项目，已跳过。")
                return
            versions = self.ctx.content.versions("modrinth", project.id)
            version = pick_best_version(versions, mc_version, "fabric", "fabric-api")
            if version is None:
                self.log.emit("[内容] 未找到匹配的 Fabric API 文件，已跳过。")
                return
            self.ctx.content.install_content(
                project,
                version,
                self.ctx.config.game_path,
                log=self.log.emit,
                cancel=self.cancel_event,
                pause=self.pause_event,
            )
            self.log.emit(f"[内容] Fabric API 已安装：{version.version_number}")
        except (ContentError, DownloadError, OSError) as exc:
            self.log.emit(f"[内容] Fabric API 安装失败（已忽略）：{exc}")

    def cancel(self) -> None:
        self.cancel_event.set()


# ---------------------------------------------------------------------------
# 加载器卡片
# ---------------------------------------------------------------------------
class LoaderCard(QFrame):
    """可点击选中的加载器卡片，显示名称、状态与版本下拉。"""

    clicked = Signal(str)

    def __init__(
        self,
        kind: str,
        title: str,
        description: str,
        with_combo: bool = True,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.kind = kind
        self.setObjectName("LoaderCard")
        self.setProperty("selected", False)
        self.setProperty("unsupported", False)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(118)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 11, 12, 11)
        layout.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(6)
        name = QLabel(title)
        name.setStyleSheet("font-weight: 700; font-size: 13px;")
        head.addWidget(name, 1)
        self.status = Badge("检测中", "gray")
        head.addWidget(self.status)
        layout.addLayout(head)

        desc = QLabel(description)
        desc.setObjectName("Tiny")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        layout.addStretch(1)

        self.combo = QComboBox()
        if with_combo:
            self.combo.setEnabled(False)
            self.combo.setToolTip("该加载器针对当前 Minecraft 版本的可用版本")
            layout.addWidget(self.combo)
        else:
            self.combo.setVisible(False)
            tip = QLabel("不安装任何 Mod 加载器")
            tip.setObjectName("Tiny")
            layout.addWidget(tip)

    # ------------------------------------------------------------------
    def set_selected(self, value: bool) -> None:
        self.setProperty("selected", value)
        _repolish(self)

    def set_pending(self) -> None:
        self.setProperty("unsupported", False)
        self.status.setText("检测中")
        self.status.set_kind("gray")
        self.combo.clear()
        self.combo.setEnabled(False)
        _repolish(self)

    def set_versions(self, versions: list[str]) -> None:
        self.setProperty("unsupported", False)
        self.status.setText("可选")
        self.status.set_kind("green")
        self.combo.clear()
        self.combo.addItems(versions)
        self.combo.setEnabled(True)
        _repolish(self)

    def set_unsupported(self, reason: str = "不支持") -> None:
        self.setProperty("unsupported", True)
        self.status.setText("不支持")
        self.status.set_kind("orange")
        self.combo.clear()
        self.combo.setEnabled(False)
        self.combo.setToolTip(reason)
        _repolish(self)

    @property
    def is_unsupported(self) -> bool:
        return bool(self.property("unsupported"))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.kind)
        super().mousePressEvent(event)


# ---------------------------------------------------------------------------
# 页面
# ---------------------------------------------------------------------------
class DownloadPage(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self._manifest: dict | None = None
        self._entries: list[dict] = []
        self._entries_by_id: dict[str, dict] = {}
        self._installed_ids: set[str] = set()
        self._detail_entry: dict | None = None
        self._selected_kind: str = _ORIGINAL
        self._loader_cards: dict[str, LoaderCard] = {}
        self._manifest_worker: ManifestWorker | None = None
        self._loader_scan: LoaderScanWorker | None = None
        self._retired_scans: list[LoaderScanWorker] = []
        self._install_worker: ChainInstallWorker | None = None
        self._install_task_id = ""
        self._install_pause = threading.Event()
        self._pending_install: tuple[dict, str, str] | None = None
        self._client_worker: ClientJarSaveWorker | None = None
        self._client_task_id = ""
        self._client_pause = threading.Event()
        self._pending_client_save: tuple[dict, Path] | None = None
        self._installing_mc = ""
        self._installing_kind = ""
        self._updating_table = False
        self._loaded = False

        self._build()
        self._connect()
        self._reload_sources()
        self.refresh()

    # ------------------------------------------------------------------
    # 构建界面
    # ------------------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack)
        self.stack.addWidget(self._build_list_page())
        self.stack.addWidget(self._build_detail_page())

    def _build_list_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(26, 20, 26, 20)
        outer.setSpacing(14)

        header, header_layout = page_header(
            "下载安装", "选择版本后自动检测可用的 Mod 加载器"
        )
        manage = QPushButton("下载源管理")
        manage.setObjectName("Chip")
        manage.clicked.connect(lambda: self.ctx.bus.navigate.emit("settings"))
        header_layout.addWidget(manage)
        outer.addWidget(header)

        tools = Card(margins=16, spacing=10)
        row1 = QHBoxLayout()
        row1.setSpacing(10)
        source_label = QLabel("版本清单来源")
        source_label.setObjectName("Muted")
        row1.addWidget(source_label)
        self.source_combo = QComboBox()
        self.source_combo.setMinimumWidth(240)
        row1.addWidget(self.source_combo)
        self.refresh_button = QPushButton("刷新清单")
        self.refresh_button.clicked.connect(lambda: self.refresh_manifest(force=True))
        row1.addWidget(self.refresh_button)
        row1.addStretch(1)
        self.status_label = QLabel("尚未加载版本清单")
        self.status_label.setObjectName("Tiny")
        row1.addWidget(self.status_label)
        tools.body.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索版本号，如 1.20.1")
        self.search_edit.setClearButtonEnabled(True)
        row2.addWidget(self.search_edit, 1)
        self.category_combo = QComboBox()
        for key, text in _CATEGORY_FILTERS:
            self.category_combo.addItem(text, key)
        self.category_combo.setFixedWidth(132)
        row2.addWidget(self.category_combo)
        self.count_label = QLabel("")
        self.count_label.setObjectName("Tiny")
        row2.addWidget(self.count_label)
        tools.body.addLayout(row2)
        outer.addWidget(tools)

        table_card = Card(margins=14, spacing=10)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["版本", "类型", "发布时间", "状态"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 96)
        self.table.setColumnWidth(2, 108)
        self.table.setColumnWidth(3, 88)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        table_card.body.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        hint = QLabel("双击任意版本，或选中后点击右侧按钮进入详情")
        hint.setObjectName("Tiny")
        bottom.addWidget(hint)
        bottom.addStretch(1)
        self.detail_button = QPushButton("查看详情并安装")
        self.detail_button.setObjectName("Primary")
        self.detail_button.setEnabled(False)
        self.detail_button.clicked.connect(self._open_selected_detail)
        bottom.addWidget(self.detail_button)
        table_card.body.addLayout(bottom)
        outer.addWidget(table_card, 1)
        return page

    def _build_detail_page(self) -> QWidget:
        page = QWidget()
        outer = QHBoxLayout(page)
        outer.setContentsMargins(26, 20, 26, 20)
        outer.setSpacing(16)

        left = QVBoxLayout()
        left.setSpacing(10)
        top_row = QHBoxLayout()
        back = QPushButton("返回版本列表")
        back.setObjectName("Ghost")
        back.clicked.connect(self._back_to_list)
        top_row.addWidget(back)
        top_row.addStretch(1)
        left.addLayout(top_row)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self.detail_title = QLabel("—")
        self.detail_title.setObjectName("DetailTitle")
        title_row.addWidget(self.detail_title)
        self.detail_type_badge = Badge("未知", "gray")
        title_row.addWidget(self.detail_type_badge)
        self.detail_installed_badge = Badge("未安装", "gray")
        title_row.addWidget(self.detail_installed_badge)
        title_row.addStretch(1)
        left.addLayout(title_row)
        self.detail_date = QLabel("")
        self.detail_date.setObjectName("Muted")
        left.addWidget(self.detail_date)
        left.addWidget(hline())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 6, 0)
        content_layout.setSpacing(12)

        location = Card(margins=16, spacing=6)
        location_title = QLabel("安装位置")
        location_title.setObjectName("CardTitle")
        location.body.addWidget(location_title)
        self.location_label = QLabel(str(self.ctx.config.game_path))
        self.location_label.setObjectName("Tiny")
        self.location_label.setWordWrap(True)
        location.body.addWidget(self.location_label)
        location_note = QLabel("原版与加载器都会安装到该目录，可在设置页修改。")
        location_note.setObjectName("Tiny")
        location_note.setWordWrap(True)
        location.body.addWidget(location_note)
        content_layout.addWidget(location)

        loaders = Card(margins=16, spacing=10)
        loaders_title = QLabel("Mod 加载器（可选）")
        loaders_title.setObjectName("CardTitle")
        loaders.body.addWidget(loaders_title)
        loaders_note = QLabel("默认安装原版；选择加载器后将自动匹配对应版本。")
        loaders_note.setObjectName("Tiny")
        loaders_note.setWordWrap(True)
        loaders.body.addWidget(loaders_note)
        grid = QGridLayout()
        grid.setSpacing(10)
        original = LoaderCard(
            _ORIGINAL,
            "原版",
            "纯净客户端，不包含任何 Mod 加载器",
            with_combo=False,
        )
        original.status.setText("默认")
        self._loader_cards[_ORIGINAL] = original
        cards: list[LoaderCard] = [original]
        for kind in _LOADER_ORDER:
            card = LoaderCard(kind, LOADER_LABELS[kind], _LOADER_DESCRIPTIONS[kind])
            self._loader_cards[kind] = card
            cards.append(card)
        for index, card in enumerate(cards):
            grid.addWidget(card, index // 3, index % 3)
        for column in range(3):
            grid.setColumnStretch(column, 1)
        loaders.body.addLayout(grid)
        content_layout.addWidget(loaders)
        content_layout.addStretch(1)
        scroll.setWidget(content)
        left.addWidget(scroll, 1)
        outer.addLayout(left, 1)

        side = Card(margins=18, spacing=10)
        side.setFixedWidth(330)
        side_title = QLabel("安装所选版本")
        side_title.setObjectName("CardTitle")
        side.body.addWidget(side_title)
        self.selection_label = QLabel("当前选择：原版")
        self.selection_label.setObjectName("Muted")
        self.selection_label.setWordWrap(True)
        side.body.addWidget(self.selection_label)
        self.install_button = QPushButton("安装所选版本")
        self.install_button.setObjectName("Primary")
        self.install_button.clicked.connect(self._start_install)
        side.body.addWidget(self.install_button)

        self.client_jar_button = QPushButton("仅下载客户端 Jar")
        self.client_jar_button.setObjectName("Ghost")
        self.client_jar_button.setToolTip("只把原版客户端 jar 保存到指定位置，不安装到游戏目录")
        self.client_jar_button.setEnabled(False)
        self.client_jar_button.clicked.connect(self._save_client_jar)
        side.body.addWidget(self.client_jar_button)

        self.progress_box = QWidget()
        progress_layout = QVBoxLayout(self.progress_box)
        progress_layout.setContentsMargins(0, 4, 0, 0)
        progress_layout.setSpacing(6)
        stage_row = QHBoxLayout()
        self.progress_stage = QLabel("准备安装")
        self.progress_stage.setStyleSheet("font-weight: 600;")
        stage_row.addWidget(self.progress_stage, 1)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setObjectName("Danger")
        self.cancel_button.clicked.connect(self._cancel_install)
        stage_row.addWidget(self.cancel_button)
        progress_layout.addLayout(stage_row)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setTextVisible(False)
        progress_layout.addWidget(self.progress_bar)
        self.progress_detail = QLabel("")
        self.progress_detail.setObjectName("Tiny")
        progress_layout.addWidget(self.progress_detail)
        self.progress_box.setVisible(False)
        side.body.addWidget(self.progress_box)

        log_title = QLabel("安装日志")
        log_title.setObjectName("Tiny")
        side.body.addWidget(log_title)
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("Console")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(800)
        self.log_view.setMinimumHeight(160)
        side.body.addWidget(self.log_view, 1)
        note = QLabel(
            "安装会先补全原版客户端，再写入所选加载器。\n"
            "速度慢时可在设置中启用 BMCLAPI 镜像或自定义下载源。"
        )
        note.setObjectName("Tiny")
        note.setWordWrap(True)
        side.body.addWidget(note)
        outer.addWidget(side)
        return page

    def _connect(self) -> None:
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        self.search_edit.textChanged.connect(lambda _: self._populate())
        self.category_combo.currentIndexChanged.connect(lambda _: self._populate())
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.cellDoubleClicked.connect(lambda _row, _col: self._open_selected_detail())
        for card in self._loader_cards.values():
            card.clicked.connect(self._select_loader)
        self.ctx.bus.config_changed.connect(self._reload_sources)
        self.ctx.bus.config_changed.connect(self.refresh)
        self.ctx.bus.versions_changed.connect(self.refresh)

    # ------------------------------------------------------------------
    # 版本清单
    # ------------------------------------------------------------------
    def _reload_sources(self) -> None:
        config = self.ctx.config
        sources = [s for s in config.sources if s.enabled and s.manifest_url]
        sources.sort(key=lambda s: s.priority)
        self.source_combo.blockSignals(True)
        self.source_combo.clear()
        for source in sources:
            label = source.name
            if source.api_key.strip():
                label += " · API Key"
            self.source_combo.addItem(label, source.id)
        index = self.source_combo.findData(config.selected_source_id)
        if index >= 0:
            self.source_combo.setCurrentIndex(index)
        elif self.source_combo.count():
            self.source_combo.setCurrentIndex(0)
            config.selected_source_id = str(self.source_combo.itemData(0))
            config.save()
        self.source_combo.blockSignals(False)

    def _on_source_changed(self, index: int) -> None:
        source_id = str(self.source_combo.itemData(index) or "")
        if not source_id or source_id == self.ctx.config.selected_source_id:
            return
        self.ctx.config.select_source(source_id)
        self.refresh_manifest(force=True)

    def refresh_manifest(self, force: bool = False) -> None:
        if self._manifest_worker is not None and self._manifest_worker.isRunning():
            return
        self._loaded = True
        self.refresh_button.setEnabled(False)
        self.refresh_button.setText("加载中…")
        self.status_label.setText("正在获取版本清单…")
        self.status_label.setStyleSheet("color: #8aa192;")
        self._manifest_worker = ManifestWorker(
            self.ctx, force, self.ctx.config.selected_source_id, self
        )
        self._manifest_worker.loaded.connect(self._on_manifest_loaded)
        self._manifest_worker.failed.connect(self._on_manifest_failed)
        self._manifest_worker.finished.connect(self._on_manifest_finished)
        self._manifest_worker.start()

    def _on_manifest_loaded(self, manifest: dict, source_name: str, cached: bool) -> None:
        versions = manifest.get("versions") if isinstance(manifest, dict) else None
        if not isinstance(versions, list):
            self._on_manifest_failed("版本清单格式不正确。")
            return
        self._manifest = manifest
        self._entries = [v for v in versions if isinstance(v, dict) and v.get("id")]
        self._entries_by_id = {str(v["id"]): v for v in self._entries}
        suffix = "（缓存）" if cached else ""
        self.status_label.setText(f"{source_name}{suffix} · {len(self._entries)} 个版本")
        self.status_label.setStyleSheet("color: #8fe89b;")
        self.status_label.setToolTip("")
        self._populate()
        self._append_log(f"[清单] 已加载 {len(self._entries)} 个版本（{source_name}{suffix}）")

    def _on_manifest_failed(self, message: str) -> None:
        self.status_label.setText("版本清单获取失败")
        self.status_label.setStyleSheet("color: #e8909a;")
        self.status_label.setToolTip(message)
        self._append_log(f"[清单] 获取失败：{message}")
        if self._manifest is None:
            self._populate()
        self.ctx.bus.toast.emit("版本清单获取失败，请检查网络或下载源设置。")

    def _on_manifest_finished(self) -> None:
        self.refresh_button.setEnabled(True)
        self.refresh_button.setText("刷新清单")
        worker = self._manifest_worker
        self._manifest_worker = None
        if worker is not None:
            worker.deleteLater()

    # ------------------------------------------------------------------
    # 列表与筛选
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """重新扫描已安装版本并刷新列表状态。"""
        self._installed_ids = {
            v.id for v in scan_installed_versions(self.ctx.config.game_path)
        }
        self._populate()
        if self._detail_entry is not None:
            self._update_detail_header()

    def _populate(self) -> None:
        if self._updating_table:
            return
        self._updating_table = True
        try:
            needle = self.search_edit.text().strip().lower()
            category = str(self.category_combo.currentData() or "all")
            selected_id = self._selected_version_id()
            visible: list[dict] = []
            for entry in self._entries:
                version_id = str(entry.get("id") or "")
                if needle and needle not in version_id.lower():
                    continue
                if category != "all" and version_category(
                    version_id, str(entry.get("type") or "")
                ) != category:
                    continue
                visible.append(entry)

            self.table.blockSignals(True)
            self.table.setRowCount(0)
            for entry in visible:
                version_id = str(entry.get("id") or "")
                entry_type = str(entry.get("type") or "")
                row = self.table.rowCount()
                self.table.insertRow(row)
                id_item = QTableWidgetItem(version_id)
                id_item.setData(Qt.UserRole, version_id)
                id_item.setToolTip(str(entry.get("url") or ""))
                self.table.setItem(row, 0, id_item)

                kind = version_category(version_id, entry_type)
                type_item = QTableWidgetItem(CATEGORY_LABELS.get(kind, entry_type or "未知"))
                type_item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, 1, type_item)

                release = str(entry.get("releaseTime") or entry.get("time") or "")[:10]
                date_item = QTableWidgetItem(release or "未知")
                date_item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, 2, date_item)

                installed = version_id in self._installed_ids
                status_item = QTableWidgetItem("已安装" if installed else "未安装")
                status_item.setTextAlignment(Qt.AlignCenter)
                status_item.setForeground(QColor("#8fe89b" if installed else "#7f9689"))
                self.table.setItem(row, 3, status_item)

            self.count_label.setText(f"共 {len(self._entries)} 个 · 显示 {len(visible)} 个")
            self.table.blockSignals(False)
            self._updating_table = False

            row = self._row_of(selected_id) if selected_id else -1
            if row < 0:
                row = self._first_visible_row(visible)
            if row >= 0:
                self.table.selectRow(row)
            self._on_selection_changed()
        finally:
            self._updating_table = False

    def _first_visible_row(self, visible: list[dict]) -> int:
        """优先选中第一个正式版，否则选中第一行。"""
        for entry in visible:
            if str(entry.get("type")) == "release":
                return self._row_of(str(entry.get("id") or ""))
        return 0 if visible else -1

    def _row_of(self, version_id: str) -> int:
        if not version_id:
            return -1
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None and item.data(Qt.UserRole) == version_id:
                return row
        return -1

    def _selected_version_id(self) -> str:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            return ""
        item = self.table.item(rows[0].row(), 0)
        return str(item.data(Qt.UserRole)) if item is not None else ""

    def _on_selection_changed(self) -> None:
        if self._updating_table:
            return
        self.detail_button.setEnabled(bool(self._selected_version_id()))

    def _open_selected_detail(self) -> None:
        version_id = self._selected_version_id()
        entry = self._entries_by_id.get(version_id)
        if entry is not None:
            self._open_detail(entry)

    def _open_detail(self, entry: dict) -> None:
        self._detail_entry = entry
        self._selected_kind = _ORIGINAL
        self._update_detail_header()
        self.location_label.setText(str(self.ctx.config.game_path))
        self._select_loader(_ORIGINAL)
        self._start_loader_scan(str(entry.get("id") or ""))
        self.stack.setCurrentIndex(1)

    def _back_to_list(self) -> None:
        self.stack.setCurrentIndex(0)
        self._retire_loader_scan()

    def _update_detail_header(self) -> None:
        entry = self._detail_entry
        if entry is None:
            return
        version_id = str(entry.get("id") or "")
        entry_type = str(entry.get("type") or "")
        category = version_category(version_id, entry_type)
        self.detail_title.setText(version_id or "—")
        self.detail_type_badge.setText(CATEGORY_LABELS.get(category, entry_type or "未知"))
        self.detail_type_badge.set_kind(
            "green"
            if category == "release"
            else ("orange" if category in ("snapshot", "april") else "gray")
        )
        installed = version_id in self._installed_ids
        self.detail_installed_badge.setText("已安装" if installed else "未安装")
        self.detail_installed_badge.set_kind("green" if installed else "gray")
        release = str(entry.get("releaseTime") or entry.get("time") or "")[:10]
        self.detail_date.setText(f"发布时间：{release or '未知'}")
        self.location_label.setText(str(self.ctx.config.game_path))

    # ------------------------------------------------------------------
    # 加载器检测
    # ------------------------------------------------------------------
    def _start_loader_scan(self, mc_version: str) -> None:
        self._retire_loader_scan()
        for kind, card in self._loader_cards.items():
            if kind == _ORIGINAL:
                continue
            card.set_pending()
        worker = LoaderScanWorker(mc_version, self)
        worker.result.connect(
            lambda kind, versions, w=worker: self._on_loader_versions(w, kind, versions)
        )
        worker.failed.connect(
            lambda kind, message, w=worker: self._on_loader_failed(w, kind, message)
        )
        worker.finished.connect(lambda w=worker: self._on_loader_scan_finished(w))
        self._loader_scan = worker
        worker.start()

    def _retire_loader_scan(self) -> None:
        """中止并解绑旧的检测线程，避免旧结果回填到当前版本。"""
        worker = self._loader_scan
        self._loader_scan = None
        if worker is None:
            return
        worker.cancel()
        # 只断开本页连接的槽，避免误伤其他地方对同一信号的连接
        for signal in (worker.result, worker.failed, worker.finished):
            try:
                signal.disconnect()
            except (RuntimeError, TypeError):
                pass
        if worker.isRunning():
            self._retired_scans.append(worker)
        else:
            worker.deleteLater()

    def _on_loader_versions(
        self, worker: LoaderScanWorker, kind: str, versions: list[str]
    ) -> None:
        if worker is not self._loader_scan:
            return
        card = self._loader_cards.get(kind)
        if card is None:
            return
        values = [str(v) for v in (versions or []) if str(v)]
        if values:
            card.set_versions(values)
        else:
            card.set_unsupported("该 Minecraft 版本没有可用的加载器版本。")

    def _on_loader_failed(self, worker: LoaderScanWorker, kind: str, message: str) -> None:
        if worker is not self._loader_scan:
            return
        card = self._loader_cards.get(kind)
        if card is None:
            return
        card.set_unsupported(message or "检测失败")
        self._append_log(f"[检测] {LOADER_LABELS.get(kind, kind)} 不可用：{message}")
        self._ensure_selection_valid()

    def _on_loader_scan_finished(self, worker: LoaderScanWorker) -> None:
        if worker is not self._loader_scan:
            return
        self._loader_scan = None
        for kind, card in self._loader_cards.items():
            if kind == _ORIGINAL:
                continue
            if card.status.text() == "检测中":
                card.set_unsupported("未检测到可用版本。")
        self._ensure_selection_valid()
        worker.deleteLater()

    def _ensure_selection_valid(self) -> None:
        """所选加载器变为不支持时自动回落到原版。"""
        card = self._loader_cards.get(self._selected_kind)
        if self._selected_kind != _ORIGINAL and (card is None or card.is_unsupported):
            self._select_loader(_ORIGINAL)
            return
        self._select_loader(self._selected_kind)

    def _select_loader(self, kind: str) -> None:
        card = self._loader_cards.get(kind)
        if card is None or card.is_unsupported:
            return
        self._selected_kind = kind
        for key, item in self._loader_cards.items():
            item.set_selected(key == kind)
        if kind == _ORIGINAL:
            self.selection_label.setText("当前选择：原版（不安装加载器）")
        else:
            label = LOADER_LABELS.get(kind, kind)
            version = card.combo.currentText()
            self.selection_label.setText(
                f"当前选择：{label}{(' ' + version) if version else ''}"
            )
        self._update_install_button()

    def _update_install_button(self) -> None:
        running = self._install_worker is not None and self._install_worker.isRunning()
        self.install_button.setEnabled(not running and self._detail_entry is not None)
        saving = self._client_worker is not None and self._client_worker.isRunning()
        self.client_jar_button.setEnabled(
            self._detail_entry is not None and not saving
        )

    # ------------------------------------------------------------------
    # 串行安装
    # ------------------------------------------------------------------
    def _start_install(self) -> None:
        entry = self._detail_entry
        if entry is None or (self._install_worker is not None and self._install_worker.isRunning()):
            return
        kind = self._selected_kind
        loader_version = ""
        if kind != _ORIGINAL:
            card = self._loader_cards.get(kind)
            if card is None or card.is_unsupported or not card.combo.isEnabled():
                return
            loader_version = str(card.combo.currentData() or card.combo.currentText())
            if kind != "liteloader" and not loader_version:
                QMessageBox.warning(self, "缺少加载器版本", "请先选择一个加载器版本。")
                return

        self._installing_mc = str(entry.get("id") or "")
        self._installing_kind = kind
        self._pending_install = (dict(entry), kind, loader_version)
        self._install_pause.clear()
        label = LOADER_LABELS.get(kind, kind) if kind != _ORIGINAL else "原版"
        task = self.ctx.downloads.submit(
            "版本",
            f"{self._installing_mc} · {label}",
            lambda _task: self._spawn_install(),
            cancel=lambda: self._install_worker.cancel() if self._install_worker else None,
            pause=self._install_pause,
            rebuild=lambda _task: self._spawn_install(_task.id),
            detail="准备安装",
        )
        self._install_task_id = task.id
        self._update_install_button()

    def _spawn_install(self, task_id: str = "") -> ChainInstallWorker:
        """创建（或重试时重建）串行安装线程。"""
        if self._pending_install is None:
            raise RuntimeError("没有待安装的版本")
        entry, kind, loader_version = self._pending_install
        if task_id:
            self._install_task_id = task_id
            self._installing_mc = str(entry.get("id") or "")
            self._installing_kind = kind
            self._append_log("[安装] 重新开始安装流程。")
        self.progress_box.setVisible(True)
        self.progress_stage.setText("准备安装")
        self.progress_bar.setValue(0)
        self.progress_detail.setText("")
        self.cancel_button.setEnabled(True)
        worker = ChainInstallWorker(
            self.ctx, entry, kind, loader_version, self._install_pause, self
        )
        worker.progress.connect(self._on_progress)
        worker.log.connect(self._append_log)
        worker.done.connect(self._on_install_done)
        worker.failed.connect(self._on_install_failed)
        worker.finished.connect(self._on_install_finished)
        self._install_worker = worker
        self._update_install_button()
        return worker

    def _cancel_install(self) -> None:
        if self._install_worker is not None and self._install_worker.isRunning():
            self._install_worker.cancel()
            self._append_log("[安装] 已请求取消。")
            self.cancel_button.setEnabled(False)

    def _on_progress(self, progress: Progress) -> None:
        self.progress_box.setVisible(True)
        self.progress_stage.setText(progress.stage)
        self.progress_bar.setValue(int(progress.percent * 1000))
        detail = progress.detail
        if progress.speed > 0:
            detail += f" · {progress.speed / 1048576:.1f} MB/s"
        self.progress_detail.setText(detail)
        if getattr(self, "_install_task_id", ""):
            self.ctx.downloads.update(
                self._install_task_id,
                percent=progress.percent,
                status="安装中",
                detail=f"{progress.stage} · {detail}" if detail else progress.stage,
                speed=progress.speed,
            )

    def _on_install_done(self, final_version_id: str) -> None:
        self.progress_box.setVisible(False)
        self.cancel_button.setEnabled(True)
        mc_version = self._installing_mc
        loader_label = (
            LOADER_LABELS.get(self._installing_kind, self._installing_kind)
            if self._installing_kind
            else "原版"
        )
        self._append_log(f"[安装] {final_version_id} 安装完成。")
        config = self.ctx.config
        if not any(i.version_id == final_version_id for i in config.instances):
            instance = config.add_instance(
                name=final_version_id,
                game_dir=str(config.game_path),
                version_id=final_version_id,
                loader=loader_label,
                mc_version=mc_version,
            )
            config.select_instance(instance.id)
            self.ctx.bus.instances_changed.emit()
        self.refresh()
        self.ctx.bus.versions_changed.emit()
        self.ctx.bus.toast.emit(f"{final_version_id} 安装完成，可在主页启动。")
        if getattr(self, "_install_task_id", ""):
            self.ctx.downloads.finish(self._install_task_id, True, final_version_id)

    def _on_install_failed(self, message: str) -> None:
        self.progress_box.setVisible(False)
        self.cancel_button.setEnabled(True)
        self._append_log(f"[安装] 失败：{message}")
        if getattr(self, "_install_task_id", ""):
            self.ctx.downloads.finish(self._install_task_id, False, message)
            self._install_task_id = ""
        # 安装日志自动复制到剪贴板，方便用户直接反馈给开发者
        QGuiApplication.clipboard().setText(self.log_view.toPlainText())
        QMessageBox.critical(
            self,
            "安装失败",
            f"{message}\n\n安装日志已复制到剪贴板，请反馈给开发者。",
        )

    def _on_install_finished(self) -> None:
        worker = self._install_worker
        self._install_worker = None
        if worker is not None:
            worker.deleteLater()
        self._update_install_button()

    # ------------------------------------------------------------------
    # 仅下载客户端 Jar
    # ------------------------------------------------------------------
    def _save_client_jar(self) -> None:
        entry = self._detail_entry
        if entry is None:
            return
        if self._client_worker is not None and self._client_worker.isRunning():
            QMessageBox.information(self, APP_NAME, "已有客户端 Jar 下载任务正在进行，请稍候。")
            return
        version_id = str(entry.get("id") or "")
        default_name = f"Minecraft-{_safe_filename(version_id, 'version')}-client.jar"
        path, _filter = QFileDialog.getSaveFileName(
            self,
            "仅下载客户端 Jar",
            str(_download_dir() / default_name),
            "Jar 文件 (*.jar);;所有文件 (*)",
        )
        if not path:
            return
        dest = Path(path)
        if not dest.suffix:
            dest = dest.with_suffix(".jar")
        self._pending_client_save = (dict(entry), dest)
        self._client_pause.clear()
        task = self.ctx.downloads.submit(
            "纯下载",
            dest.name,
            lambda item: self._spawn_client_save(item.id),
            cancel=lambda: self._client_worker.cancel() if self._client_worker else None,
            pause=self._client_pause,
            rebuild=lambda item: self._spawn_client_save(item.id),
            target_dir=str(dest.parent),
            detail=f"另存为：{dest.name}",
        )
        self._client_task_id = task.id
        self._append_log(f"[下载] 另存为 {dest}")
        self._update_install_button()

    def _spawn_client_save(self, task_id: str = "") -> ClientJarSaveWorker:
        """创建（或重试时重建）客户端 Jar 下载线程。"""
        if self._pending_client_save is None:
            raise RuntimeError("没有待保存的客户端 Jar")
        entry, dest = self._pending_client_save
        worker = ClientJarSaveWorker(self.ctx, entry, dest, self)
        worker.pause_event = self._client_pause
        worker.log.connect(self._append_log)
        worker.log.connect(self.ctx.bus.log.emit)
        worker.progress.connect(
            lambda value, speed, detail, tid=task_id: self.ctx.downloads.update(
                tid, percent=value, status="下载中", detail=detail, speed=speed
            )
            if tid
            else None
        )
        worker.done.connect(
            lambda path, tid=task_id: self._on_client_done(tid, path)
        )
        worker.failed.connect(
            lambda message, tid=task_id, w=worker: self._on_client_failed(tid, message, w)
        )
        worker.finished.connect(lambda w=worker: self._on_client_finished(w))
        self._client_worker = worker
        if task_id:
            self._client_task_id = task_id
        self._update_install_button()
        return worker

    def _on_client_done(self, task_id: str, path: str) -> None:
        self._append_log(f"[下载] 文件已保存至：{path}")
        self.ctx.bus.log.emit(f"[下载] 文件已保存至：{path}")
        self.ctx.bus.toast.emit(f"文件已保存至：{path}")
        if task_id:
            self.ctx.downloads.finish(task_id, True, f"已保存至：{path}")

    def _on_client_failed(
        self, task_id: str, message: str, worker: ClientJarSaveWorker
    ) -> None:
        self._append_log(f"[下载] 失败：{message}")
        if task_id:
            self.ctx.downloads.finish(task_id, False, message)
        if worker.cancel_event.is_set():
            self.ctx.bus.toast.emit("下载已取消。")
            return
        self.ctx.bus.log.emit(f"[错误] {message}")
        QMessageBox.warning(self, "仅下载失败", message)

    def _on_client_finished(self, worker: ClientJarSaveWorker) -> None:
        if worker is not self._client_worker:
            worker.deleteLater()
            return
        self._client_worker = None
        worker.deleteLater()
        self._update_install_button()

    def _append_log(self, line: str) -> None:
        self.log_view.appendPlainText(line)
        bar = self.log_view.verticalScrollBar()
        bar.setValue(bar.maximum())

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def ensure_loaded(self) -> None:
        if self._loaded:
            return
        if self._manifest is None and not (
            self._manifest_worker is not None and self._manifest_worker.isRunning()
        ):
            self.refresh_manifest(force=False)

    def shutdown(self) -> None:
        """取消并等待所有后台线程，避免 QThread 析构崩溃。"""
        self._retire_loader_scan()
        self._manifest_worker_cleanup()
        workers: list[QThread] = [*self._retired_scans]
        self._retired_scans = []
        install_worker = self._install_worker
        self._install_worker = None
        if install_worker is not None:
            install_worker.cancel()
            workers.append(install_worker)
        client_worker = self._client_worker
        self._client_worker = None
        if client_worker is not None:
            client_worker.cancel()
            workers.append(client_worker)
        for worker in workers:
            wait_thread(worker, 2000)
            if not worker.isRunning():
                worker.deleteLater()

    def _manifest_worker_cleanup(self) -> None:
        worker = self._manifest_worker
        self._manifest_worker = None
        if worker is not None:
            wait_thread(worker, 2000)
            if not worker.isRunning():
                worker.deleteLater()
