"""内容中心：封面卡片浏览、项目详情、版本分组与安装（类似 HMCL 内容中心）。"""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME
from ..config import INSTANCES_DIR, write_instance_manifest
from ..content import (
    PROJECT_TYPES,
    SOURCE_LABELS,
    ContentClient,
    ContentError,
    ContentProject,
    ContentVersion,
    is_version_compatible,
    pick_best_version,
)
from ..context import AppContext, wait_thread
from ..installer import GameInstaller
from ..java import pick_java
from ..modloader import install_loader, java_for_mc
from ..version import scan_installed_versions
from .covers import CoverLoader, make_placeholder
from .widgets import Badge, Card, page_header

TYPE_BADGE_KIND = {
    "mod": "blue",
    "modpack": "orange",
    "resourcepack": "green",
    "shader": "gray",
}

LOADER_LABELS = {
    "forge": "Forge",
    "neoforge": "NeoForge",
    "fabric": "Fabric",
    "quilt": "Quilt",
    "liteloader": "LiteLoader",
    "optifine": "OptiFine",
}

LOADER_BADGE_KIND = {
    "forge": "orange",
    "fabric": "green",
    "neoforge": "blue",
    "quilt": "green",
}

INSTALLED_LOADER_KEYS = {
    "Forge": "forge",
    "NeoForge": "neoforge",
    "Fabric": "fabric",
    "Quilt": "quilt",
    "OptiFine": "optifine",
    "LiteLoader": "liteloader",
    "原版": "",
    "损坏": "",
}

_TYPE_FOLDERS = {"mod": "mods", "resourcepack": "resourcepacks", "shader": "shaderpacks"}

_LOADER_WORDS = {
    "forge",
    "neoforge",
    "fabric",
    "quilt",
    "liteloader",
    "optifine",
    "optifabric",
    "minecraft",
}


def _fmt_count(value: int) -> str:
    number = int(value or 0)
    if number >= 1_000_000:
        return f"{number / 1_000_000:.1f}M"
    if number >= 1000:
        return f"{number / 1000:.1f}k"
    return str(number)


def _fmt_size(value: int) -> str:
    size = float(value or 0)
    if size <= 0:
        return "-"
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return "-"


def _natural_key(text: str) -> tuple:
    parts = re.split(r"[.\-+_ ]", (text or "").strip().lower())
    key: list[tuple[int, object]] = []
    for part in parts:
        if part.isdigit():
            key.append((0, int(part)))
        elif part:
            key.append((1, part))
    return tuple(key)


def _is_mc_version(text: str) -> bool:
    return bool(re.fullmatch(r"\d+\.\d+(?:\.\d+)?", (text or "").strip()))


def _main_mc_version(version: ContentVersion) -> str:
    """取 game_versions 中最新的一个 Minecraft 版本。"""
    candidates = [str(v).strip() for v in version.game_versions if _is_mc_version(v)]
    if not candidates:
        candidates = [
            str(v).strip()
            for v in version.game_versions
            if str(v).strip() and str(v).strip().lower() not in _LOADER_WORDS
        ]
    if not candidates:
        return ""
    return max(candidates, key=_natural_key)


def _version_loader_key(version: ContentVersion) -> str:
    for loader in version.loaders:
        key = str(loader).strip().lower()
        if key and key not in ("minecraft",):
            return key
    return ""


def _version_loader_text(version: ContentVersion) -> str:
    key = _version_loader_key(version)
    if not key:
        return "通用"
    return LOADER_LABELS.get(key, key.upper())


def _rounded_pixmap(pixmap: QPixmap | None, size: QSize, radius: int = 10) -> QPixmap:
    """等比裁剪填充并做圆角。"""
    if pixmap is None or pixmap.isNull():
        return make_placeholder(size, "")
    scaled = pixmap.scaled(size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    x = max(0, (scaled.width() - size.width()) // 2)
    y = max(0, (scaled.height() - size.height()) // 2)
    cropped = scaled.copy(x, y, size.width(), size.height())
    result = QPixmap(size)
    result.fill(Qt.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.Antialiasing, True)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size.width(), size.height()), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, cropped)
    painter.end()
    return result


def _installed_mc_version(version) -> str:
    text = f"{version.base_version or ''} {version.id or ''}"
    match = re.search(r"(\d+\.\d+(?:\.\d+)?)", text)
    return match.group(1) if match else ""


def scan_targets(ctx: AppContext) -> list[dict]:
    """扫描所有实例及其已安装版本，作为安装目标。"""
    targets: list[dict] = []
    for instance in ctx.config.instance_list():
        root = Path(os.path.expandvars(instance.game_dir)).expanduser()
        try:
            installed = scan_installed_versions(root)
        except OSError:
            installed = []
        if not installed:
            targets.append(
                {
                    "label": f"{instance.name} · 未检测到已安装版本（按项目推断）",
                    "kind": "instance",
                    "instance_name": instance.name,
                    "game_dir": str(root),
                    "version_id": "",
                    "mc_version": "",
                    "loader": "",
                }
            )
            continue
        for version in installed:
            label = f"{instance.name} · {version.id}"
            if version.loader:
                label += f"（{version.loader}）"
            targets.append(
                {
                    "label": label,
                    "kind": "instance",
                    "instance_name": instance.name,
                    "game_dir": str(root),
                    "version_id": version.id,
                    "mc_version": _installed_mc_version(version),
                    "loader": INSTALLED_LOADER_KEYS.get(version.loader, ""),
                }
            )
    global_dir = ctx.config.game_path
    targets.append(
        {
            "label": f"全局目录（不指定版本）· {global_dir}",
            "kind": "global",
            "instance_name": "全局目录",
            "game_dir": str(global_dir),
            "version_id": "",
            "mc_version": "",
            "loader": "",
        }
    )
    return targets


class SearchWorker(QThread):
    ok = Signal(list)
    failed = Signal(str)

    def __init__(
        self,
        client: ContentClient,
        source: str,
        project_type: str,
        query: str,
        game_version: str,
        loader: str,
        offset: int,
        limit: int,
        parent=None,
    ):
        super().__init__(parent)
        self.client = client
        self.source = source
        self.project_type = project_type
        self.query = query
        self.game_version = game_version
        self.loader = loader
        self.offset = offset
        self.limit = limit

    def run(self) -> None:
        try:
            projects = self.client.search(
                self.source,
                self.project_type,
                self.query,
                self.game_version,
                self.loader,
                self.offset,
                self.limit,
            )
            self.ok.emit(projects)
        except ContentError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"搜索失败：{exc}")


