"""Mod 加载器页：按 Minecraft 版本分类浏览并安装 Forge / NeoForge / Fabric / Quilt / LiteLoader。"""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..context import AppContext, wait_thread
from ..installer import GameInstaller
from ..java import detect_java_installed, pick_java
from ..modloader import (
    LOADER_LABELS,
    LoaderError,
    install_loader,
    java_for_mc,
    list_loader_mc_versions,
    list_loader_versions,
)
from ..net import Cancelled
from .widgets import Card, page_header

MAX_LOADER_ROWS = 12

# 「类型/备注」列的说明
LOADER_NOTES = {
    "forge": "官方安装器",
    "neoforge": "官方安装器",
    "fabric": "Profile JSON",
    "quilt": "Profile JSON",
    "liteloader": "TweakClass 注入",
}


# ---------------------------------------------------------------------------
# 查询 worker
# ---------------------------------------------------------------------------
class LoaderMcWorker(QThread):
    """异步获取某加载器支持的 Minecraft 版本列表。"""

    done = Signal(str, object)  # (kind, MC 版本列表)

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self.kind = kind

    def run(self) -> None:
        versions = []
        for attempt in range(2):
            try:
                versions = list_loader_mc_versions(self.kind)
            except Exception:  # noqa: BLE001
                versions = []
            if versions or attempt:
                break
            time.sleep(0.8)  # 元数据源偶发失败，重试一次
        self.done.emit(self.kind, versions)


