"""依赖补全页：第三方模块下载，以及游戏缺失依赖的检查与静默补全。"""

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
from ..content import detect_mod_conflicts, scan_mod_metadata
from ..context import AppContext, wait_thread
from ..dependencies import (
    DISCLAIMER,
    MissingItem,
    install_third_party,
    required_java,
    scan_missing,
    summarize_missing,
    third_party_modules,
)
from ..installer import GameInstaller
from ..java import download_java, java_key
from ..net import Cancelled
from ..version import load_version, scan_installed_versions
from .widgets import Card, page_header, related_features_row

_FILE_KINDS = ("client", "library", "assets", "logging", "version")


class ModuleInstallWorker(QThread):
    """下载安装一个第三方模块（陶瓦联机 / authlib-injector）。"""

    done = Signal(str, str)  # module_id, 安装路径
    failed = Signal(str, str)  # module_id, 错误信息
    progress = Signal(float, str)  # 0~1 进度, 说明
    logged = Signal(str)

    def __init__(
        self,
        module_id: str,
        config,
        cancel_event: threading.Event | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.module_id = module_id
        self.config = config
        self.cancel_event = cancel_event or threading.Event()

    def run(self) -> None:
        try:
            path = install_third_party(
                self.module_id,
                self.config,
                log=self.logged.emit,
                progress=lambda ratio, detail: self.progress.emit(ratio, detail),
                cancel=self.cancel_event,
            )
            self.done.emit(self.module_id, str(path))
        except Cancelled:
            pass
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(self.module_id, str(exc))


class VersionRepairWorker(QThread):
    """调用 GameInstaller.ensure_version 补全版本文件（客户端 / 依赖库 / 资源）。"""

    done = Signal(str)  # version_id
    failed = Signal(str)
    progress = Signal(float, str)
    logged = Signal(str)

    def __init__(
        self,
        config,
        sources,
        version_id: str,
        cancel_event: threading.Event | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.config = config
        self.sources = sources
        self.version_id = version_id
        self.cancel_event = cancel_event or threading.Event()

    def run(self) -> None:
        try:
            installer = GameInstaller(
                self.config,
                self.sources,
                progress_cb=lambda p: self.progress.emit(
                    float(p.percent), f"{p.stage} {p.detail}".strip()
                ),
                log_cb=self.logged.emit,
                cancel=self.cancel_event,
            )
            installer.ensure_version(self.version_id)
            self.done.emit(self.version_id)
        except Cancelled:
            pass
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class MissingModWorker(QThread):
    """检测 mods/ 里缺失的前置并自动搜索安装最新兼容版本。"""

    done = Signal(list)
    failed = Signal(str)
    logged = Signal(str)

    def __init__(
        self,
        ctx: AppContext,
        version_id: str,
        game_version: str,
        loader: str,
        parent=None,
    ):
        super().__init__(parent)
        self.ctx = ctx
        self.version_id = version_id
        self.game_version = game_version
        self.loader = loader

    def run(self) -> None:
        try:
            mods_dir = self.ctx.config.resolve_game_dirs(self.version_id).targets("mods")[0]
            conflicts = (
                detect_mod_conflicts(scan_mod_metadata(mods_dir))
                if mods_dir.is_dir()
                else []
            )
            missing = sorted(
                {
                    str(item.get("modid") or "")
                    for item in conflicts
                    if str(item.get("type") or "") == "missing_dependency"
                }
                - {""}
            )
            if not missing:
                self.done.emit([])
                return
            installed: list[str] = []
            for modid in missing:
                if not self.game_version:
                    self.logged.emit(f"[补全] 未知游戏版本，跳过 {modid}")
                    continue
                try:
                    projects = self.ctx.content.search(
                        "modrinth",
                        "mod",
                        modid,
                        game_version=self.game_version,
                        loader=self.loader,
                        limit=5,
                    )
                except Exception as exc:  # noqa: BLE001
                    self.logged.emit(f"[补全] 搜索 {modid} 失败：{exc}")
                    continue
                if not projects:
                    self.logged.emit(f"[补全] 未找到 {modid} 的兼容版本")
                    continue
                project = next(
                    (
                        item
                        for item in projects
                        if item.slug.lower() == modid.lower()
                        or item.title.lower() == modid.lower()
                    ),
                    projects[0],
                )
                try:
                    versions = self.ctx.content.versions(
                        "modrinth", project.id, self.game_version, self.loader
                    )
                    files = [
                        f for v in versions[:2] for f in v.files if f.filename.endswith(".jar")
                    ]
                    if not files:
                        self.logged.emit(f"[补全] {modid} 没有可下载的 jar")
                        continue
                    dest = self.ctx.content.download_to("modrinth", files[0], mods_dir)
                    installed.append(dest.name)
                    self.logged.emit(f"[补全] 已安装前置 {modid} → {dest.name}")
                except Exception as exc:  # noqa: BLE001
                    self.logged.emit(f"[补全] 安装 {modid} 失败：{exc}")
            self.done.emit(installed)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class JavaInstallWorker(QThread):
    """按所需主版本下载并解压 Adoptium JRE。"""

    done = Signal(object)
    failed = Signal(str)
    progress = Signal(float, str)
    logged = Signal(str)

    def __init__(
        self,
        major: int,
        dest_root: Path,
        cancel_event: threading.Event | None = None,
        pause_event: threading.Event | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.major = int(major)
        self.dest_root = Path(dest_root)
        self.cancel_event = cancel_event or threading.Event()
        self.pause_event = pause_event or threading.Event()

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
            detail = f"{state['bytes'] / 1048576:.1f} MB · {speed / 1048576:.1f} MB/s"
            self.progress.emit(percent, detail)

        try:
            info = download_java(
                self.major,
                self.dest_root,
                log=self.logged.emit,
                on_bytes=on_bytes,
                cancel=self.cancel_event,
                pause=self.pause_event,
                on_total=on_total,
            )
            self.done.emit(info)
        except Cancelled:
            pass
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class CheckWorker(QThread):
    done = Signal(str, object, object)  # version_id, merged, 缺失项列表

    def __init__(self, config, version_id: str, javas: list, parent=None):
        super().__init__(parent)
        self.config = config
        self.version_id = version_id
        self.javas = list(javas or [])

    def run(self) -> None:
        merged, items = scan_missing(self.config, self.version_id, self.javas)
        self.done.emit(self.version_id, merged, items)


class DependenciesPage(QWidget):
    """依赖补全：第三方模块清单 + 游戏依赖检查 / 静默补全。"""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self._workers: list[QThread] = []
        self._check_worker: CheckWorker | None = None
        self._check_key = ""
        self._build()
        self.refresh()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 18, 24, 18)
        outer.setSpacing(14)
        header, _ = page_header(
            "依赖补全",
            "所有不可内置的第三方依赖统一入口，并检查游戏缺失的 Java、客户端、依赖库与资源文件",
        )
        outer.addWidget(header)

        modules_card = Card(margins=16, spacing=10)
        modules_card.body.addWidget(
            QLabel("<span style='font-size:15px;font-weight:700;'>第三方模块</span>")
        )
        disclaimer = QLabel(DISCLAIMER)
        disclaimer.setWordWrap(True)
        disclaimer.setStyleSheet("color: #ffb454;")
        modules_card.body.addWidget(disclaimer)

        module_table = QTableWidget(0, 5)
        module_table.setHorizontalHeaderLabels(["模块", "类别", "状态", "说明", "操作"])
        module_table.verticalHeader().setVisible(False)
        module_table.setSelectionMode(QAbstractItemView.NoSelection)
        module_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        module_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        module_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        module_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        module_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        module_table.setColumnWidth(4, 140)
        module_table.verticalHeader().setDefaultSectionSize(40)
        modules_card.body.addWidget(module_table)
        self._module_table = module_table

        modules_hint = QLabel(
            "「下载」在本页完成安装；「前往」表示需在对应页面使用官方安装器按版本安装，本页只提供统一入口。"
        )
        modules_hint.setObjectName("Tiny")
        modules_hint.setWordWrap(True)
        modules_card.body.addWidget(modules_hint)
        outer.addWidget(modules_card)

        check_card = Card(margins=16, spacing=10)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        label = QLabel("游戏版本")
        label.setObjectName("Tiny")
        toolbar.addWidget(label)
        self._version_combo = QComboBox()
        self._version_combo.setMinimumWidth(220)
        toolbar.addWidget(self._version_combo)
        self._reload_btn = QPushButton("刷新列表")
        self._reload_btn.setObjectName("Ghost")
        self._reload_btn.clicked.connect(self.refresh)
        toolbar.addWidget(self._reload_btn)
        self._check_btn = QPushButton("检查缺失依赖")
        self._check_btn.setObjectName("Primary")
        self._check_btn.setFixedHeight(28)
        self._check_btn.clicked.connect(lambda: self._check())
        toolbar.addWidget(self._check_btn)
        self._fix_mods_btn = QPushButton("补全缺失前置")
        self._fix_mods_btn.setObjectName("Mini")
        self._fix_mods_btn.setFixedHeight(28)
        self._fix_mods_btn.setToolTip("在 mods/ 中检测缺失的 Mod 前置并自动搜索安装最新兼容版本")
        self._fix_mods_btn.clicked.connect(lambda: self._install_missing_mods())
        toolbar.addWidget(self._fix_mods_btn)
        self._check_status = QLabel("")
        self._check_status.setObjectName("Tiny")
        self._check_status.setWordWrap(True)
        toolbar.addWidget(self._check_status, 1)
        check_card.body.addLayout(toolbar)

        result_table = QTableWidget(0, 3)
        result_table.setHorizontalHeaderLabels(["依赖项", "状态", "说明"])
        result_table.verticalHeader().setVisible(False)
        result_table.setSelectionMode(QAbstractItemView.NoSelection)
        result_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        result_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        result_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        result_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        result_table.verticalHeader().setDefaultSectionSize(36)
        check_card.body.addWidget(result_table)
        self._result_table = result_table

        hint = QLabel(
            "检查范围：所需 Java、客户端 jar、libraries 依赖库、assets 资源与日志配置。"
            "补全任务会登记到下载中心，可暂停 / 取消 / 重试；确认补全后后台静默执行，不影响继续使用启动器。"
        )
        hint.setObjectName("Tiny")
        hint.setWordWrap(True)
        check_card.body.addWidget(hint)
        outer.addWidget(check_card, 1)
        outer.addWidget(related_features_row(self.ctx, "deps"))

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        self._rebuild_modules()
        self._rebuild_versions()

    def _rebuild_modules(self) -> None:
        modules = third_party_modules(self.ctx.config, self.ctx.javas)
        table = self._module_table
        table.setRowCount(0)
        for row, item in enumerate(modules):
            table.insertRow(row)
            name = QTableWidgetItem(str(item["name"]))
            name.setToolTip(f"{item['license']} · {item['homepage']}")
            table.setItem(row, 0, name)

            category = QTableWidgetItem(str(item.get("category") or "第三方模块"))
            category.setTextAlignment(Qt.AlignCenter)
            category.setToolTip(str(item.get("license") or ""))
            table.setItem(row, 1, category)

            installed = item.get("installed")
            if installed is None:
                status = QTableWidgetItem("按需安装")
                status.setForeground(Qt.GlobalColor.gray)
            elif bool(installed):
                status = QTableWidgetItem("已安装")
                status.setForeground(Qt.GlobalColor.green)
            else:
                status = QTableWidgetItem("缺失")
                status.setForeground(Qt.GlobalColor.red)
            status.setTextAlignment(Qt.AlignCenter)
            status.setToolTip(str(item.get("path") or ""))
            table.setItem(row, 2, status)

            summary = QTableWidgetItem(f"{item['summary']}（{item['version']}）")
            summary.setToolTip(
                f"{item.get('license') or ''}\n{item.get('homepage') or ''}\n"
                f"{item.get('path') or ''}"
            )
            table.setItem(row, 3, summary)

            actions = QWidget()
            layout = QHBoxLayout(actions)
            layout.setContentsMargins(4, 2, 4, 2)
            layout.setSpacing(6)
            if str(item.get("action")) == "navigate":
                target = str(item.get("target") or "")
                goto_btn = QPushButton(str(item.get("action_text") or "前往"))
                goto_btn.setObjectName("Ghost")
                goto_btn.setFixedHeight(26)
                goto_btn.clicked.connect(
                    lambda _checked=False, key=target: self.ctx.bus.navigate.emit(key)
                )
                layout.addWidget(goto_btn, 0, Qt.AlignCenter)
            elif bool(installed):
                open_btn = QPushButton("定位")
                open_btn.setObjectName("Ghost")
                open_btn.setFixedHeight(26)
                open_btn.clicked.connect(
                    lambda _checked=False, data=item: self._open_path(data.get("path"))
                )
                layout.addWidget(open_btn, 0, Qt.AlignCenter)
            else:
                install_btn = QPushButton("下载")
                install_btn.setObjectName("Primary")
                install_btn.setFixedHeight(26)
                install_btn.clicked.connect(
                    lambda _checked=False, data=item: self._install_module(data)
                )
                layout.addWidget(install_btn, 0, Qt.AlignCenter)
            table.setCellWidget(row, 4, actions)

    def _rebuild_versions(self) -> None:
        previous = self._version_combo.currentData()
        versions = scan_installed_versions(self.ctx.config.game_path)
        self._version_combo.blockSignals(True)
        self._version_combo.clear()
        for version in versions:
            text = version.id + (f"（{version.loader}）" if version.loader else "")
            self._version_combo.addItem(text, version.id)
        if previous:
            index = self._version_combo.findData(previous)
            if index >= 0:
                self._version_combo.setCurrentIndex(index)
        self._version_combo.blockSignals(False)
        has_version = self._version_combo.count() > 0
        self._version_combo.setEnabled(has_version)
        self._check_btn.setEnabled(has_version)
        if not has_version:
            self._check_status.setText("未检测到已安装的版本，请先在「下载安装」中安装游戏。")

    def _open_path(self, path: str) -> None:
        if not str(path or "").strip():
            self.ctx.bus.toast.emit("当前平台不支持该模块，无法定位目录。")
            return
        target = Path(str(path))
        if not target.exists():
            self.ctx.bus.toast.emit("目录尚不存在，请先下载该模块。")
            return
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        folder = target if target.is_dir() else target.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    # ------------------------------------------------------------------
    def _install_module(self, item: dict) -> None:
        if str(item.get("action")) != "install":
            self.ctx.bus.toast.emit("该依赖需在对应页面安装，请点击「前往」。")
            return
        if bool(item.get("installed")):
            self.ctx.bus.toast.emit("该模块已安装，无需重复下载。")
            return
        module_id = str(item.get("id") or "")
        cancel_event = threading.Event()

        def factory(task) -> QThread:
            # 重试时复用同一事件，先清掉上一次取消留下的标记
            cancel_event.clear()
            task.cancel = cancel_event.set
            worker = ModuleInstallWorker(module_id, self.ctx.config, cancel_event, self)
            worker.progress.connect(
                lambda ratio, detail, tid=task.id: self.ctx.downloads.update(
                    tid, percent=ratio, status="安装中", stage=detail
                )
            )
            worker.logged.connect(self.ctx.bus.log.emit)
            worker.done.connect(
                lambda mid, path, tid=task.id: self._on_module_done(tid, mid, path)
            )
            worker.failed.connect(
                lambda mid, message, tid=task.id: self._on_task_failed(tid, message)
            )
            worker.finished.connect(lambda w=worker: self._discard_worker(w))
            self._workers.append(worker)
            return worker

        self.ctx.downloads.submit(
            kind="第三方模块",
            name=str(item.get("name") or module_id),
            factory=factory,
            cancel=cancel_event.set,
            rebuild=factory,
            target_dir=str(item.get("path") or ""),
            detail=f"{item.get('license') or ''} · 仅为方便用户提供",
        )
        self.ctx.bus.toast.emit(f"已加入下载中心：{item.get('name') or module_id}")

    def _on_module_done(self, task_id: str, module_id: str, path: str) -> None:
        self.ctx.downloads.finish(task_id, ok=True)
        self.ctx.bus.log.emit(f"[依赖] {module_id} 安装完成：{path}")
        self.ctx.bus.toast.emit("第三方模块已安装完成。")
        self._rebuild_modules()

    # ------------------------------------------------------------------
    def _check(self) -> None:
        version_id = self._version_combo.currentData()
        if not version_id:
            self.ctx.bus.toast.emit("请先选择要检查的游戏版本。")
            return
        if self._check_worker is not None and self._check_worker.isRunning():
            self.ctx.bus.toast.emit("正在检查，请稍候。")
            return
        self._check_key = str(version_id)
        self._check_btn.setEnabled(False)
        self._check_status.setText(f"正在检查 {version_id} 的依赖…")
        self._result_table.setRowCount(0)

        worker = CheckWorker(self.ctx.config, str(version_id), self.ctx.javas, self)
        self._check_worker = worker
        worker.done.connect(self._on_check_done)
        worker.finished.connect(lambda: setattr(self, "_check_worker", None))
        worker.start()

    def _install_missing_mods(self) -> None:
        version_id = self._version_combo.currentData()
        if not version_id:
            self.ctx.bus.toast.emit("请先选择要补全的游戏版本。")
            return
        if getattr(self, "_fix_mod_worker", None) is not None and self._fix_mod_worker.isRunning():
            self.ctx.bus.toast.emit("正在补全前置，请稍候。")
            return
        game_version = ""
        try:
            merged = load_version(self.ctx.config.game_path, str(version_id))
            game_version = str(merged.jar_id or "")
        except Exception:
            game_version = ""
        low = str(version_id).lower()
        loader = next(
            (name for name in ("neoforge", "forge", "fabric", "quilt") if name in low), ""
        )
        self._fix_mods_btn.setEnabled(False)
        self._check_status.setText("正在检测并补全缺失的 Mod 前置…")
        worker = MissingModWorker(self.ctx, str(version_id), game_version, loader, self)
        self._fix_mod_worker = worker
        worker.logged.connect(self.ctx.bus.log_line.emit)
        worker.failed.connect(lambda text: self._check_status.setText(f"补全失败：{text}"))
        worker.done.connect(self._on_missing_mods_done)
        worker.finished.connect(self._on_missing_mods_finished)
        worker.start()

    def _on_missing_mods_finished(self) -> None:
        self._fix_mods_btn.setEnabled(True)
        self._fix_mod_worker = None

    def _on_missing_mods_done(self, installed: list) -> None:
        names = [str(name) for name in (installed or [])]
        if not names:
            self._check_status.setText("没有发现缺失前置，或未能找到兼容版本（详见日志）。")
            return
        self._check_status.setText(f"已补全 {len(names)} 个前置：{', '.join(names[:4])}")
        self.ctx.bus.toast.emit(f"已补全 {len(names)} 个缺失前置。")

    def _on_check_done(self, version_id: str, merged, items) -> None:
        if version_id != self._check_key:
            return
        self._check_btn.setEnabled(True)
        rows: list[MissingItem] = list(items or [])
        table = self._result_table
        table.setRowCount(0)
        if merged is None:
            self._check_status.setText("版本无法读取，无法检查依赖")
            return
        elif not rows:
            table.insertRow(0)
            ok_item = QTableWidgetItem("全部依赖")
            ok_item.setForeground(Qt.GlobalColor.green)
            table.setItem(0, 0, ok_item)
            status = QTableWidgetItem("完整")
            status.setTextAlignment(Qt.AlignCenter)
            status.setForeground(Qt.GlobalColor.green)
            table.setItem(0, 1, status)
            table.setItem(0, 2, QTableWidgetItem("Java、客户端、依赖库与资源均未缺失"))
            self._check_status.setText(f"{version_id} 依赖完整")
            return
        else:
            for row, item in enumerate(rows):
                table.insertRow(row)
                table.setItem(row, 0, QTableWidgetItem(item.name))
                status = QTableWidgetItem("缺失")
                status.setTextAlignment(Qt.AlignCenter)
                status.setForeground(Qt.GlobalColor.red)
                table.setItem(row, 1, status)
                table.setItem(row, 2, QTableWidgetItem(item.detail))
            self._check_status.setText(
                f"{version_id} 检查完成：{len(rows)} 项缺失"
            )

        names = "\n".join(f"· {item.name}" for item in rows)
        answer = QMessageBox.question(
            self,
            "检测到缺失依赖",
            f"{version_id} 缺少以下依赖：\n{names}\n\n"
            "是否现在自动补全？补全任务会显示在下载中心，可暂停或取消。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            return
        self._start_repairs(version_id, merged, rows)

    # ------------------------------------------------------------------
    def _start_repairs(self, version_id: str, merged, items: list[MissingItem]) -> None:
        java_major = required_java(merged) if merged is not None else 21
        need_java = any(item.is_java for item in items)
        file_kinds = {item.kind for item in items}
        need_files = bool(file_kinds & set(_FILE_KINDS))

        submitted = 0
        if need_java:
            self._submit_java(java_major)
            submitted += 1
        if need_files:
            self._submit_repair(version_id)
            submitted += 1
        if submitted:
            self.ctx.bus.toast.emit(
                f"已加入下载中心，正在静默补全 {version_id} 的缺失依赖。"
            )
            self._check_status.setText(
                f"{version_id}：补全任务已加入下载中心（{summarize_missing(items)}）"
            )

    def _submit_java(self, major: int) -> None:
        cancel_event = threading.Event()
        pause_event = threading.Event()

        def factory(task) -> QThread:
            cancel_event.clear()
            pause_event.clear()
            task.cancel = cancel_event.set
            task.pause_event = pause_event
            worker = JavaInstallWorker(
                major, DATA_DIR / "runtime", cancel_event, pause_event, self
            )
            worker.progress.connect(
                lambda percent, detail, tid=task.id: self.ctx.downloads.update(
                    tid, percent=percent, status="下载中", stage=detail
                )
            )
            worker.logged.connect(self.ctx.bus.log.emit)
            worker.done.connect(
                lambda info, tid=task.id: self._on_java_done(tid, info)
            )
            worker.failed.connect(
                lambda message, tid=task.id: self._on_task_failed(tid, message)
            )
            worker.finished.connect(lambda w=worker: self._discard_worker(w))
            self._workers.append(worker)
            return worker

        self.ctx.downloads.submit(
            kind="Java",
            name=f"Java {major}（依赖补全）",
            factory=factory,
            cancel=cancel_event.set,
            pause=pause_event,
            rebuild=factory,
            target_dir=str(DATA_DIR / "runtime"),
            detail="Adoptium JRE · 自动补全缺失 Java",
        )

    def _submit_repair(self, version_id: str) -> None:
        cancel_event = threading.Event()
        game_dir = self.ctx.config.game_path

        def factory(task) -> QThread:
            cancel_event.clear()
            task.cancel = cancel_event.set
            worker = VersionRepairWorker(
                self.ctx.config.with_game_dir(game_dir),
                self.ctx.sources,
                version_id,
                cancel_event,
                self,
            )
            worker.progress.connect(
                lambda percent, detail, tid=task.id: self.ctx.downloads.update(
                    tid, percent=percent, status="补全中", stage=detail
                )
            )
            worker.logged.connect(self.ctx.bus.log.emit)
            worker.done.connect(
                lambda vid, tid=task.id: self._on_repair_done(tid, vid)
            )
            worker.failed.connect(
                lambda message, tid=task.id: self._on_task_failed(tid, message)
            )
            worker.finished.connect(lambda w=worker: self._discard_worker(w))
            self._workers.append(worker)
            return worker

        self.ctx.downloads.submit(
            kind="游戏文件",
            name=f"{version_id} 缺失文件补全",
            factory=factory,
            cancel=cancel_event.set,
            rebuild=factory,
            target_dir=str(game_dir),
            detail="客户端 / 依赖库 / 资源自动补全",
        )

    def _on_java_done(self, task_id: str, info) -> None:
        self.ctx.downloads.finish(task_id, ok=True)
        if info is not None:
            if all(java_key(j.path) != java_key(info.path) for j in self.ctx.javas):
                self.ctx.javas.append(info)
            self.ctx.bus.javas_changed.emit()
        self.ctx.bus.log.emit("[依赖] 缺失 Java 已自动安装完成")
        self.ctx.bus.toast.emit("缺失的 Java 已自动补全。")

    def _on_repair_done(self, task_id: str, version_id: str) -> None:
        self.ctx.downloads.finish(task_id, ok=True)
        self.ctx.bus.log.emit(f"[依赖] {version_id} 缺失文件补全完成")
        self.ctx.bus.toast.emit(f"{version_id} 缺失文件已补全，可重新检查或直接启动。")
        self.ctx.bus.versions_changed.emit()

    def _on_task_failed(self, task_id: str, message: str) -> None:
        self.ctx.downloads.finish(task_id, ok=False, message=message)
        self.ctx.bus.log.emit(f"[依赖] 补全失败：{message}")
        self.ctx.bus.toast.emit(f"依赖补全失败：{message}")

    def _discard_worker(self, worker: QThread) -> None:
        if worker in self._workers:
            self._workers.remove(worker)
        worker.deleteLater()

    # ------------------------------------------------------------------
    def shutdown(self) -> None:
        for worker in list(self._workers):
            cancel_event = getattr(worker, "cancel_event", None)
            if cancel_event is not None:
                try:
                    cancel_event.set()
                except Exception:  # noqa: BLE001
                    pass
        for worker in list(self._workers):
            wait_thread(worker, 2000)
        self._workers.clear()
        if self._check_worker is not None:
            wait_thread(self._check_worker, 2000)
            self._check_worker = None
