"""基岩版页面：浏览 MCAPPX 历史版本与微软商店版本，用内置浏览器（Edge 内核）下载安装包。"""

from __future__ import annotations

import platform
import re
import shutil
import threading
import time
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QThread, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import bedrock
from ..config import DATA_DIR
from ..context import AppContext, wait_thread
from ..net import Cancelled
from .widgets import Card, page_header


def _local_arch() -> str:
    """本机架构对应的安装包类型（基岩版只提供 x64 / x86 / arm）。"""
    machine = platform.machine().lower()
    if machine in ("arm64", "aarch64"):
        return "arm"
    return "x64"


# ---------------------------------------------------------------------------
# 后台 worker
# ---------------------------------------------------------------------------
class StoreFetchWorker(QThread):
    """查询微软商店清单（rg-adguard 接口，返回各架构 Appx 与依赖包直链）。"""

    done = Signal(str, object)
    failed = Signal(str, str)

    def __init__(self, ring: str, parent=None):
        super().__init__(parent)
        self.ring = ring
        # 退出时置位，让内部重试立即中断，避免 wait_thread 超时后线程仍在跑
        self.cancel_event = threading.Event()

    def run(self) -> None:
        try:
            rows = bedrock.fetch_store_packages(self.ring, cancel=self.cancel_event)
            self.done.emit(self.ring, rows)
        except Cancelled:
            return
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(self.ring, str(exc))


class BedrockWorker(QThread):
    """下载 + 校验 + 安装一条龙；可被下载中心暂停 / 取消。"""

    progress = Signal(float, float)
    stage = Signal(str)
    segment = Signal(int, int)
    done = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        url: str,
        dest: Path,
        size: int = 0,
        workers: int = 8,
        sha256: str = "",
        sha1: str = "",
        install: bool = False,
        dependencies: list[dict] | None = None,
        cancel_event: threading.Event | None = None,
        pause_event: threading.Event | None = None,
        ctx: AppContext | None = None,
        local_path: Path | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.url = url
        self.dest = Path(dest)
        self.size = int(size or 0)
        self.workers = int(workers or 8)
        self.sha256 = sha256
        self.sha1 = sha1
        self.install = install
        self.dependencies = list(dependencies or [])
        self.cancel_event = cancel_event or threading.Event()
        self.pause_event = pause_event or threading.Event()
        self.ctx = ctx
        # 本地安装包：跳过下载与校验，直接安装用户选中的文件
        self.local_path = Path(local_path) if local_path else None

    def _log(self, text: str) -> None:
        if self.ctx is not None:
            self.ctx.bus.log.emit(text)

    def run(self) -> None:
        state = {"total": self.size, "bytes": 0, "last_t": time.time(), "last_b": 0}

        def on_total(total: int) -> None:
            state["total"] = int(total or 0)

        def on_bytes(done: int) -> None:
            state["bytes"] = int(done or 0)
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
            if self.local_path is not None:
                path = self.local_path
                if not path.exists():
                    raise bedrock.DownloadError(
                        self.tr("安装包不存在：{0}").format(path)
                    )
            else:
                self.stage.emit(self.tr("下载安装包"))
                downloader = bedrock.MultiPartDownload(
                    self.url,
                    self.dest,
                    workers=self.workers,
                    size=self.size,
                    cancel=self.cancel_event,
                    pause=self.pause_event,
                    on_bytes=on_bytes,
                    on_total=on_total,
                    # 分段完成数与总分段数交给下载中心显示「剩余文件」
                    on_segment_done=lambda done_n, total_n: self.segment.emit(
                        int(done_n), int(total_n)
                    ),
                )
                path = downloader.run()
                self.progress.emit(1.0, 0.0)

                if self.sha256:
                    self.stage.emit(self.tr("校验文件完整性"))
                    if bedrock.sha256_of(path) != self.sha256.lower():
                        raise bedrock.DownloadError(self.tr("SHA256 校验失败，文件可能已损坏"))
                elif self.sha1:
                    self.stage.emit(self.tr("校验文件完整性"))
                    if bedrock.sha1_of(path) != self.sha1.lower():
                        raise bedrock.DownloadError(self.tr("SHA1 校验失败，文件可能已损坏"))

            if self.install:
                self._install_with_dependencies(path)
            self.done.emit(str(path))
        except Cancelled:
            pass
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))

    def _install_with_dependencies(self, path: Path) -> None:
        self.stage.emit(self.tr("安装到系统"))
        try:
            bedrock.install_appx(path, self.cancel_event, log=self._log)
            return
        except Cancelled:
            raise
        except Exception as exc:  # noqa: BLE001
            first_error = exc
        if not self.dependencies:
            # 本地安装包没有携带依赖清单：从商店清单里临时取一次 VCLibs
            try:
                raw = bedrock.fetch_store_packages("Retail")
                arch = _local_arch()
                self.dependencies = bedrock.dependency_entries(raw, arch)
            except Exception as exc:  # noqa: BLE001
                self._log(f"[基岩版] 获取运行库依赖失败：{exc}")
        if not self.dependencies:
            raise first_error
        # 缺少运行库时先补依赖再重试一次
        self.stage.emit(self.tr("安装运行库依赖"))
        for dep in self.dependencies:
            dep_path = path.parent / str(dep.get("name") or "dependency.appx")
            try:
                if not dep_path.exists():
                    bedrock.MultiPartDownload(
                        str(dep.get("url") or ""),
                        dep_path,
                        workers=4,
                        size=int(dep.get("size") or 0),
                        cancel=self.cancel_event,
                        pause=self.pause_event,
                    ).run()
                bedrock.install_appx(dep_path, self.cancel_event, log=self._log)
            except Cancelled:
                raise
            except Exception as dep_error:  # noqa: BLE001
                self._log(f"[基岩版] 依赖安装失败：{dep_error}")
        bedrock.install_appx(path, self.cancel_event, log=self._log)