class LoaderVersionsWorker(QThread):
    """异步获取某加载器在某 MC 版本下可用的加载器版本。"""

    done = Signal(str, str, object)  # (kind, mc, 版本列表)
    failed = Signal(str, str, str)  # (kind, mc, 错误信息)

    def __init__(self, kind: str, mc_version: str, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.mc_version = mc_version

    def run(self) -> None:
        for attempt in range(2):
            try:
                versions = list_loader_versions(self.kind, self.mc_version)
                self.done.emit(self.kind, self.mc_version, versions)
                return
            except Exception as exc:  # noqa: BLE001
                if attempt:
                    self.failed.emit(self.kind, self.mc_version, str(exc))
                    return
                time.sleep(0.6)  # maven 镜像偶发失败，重试一次


# ---------------------------------------------------------------------------
# 安装 worker
# ---------------------------------------------------------------------------
class LoaderInstallWorker(QThread):
    """先确保原版版本已安装，再调用 install_loader 安装加载器。"""

    progress = Signal(float, str, str)  # (0~1 进度, 阶段, 详情)
    log = Signal(str)
    done = Signal(str)  # 安装后的版本 ID
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        ctx: AppContext,
        kind: str,
        mc_version: str,
        loader_version: str,
        java_path: str,
        cancel_event: threading.Event | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.ctx = ctx
        self.kind = kind
        self.mc_version = mc_version
        self.loader_version = loader_version
        self.java_path = java_path
        self.cancel_event = cancel_event or threading.Event()
        self._loader_phase = False
        self._last_percent = 0.0

    def _on_installer_progress(self, p) -> None:
        # 0 ~ 0.45：原版版本；0.45 ~ 1.0：加载器及其依赖库
        # 加载器阶段内部还会再走一遍 0→1（ensure_version），这里只保证进度条不回退
        if self._loader_phase:
            percent = 0.45 + float(getattr(p, "percent", 0.0)) * 0.55
            stage = f"加载器 · {getattr(p, 'stage', '')}".rstrip(" ·")
        else:
            percent = float(getattr(p, "percent", 0.0)) * 0.45
            stage = f"原版 · {getattr(p, 'stage', '')}".rstrip(" ·")
        detail = str(getattr(p, "detail", "") or "")
        speed = float(getattr(p, "speed", 0.0) or 0.0)
        if speed > 0:
            detail += f" · {speed / 1048576:.1f} MB/s"
        value = max(self._last_percent, max(0.0, min(percent, 1.0)))
        self._last_percent = value
        self.progress.emit(value, stage or "安装中", detail)

    def run(self) -> None:
        label = LOADER_LABELS.get(self.kind, self.kind)
        try:
            config = self.ctx.config
            installer = GameInstaller(
                config,
                self.ctx.sources,
                progress_cb=self._on_installer_progress,
                log_cb=self.log.emit,
                cancel=self.cancel_event,
            )
            json_path = (
                config.versions_path / self.mc_version / f"{self.mc_version}.json"
            )
            if json_path.exists():
                self.log.emit(f"[原版] Minecraft {self.mc_version} 已存在，跳过下载。")
                self.progress.emit(0.45, "检查原版", self.mc_version)
            else:
                self.progress.emit(0.0, "安装原版", f"准备安装 Minecraft {self.mc_version}")
                payload, _name, _cached = self.ctx.sources.get_manifest()
                entries = payload.get("data", {}).get("versions", [])
                entry = next(
                    (
                        v
                        for v in entries
                        if isinstance(v, dict) and str(v.get("id")) == self.mc_version
                    ),
                    None,
                )
                if entry is None:
                    raise LoaderError(
                        f"版本清单中找不到 Minecraft {self.mc_version}，无法安装原版。"
                    )
                installer.install_version(entry)
            if self.cancel_event.is_set():
                raise Cancelled()

            self._loader_phase = True
            self.progress.emit(0.45, "安装加载器", f"{label} {self.loader_version}".strip())
            version_id = install_loader(
                installer,
                self.kind,
                self.mc_version,
                self.loader_version,
                self.java_path,
                self.log.emit,
                self.cancel_event,
            )
            self.progress.emit(1.0, "安装完成", version_id)
            self.log.emit(f"[完成] {label} 已安装：{version_id}")
            self.done.emit(version_id)
        except Cancelled:
            self.cancelled.emit()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


# ---------------------------------------------------------------------------
class LoadersPage(QWidget):
    """Mod 加载器页：左侧按 MC 版本浏览，右侧展示可安装的加载器版本。"""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self._workers: list[QThread] = []
        self._mc_versions: list[str] = []
        self._mc_request = ""
        self._versions_request = ""
        self._row_buttons: list[tuple[str, QPushButton]] = []
        self._busy: set[str] = set()
        self._build()
        self.refresh()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 18, 24, 18)
        outer.setSpacing(14)
        header, _ = page_header(
            "Mod 加载器",
            "按 Minecraft 版本分类浏览并安装 Forge / NeoForge / Fabric / Quilt / LiteLoader",
        )
        outer.addWidget(header)

        card = Card(margins=14, spacing=10)
        tip = QLabel(
            "版本列表来自各加载器官方元数据服务；选择左侧 Minecraft 版本后，"
            "右侧会列出该版本下可安装的加载器版本。"
        )
        tip.setObjectName("Tiny")
        tip.setWordWrap(True)
        card.body.addWidget(tip)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        kind_label = QLabel("加载器")
        kind_label.setObjectName("Tiny")
        toolbar.addWidget(kind_label)

        self._kind_combo = QComboBox()
        self._kind_combo.setMinimumWidth(150)
        for key, label in LOADER_LABELS.items():
            self._kind_combo.addItem(label, key)
        toolbar.addWidget(self._kind_combo)

        self._refresh_btn = QPushButton("刷新")
        self._refresh_btn.setObjectName("Ghost")
        self._refresh_btn.setFixedHeight(28)
        self._refresh_btn.clicked.connect(lambda: self.refresh(force=True))
        toolbar.addWidget(self._refresh_btn)

        self._status_label = QLabel("")
        self._status_label.setObjectName("Tiny")
        self._status_label.setWordWrap(True)
        toolbar.addWidget(self._status_label, 1)
        card.body.addLayout(toolbar)

        split = QHBoxLayout()
        split.setSpacing(12)

        left = QWidget()
        left.setFixedWidth(250)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        mc_caption = QLabel("Minecraft 版本")
        mc_caption.setObjectName("Muted")
        left_layout.addWidget(mc_caption)
        self._mc_list = QListWidget()
        self._mc_list.setUniformItemSizes(True)
        left_layout.addWidget(self._mc_list, 1)
        split.addWidget(left)

        right = QVBoxLayout()
        right.setSpacing(6)
        version_caption = QLabel("可安装的加载器版本")
        version_caption.setObjectName("Muted")
        right.addWidget(version_caption)

        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(["加载器版本", "类型/备注", "操作"])
        table.verticalHeader().setVisible(False)
        table.setSelectionMode(QAbstractItemView.NoSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.setColumnWidth(2, 110)
        table.verticalHeader().setDefaultSectionSize(38)
        right.addWidget(table, 1)
        split.addLayout(right, 1)

        card.body.addLayout(split, 1)
        self._table = table

        hint = QLabel(
            "安装会先确保对应原版 Minecraft 版本与加载器依赖库下载完成，任务会登记到下载中心，"
            "可随时暂停、取消或重试。"
        )
        hint.setObjectName("Tiny")
        hint.setWordWrap(True)
        card.body.addWidget(hint)
        outer.addWidget(card, 1)

        self._show_table_placeholder("请选择左侧的 Minecraft 版本")
        # 构造完成后再接线，避免初始化期间重复请求
        self._mc_list.currentItemChanged.connect(self._on_mc_changed)
        self._kind_combo.currentIndexChanged.connect(self._on_kind_changed)

    # ------------------------------------------------------------------
    def _current_kind(self) -> str:
        return str(self._kind_combo.currentData() or "forge")

    def _current_mc(self) -> str:
        item = self._mc_list.currentItem()
        return str(item.data(Qt.UserRole) or "") if item is not None else ""

    @staticmethod
    def _task_key(kind: str, mc_version: str, loader_version: str) -> str:
        return f"{kind}·{mc_version}·{loader_version}"

    # ------------------------------------------------------------------
    def refresh(self, force: bool = False) -> None:
        """按当前加载器获取支持的 Minecraft 版本；force=True 时强制重新联网获取。"""
        if not force and (self._mc_versions or not self._refresh_btn.isEnabled()):
            return  # 已有数据或请求仍在进行
        kind = self._current_kind()
        self._mc_request = kind
        self._mc_versions = []
        self._versions_request = ""
        self._refresh_btn.setEnabled(False)
        self._status_label.setText(
            f"正在获取 {LOADER_LABELS.get(kind, kind)} 支持的 Minecraft 版本…"
        )
        self._mc_list.clear()
        self._show_table_placeholder("正在获取版本…")

        worker = LoaderMcWorker(kind, self)
        worker.done.connect(self._on_mc_versions)
        worker.finished.connect(lambda w=worker: self._discard_worker(w))
        self._workers.append(worker)
        worker.start()

    def shutdown(self) -> None:
        """关闭页面：取消并等待仍在运行的查询 / 安装 worker。"""
        for worker in list(self._workers):
            cancel_event = getattr(worker, "cancel_event", None)
            if cancel_event is not None:
                try:
                    cancel_event.set()
                except Exception:  # noqa: BLE001
                    pass
            try:
                worker.requestInterruption()
            except Exception:  # noqa: BLE001
                pass
        for worker in list(self._workers):
            wait_thread(worker, 2000)
        self._workers.clear()

    def _discard_worker(self, worker: QThread) -> None:
        if worker in self._workers:
            self._workers.remove(worker)
        worker.deleteLater()

    # ------------------------------------------------------------------
    def _on_kind_changed(self, _index: int = -1) -> None:
        self.refresh(force=True)

    def _on_mc_versions(self, kind: str, versions: object) -> None:
        if kind != self._mc_request:
            return  # 已切换到其他加载器，丢弃旧结果
        self._refresh_btn.setEnabled(True)
        rows = [str(v) for v in versions or [] if str(v)] if isinstance(versions, list) else []
        self._mc_versions = rows
        self._mc_list.clear()
        label = LOADER_LABELS.get(kind, kind)
        if not rows:
            self._status_label.setText(
                f"获取 {label} 支持的 Minecraft 版本失败，请检查网络后重试"
            )
            self._show_table_placeholder("暂无可用 Minecraft 版本")
            return
        for version in rows:
            item = QListWidgetItem(f"Minecraft {version}")
            item.setData(Qt.UserRole, version)
            self._mc_list.addItem(item)
        self._status_label.setText(f"{label} 支持 {len(rows)} 个 Minecraft 版本")
        self._mc_list.setCurrentRow(0)

    def _on_mc_changed(self, current: QListWidgetItem | None, _previous=None) -> None:
        if current is None:
            return
        mc_version = str(current.data(Qt.UserRole) or "")
        if mc_version:
            self._load_versions(mc_version)

    def _load_versions(self, mc_version: str) -> None:
        kind = self._current_kind()
        self._versions_request = f"{kind}:{mc_version}"
        self._show_table_placeholder(f"正在获取 Minecraft {mc_version} 的加载器版本…")

        worker = LoaderVersionsWorker(kind, mc_version, self)
        worker.done.connect(self._on_versions)
        worker.failed.connect(self._on_versions_failed)
        worker.finished.connect(lambda w=worker: self._discard_worker(w))
        self._workers.append(worker)
        worker.start()

    def _on_versions(self, kind: str, mc_version: str, versions: object) -> None:
        if f"{kind}:{mc_version}" != self._versions_request:
            return
        rows = (
            [str(v) for v in versions or [] if str(v)][:MAX_LOADER_ROWS]
            if isinstance(versions, list)
            else []
        )
        self._populate(kind, mc_version, rows)

    def _on_versions_failed(self, kind: str, mc_version: str, message: str) -> None:
        if f"{kind}:{mc_version}" != self._versions_request:
            return
        self._show_table_placeholder(f"获取失败：{message}")
        self.ctx.bus.log.emit(f"[Mod 加载器] 获取版本失败：{message}")

    # ------------------------------------------------------------------
    def _show_table_placeholder(self, text: str) -> None:
        table = self._table
        table.setRowCount(0)
        self._row_buttons = []
        table.insertRow(0)
        item = QTableWidgetItem(text)
        item.setForeground(Qt.GlobalColor.gray)
        table.setItem(0, 0, item)

    def _populate(self, kind: str, mc_version: str, rows: list[str]) -> None:
        table = self._table
        table.setRowCount(0)
        self._row_buttons = []
        if not rows:
            self._show_table_placeholder("该 Minecraft 版本没有可安装的加载器版本")
            return
        note = LOADER_NOTES.get(kind, "官方安装")
        for row, loader_version in enumerate(rows):
            table.insertRow(row)
            version_item = QTableWidgetItem(
                loader_version + ("（最新）" if row == 0 else "")
            )
            version_item.setData(Qt.UserRole, loader_version)
            table.setItem(row, 0, version_item)

            note_item = QTableWidgetItem(note)
            note_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 1, note_item)

            actions = QWidget()
            action_layout = QHBoxLayout(actions)
            action_layout.setContentsMargins(4, 2, 4, 2)
            action_layout.setSpacing(6)
            install_btn = QPushButton("安装")
            install_btn.setObjectName("Primary")
            install_btn.setFixedHeight(26)
            install_btn.setEnabled(
                self._task_key(kind, mc_version, loader_version) not in self._busy
            )
            install_btn.clicked.connect(
                lambda _checked=False, mc=mc_version, lv=loader_version: self._install(mc, lv)
            )
            action_layout.addWidget(install_btn, 0, Qt.AlignCenter)
            table.setCellWidget(row, 2, actions)
            self._row_buttons.append((loader_version, install_btn))

    def _refresh_buttons(self) -> None:
        kind = self._current_kind()
        mc_version = self._current_mc()
        for loader_version, button in self._row_buttons:
            button.setEnabled(
                self._task_key(kind, mc_version, loader_version) not in self._busy
            )

    # ------------------------------------------------------------------
    def _install(self, mc_version: str, loader_version: str) -> None:
        kind = self._current_kind()
        key = self._task_key(kind, mc_version, loader_version)
        if key in self._busy:
            return
        label = LOADER_LABELS.get(kind, kind)

        javas = list(self.ctx.javas)
        if not javas:
            javas = detect_java_installed()
            if javas:
                self.ctx.javas = javas
        java, hint = pick_java(
            javas, java_for_mc(mc_version), str(self.ctx.config.java_path or "")
        )
        if java is None:
            QMessageBox.warning(
                self,
                "缺少 Java",
                f"安装 {label} 需要 Java {java_for_mc(mc_version)}。\n"
                f"{hint or '未检测到 Java，请先在设置页指定 Java 后重试。'}",
            )
            return
        if hint:
            self.ctx.bus.log.emit(f"[Mod 加载器] {hint}")
        java_path = java.path

        def factory(task) -> QThread:
            # 每次（含重试）都新建事件，避免取消后重试立即再次取消
            cancel_event = threading.Event()
            task.cancel = cancel_event.set
            worker = LoaderInstallWorker(
                self.ctx,
                kind,
                mc_version,
                loader_version,
                java_path,
                cancel_event,
                self,
            )
            worker.progress.connect(
                lambda percent, stage, detail, tid=task.id: self.ctx.downloads.update(
                    tid,
                    percent=percent,
                    status="安装中",
                    stage=stage,
                    detail=detail,
                )
            )
            worker.done.connect(
                lambda version_id, tid=task.id, k=key: self._on_install_done(
                    tid, version_id, k
                )
            )
            worker.failed.connect(
                lambda message, tid=task.id, k=key: self._on_install_failed(
                    tid, message, k
                )
            )
            worker.cancelled.connect(
                lambda tid=task.id, k=key: self._on_install_cancelled(tid, k)
            )
            worker.finished.connect(lambda w=worker: self._discard_worker(w))
            self._workers.append(worker)
            return worker

        self._busy.add(key)
        self._refresh_buttons()
        self._status_label.setText(f"已加入下载中心：{label} {loader_version} · MC {mc_version}")
        self.ctx.downloads.submit(
            kind="加载器",
            name=f"{label} {loader_version} · MC {mc_version}",
            factory=factory,
            rebuild=factory,
            target_dir=str(self.ctx.config.game_path),
            detail=f"Minecraft {mc_version}",
        )
        self.ctx.bus.toast.emit(f"已加入下载中心：{label} {loader_version} · MC {mc_version}")

    def _on_install_done(self, task_id: str, version_id: str, key: str) -> None:
        self._busy.discard(key)
        self._refresh_buttons()
        self.ctx.downloads.finish(task_id, ok=True, message=version_id)
        self._status_label.setText(f"安装完成：{version_id}")
        self.ctx.bus.toast.emit(f"加载器安装完成：{version_id}")

    def _on_install_failed(self, task_id: str, message: str, key: str) -> None:
        self._busy.discard(key)
        self._refresh_buttons()
        self.ctx.downloads.finish(task_id, ok=False, message=message)
        self._status_label.setText("安装失败，请查看下载中心或日志")
        self.ctx.bus.log.emit(f"[Mod 加载器] 安装失败：{message}")
        QMessageBox.warning(self, "加载器安装失败", message)

    def _on_install_cancelled(self, task_id: str, key: str) -> None:
        self._busy.discard(key)
        self._refresh_buttons()
        self.ctx.downloads.finish_cancelled(task_id, "安装已取消。")
        self._status_label.setText("安装已取消")
        self.ctx.bus.toast.emit("加载器安装已取消。")