class VersionsWorker(QThread):
    """获取项目文件列表，可按 Minecraft 版本过滤（懒加载）。"""

    ok = Signal(list)
    failed = Signal(str)

    def __init__(
        self,
        client: ContentClient,
        project: ContentProject,
        game_version: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.client = client
        self.project = project
        self.game_version = game_version

    def run(self) -> None:
        try:
            versions = self.client.versions(
                self.project.source, self.project.id, self.game_version
            )
            self.ok.emit(versions)
        except ContentError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"获取版本失败：{exc}")


class ProjectVersionsWorker(QThread):
    """轻量获取项目支持的 Minecraft 版本列表。"""

    ok = Signal(list)
    failed = Signal(str)

    def __init__(self, client: ContentClient, project: ContentProject, parent=None):
        super().__init__(parent)
        self.client = client
        self.project = project

    def run(self) -> None:
        try:
            self.ok.emit(
                self.client.project_game_versions(self.project.source, self.project.id)
            )
        except ContentError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"获取支持的版本失败：{exc}")


class ManifestWorker(QThread):
    ok = Signal(list)

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx

    def run(self) -> None:
        try:
            payload, _name, _cached = self.ctx.sources.get_manifest()
            entries = payload.get("data", {}).get("versions", [])
            releases = [str(v.get("id")) for v in entries if v.get("type") == "release"]
            self.ok.emit(releases)
        except Exception:  # noqa: BLE001 - 清单失败时仅保留“全部版本”
            self.ok.emit([])


class TargetScanWorker(QThread):
    ok = Signal(list)

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx

    def run(self) -> None:
        try:
            self.ok.emit(scan_targets(self.ctx))
        except Exception:  # noqa: BLE001
            self.ok.emit([])


class ContentInstallWorker(QThread):
    progress = Signal(float, str)
    log = Signal(str)
    done = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        ctx: AppContext,
        project: ContentProject,
        version: ContentVersion,
        instance_dir: Path,
        parent=None,
    ):
        super().__init__(parent)
        self.ctx = ctx
        self.project = project
        self.version = version
        self.instance_dir = instance_dir
        self.cancel_event = threading.Event()
        self.pause_event = threading.Event()

    def _emit(self, value: float, detail: str = "") -> None:
        self.progress.emit(max(0.0, min(1.0, value)), detail)

    def run(self) -> None:
        try:
            if self.project.project_type == "modpack":
                self._install_modpack()
            else:
                self._install_single()
        except ContentError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"安装失败：{exc}")

    def _install_single(self) -> None:
        self._emit(0.05, "准备下载…")
        self.instance_dir.mkdir(parents=True, exist_ok=True)
        installed = self.ctx.content.install_content(
            self.project,
            self.version,
            self.instance_dir,
            log=self.log.emit,
            cancel=self.cancel_event,
            pause=self.pause_event,
        )
        self._emit(1.0, "安装完成")
        self.log.emit(f"[完成] 已安装 {len(installed)} 个文件到 {self.instance_dir}")
        self.done.emit(f"{self.project.title} 安装完成。")

    def _install_modpack(self) -> None:
        self._emit(0.02, "下载整合包…")
        zip_path, meta = self.ctx.content.prepare_modpack(
            self.project,
            self.version,
            log=self.log.emit,
            cancel=self.cancel_event,
            pause=self.pause_event,
        )
        self.log.emit(f"[整合包] {meta.name} · MC {meta.mc_version} · {meta.loader or '原版'}")
        if not meta.mc_version:
            raise ContentError("整合包缺少 Minecraft 版本信息。")

        slug_base = re.sub(r"[^\w\-]+", "-", self.project.title.lower()).strip("-")[:36]
        slug = f"{slug_base or 'modpack'}-{self.project.id[:6]}"
        target = INSTANCES_DIR / slug
        target.mkdir(parents=True, exist_ok=True)

        clone = self.ctx.config.with_game_dir(target)
        installer = GameInstaller(
            clone,
            self.ctx.sources,
            progress_cb=lambda p: self._emit(0.05 + p.percent * 0.4, p.detail),
            log_cb=self.log.emit,
            cancel=self.cancel_event,
            pause=self.pause_event,
        )
        if self.cancel_event.is_set():
            raise ContentError("安装已取消。")

        mc_version = meta.mc_version
        version_json = target / "versions" / mc_version / f"{mc_version}.json"
        if not version_json.exists():
            self.log.emit(f"[整合包] 安装基础版本 {mc_version}…")
            payload, _name, _cached = self.ctx.sources.get_manifest()
            entries = payload.get("data", {}).get("versions", [])
            entry = next((v for v in entries if str(v.get("id")) == mc_version), None)
            if entry is None:
                raise ContentError(f"版本清单中找不到 Minecraft {mc_version}。")
            installer.install_version(entry)
        else:
            self.log.emit(f"[整合包] 基础版本 {mc_version} 已存在，跳过。")

        version_id = mc_version
        if meta.loader:
            self._emit(0.47, f"安装 {meta.loader} 加载器…")
            java, warning = pick_java(self.ctx.javas, java_for_mc(mc_version))
            if java is None:
                raise ContentError(
                    f"整合包需要 Java {java_for_mc(mc_version)}，未找到可用 Java。{warning}"
                )
            version_id = install_loader(
                installer,
                meta.loader,
                mc_version,
                meta.loader_version,
                java_path=java.path,
                log=self.log.emit,
                cancel=self.cancel_event,
            )
            self.log.emit(f"[整合包] 加载器版本：{version_id}")
        self._emit(0.6, "下载整合包内容…")
        self.ctx.content.install_modpack_files(
            zip_path,
            meta,
            target,
            log=self.log.emit,
            cancel=self.cancel_event,
            progress=lambda value, detail: self._emit(0.6 + value * 0.35, detail),
            pause=self.pause_event,
        )
        instance = self.ctx.config.add_instance(
            meta.name or self.project.title,
            str(target),
            version_id=version_id,
            loader=meta.loader,
            mc_version=meta.mc_version,
            modpack=self.project.title,
            loader_version=meta.loader_version,
        )
        write_instance_manifest(instance, target)
        self.ctx.config.select_instance(instance.id)
        self.ctx.config.save()
        self.ctx.bus.instances_changed.emit()
        self._emit(1.0, "整合包安装完成")
        self.log.emit(f"[完成] 整合包已安装为实例「{instance.name}」，返回主页即可启动。")
        self.done.emit(f"整合包「{instance.name}」安装完成，已切换到该实例。")


