"""Java 中心：从各家官方渠道动态获取可用版本，下载任务统一登记到下载中心（kind="Java"）。"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..config import DATA_DIR
from ..context import AppContext, wait_thread
from ..java import (
    detect_java_installed,
    download_java,
    fetch_distribution_versions,
    find_java_in,
    java_key,
    java_runtime_name,
    list_java_distributions,
)
from ..net import Cancelled
from .widgets import Card, page_header

# 与设置页的 Java 下载目录保持一致
JAVA_ROOT = DATA_DIR / "runtime"


def _fmt_size(value: object) -> str:
    try:
        size = int(value or 0)
    except (TypeError, ValueError):
        size = 0
    if size <= 0:
        return "未知"
    if size >= 1024 ** 3:
        return f"{size / 1024 ** 3:.2f} GB"
    return f"{size / 1024 ** 2:.1f} MB"


# ---------------------------------------------------------------------------
# 版本查询 / 下载 worker
# ---------------------------------------------------------------------------
class ResolveWorker(QThread):
    """异步获取某发行版某主版本的可用版本列表（联网，不阻塞界面）。"""

    done = Signal(str, object)  # (请求 key, 版本列表)
    failed = Signal(str, str)  # (请求 key, 错误信息)

    def __init__(self, dist_id: str, major: int, force: bool = False, parent=None):
        super().__init__(parent)
        self.dist_id = dist_id
        self.major = int(major)
        self.force = force

    def run(self) -> None:
        key = f"{self.dist_id}:{self.major}"
        try:
            versions = fetch_distribution_versions(
                self.dist_id, self.major, force=self.force
            )
            self.done.emit(key, versions)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(key, str(exc))


class JavaCenterInstallWorker(QThread):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(float, float)  # 0~1 进度, 字节/秒

    def __init__(
        self,
        major: int,
        dest_root: Path,
        task_id: str = "",
        cancel_event: threading.Event | None = None,
        pause_event: threading.Event | None = None,
        url: str = "",
        target_name: str = "",
        size: int = 0,
        parent=None,
    ):
        super().__init__(parent)
        self.major = int(major)
        self.dest_root = Path(dest_root)
        self.task_id = task_id
        self.cancel_event = cancel_event or threading.Event()
        self.pause_event = pause_event or threading.Event()
        self.url = url
        self.target_name = target_name
        self.size = int(size or 0)

    def run(self) -> None:
        state = {"total": 0, "bytes": 0, "last_t": time.time(), "last_b": 0}

        def on_total(total: int) -> None:
            state["total"] = int(total)

        def on_bytes(n: int) -> None:
            state["bytes"] += n
            now = time.time()
            if now - state["last_t"] < 0.25:
                return
            dt = now - state["last_t"]
            speed = (state["bytes"] - state["last_b"]) / dt if dt > 0 else 0.0
            state["last_t"], state["last_b"] = now, state["bytes"]
            total = state["total"]
            percent = min(1.0, state["bytes"] / total) if total else 0.0
            self.progress.emit(percent, speed)

        try:
            info = download_java(
                self.major,
                self.dest_root,
                log=lambda text: None,
                on_bytes=on_bytes,
                cancel=self.cancel_event,
                pause=self.pause_event,
                on_total=on_total,
                url=self.url,
                target_name=self.target_name,
                size=self.size,
            )
            self.done.emit(info)
        except Cancelled:
            pass  # 已由下载中心标记为取消
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


# ---------------------------------------------------------------------------
class JavaCenterPage(QWidget):
    """Java 中心页：按发行版 + 主版本筛选，列出官方渠道的真实版本并提供下载。"""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self._distributions = list_java_distributions()
        self._versions: list[dict] = []
        self._request_key = ""
        self._workers: list[QThread] = []
        self._build()
        self.refresh()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 18, 24, 18)
        outer.setSpacing(14)
        header, _ = page_header(
            "Java 中心", "从各家官方渠道获取可用版本，下载安装到本地运行时目录（data/runtime）"
        )
        outer.addWidget(header)

        card = Card(margins=14, spacing=10)
        tip = QLabel(
            "版本列表来自各发行版官方 API / 官方下载页；查询失败时自动回退到官方最新版稳定链接。"
            "下载任务统一登记到下载中心，可暂停 / 取消 / 重试。"
        )
        tip.setObjectName("Tiny")
        tip.setWordWrap(True)
        card.body.addWidget(tip)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        dist_label = QLabel("发行版")
        dist_label.setObjectName("Tiny")
        toolbar.addWidget(dist_label)

        self._dist_combo = QComboBox()
        self._dist_combo.setMinimumWidth(230)
        for dist in self._distributions:
            self._dist_combo.addItem(f"{dist['name']}（{dist['vendor']}）", dist["id"])
        toolbar.addWidget(self._dist_combo)

        major_label = QLabel("主版本")
        major_label.setObjectName("Tiny")
        toolbar.addWidget(major_label)

        self._major_combo = QComboBox()
        self._major_combo.setMinimumWidth(110)
        toolbar.addWidget(self._major_combo)
        self._populate_majors(default=21)

        self._refresh_btn = QPushButton("重新获取")
        self._refresh_btn.setObjectName("Ghost")
        self._refresh_btn.setFixedHeight(28)
        self._refresh_btn.clicked.connect(lambda: self.refresh(force=True))
        toolbar.addWidget(self._refresh_btn)

        self._status_label = QLabel("")
        self._status_label.setObjectName("Tiny")
        self._status_label.setWordWrap(True)
        toolbar.addWidget(self._status_label, 1)
        card.body.addLayout(toolbar)

        # 选择变化只触发一次查询（构造完成后再接线，避免初始化期重复请求）
        self._dist_combo.currentIndexChanged.connect(self._on_distribution_changed)
        self._major_combo.currentIndexChanged.connect(self._on_major_changed)

        table = QTableWidget(0, 5)
        table.setHorizontalHeaderLabels(["版本", "大小", "来源", "状态", "操作"])
        table.verticalHeader().setVisible(False)
        table.setSelectionMode(QAbstractItemView.NoSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        table.setColumnWidth(1, 100)
        table.setColumnWidth(3, 110)
        table.setColumnWidth(4, 130)
        table.verticalHeader().setDefaultSectionSize(38)
        card.body.addWidget(table, 1)
        self._table = table

        hint = QLabel(f"安装目录：{JAVA_ROOT}（按发行版与版本分目录，互不覆盖）")
        hint.setObjectName("Tiny")
        hint.setWordWrap(True)
        card.body.addWidget(hint)
        outer.addWidget(card, 1)

    # ------------------------------------------------------------------
    def _current_distribution(self) -> dict | None:
        dist_id = self._dist_combo.currentData()
        for dist in self._distributions:
            if dist["id"] == dist_id:
                return dist
        return self._distributions[0] if self._distributions else None

    def _current_major(self) -> int | None:
        value = self._major_combo.currentData()
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _populate_majors(self, default: int = 21) -> None:
        dist = self._current_distribution()
        if dist is None:
            return
        majors = list(dist.get("majors") or [8, 11, 17, 21])
        previous = self._major_combo.currentData()
        target = previous if previous in majors else (
            default if default in majors else majors[-1]
        )
        self._major_combo.blockSignals(True)
        self._major_combo.clear()
        for major in majors:
            self._major_combo.addItem(f"Java {major}", int(major))
        index = self._major_combo.findData(target)
        self._major_combo.setCurrentIndex(index if index >= 0 else 0)
        self._major_combo.blockSignals(False)

    def _on_distribution_changed(self, _index: int = -1) -> None:
        self._populate_majors()
        self.refresh()

    def _on_major_changed(self, _index: int = -1) -> None:
        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self, force: bool = False) -> None:
        """按当前筛选异步获取版本列表；force=True 时忽略缓存。"""
        dist = self._current_distribution()
        major = self._current_major()
        if dist is None or major is None:
            return
        self._request_key = f"{dist['id']}:{major}"
        self._refresh_btn.setEnabled(False)
        self._status_label.setText(f"正在获取 {dist['name']} Java {major} 版本…")
        self._show_placeholder("正在获取版本…")

        worker = ResolveWorker(dist["id"], major, force=force, parent=self)
        worker.done.connect(self._on_versions)
        worker.failed.connect(self._on_versions_failed)
        worker.finished.connect(lambda w=worker: self._discard_worker(w))
        self._workers.append(worker)
        worker.start()

    def shutdown(self) -> None:
        """关闭页面：取消并等待仍在运行的查询 / 下载 worker。"""
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
    def _show_placeholder(self, text: str) -> None:
        self._versions = []
        table = self._table
        table.setRowCount(0)
        table.insertRow(0)
        item = QTableWidgetItem(text)
        item.setForeground(Qt.GlobalColor.gray)
        table.setItem(0, 0, item)

    def _on_versions(self, key: str, versions: object) -> None:
        if key != self._request_key:
            return  # 已经切换到其他发行版 / 主版本，丢弃旧结果
        self._refresh_btn.setEnabled(True)
        rows = [
            dict(item)
            for item in (versions or [])
            if isinstance(item, dict) and str(item.get("url") or "")
        ] if isinstance(versions, list) else []
        if not rows:
            self._status_label.setText("获取失败，暂无可用版本，请检查网络后重试")
            self._show_placeholder("获取失败，请检查网络后重试")
            return
        self._versions = rows
        if all(bool(row.get("fallback")) for row in rows):
            self._status_label.setText("获取失败，已回退到默认下载（官方最新版）")
        else:
            channel = str(rows[0].get("channel") or "")
            self._status_label.setText(f"已获取 {len(rows)} 个版本" + (f" · {channel}" if channel else ""))
        self._populate(rows)

    def _on_versions_failed(self, key: str, message: str) -> None:
        if key != self._request_key:
            return
        self._refresh_btn.setEnabled(True)
        self._status_label.setText("获取失败，已回退到默认下载")
        self._show_placeholder("获取失败，已回退到默认下载")
        self.ctx.bus.log.emit(f"[Java 中心] 获取版本失败：{message}")

    def _populate(self, rows: list[dict]) -> None:
        table = self._table
        table.setRowCount(0)
        for row, item in enumerate(rows):
            table.insertRow(row)
            version_text = str(item.get("version") or "")
            if item.get("latest"):
                version_text += "（最新）"
            version_item = QTableWidgetItem(version_text)
            version_item.setData(Qt.UserRole, item.get("url"))
            version_item.setToolTip(str(item.get("name") or item.get("url") or ""))
            table.setItem(row, 0, version_item)

            size_item = QTableWidgetItem(_fmt_size(item.get("size")))
            size_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 1, size_item)

            source_item = QTableWidgetItem(str(item.get("channel") or ""))
            source_item.setToolTip(str(item.get("note") or ""))
            table.setItem(row, 2, source_item)

            installed = self._installed_path(item)
            status_item = QTableWidgetItem("已安装" if installed else "可下载")
            status_item.setTextAlignment(Qt.AlignCenter)
            status_item.setForeground(
                Qt.GlobalColor.green if installed else Qt.GlobalColor.cyan
            )
            status_item.setToolTip(installed)
            table.setItem(row, 3, status_item)

            actions = QWidget()
            action_layout = QHBoxLayout(actions)
            action_layout.setContentsMargins(4, 2, 4, 2)
            action_layout.setSpacing(6)
            install_btn = QPushButton("下载")
            install_btn.setObjectName("Primary")
            install_btn.setFixedHeight(26)
            install_btn.clicked.connect(lambda _checked=False, data=item: self._install(data))
            action_layout.addWidget(install_btn, 0, Qt.AlignCenter)
            table.setCellWidget(row, 4, actions)

    def _installed_path(self, item: dict) -> str:
        major = int(item.get("major") or self._current_major() or 0)
        name = java_runtime_name(
            major, str(item.get("id") or ""), str(item.get("version") or "")
        )
        return find_java_in(JAVA_ROOT / name)

    # ------------------------------------------------------------------
    def _install(self, item: dict) -> None:
        if self._installed_path(item):
            self.ctx.bus.toast.emit("该版本已安装，无需重复下载。")
            return
        url = str(item.get("url") or "")
        if not url:
            return
        major = int(item.get("major") or self._current_major() or 0)
        target_name = java_runtime_name(
            major, str(item.get("id") or ""), str(item.get("version") or "")
        )
        dist_name = str(item.get("dist_name") or "")
        version_label = str(item.get("version") or "")

        def factory(task) -> QThread:
            # 每次（含重试）都新建事件，避免取消后重试立即再次取消
            cancel_event = threading.Event()
            pause_event = threading.Event()
            task.cancel = cancel_event.set
            task.pause_event = pause_event
            worker = JavaCenterInstallWorker(
                major,
                JAVA_ROOT,
                task.id,
                cancel_event,
                pause_event,
                url,
                target_name,
                int(item.get("size") or 0),
                self,
            )
            worker.progress.connect(
                lambda percent, speed, tid=task.id: self.ctx.downloads.update(
                    tid,
                    percent=percent,
                    speed=speed,
                    stage=f"下载 Java {major}",
                )
            )
            worker.done.connect(lambda info, tid=task.id: self._on_installed(tid, info))
            worker.failed.connect(
                lambda message, tid=task.id: self._on_install_failed(tid, message)
            )
            worker.finished.connect(lambda w=worker: self._discard_worker(w))
            self._workers.append(worker)
            return worker

        detail = str(item.get("note") or item.get("channel") or "")
        self.ctx.downloads.submit(
            kind="Java",
            name=f"{dist_name} Java {version_label}",
            factory=factory,
            rebuild=factory,
            target_dir=str(JAVA_ROOT),
            detail=detail,
        )
        self.ctx.bus.toast.emit(f"已加入下载中心：{dist_name} Java {version_label}")

    def _on_installed(self, task_id: str, info) -> None:
        self.ctx.downloads.finish(task_id, ok=True)
        self.ctx.javas = detect_java_installed()
        if info is not None and all(
            java_key(j.path) != java_key(info.path) for j in self.ctx.javas
        ):
            self.ctx.javas.append(info)
        self.ctx.bus.javas_changed.emit()
        self.ctx.bus.toast.emit(
            f"Java {getattr(info, 'version', '')} 已安装完成。"
        )
        self.refresh()

    def _on_install_failed(self, task_id: str, message: str) -> None:
        self.ctx.downloads.finish(task_id, ok=False, message=message)
        self.ctx.bus.log.emit(f"[Java 中心] Java 安装失败：{message}")
        QMessageBox.warning(self, "Java 安装失败", message)