# ---------------------------------------------------------------------------
class InstalledQueryWorker(QThread):
    """后台查询系统已安装的基岩版（PowerShell 约 1.6s，放到线程里避免卡界面）。"""

    done = Signal(object)

    def run(self) -> None:
        try:
            self.done.emit(bedrock.installed_package())
        except Exception:  # noqa: BLE001 - 查询失败按未安装显示
            self.done.emit(None)


# ---------------------------------------------------------------------------
class BedrockPage(QWidget):
    """基岩版页：展示版本目录，通过内置浏览器下载安装包并本地安装。"""

    PACKAGE_SUFFIXES = (".appx", ".msix", ".appxbundle", ".msixbundle")

    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self._store_cache: dict[str, list[dict]] = {}
        self._store_errors: dict[str, str] = {}
        self._workers: list[QThread] = []
        self._rows: list[dict] = []
        self._installed: dict | None = None
        self._installed_at = 0.0
        self._installed_worker: InstalledQueryWorker | None = None
        self._last_page_url = bedrock.MCAPPX_PAGE
        self._pending_launch = 0.0
        self._seen_files: set[str] = set()
        self._watcher: QFileSystemWatcher | None = None
        self._download_dirs: list[Path] = []
        self._build()
        self._refresh_runtime_card()
        self._reload()
        self.refresh()
        self._setup_download_watch()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 18, 24, 18)
        outer.setSpacing(14)
        header, _ = page_header(
            self.tr("基岩版"),
            self.tr("用内置浏览器（Edge 内核）打开下载页，下载完成后自动归档到本地，再安装并启动"),
        )
        outer.addWidget(header)

        # ---------- 运行状态 ----------
        runtime = Card(margins=14, spacing=10)
        row = QHBoxLayout()
        row.setSpacing(10)
        self._runtime_label = QLabel("")
        self._runtime_label.setObjectName("CardTitle")
        row.addWidget(self._runtime_label)
        self._runtime_detail = QLabel("")
        self._runtime_detail.setObjectName("Tiny")
        self._runtime_detail.setMinimumWidth(0)
        row.addWidget(self._runtime_detail, 1)

        self._launch_btn = QPushButton(self.tr("启动基岩版"))
        self._launch_btn.setObjectName("PrimaryCompact")
        self._launch_btn.setFixedHeight(32)
        self._launch_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._launch_btn.clicked.connect(self._launch)
        row.addWidget(self._launch_btn)

        self._uninstall_btn = QPushButton(self.tr("卸载"))
        self._uninstall_btn.setObjectName("GhostCompact")
        self._uninstall_btn.setFixedHeight(32)
        self._uninstall_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._uninstall_btn.clicked.connect(self._uninstall)
        row.addWidget(self._uninstall_btn)

        self._local_btn = QPushButton(self.tr("从本地安装"))
        self._local_btn.setObjectName("GhostCompact")
        self._local_btn.setFixedHeight(32)
        self._local_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._local_btn.clicked.connect(self._install_local)
        row.addWidget(self._local_btn)

        store_btn = QPushButton(self.tr("打开微软商店"))
        store_btn.setObjectName("GhostCompact")
        store_btn.setFixedHeight(32)
        store_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        store_btn.clicked.connect(lambda: bedrock.open_url(bedrock.STORE_PAGE))
        row.addWidget(store_btn)
        runtime.body.addLayout(row)

        dir_row = QHBoxLayout()
        dir_row.setSpacing(8)
        self._dir_label = QLabel(
            self.tr("安装包下载目录：{0}").format(bedrock.DOWNLOAD_ROOT)
        )
        self._dir_label.setObjectName("Tiny")
        self._dir_label.setWordWrap(True)
        dir_row.addWidget(self._dir_label, 1)
        open_dir_btn = QPushButton(self.tr("打开目录"))
        open_dir_btn.setObjectName("GhostCompact")
        open_dir_btn.setFixedHeight(26)
        open_dir_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        open_dir_btn.clicked.connect(self._open_download_dir)
        dir_row.addWidget(open_dir_btn)
        runtime.body.addLayout(dir_row)
        outer.addWidget(runtime)

        # ---------- 版本列表 ----------
        card = Card(margins=14, spacing=10)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        category_label = QLabel(self.tr("分类"))
        category_label.setObjectName("Tiny")
        toolbar.addWidget(category_label)
        self._category_combo = QComboBox()
        self._category_combo.setMinimumWidth(170)
        self._category_combo.addItem(self.tr("历史版本（MCAPPX）"), "mcappx")
        self._category_combo.addItem(self.tr("微软商店 · 正式版"), "store:Retail")
        self._category_combo.addItem(self.tr("微软商店 · 预览版"), "store:RP")
        toolbar.addWidget(self._category_combo)

        arch_label = QLabel(self.tr("架构"))
        arch_label.setObjectName("Tiny")
        toolbar.addWidget(arch_label)
        self._arch_combo = QComboBox()
        self._arch_combo.setMinimumWidth(96)
        self._arch_combo.addItem(self.tr("自动（{0}）").format(_local_arch()), "auto")
        self._arch_combo.addItem("x64", "x64")
        self._arch_combo.addItem("x86", "x86")
        self._arch_combo.addItem("arm", "arm")
        toolbar.addWidget(self._arch_combo)

        major_label = QLabel(self.tr("主版本"))
        major_label.setObjectName("Tiny")
        toolbar.addWidget(major_label)
        self._major_combo = QComboBox()
        self._major_combo.setMinimumWidth(120)
        self._major_combo.addItem(self.tr("全部主版本"), "all")
        for major in bedrock.load_catalog().get("majors") or []:
            label = str(major.get("name") or major.get("id") or "")
            if label:
                self._major_combo.addItem(label, str(major.get("id") or ""))
        toolbar.addWidget(self._major_combo)

        self._search = QLineEdit()
        self._search.setPlaceholderText(self.tr("搜索版本号，例如 1.8.1"))
        self._search.setMinimumWidth(140)
        toolbar.addWidget(self._search)

        self._refresh_btn = QPushButton(self.tr("重新获取"))
        self._refresh_btn.setObjectName("Ghost")
        self._refresh_btn.setFixedHeight(28)
        self._refresh_btn.clicked.connect(lambda: self._reload(force=True))
        toolbar.addWidget(self._refresh_btn)

        self._status_label = QLabel("")
        self._status_label.setObjectName("Tiny")
        self._status_label.setWordWrap(True)
        toolbar.addWidget(self._status_label, 1)
        card.body.addLayout(toolbar)

        table = QTableWidget(0, 7)
        table.setHorizontalHeaderLabels(
            [
                self.tr("版本"),
                self.tr("架构"),
                self.tr("大小"),
                self.tr("发布日期"),
                self.tr("来源"),
                self.tr("状态"),
                self.tr("操作"),
            ]
        )
        table.verticalHeader().setVisible(False)
        table.setSelectionMode(QAbstractItemView.NoSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        table.setColumnWidth(1, 60)
        table.setColumnWidth(2, 90)
        table.setColumnWidth(3, 100)
        table.setColumnWidth(6, 250)
        table.verticalHeader().setDefaultSectionSize(40)
        card.body.addWidget(table, 1)
        self._table = table

        tip = QLabel(
            self.tr(
                "下载不再走启动器内置的离线直链：点「在浏览器下载」会切到内置浏览器打开该版本的下载页，"
                "点击页面上的下载按钮后由 Edge 内核完成下载；下载完成的 .appx / .msix 安装包会自动"
                "归档到上方下载目录，随后可点「从本地安装」。"
            )
        )
        tip.setObjectName("Tiny")
        tip.setWordWrap(True)
        card.body.addWidget(tip)
        outer.addWidget(card, 1)

        # 构造完成后再接线，避免初始化期触发重复刷新
        self._category_combo.currentIndexChanged.connect(lambda _i: self._reload())
        self._arch_combo.currentIndexChanged.connect(lambda _i: self._render_rows())
        self._major_combo.currentIndexChanged.connect(lambda _i: self._render_rows())
        self._search.textChanged.connect(lambda _t: self._render_rows())

    # ------------------------------------------------------------------
    def _arch_filter(self) -> str:
        value = self._arch_combo.currentData()
        return _local_arch() if value == "auto" else str(value)

    def _open_download_dir(self) -> None:
        try:
            bedrock.DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)
            import os

            os.startfile(str(bedrock.DOWNLOAD_ROOT))  # noqa: S606
        except Exception:  # noqa: BLE001
            self.ctx.bus.toast.emit(self.tr("无法打开下载目录"))

    def _refresh_runtime_card(self) -> None:
        info = self._installed
        if info is None:
            self._runtime_label.setText(self.tr("尚未安装基岩版"))
            self._runtime_detail.setText(
                self.tr("选择下方版本下载安装，安装后可直接启动")
            )
            self._launch_btn.setEnabled(False)
            self._uninstall_btn.setEnabled(False)
            return
        version = str(info.get("Version") or "")
        arch = bedrock.arch_name(info.get("Architecture"))
        family = str(info.get("PackageFamilyName") or "")
        self._runtime_label.setText(self.tr("已安装：{0}").format(version))
        self._runtime_detail.setText(self.tr("架构 {0}").format(arch))
        self._runtime_detail.setToolTip(family)
        self._launch_btn.setEnabled(True)
        self._uninstall_btn.setEnabled(True)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """侧边栏切到本页时调用：异步刷新已安装状态（PowerShell 查询约 1.6s，不能卡界面）。"""
        if self._installed_worker is not None and self._installed_worker.isRunning():
            return
        if time.time() - self._installed_at < 10 and self._installed_at:
            self._refresh_runtime_card()
            self._render_rows()
            return
        worker = InstalledQueryWorker(self)
        worker.done.connect(self._on_installed_ready)
        worker.finished.connect(lambda w=worker: self._release_installed_worker(w))
        self._installed_worker = worker
        worker.start()

    def _on_installed_ready(self, info: object) -> None:
        self._installed = info if isinstance(info, dict) else None
        self._installed_at = time.time()
        self._refresh_runtime_card()
        self._render_rows()

    def _release_installed_worker(self, worker: QThread) -> None:
        if self._installed_worker is worker:
            self._installed_worker = None
        worker.deleteLater()

    def _reload(self, force: bool = False) -> None:
        category = str(self._category_combo.currentData() or "mcappx")
        self._major_combo.setEnabled(not category.startswith("store:"))
        if category.startswith("store:"):
            ring = category.split(":", 1)[1]
            if force:
                self._store_cache.pop(ring, None)
                self._store_errors.pop(ring, None)
            cached = self._store_cache.get(ring)
            if cached is None:
                self._fetch_store(ring)
                self._status_label.setText(self.tr("正在从微软商店获取版本列表…"))
                self._rows = []
                self._render_rows()
                return
            self._populate_store(cached, ring)
        else:
            self._populate_catalog()

    def _fetch_store(self, ring: str) -> None:
        self._refresh_btn.setEnabled(False)
        worker = StoreFetchWorker(ring, self)
        worker.done.connect(self._on_store_done)
        worker.failed.connect(self._on_store_failed)
        worker.finished.connect(lambda w=worker: self._discard_worker(w))
        self._workers.append(worker)
        worker.start()

    def _on_store_done(self, ring: str, rows: object) -> None:
        self._refresh_btn.setEnabled(True)
        self._store_cache[ring] = [dict(item) for item in rows] if isinstance(rows, list) else []
        current = str(self._category_combo.currentData() or "")
        if current == f"store:{ring}":
            if self._store_cache[ring]:
                self._populate_store(self._store_cache[ring], ring)
            else:
                self._status_label.setText(self.tr("微软商店接口没有返回可用的安装包"))
                self._rows = []
                self._render_rows()

    def _on_store_failed(self, ring: str, message: str) -> None:
        self._refresh_btn.setEnabled(True)
        self._store_errors[ring] = message
        self.ctx.bus.log.emit(f"[基岩版] 商店清单获取失败：{message}")
        current = str(self._category_combo.currentData() or "")
        if current == f"store:{ring}":
            self._status_label.setText(
                self.tr("获取失败，请检查网络或代理后点击「重新获取」")
            )
            self._rows = []
            self._render_rows()

    # ------------------------------------------------------------------
    def _populate_catalog(self) -> None:
        catalog = bedrock.load_catalog()
        arch = self._arch_filter()
        rows: list[dict] = []
        for release in catalog.get("releases") or []:
            archs = list(release.get("archs") or ["x64"])
            if arch not in archs:
                continue
            links = dict((release.get("links") or {}).get(arch) or {})
            sizes = dict(release.get("sizes") or {})
            hashes = dict(release.get("sha256") or {})
            rows.append(
                {
                    "version": str(release.get("version") or ""),
                    "channel": str(release.get("channel") or "release"),
                    "source": "mcappx",
                    "arch": arch,
                    "size": int(sizes.get(arch) or 0),
                    "date": str(release.get("date") or ""),
                    "page_url": str(release.get("url") or ""),
                    "download_url": str(links.get("jp") or links.get("us") or ""),
                    "sha256": str(hashes.get(arch) or ""),
                    "sha1": "",
                    "package_id": str(release.get("package_id") or ""),
                    "major": str(release.get("major") or ""),
                    "format": str(release.get("format") or "Appx"),
                    "dependencies": [],
                }
            )
        rows.sort(key=lambda item: _version_key(item["version"]), reverse=True)
        self._rows = rows
        self._status_label.setText(
            self.tr("MCAPPX 目录共 {0} 条（内置离线缓存）").format(len(rows))
        )
        self._render_rows()

    def _populate_store(self, raw: list[dict], ring: str) -> None:
        arch = self._arch_filter()
        shown = bedrock.build_store_entries(raw)
        rows: list[dict] = []
        for entry in shown:
            if str(entry.get("arch")) != arch:
                continue
            rows.append(
                {
                    "version": str(entry.get("version") or ""),
                    "channel": str(entry.get("channel") or ring),
                    "source": "store",
                    "arch": str(entry.get("arch") or ""),
                    "size": int(entry.get("size") or 0),
                    "date": "",
                    "page_url": bedrock.STORE_PAGE,
                    "download_url": str(entry.get("url") or ""),
                    "sha256": "",
                    "sha1": str(entry.get("sha1") or ""),
                    "package_id": str(entry.get("package") or ""),
                    "format": "Appx",
                    "dependencies": bedrock.dependency_entries(raw, arch),
                }
            )
        rows.sort(key=lambda item: _version_key(item["version"]), reverse=True)
        self._rows = rows
        self._status_label.setText(
            self.tr("微软商店接口返回 {0} 个可安装包").format(len(rows))
        )
        self._render_rows()

    # ------------------------------------------------------------------
    def _render_rows(self) -> None:
        arch = self._arch_filter()
        keyword = self._search.text().strip().lower()
        major = str(self._major_combo.currentData() or "all")
        rows = [
            row for row in self._rows
            if (not keyword or keyword in row["version"].lower())
            and ((not row.get("arch")) or row.get("arch") == arch)
            and (major == "all" or not row.get("major") or row.get("major") == major)
        ]
        table = self._table
        table.setRowCount(0)
        installed_raw = str((self._installed or {}).get("Version") or "")
        installed_key = _version_tuple(installed_raw) if installed_raw else ()
        for index, row in enumerate(rows):
            table.insertRow(index)
            channel = row.get("channel") or ""
            version_text = row["version"]
            if row.get("source") == "mcappx" and channel == "preview":
                version_text += " " + self.tr("（预览）")
            version_item = QTableWidgetItem(version_text)
            version_item.setToolTip(
                self.tr("安装包ID：{0}").format(row.get("package_id") or "-")
            )
            table.setItem(index, 0, version_item)

            arch_item = QTableWidgetItem(str(row.get("arch") or "-"))
            arch_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(index, 1, arch_item)

            size_item = QTableWidgetItem(bedrock.human_size(row.get("size")))
            size_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(index, 2, size_item)

            date_item = QTableWidgetItem(str(row.get("date") or "-"))
            date_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(index, 3, date_item)

            source_text = self.tr("微软商店") if row.get("source") == "store" else "MCAPPX"
            source_item = QTableWidgetItem(source_text)
            source_item.setToolTip(str(row.get("page_url") or ""))
            table.setItem(index, 4, source_item)

            # 页面版本号（1.8.1）与安装包版本号（1.8.102.0）不同，按主版本前缀匹配
            installed = _installed_match(installed_key, row)
            if installed:
                status_text, color = self.tr("已安装"), Qt.GlobalColor.green
            else:
                status_text, color = self.tr("浏览器下载"), Qt.GlobalColor.cyan
            status_item = QTableWidgetItem(status_text)
            status_item.setTextAlignment(Qt.AlignCenter)
            status_item.setForeground(color)
            table.setItem(index, 5, status_item)

            actions = QWidget()
            action_layout = QHBoxLayout(actions)
            action_layout.setContentsMargins(4, 2, 4, 2)
            action_layout.setSpacing(6)
            if installed:
                launch_btn = QPushButton(self.tr("启动"))
                launch_btn.setObjectName("PrimaryCompact")
                launch_btn.setFixedHeight(28)
                launch_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
                launch_btn.clicked.connect(self._launch)
                action_layout.addWidget(launch_btn)
            browser_btn = QPushButton(self.tr("在浏览器下载"))
            browser_btn.setObjectName("PrimaryCompact")
            browser_btn.setFixedHeight(28)
            browser_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            browser_btn.setToolTip(
                self.tr("在内置浏览器（Edge 内核）打开该版本下载页，点击下载后保存到本机")
            )
            browser_btn.clicked.connect(
                lambda _checked=False, data=row: self._open_in_browser(data)
            )
            action_layout.addWidget(browser_btn)
            action_layout.addStretch(1)
            table.setCellWidget(index, 6, actions)

    # ------------------------------------------------------------------
    def _open_in_browser(self, row: dict) -> None:
        """把该版本的内置下载页交给内置浏览器（优先 Edge 内核），下载由 Edge 完成。"""
        url = str(row.get("page_url") or "")
        if not url:
            url = bedrock.STORE_PAGE if row.get("source") == "store" else bedrock.MCAPPX_PAGE
        self._last_page_url = url
        self.ctx.bus.open_browser.emit(url)
        self.ctx.bus.toast.emit(
            self.tr("已在内置浏览器打开下载页，点击页面上的下载按钮即可保存到本机")
        )

    # ------------------------------------------------------------------
    def _build_factory(self, worker_kwargs: dict, install: bool):
        """生成下载中心需要的 worker 工厂（暂停 / 取消通过 task 事件联动）。"""

        def factory(task) -> QThread:
            cancel_event = threading.Event()
            pause_event = threading.Event()
            task.cancel = cancel_event.set
            task.pause_event = pause_event
            worker = BedrockWorker(
                cancel_event=cancel_event,
                pause_event=pause_event,
                install=install,
                ctx=self.ctx,
                parent=self,
                **worker_kwargs,
            )
            worker.progress.connect(
                lambda percent, speed, tid=task.id: self.ctx.downloads.update(
                    tid, percent=percent, speed=speed
                )
            )
            worker.stage.connect(
                lambda text, tid=task.id: self.ctx.downloads.update(tid, stage=text)
            )
            worker.segment.connect(
                lambda done_n, total_n, tid=task.id: self.ctx.downloads.update(
                    tid, files_done=done_n, files_total=total_n
                )
            )
            worker.done.connect(
                lambda path, tid=task.id: self._on_done(tid, path, install)
            )
            worker.failed.connect(lambda message, tid=task.id: self._on_failed(tid, message))
            worker.finished.connect(lambda w=worker: self._discard_worker(w))
            self._workers.append(worker)
            return worker

        return factory

    # ---- 浏览器下载归档 -----------------------------------------------
    def _watch_dirs(self) -> list[Path]:
        dirs: list[Path] = []
        home_downloads = Path.home() / "Downloads"
        if home_downloads.is_dir():
            dirs.append(home_downloads)
        fallback = DATA_DIR / "downloads"
        if fallback.is_dir():
            dirs.append(fallback)
        return dirs

    def _setup_download_watch(self) -> None:
        """监听浏览器下载目录：新出现的 Appx/MSIX 安装包自动归档到 bedrock 目录。"""
        bedrock.DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)
        self._download_dirs = self._watch_dirs()
        if not self._download_dirs:
            return
        watcher = QFileSystemWatcher(self)
        for folder in self._download_dirs:
            watcher.addPath(str(folder))
            for existing in folder.glob("*"):
                if existing.suffix.lower() in self.PACKAGE_SUFFIXES:
                    self._seen_files.add(str(existing).lower())
        watcher.directoryChanged.connect(self._on_download_dir_changed)
        self._watcher = watcher

    def _on_download_dir_changed(self, _path: str) -> None:
        # 浏览器写入文件需要一点时间，稍后再扫描，避免拿到半成品
        QTimer.singleShot(1500, self._scan_downloads)

    def _scan_downloads(self) -> None:
        moved = 0
        for folder in self._download_dirs:
            if not folder.is_dir():
                continue
            for path in sorted(folder.glob("*")):
                if path.suffix.lower() not in self.PACKAGE_SUFFIXES:
                    continue
                key = str(path).lower()
                if key in self._seen_files:
                    continue
                try:
                    if path.stat().st_size <= 0:
                        continue
                except OSError:
                    continue
                target = bedrock.DOWNLOAD_ROOT / path.name
                try:
                    shutil.move(str(path), str(target))
                except OSError:
                    # 文件可能仍被浏览器占用，留给用户手动「从本地安装」
                    continue
                self._seen_files.add(key)
                moved += 1
                self.ctx.bus.log.emit(f"[基岩版] 浏览器下载完成：{target}")
                self.ctx.bus.toast.emit(
                    self.tr("安装包已归档：{0}，可点「从本地安装」").format(target.name)
                )
        if moved:
            self.refresh()

    def _install_local(self) -> None:
        """安装内置浏览器下载完成后归档到本地的 .appx / .msix 安装包。"""
        chosen, _filter = QFileDialog.getOpenFileName(
            self,
            self.tr("选择基岩版安装包"),
            str(bedrock.DOWNLOAD_ROOT),
            self.tr("Appx 安装包 (*.appx *.msix *.appxbundle *.msixbundle *.Appx)"),
        )
        if not chosen:
            return
        path = Path(chosen)
        factory = self._build_factory(
            dict(url="", dest=path, local_path=path, dependencies=[]), True
        )
        name = self.tr("本地安装 {0}").format(path.name)
        self.ctx.downloads.submit(
            kind="Bedrock",
            name=name,
            factory=factory,
            rebuild=factory,
            target_dir=str(path.parent),
            detail=self.tr("本地安装包"),
        )
        self.ctx.bus.toast.emit(self.tr("已加入下载中心：{0}").format(name))

    def _on_done(self, task_id: str, path: str, install: bool) -> None:
        if install:
            self.ctx.downloads.update(task_id, stage=self.tr("安装完成"))
            self.ctx.downloads.finish(
                task_id, ok=True, message=self.tr("安装包已保存到 {0}").format(path)
            )
            # 安装后重新查询系统已安装版本（异步，避免阻塞界面）
            self._installed_at = 0.0
            self.refresh()
            self.ctx.bus.versions_changed.emit()
            self.ctx.bus.toast.emit(self.tr("基岩版安装完成，可直接启动"))
        else:
            self.ctx.downloads.update(task_id, stage=self.tr("下载完成"))
            self.ctx.downloads.finish(
                task_id, ok=True, message=self.tr("安装包已保存到 {0}").format(path)
            )
            self.ctx.bus.toast.emit(self.tr("安装包已保存：{0}").format(path))

    def _on_failed(self, task_id: str, message: str) -> None:
        self.ctx.downloads.finish(task_id, ok=False, message=message)
        self.ctx.bus.log.emit(f"[基岩版] 下载 / 安装失败：{message}")
        if "人机验证" in message:
            box = QMessageBox(self)
            box.setWindowTitle(self.tr("需要浏览器下载"))
            box.setText(message)
            box.setInformativeText(
                self.tr("是否用默认浏览器打开该版本的下载页？")
            )
            open_btn = box.addButton(self.tr("打开下载页"), QMessageBox.AcceptRole)
            box.addButton(self.tr("取消"), QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() == open_btn:
                bedrock.open_url(self._last_page_url or bedrock.MCAPPX_PAGE)
            return
        QMessageBox.warning(self, self.tr("基岩版操作失败"), message)

    # ------------------------------------------------------------------
    def _launch(self) -> None:
        ok, message = bedrock.launch_installed()
        if not ok:
            QMessageBox.warning(self, self.tr("无法启动基岩版"), message)
            return
        self.ctx.bus.log.emit(f"[基岩版] 已启动：{message}")
        self.ctx.bus.toast.emit(self.tr("正在启动基岩版…"))
        # 20 秒后确认进程真的起来了：未授权 / 未登录时会静默失败，需要给出原因
        self._pending_launch = time.time()
        QTimer.singleShot(20000, self._verify_launch)

    def _verify_launch(self) -> None:
        if not getattr(self, "_pending_launch", 0):
            return
        if bedrock.is_game_running():
            self._pending_launch = 0
            return
        self._pending_launch = 0
        hint = bedrock.activation_hint()
        if hint:
            QMessageBox.warning(self, self.tr("基岩版未能启动"), hint)
        else:
            self.ctx.bus.toast.emit(
                self.tr("未检测到基岩版进程，请稍等或重试；若持续失败请确认已用正版账号登录微软商店")
            )

    def _uninstall(self) -> None:
        info = self._installed or {}
        answer = QMessageBox.question(
            self,
            self.tr("卸载基岩版"),
            self.tr("确定卸载已安装的基岩版 {0} 吗？存档会保留在系统中。").format(
                info.get("Version") or ""
            ),
        )
        if answer != QMessageBox.Yes:
            return
        ok, message = bedrock.uninstall_installed()
        if not ok:
            QMessageBox.warning(self, self.tr("卸载失败"), message)
            return
        self._installed_at = 0.0
        self.refresh()
        self.ctx.bus.versions_changed.emit()
        self.ctx.bus.toast.emit(self.tr("基岩版已卸载"))

    # ------------------------------------------------------------------
    def _discard_worker(self, worker: QThread) -> None:
        if worker in self._workers:
            self._workers.remove(worker)
        worker.deleteLater()

    def shutdown(self) -> None:
        if self._watcher is not None:
            try:
                self._watcher.directoryChanged.disconnect(self._on_download_dir_changed)
            except (RuntimeError, TypeError):
                pass
            for folder in self._download_dirs:
                try:
                    self._watcher.removePath(str(folder))
                except (RuntimeError, TypeError):
                    pass
            self._watcher = None
            self._download_dirs = []
        if self._installed_worker is not None:
            wait_thread(self._installed_worker, 2000)
            self._installed_worker = None
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


def _version_key(version: str) -> tuple:
    parts = []
    for piece in str(version).split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _version_tuple(version: object) -> tuple[int, int, int, int]:
    """把任意版本串规整成 4 段元组，便于比较「1.8.102」与「1.8.102.0」。"""
    numbers = [int(piece) for piece in re.findall(r"\d+", str(version))][:4]
    numbers += [0] * (4 - len(numbers))
    return tuple(numbers[:4])  # type: ignore[return-value]


def _installed_match(installed_key: tuple, row: dict) -> bool:
    """判断该行是否已安装。

    MCAPPX 页面版本（1.8.1）与系统包版本（1.8.102.0）末段永远不同，
    因此按「前两段」主版本线比较：1.8.x 下有已装包即视为该行已安装。
    """
    if not installed_key:
        return False
    candidates = {_version_tuple(row.get("version") or "")}
    if row.get("package_id"):
        candidates.add(_version_tuple(row["package_id"]))
    for cand in candidates:
        if installed_key[:2] == cand[:2]:
            return True
    return False