class ProjectCard(QFrame):
    """可点击的项目封面卡片。"""

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ProjectCard")
        self.setAttribute(Qt.WA_Hover, True)
        self.setCursor(Qt.PointingHandCursor)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class InstallDialog(QDialog):
    """安装确认：选择目标版本并自动匹配文件，可手动更换。"""

    def __init__(
        self,
        ctx: AppContext,
        project: ContentProject,
        versions: list[ContentVersion],
        targets: list[dict],
        parent: QWidget | None = None,
        preferred: str = "",
    ):
        super().__init__(parent)
        self.ctx = ctx
        self.project = project
        self.versions = [v for v in versions if v.primary_file is not None]
        self.targets = list(targets) if targets else scan_targets(ctx)
        self.selected_version: ContentVersion | None = None
        self.selected_target: dict | None = None
        self._preferred_id = preferred
        self._version_by_id = {v.id: v for v in self.versions}

        self.setObjectName("Root")
        self.setWindowTitle(f"安装 {project.title}")
        self.setModal(True)
        self.setMinimumWidth(580)
        self._build()
        self._populate()
        self._auto_match()
        self._update_dir()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        title = QLabel(self.project.title)
        title.setObjectName("CardTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        badges = QHBoxLayout()
        badges.setSpacing(6)
        badges.addWidget(Badge(self.project.source_label, "blue" if self.project.source == "modrinth" else "orange"))
        badges.addWidget(Badge(self.project.type_label, TYPE_BADGE_KIND.get(self.project.project_type, "gray")))
        if self.project.author:
            badges.addWidget(Badge(self.project.author, "gray"))
        badges.addStretch(1)
        layout.addLayout(badges)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)
        target_caption = QLabel("目标版本")
        target_caption.setObjectName("Muted")
        form.addWidget(target_caption, 0, 0, Qt.AlignTop)
        self.target_combo = QComboBox()
        self.target_combo.setMinimumWidth(440)
        form.addWidget(self.target_combo, 0, 1)
        file_caption = QLabel("文件版本")
        file_caption.setObjectName("Muted")
        form.addWidget(file_caption, 1, 0, Qt.AlignTop)
        self.file_combo = QComboBox()
        form.addWidget(self.file_combo, 1, 1)
        form.setColumnStretch(1, 1)
        layout.addLayout(form)

        self.match_label = QLabel("")
        self.match_label.setObjectName("Muted")
        self.match_label.setWordWrap(True)
        layout.addWidget(self.match_label)

        self.dir_label = QLabel("")
        self.dir_label.setObjectName("Tiny")
        self.dir_label.setWordWrap(True)
        layout.addWidget(self.dir_label)

        if self.project.project_type == "modpack":
            hint = QLabel("整合包会新建独立实例，并自动安装基础版本与加载器。")
            hint.setObjectName("Tiny")
            hint.setWordWrap(True)
            layout.addWidget(hint)

        layout.addStretch(1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel_button = QPushButton("取消")
        cancel_button.setObjectName("Ghost")
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(cancel_button)
        self.confirm_button = QPushButton("确认安装")
        self.confirm_button.setObjectName("Primary")
        self.confirm_button.clicked.connect(self._accept)
        buttons.addWidget(self.confirm_button)
        layout.addLayout(buttons)

    def _populate(self) -> None:
        for target in self.targets:
            self.target_combo.addItem(str(target.get("label") or "未命名目标"), target)
        for version in self.versions:
            file = version.primary_file
            filename = file.filename if file else (version.name or version.version_number)
            index = self.file_combo.count()
            self.file_combo.addItem(filename, version.id)
            mc = _main_mc_version(version) or "不限"
            self.file_combo.setItemData(
                index,
                f"{version.name or version.version_number} · MC {mc} · {_version_loader_text(version)}",
                Qt.ToolTipRole,
            )
        self.target_combo.currentIndexChanged.connect(lambda _i: self._auto_match())
        self.file_combo.currentIndexChanged.connect(lambda _i: self._update_match(manual=True))
        self.target_combo.currentIndexChanged.connect(lambda _i: self._update_dir())

    # ------------------------------------------------------------------
    def _current_version(self) -> ContentVersion | None:
        version_id = str(self.file_combo.currentData() or "")
        return self._version_by_id.get(version_id)

    def _auto_match(self) -> None:
        target = self.target_combo.currentData()
        if not isinstance(target, dict):
            return
        if self._preferred_id:
            preferred = self._version_by_id.get(self._preferred_id)
            self._preferred_id = ""
            if preferred is not None:
                index = self.file_combo.findData(preferred.id)
                if index >= 0:
                    self.file_combo.blockSignals(True)
                    self.file_combo.setCurrentIndex(index)
                    self.file_combo.blockSignals(False)
                self.confirm_button.setEnabled(True)
                self._update_match(manual=True)
                return
        mc = str(target.get("mc_version") or "")
        loader = str(target.get("loader") or "")
        keyword = self.project.slug or self.project.title
        candidates = [
            version for version in self.versions if is_version_compatible(version, mc, loader)
        ]
        self._match_incomplete = not candidates
        if not candidates:
            candidates = self.versions
        best = pick_best_version(candidates, mc, loader, keyword)
        if best is None and candidates:
            best = candidates[0]
        if best is None:
            self.match_label.setText("该项目没有可安装的文件。")
            self.confirm_button.setEnabled(False)
            return
        self.confirm_button.setEnabled(True)
        index = self.file_combo.findData(best.id)
        if index >= 0:
            self.file_combo.blockSignals(True)
            self.file_combo.setCurrentIndex(index)
            self.file_combo.blockSignals(False)
        self._update_match(manual=False)

    def _update_match(self, manual: bool) -> None:
        version = self._current_version()
        target = self.target_combo.currentData()
        if version is None or version.primary_file is None:
            self.match_label.setText("没有可安装的文件。")
            self.confirm_button.setEnabled(False)
            return
        self.confirm_button.setEnabled(True)
        mc = _main_mc_version(version) or "不限"
        prefix = "已选择" if manual else "已自动匹配"
        mc_wanted = str(target.get("mc_version") or "") if isinstance(target, dict) else ""
        loader_wanted = str(target.get("loader") or "") if isinstance(target, dict) else ""
        note = ""
        if mc_wanted and not is_version_compatible(version, mc_wanted, loader_wanted):
            note = "（注意：该文件可能不兼容目标版本或加载器）"
        self.match_label.setText(
            f"{prefix}：{version.primary_file.filename}（MC {mc} · {_version_loader_text(version)}）{note}"
        )

    def _update_dir(self) -> None:
        target = self.target_combo.currentData()
        if not isinstance(target, dict):
            self.dir_label.setText("")
            return
        if self.project.project_type == "modpack":
            self.dir_label.setText(f"新建实例目录：{INSTANCES_DIR}")
            return
        folder = _TYPE_FOLDERS.get(self.project.project_type, "mods")
        root = Path(str(target.get("game_dir") or ""))
        self.dir_label.setText(f"下载目标：{root / folder}")

    def _accept(self) -> None:
        version = self._current_version()
        target = self.target_combo.currentData()
        if version is None:
            QMessageBox.information(self, APP_NAME, "请选择要安装的文件版本。")
            return
        if not isinstance(target, dict):
            QMessageBox.information(self, APP_NAME, "请选择安装目标。")
            return
        self.selected_version = version
        self.selected_target = target
        self.accept()


class ContentPage(QWidget):
    LIMIT = 24
    COLUMNS = 4
    COVER_SIZE = 168

    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self.client = ctx.content
        self._covers = CoverLoader(self)
        self._projects: list[ContentProject] = []
        self._versions: list[ContentVersion] = []
        self._project_mc_versions: list[str] = []
        self._active_mc = ""
        self._targets: list[dict] = []
        self._detail_project: ContentProject | None = None
        self._offset = 0
        self._generation = 0
        self._detail_generation = 0
        self._workers: list[QThread] = []
        self._install_task_id = ""
        self._install_worker: ContentInstallWorker | None = None
        self._install_pause = threading.Event()
        self._pending_install: tuple[ContentProject, ContentVersion, Path] | None = None
        self._cancel_requested = False
        self._target_worker: TargetScanWorker | None = None
        self._render_actions: list[tuple] = []
        self._render_index = 0
        self._render_gen = -1
        self._progress_views: list[dict] = []
        self._build()
        self._start_manifest()
        self._search(reset=True)
        self.refresh()

    # ------------------------------------------------------------------
    # 构建界面
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.stack = QStackedWidget()
        self.list_page = self._build_list_page()
        self.detail_page = self._build_detail_page()
        self.stack.addWidget(self.list_page)
        self.stack.addWidget(self.detail_page)
        outer.addWidget(self.stack)

    def _build_list_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 20, 26, 20)
        layout.setSpacing(14)

        header, _header_layout = page_header(
            "内容中心", "Modrinth / CurseForge 的 Mod、整合包、资源包、光影包"
        )
        layout.addWidget(header)

        filters = Card(margins=14, spacing=10)
        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)
        self.source_combo = QComboBox()
        for key, label in SOURCE_LABELS.items():
            self.source_combo.addItem(label, key)
        self.type_combo = QComboBox()
        for key, label in PROJECT_TYPES.items():
            self.type_combo.addItem(label, key)
        self.version_combo = QComboBox()
        self.version_combo.addItem("全部版本", "")
        self.loader_combo = QComboBox()
        self.loader_combo.addItem("全部加载器", "")
        for key, label in (
            ("forge", "Forge"),
            ("neoforge", "NeoForge"),
            ("fabric", "Fabric"),
            ("quilt", "Quilt"),
        ):
            self.loader_combo.addItem(label, key)
        for caption_text, widget, width in (
            ("来源", self.source_combo, 120),
            ("类型", self.type_combo, 110),
            ("Minecraft 版本", self.version_combo, 150),
            ("加载器", self.loader_combo, 120),
        ):
            caption = QLabel(caption_text)
            caption.setObjectName("Muted")
            filter_row.addWidget(caption)
            widget.setFixedWidth(width)
            filter_row.addWidget(widget)
        filter_row.addStretch(1)
        filters.body.addLayout(filter_row)

        search_row = QHBoxLayout()
        search_row.setSpacing(10)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索名称、关键词…")
        self.search_edit.returnPressed.connect(lambda: self._search(reset=True))
        search_row.addWidget(self.search_edit, 1)
        self.search_button = QPushButton("搜索")
        self.search_button.setObjectName("Primary")
        self.search_button.clicked.connect(lambda: self._search(reset=True))
        search_row.addWidget(self.search_button)
        filters.body.addLayout(search_row)
        layout.addWidget(filters)

        result_card = Card(margins=14, spacing=10)
        status_row = QHBoxLayout()
        status_row.setSpacing(10)
        self.list_status = QLabel("正在加载内容…")
        self.list_status.setObjectName("Muted")
        status_row.addWidget(self.list_status)
        status_row.addStretch(1)
        self.result_count = QLabel("")
        self.result_count.setObjectName("Tiny")
        status_row.addWidget(self.result_count)
        result_card.body.addLayout(status_row)

        self.results_scroll = QScrollArea()
        self.results_scroll.setWidgetResizable(True)
        self.results_host = QWidget()
        host_layout = QVBoxLayout(self.results_host)
        host_layout.setContentsMargins(0, 0, 4, 0)
        host_layout.setSpacing(0)
        self.results_grid = QGridLayout()
        self.results_grid.setHorizontalSpacing(14)
        self.results_grid.setVerticalSpacing(14)
        for column in range(self.COLUMNS):
            self.results_grid.setColumnStretch(column, 1)
        host_layout.addLayout(self.results_grid)
        host_layout.addStretch(1)
        self.results_scroll.setWidget(self.results_host)
        result_card.body.addWidget(self.results_scroll, 1)

        more_row = QHBoxLayout()
        more_row.setSpacing(10)
        self.more_button = QPushButton("加载更多")
        self.more_button.setObjectName("Ghost")
        self.more_button.setEnabled(False)
        self.more_button.clicked.connect(lambda: self._search(reset=False))
        more_row.addWidget(self.more_button)
        more_row.addStretch(1)
        self.load_hint = QLabel("")
        self.load_hint.setObjectName("Tiny")
        more_row.addWidget(self.load_hint)
        result_card.body.addLayout(more_row)
        layout.addWidget(result_card, 1)
        layout.addWidget(self._build_progress_card())

        self.source_combo.currentIndexChanged.connect(lambda _i: self._search(reset=True))
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        self.version_combo.currentIndexChanged.connect(lambda _i: self._search(reset=True))
        self.loader_combo.currentIndexChanged.connect(lambda _i: self._search(reset=True))
        return page

    def _build_detail_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 20, 26, 20)
        layout.setSpacing(12)

        back = QPushButton("返回内容列表")
        back.setObjectName("Ghost")
        back.clicked.connect(self._back_to_list)
        layout.addWidget(back, 0, Qt.AlignLeft)

        head = Card(margins=18, spacing=10)
        top = QHBoxLayout()
        top.setSpacing(14)
        self.detail_cover = QLabel()
        self.detail_cover.setObjectName("Cover")
        self.detail_cover.setFixedSize(120, 120)
        self.detail_cover.setAlignment(Qt.AlignCenter)
        top.addWidget(self.detail_cover, 0, Qt.AlignTop)

        info = QVBoxLayout()
        info.setSpacing(6)
        self.detail_title = QLabel("项目详情")
        self.detail_title.setObjectName("DetailTitle")
        self.detail_title.setWordWrap(True)
        info.addWidget(self.detail_title)
        self.detail_badge_layout = QHBoxLayout()
        self.detail_badge_layout.setSpacing(6)
        info.addLayout(self.detail_badge_layout)
        self.detail_desc = QLabel("")
        self.detail_desc.setObjectName("Muted")
        self.detail_desc.setWordWrap(True)
        self.detail_desc.setMaximumHeight(58)
        info.addWidget(self.detail_desc)
        self.detail_count = QLabel("正在获取文件列表…")
        self.detail_count.setObjectName("Stat")
        info.addWidget(self.detail_count)
        info.addStretch(1)
        top.addLayout(info, 1)

        self.detail_site = QPushButton("在浏览器打开")
        self.detail_site.setObjectName("Chip")
        self.detail_site.setEnabled(False)
        self.detail_site.clicked.connect(self._open_project_page)
        top.addWidget(self.detail_site, 0, Qt.AlignTop)
        head.body.addLayout(top)
        layout.addWidget(head)

        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.versions_host = QWidget()
        self.versions_layout = QVBoxLayout(self.versions_host)
        self.versions_layout.setContentsMargins(2, 2, 4, 2)
        self.versions_layout.setSpacing(8)
        self.detail_scroll.setWidget(self.versions_host)
        layout.addWidget(self.detail_scroll, 1)
        layout.addWidget(self._build_progress_card())
        return page

    def _build_progress_card(self) -> Card:
        card = Card(margins=14, spacing=8)
        row = QHBoxLayout()
        row.setSpacing(10)
        label = QLabel("就绪")
        label.setObjectName("Muted")
        row.addWidget(label, 1)
        bar = QProgressBar()
        bar.setRange(0, 1000)
        bar.setValue(0)
        bar.setFixedWidth(240)
        row.addWidget(bar)
        cancel = QPushButton("取消")
        cancel.setObjectName("Ghost")
        cancel.clicked.connect(self._cancel_install)
        row.addWidget(cancel)
        card.body.addLayout(row)
        card.setVisible(False)
        self._progress_views.append({"card": card, "label": label, "bar": bar, "button": cancel})
        return card

    # ------------------------------------------------------------------
    # 异步任务管理
    def _track(self, worker: QThread) -> None:
        self._workers.append(worker)
        worker.finished.connect(lambda w=worker: self._forget_worker(w))

    def _forget_worker(self, worker: QThread) -> None:
        try:
            self._workers.remove(worker)
        except ValueError:
            pass

    def _start_manifest(self) -> None:
        worker = ManifestWorker(self.ctx, self)
        worker.ok.connect(self._on_manifest)
        self._track(worker)
        worker.start()

    def _on_manifest(self, versions: list) -> None:
        if not versions:
            return
        blocked = self.version_combo.blockSignals(True)
        try:
            existing = {
                str(self.version_combo.itemData(i) or "")
                for i in range(self.version_combo.count())
            }
            for version in versions:
                if version not in existing:
                    self.version_combo.addItem(version, version)
        finally:
            self.version_combo.blockSignals(blocked)

    # ------------------------------------------------------------------
    # 搜索与卡片列表
    def _on_type_changed(self, _index: int) -> None:
        project_type = str(self.type_combo.currentData() or "mod")
        needs_loader = project_type in ("mod", "modpack")
        blocked = self.loader_combo.blockSignals(True)
        self.loader_combo.setEnabled(needs_loader)
        if not needs_loader:
            self.loader_combo.setCurrentIndex(0)
        self.loader_combo.blockSignals(blocked)
        self._search(reset=True)

    def _filters(self) -> tuple[str, str, str, str]:
        return (
            str(self.source_combo.currentData() or "modrinth"),
            str(self.type_combo.currentData() or "mod"),
            self.search_edit.text().strip(),
            str(self.version_combo.currentData() or ""),
        )

    def _search(self, reset: bool) -> None:
        source, project_type, query, game_version = self._filters()
        loader = str(self.loader_combo.currentData() or "") if self.loader_combo.isEnabled() else ""
        if reset:
            self._generation += 1
            self._offset = 0
            self._projects = []
            self._clear_results()
            self.result_count.setText("")
            self.more_button.setEnabled(False)
            self.load_hint.setText("")
        generation = self._generation
        self.search_button.setEnabled(False)
        self.more_button.setEnabled(False)
        self.list_status.setText(f"正在搜索 {SOURCE_LABELS.get(source, source)}…")
        worker = SearchWorker(
            self.client,
            source,
            project_type,
            query,
            game_version,
            loader,
            self._offset,
            self.LIMIT,
            self,
        )
        worker.ok.connect(lambda data, g=generation, r=reset: self._on_search_result(g, data, r))
        worker.failed.connect(lambda message, g=generation: self._on_search_failed(g, message))
        self._track(worker)
        worker.start()

    def _clear_results(self) -> None:
        while self.results_grid.count():
            item = self.results_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _on_search_result(self, generation: int, projects: list, reset: bool) -> None:
        if generation != self._generation:
            return
        self.search_button.setEnabled(True)
        start = len(self._projects)
        if reset:
            self._projects = []
            start = 0
        self._projects.extend(projects)
        for offset, project in enumerate(projects):
            index = start + offset
            card = self._make_card(project, generation)
            self.results_grid.addWidget(card, index // self.COLUMNS, index % self.COLUMNS)
        self._offset += len(projects)
        self.more_button.setEnabled(len(projects) >= self.LIMIT)
        self.result_count.setText(f"已显示 {len(self._projects)} 项")
        if self._projects:
            self.list_status.setText("搜索完成")
        elif reset:
            self.list_status.setText("没有找到内容，可更换关键词或调整筛选条件。")
            empty = QLabel("没有找到内容\n\n换个关键词、切换来源，或放宽 Minecraft 版本与加载器筛选。")
            empty.setObjectName("Muted")
            empty.setAlignment(Qt.AlignCenter)
            empty.setMinimumHeight(160)
            self.results_grid.addWidget(empty, 0, 0, 1, self.COLUMNS)
        if len(projects) < self.LIMIT:
            self.load_hint.setText("已到底部")
        else:
            self.load_hint.setText("")

    def _on_search_failed(self, generation: int, message: str) -> None:
        if generation != self._generation:
            return
        self.search_button.setEnabled(True)
        self.more_button.setEnabled(bool(self._projects))
        self.list_status.setText("搜索失败")
        self.ctx.bus.log.emit(f"[错误] {message}")
        QMessageBox.warning(self, APP_NAME, message)

    def _make_card(self, project: ContentProject, generation: int) -> ProjectCard:
        card = ProjectCard()
        card.setMinimumWidth(self.COVER_SIZE + 22)
        body = QVBoxLayout(card)
        body.setContentsMargins(11, 11, 11, 11)
        body.setSpacing(8)

        cover = QLabel()
        cover.setObjectName("Cover")
        cover.setFixedSize(self.COVER_SIZE, self.COVER_SIZE)
        cover.setAlignment(Qt.AlignCenter)
        body.addWidget(cover, 0, Qt.AlignHCenter)
        self._apply_cover(cover, None, QSize(self.COVER_SIZE, self.COVER_SIZE), project.title)

        title = QLabel()
        title.setWordWrap(False)
        title.setMinimumWidth(self.COVER_SIZE)
        title.setMaximumWidth(self.COVER_SIZE)
        title.setStyleSheet("font-weight: 700; font-size: 13px; color: #eaf4ec;")
        title.setText(title.fontMetrics().elidedText(project.title, Qt.ElideRight, self.COVER_SIZE))
        title.setToolTip(project.title)
        body.addWidget(title, 0, Qt.AlignHCenter)

        stat_text = f"{project.author or '未知作者'} · {_fmt_count(project.downloads)} 次下载"
        stat = QLabel()
        stat.setObjectName("Stat")
        stat.setMinimumWidth(self.COVER_SIZE)
        stat.setMaximumWidth(self.COVER_SIZE)
        stat.setText(stat.fontMetrics().elidedText(stat_text, Qt.ElideRight, self.COVER_SIZE))
        stat.setToolTip(stat_text)
        body.addWidget(stat, 0, Qt.AlignHCenter)

        body.addWidget(
            Badge(project.type_label, TYPE_BADGE_KIND.get(project.project_type, "gray")),
            0,
            Qt.AlignLeft,
        )

        card.clicked.connect(lambda p=project: self._open_detail(p))
        self._load_cover(cover, project.icon_url, QSize(self.COVER_SIZE, self.COVER_SIZE), project.title, generation)
        return card

    def _apply_cover(self, label: QLabel, pixmap: QPixmap | None, size: QSize, text: str) -> None:
        try:
            if pixmap is None or pixmap.isNull():
                label.setPixmap(make_placeholder(size, text))
            else:
                label.setPixmap(_rounded_pixmap(pixmap, size, 10))
        except RuntimeError:
            pass

    def _load_cover(
        self,
        label: QLabel,
        url: str,
        size: QSize,
        text: str,
        generation: int | None = None,
        project: ContentProject | None = None,
    ) -> None:
        def callback(pixmap: QPixmap | None) -> None:
            if project is not None and self._detail_project is not project:
                return
            if generation is not None and generation != self._generation:
                return
            self._apply_cover(label, pixmap, size, text)

        self._apply_cover(label, None, size, text)
        self._covers.load(url, callback, size)

    # ------------------------------------------------------------------
    # 详情页
    def _open_detail(self, project: ContentProject) -> None:
        self._detail_project = project
        self._versions = []
        self._detail_generation += 1
        generation = self._detail_generation
        self._render_gen = -1

        self.detail_title.setText(project.title)
        self.detail_desc.setText(project.description or "（暂无简介）")
        self.detail_desc.setToolTip(project.description or "")
        self.detail_count.setText("正在获取文件列表…")
        self.detail_site.setEnabled(bool(project.page_url))
        self._set_detail_badges(project)
        self._load_cover(
            self.detail_cover,
            project.icon_url,
            QSize(120, 120),
            project.title,
            project=project,
        )
        self._clear_versions()
        self._active_mc = ""
        self._project_mc_versions = []
        status = QLabel("正在获取支持的 Minecraft 版本…")
        status.setObjectName("Muted")
        self.versions_layout.addWidget(status)
        self.detail_scroll.verticalScrollBar().setValue(0)

        worker = ProjectVersionsWorker(self.client, project, self)
        worker.ok.connect(lambda data, g=generation: self._on_project_versions(g, data))
        worker.failed.connect(
            lambda message, g=generation: self._on_project_versions_failed(g, message)
        )
        self._track(worker)
        worker.start()
        self.stack.setCurrentIndex(1)

    def _set_detail_badges(self, project: ContentProject) -> None:
        while self.detail_badge_layout.count():
            item = self.detail_badge_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.detail_badge_layout.addWidget(Badge(project.author or "未知作者", "gray"))
        self.detail_badge_layout.addWidget(Badge(f"{_fmt_count(project.downloads)} 次下载", "gray"))
        self.detail_badge_layout.addWidget(
            Badge(project.source_label, "blue" if project.source == "modrinth" else "orange")
        )
        self.detail_badge_layout.addWidget(
            Badge(project.type_label, TYPE_BADGE_KIND.get(project.project_type, "gray"))
        )
        self.detail_badge_layout.addStretch(1)

    def _clear_versions(self) -> None:
        while self.versions_layout.count():
            item = self.versions_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _on_project_versions(self, generation: int, mc_versions: list) -> None:
        if generation != self._detail_generation:
            return
        self._project_mc_versions = [str(v) for v in mc_versions]
        self._render_chooser()

    def _on_project_versions_failed(self, generation: int, message: str) -> None:
        if generation != self._detail_generation:
            return
        self._project_mc_versions = []
        self._render_chooser(hint=message)
        self.ctx.bus.log.emit(f"[提示] {message}")

    def _render_chooser(self, hint: str = "") -> None:
        """展示支持的 Minecraft 版本，点击后再加载对应文件列表。"""
        self._active_mc = ""
        self._versions = []
        self._render_gen = -1
        self._clear_versions()
        versions = self._project_mc_versions
        if versions:
            self.detail_count.setText(
                f"支持 {len(versions)} 个 Minecraft 版本，请选择版本加载文件"
            )
        else:
            self.detail_count.setText("未获取到版本列表，可直接加载全部文件")
        tip = QLabel(
            hint
            or "为避免一次请求过多文件造成卡顿，请先选择 Minecraft 版本，再加载该版本的文件。"
        )
        tip.setObjectName("Muted")
        tip.setWordWrap(True)
        self.versions_layout.addWidget(tip)
        if versions:
            grid = QGridLayout()
            grid.setHorizontalSpacing(8)
            grid.setVerticalSpacing(8)
            for index, mc in enumerate(versions):
                button = QPushButton(mc)
                button.setObjectName("Chip")
                button.clicked.connect(
                    lambda _checked=False, value=mc: self._load_version_files(value)
                )
                grid.addWidget(button, index // 6, index % 6)
            holder = QWidget()
            holder.setLayout(grid)
            self.versions_layout.addWidget(holder)
        all_button = QPushButton("加载全部版本文件")
        all_button.setObjectName("Ghost")
        all_button.clicked.connect(lambda: self._load_version_files(""))
        self.versions_layout.addWidget(all_button, 0, Qt.AlignLeft)
        self.versions_layout.addStretch(1)

    def _load_version_files(self, mc_version: str) -> None:
        project = self._detail_project
        if project is None:
            return
        self._active_mc = mc_version
        self._detail_generation += 1
        generation = self._detail_generation
        self._render_gen = -1
        self._clear_versions()
        self.detail_count.setText(
            f"正在加载 Minecraft {mc_version} 的文件…" if mc_version else "正在加载全部文件…"
        )
        status = QLabel("正在请求文件列表…")
        status.setObjectName("Muted")
        self.versions_layout.addWidget(status)
        worker = VersionsWorker(self.client, project, mc_version, self)
        worker.ok.connect(lambda data, g=generation: self._on_versions(g, data))
        worker.failed.connect(lambda message, g=generation: self._on_versions_failed(g, message))
        self._track(worker)
        worker.start()

    def _on_versions(self, generation: int, versions: list) -> None:
        if generation != self._detail_generation:
            return
        self._versions = list(versions)
        self._clear_versions()
        mc_label = f"Minecraft {self._active_mc}" if self._active_mc else "全部版本"
        self.detail_count.setText(f"{mc_label} · 共 {len(self._versions)} 个文件")
        if self._project_mc_versions:
            back = QPushButton("← 返回 Minecraft 版本选择")
            back.setObjectName("Ghost")
            back.clicked.connect(lambda: self._render_chooser())
            self.versions_layout.addWidget(back, 0, Qt.AlignLeft)
        if not self._versions:
            label = QLabel("该版本下暂时没有可用文件。")
            label.setObjectName("Muted")
            self.versions_layout.addWidget(label)
            return

        groups: dict[str, list[ContentVersion]] = {}
        for version in self._versions:
            groups.setdefault(_main_mc_version(version), []).append(version)
        ordered = sorted([key for key in groups if key], key=_natural_key, reverse=True)
        if "" in groups:
            ordered.append("")

        actions: list[tuple] = []
        for mc in ordered:
            items = groups[mc]
            header_text = (
                f"Minecraft {mc} · {len(items)} 个文件"
                if mc
                else f"未知版本 · {len(items)} 个文件"
            )
            actions.append(("header", header_text))
            for version in items:
                actions.append(("row", version))
        self._render_actions = actions
        self._render_index = 0
        self._render_gen = generation
        QTimer.singleShot(0, self._render_tick)

    def _render_tick(self) -> None:
        if self._render_gen != self._detail_generation:
            return
        rendered = 0
        while self._render_index < len(self._render_actions) and rendered < 80:
            action = self._render_actions[self._render_index]
            self._render_index += 1
            rendered += 1
            if action[0] == "header":
                header = QLabel(str(action[1]))
                header.setObjectName("GroupHeader")
                self.versions_layout.addWidget(header)
            else:
                self.versions_layout.addWidget(self._make_version_row(action[1]))
        if self._render_index < len(self._render_actions):
            QTimer.singleShot(0, self._render_tick)
        else:
            self.versions_layout.addStretch(1)

    def _make_version_row(self, version: ContentVersion) -> QFrame:
        row = QFrame()
        row.setObjectName("VersionRow")
        row.setAttribute(Qt.WA_Hover, True)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        file = version.primary_file
        filename = file.filename if file else (version.name or version.version_number)
        left = QVBoxLayout()
        left.setSpacing(2)
        name_label = QLabel()
        name_label.setText(name_label.fontMetrics().elidedText(filename, Qt.ElideMiddle, 360))
        name_label.setToolTip(filename)
        name_label.setStyleSheet("font-weight: 600; color: #dfece3;")
        left.addWidget(name_label)
        sub_text = version.name or version.version_number
        sub_label = QLabel()
        sub_label.setObjectName("Tiny")
        sub_label.setText(sub_label.fontMetrics().elidedText(sub_text, Qt.ElideRight, 360))
        sub_label.setToolTip(sub_text)
        left.addWidget(sub_label)
        layout.addLayout(left, 1)

        loader_key = _version_loader_key(version)
        badge_label = LOADER_LABELS.get(loader_key, "通用" if not loader_key else loader_key.upper())
        layout.addWidget(
            Badge(badge_label, LOADER_BADGE_KIND.get(loader_key, "gray")), 0, Qt.AlignVCenter
        )

        date_label = QLabel(version.date[:10] if version.date else "-")
        date_label.setObjectName("Tiny")
        date_label.setFixedWidth(86)
        layout.addWidget(date_label)
        size_label = QLabel(_fmt_size(file.size if file else 0))
        size_label.setObjectName("Stat")
        size_label.setFixedWidth(78)
        size_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(size_label)
        install_button = QPushButton("安装")
        install_button.setObjectName("Chip")
        install_button.clicked.connect(
            lambda _checked=False, target_version=version: self._open_install_dialog(
                target_version.id
            )
        )
        layout.addWidget(install_button)
        return row

    def _on_versions_failed(self, generation: int, message: str) -> None:
        if generation != self._detail_generation:
            return
        self._clear_versions()
        self.detail_count.setText("获取文件列表失败")
        if self._project_mc_versions:
            back = QPushButton("← 返回 Minecraft 版本选择")
            back.setObjectName("Ghost")
            back.clicked.connect(lambda: self._render_chooser())
            self.versions_layout.addWidget(back, 0, Qt.AlignLeft)
        label = QLabel(message)
        label.setObjectName("Muted")
        label.setWordWrap(True)
        self.versions_layout.addWidget(label)
        self.ctx.bus.log.emit(f"[错误] {message}")

    def _back_to_list(self) -> None:
        self._detail_generation += 1
        self._render_gen = -1
        self._render_actions = []
        self._render_index = -1
        self.stack.setCurrentIndex(0)

    def _open_project_page(self) -> None:
        project = self._detail_project
        if project is not None and project.page_url:
            self.ctx.bus.open_browser.emit(project.page_url)

    # ------------------------------------------------------------------
    # 安装
    def _open_install_dialog(self, preferred_id: str = "") -> None:
        project = self._detail_project
        if project is None:
            return
        if self._install_worker is not None and self._install_worker.isRunning():
            QMessageBox.information(self, APP_NAME, "已有安装任务正在进行，请等待完成或先取消。")
            return
        if not self._versions:
            QMessageBox.information(self, APP_NAME, "版本列表尚未加载完成，请稍后再试。")
            return
        targets = self._targets or scan_targets(self.ctx)
        dialog = InstallDialog(
            self.ctx, project, self._versions, targets, self, preferred=preferred_id
        )
        if dialog.exec() != QDialog.Accepted:
            return
        if dialog.selected_version is None or dialog.selected_target is None:
            return
        self._start_install(project, dialog.selected_version, dialog.selected_target)

    def _start_install(
        self, project: ContentProject, version: ContentVersion, target: dict
    ) -> None:
        target_dir = Path(str(target.get("game_dir") or self.ctx.config.game_path))
        self._cancel_requested = False
        self._pending_install = (project, version, target_dir)
        self._install_pause.clear()
        self._install_log_lines: list[str] = []
        kind_label = {
            "mod": "Mod",
            "modpack": "整合包",
            "resourcepack": "资源包",
            "shader": "光影包",
        }.get(project.project_type, "内容")
        task = self.ctx.downloads.submit(
            kind_label,
            project.title,
            lambda _task: self._spawn_install(),
            cancel=lambda: (
                self._install_worker.cancel_event.set if self._install_worker else None
            ),
            pause=self._install_pause,
            rebuild=lambda _task: self._spawn_install(_task.id),
            target_dir=str(target_dir),
            detail="准备下载…",
        )
        self._install_task_id = task.id
        self._reset_progress(
            f"开始安装 {version.primary_file.filename if version.primary_file else project.title}…"
        )

    def _spawn_install(self, task_id: str = "") -> ContentInstallWorker:
        """创建（或重试时重建）内容安装线程。"""
        if self._pending_install is None:
            raise RuntimeError("没有待安装的内容")
        project, version, target_dir = self._pending_install
        worker = ContentInstallWorker(self.ctx, project, version, target_dir, self)
        worker.pause_event = self._install_pause
        worker.progress.connect(self._on_install_progress)
        worker.log.connect(self._append_install_log)
        worker.progress.connect(
            lambda value, detail, tid=task_id: self.ctx.downloads.update(
                tid, percent=value, status="下载中", detail=detail
            )
            if tid
            else None
        )
        worker.done.connect(self._on_install_done)
        worker.failed.connect(self._on_install_failed)
        self._install_worker = worker
        if task_id:
            self._install_task_id = task_id
        return worker

    def _reset_progress(self, detail: str) -> None:
        for view in self._progress_views:
            try:
                view["card"].setVisible(True)
                view["bar"].setValue(0)
                view["label"].setText(detail)
                view["button"].setEnabled(True)
            except RuntimeError:
                continue

    def _set_progress(self, value: float, detail: str = "") -> None:
        for view in self._progress_views:
            try:
                view["card"].setVisible(True)
                view["bar"].setValue(int(max(0.0, min(1.0, value)) * 1000))
                if detail:
                    view["label"].setText(detail)
            except RuntimeError:
                continue

    def _on_install_progress(self, value: float, detail: str) -> None:
        self._set_progress(value, detail)

    def _on_install_done(self, message: str) -> None:
        self._set_progress(1.0, "安装完成")
        for view in self._progress_views:
            try:
                view["button"].setEnabled(False)
            except RuntimeError:
                continue
        self.ctx.bus.toast.emit(message)
        self.ctx.bus.versions_changed.emit()
        self.refresh()
        if getattr(self, "_install_task_id", ""):
            self.ctx.downloads.finish(self._install_task_id, True, message)
            self._install_task_id = ""

    def _on_install_failed(self, message: str) -> None:
        if getattr(self, "_install_task_id", ""):
            self.ctx.downloads.finish(
                self._install_task_id, not self._cancel_requested, message
            )
            self._install_task_id = ""
        for view in self._progress_views:
            try:
                view["button"].setEnabled(False)
            except RuntimeError:
                continue
        if self._cancel_requested:
            self._set_progress(0.0, "安装已取消")
            self.ctx.bus.toast.emit("安装已取消。")
            return
        self._set_progress(0.0, "安装失败")
        logs = "\n".join(getattr(self, "_install_log_lines", [])[-40:])
        QGuiApplication.clipboard().setText(f"{message}\n\n{logs}".strip())
        self.ctx.bus.log.emit(f"[错误] {message}")
        QMessageBox.warning(
            self,
            APP_NAME,
            f"{message}\n\n安装日志已复制到剪贴板，请反馈给开发者。",
        )

    def _append_install_log(self, message: str) -> None:
        self.ctx.bus.log.emit(message)
        lines = getattr(self, "_install_log_lines", None)
        if lines is None:
            lines = self._install_log_lines = []
        lines.append(message)
        if len(lines) > 200:
            del lines[:100]

    def _cancel_install(self) -> None:
        worker = self._install_worker
        if worker is None or not worker.isRunning():
            return
        self._cancel_requested = True
        worker.cancel_event.set()
        self._set_progress(0.0, "正在取消安装…")
        for view in self._progress_views:
            try:
                view["button"].setEnabled(False)
            except RuntimeError:
                continue

    # ------------------------------------------------------------------
    # 生命周期
    def refresh(self) -> None:
        """重新扫描已安装版本，供安装目标选择使用。"""
        if self._target_worker is not None and self._target_worker.isRunning():
            return
        worker = TargetScanWorker(self.ctx, self)
        worker.ok.connect(self._on_targets)
        self._target_worker = worker
        self._track(worker)
        worker.start()

    def _on_targets(self, targets: list) -> None:
        self._targets = list(targets)

    def shutdown(self) -> None:
        self._generation += 1
        self._detail_generation += 1
        self._render_gen = -1
        worker = self._install_worker
        if worker is not None and worker.isRunning():
            worker.cancel_event.set()
        workers = list(self._workers)
        if worker is not None and worker not in workers:
            workers.append(worker)
        for item in workers:
            wait_thread(item, 1500)
        self._covers.shutdown()
