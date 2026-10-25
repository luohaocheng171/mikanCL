"""拖拽导入：识别 Mod、整合包、资源包、光影包与世界存档并安装。"""

from __future__ import annotations

import json
import re
import shutil
import threading
import traceback
import zipfile
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ..config import (
    INSTANCES_DIR,
    LOG_DIR,
    read_instance_manifest,
    write_instance_manifest,
)
from ..context import AppContext
from ..content import ContentError
from ..installer import GameInstaller
from ..java import pick_java
from ..launcher import prepare_isolated_dir
from ..modloader import install_loader, java_for_mc
from .widgets import Badge, Card

KIND_LABELS = {
    "mod": "Mod",
    "modpack": "整合包",
    "resourcepack": "资源包",
    "shader": "光影包",
    "world": "世界存档",
}
_KIND_FOLDERS = {"mod": "mods", "resourcepack": "resourcepacks", "shader": "shaderpacks"}


def _zip_names(path: Path) -> list[str]:
    try:
        with zipfile.ZipFile(path) as archive:
            return [name.replace("\\", "/") for name in archive.namelist()]
    except (OSError, zipfile.BadZipFile):
        return []


def write_install_error_log(title: str, detail: str) -> Path | None:
    """把安装失败的详细信息追加写入 data/logs/install_error.log。"""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = LOG_DIR / "install_error.log"
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(f"\n==== {datetime.now():%Y-%m-%d %H:%M:%S} · {title} ====\n{detail}\n")
        return path
    except OSError:
        return None


def detect_path(path: Path) -> str:
    """根据文件后缀与内部结构判断拖入内容类型。"""
    if path.is_dir():
        if (path / "level.dat").is_file():
            return "world"
        if any(
            (path / marker).is_file()
            for marker in (
                "manifest.json",
                "modrinth.index.json",
                "mmc-pack.json",
                "instance.cfg",
                "instance.json",
            )
        ):
            return "modpack"
        return ""
    suffix = path.suffix.lower()
    if suffix == ".jar":
        return "mod"
    if suffix in (".mrpack", ".mikan"):
        return "modpack"
    if suffix != ".zip":
        return ""
    names = _zip_names(path)
    if not names:
        return ""
    lowered = [name.lower() for name in names]
    if any(name.endswith("level.dat") for name in lowered):
        return "world"
    if any(
        name.endswith("modrinth.index.json") or name.endswith("mmc-pack.json")
        or name.endswith("instance.cfg") or name == "instance.json"
        for name in lowered
    ):
        return "modpack"
    if any(name.endswith("manifest.json") for name in lowered):
        return "modpack"
    if any(name.startswith("shaders/") or "/shaders/" in name for name in lowered):
        return "shader"
    if any(name.endswith("pack.mcmeta") for name in lowered):
        return "resourcepack"
    if any(name.endswith(".jar") for name in lowered):
        return "modpack"
    return ""


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    index = 2
    while True:
        candidate = path.with_name(f"{stem} ({index}){suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def _safe_extract(archive: zipfile.ZipFile, target: Path, prefix: str = "") -> int:
    count = 0
    for info in archive.infolist():
        if info.is_dir():
            continue
        name = info.filename.replace("\\", "/")
        if prefix:
            if not name.startswith(prefix):
                continue
            name = name[len(prefix):]
        if not name or name.startswith("/") or ".." in Path(name).parts:
            continue
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as source, open(destination, "wb") as output:
            shutil.copyfileobj(source, output)
        count += 1
    return count


def _world_zip_prefix(names: list[str]) -> str:
    tops: set[str] = set()
    for name in names:
        clean = name.strip("/")
        if not clean:
            continue
        tops.add(clean.split("/", 1)[0])
    if len(tops) == 1:
        top = tops.pop()
        if any(name.startswith(top + "/level.dat") for name in names):
            return top + "/"
    return ""


def install_world(path: Path, game_dir: Path, log=None) -> str:
    saves = game_dir / "saves"
    saves.mkdir(parents=True, exist_ok=True)
    if path.is_dir():
        destination = _unique_path(saves / path.name)
        shutil.copytree(path, destination)
        return str(destination)
    destination = _unique_path(saves / path.stem)
    destination.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(path) as archive:
            names = [name.replace("\\", "/") for name in archive.namelist()]
            prefix = _world_zip_prefix(names)
            _safe_extract(archive, destination, prefix)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ContentError(f"世界存档解压失败：{exc}") from exc
    return str(destination)


def install_file(ctx: AppContext, path: Path, kind: str, target: dict, log=None) -> str:
    root = Path(str(target.get("game_dir") or ctx.config.game_path))
    version_id = str(target.get("version_id") or "")
    mode = ctx.config.isolation_for(version_id) if version_id else "none"
    game_dir = prepare_isolated_dir(root, version_id, mode) if version_id else root
    if kind == "world":
        return install_world(path, game_dir, log)
    folder = _KIND_FOLDERS.get(kind)
    if folder is None:
        raise ContentError(f"暂不支持导入类型：{kind}")
    destination_dir = game_dir / folder
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = _unique_path(destination_dir / path.name)
    shutil.copy2(path, destination)
    return str(destination)


class FileDropWorker(QThread):
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, ctx: AppContext, path: Path, kind: str, target: dict, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.path = path
        self.kind = kind
        self.target = target

    def run(self) -> None:
        try:
            destination = install_file(self.ctx, self.path, self.kind, self.target, self.ctx.bus.log.emit)
            self.done.emit(
                f"{self.path.name} 已作为{KIND_LABELS.get(self.kind, self.kind)}导入到 {destination}"
            )
        except ContentError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"导入失败：{exc}")


class ModpackDropWorker(QThread):
    """拖入的整合包：创建/恢复独立实例，安装基础版本、加载器与整合包内容。"""

    progress = Signal(float, str)
    log = Signal(str)
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, ctx: AppContext, path: Path, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.path = path
        self.cancel_event = threading.Event()
        self.pause_event = threading.Event()
        self.failure_detail = ""

    def _emit(self, value: float, detail: str = "") -> None:
        self.progress.emit(max(0.0, min(1.0, value)), detail)

    def _fail(self, message: str, exc: BaseException | None = None) -> None:
        detail = traceback.format_exc() if exc is not None else ""
        self.failure_detail = f"{message}\n{detail}".strip()
        log_path = write_install_error_log(self.path.name, self.failure_detail)
        if log_path is not None:
            self.log.emit(f"[日志] 详细错误已写入 {log_path}")
        self.failed.emit(message)

    def _read_manifest(self) -> dict | None:
        """识别 MikanCL 导出的 instance.json，走「恢复实例」分支。"""
        if self.path.is_dir():
            data = read_instance_manifest(self.path)
        else:
            try:
                with zipfile.ZipFile(self.path) as archive:
                    if "instance.json" not in archive.namelist():
                        return None
                    data = json.loads(archive.read("instance.json").decode("utf-8"))
            except (OSError, zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError):
                return None
        if isinstance(data, dict):
            payload = data.get("instance")
            return payload if isinstance(payload, dict) else data
        return None

    def _make_installer(self, target: Path, base: float, span: float) -> GameInstaller:
        return GameInstaller(
            self.ctx.config.with_game_dir(target),
            self.ctx.sources,
            progress_cb=lambda p: self._emit(base + p.percent * span, p.detail),
            log_cb=self.log.emit,
            cancel=self.cancel_event,
            pause=self.pause_event,
        )

    def _install_loader_if_needed(
        self,
        installer: GameInstaller,
        target: Path,
        mc_version: str,
        loader: str,
        loader_version: str,
        version_id: str,
    ) -> str:
        if not loader:
            return version_id
        if (target / "versions" / version_id / f"{version_id}.json").is_file():
            return version_id
        self._emit(0.47, f"安装 {loader} 加载器…")
        java, warning = pick_java(self.ctx.javas, java_for_mc(mc_version))
        if java is None:
            raise ContentError(
                f"整合包需要 Java {java_for_mc(mc_version)}，未找到可用 Java。{warning}"
            )
        return install_loader(
            installer,
            loader,
            mc_version,
            loader_version,
            java_path=java.path,
            log=self.log.emit,
            cancel=self.cancel_event,
        )

    def run(self) -> None:
        manifest = self._read_manifest()
        if manifest is not None:
            self._restore(manifest)
            return
        try:
            meta = self.ctx.content.parse_modpack(self.path)
        except ContentError as exc:
            self._fail(str(exc), exc)
            return
        except Exception as exc:  # noqa: BLE001
            self._fail(f"解析整合包失败：{exc}", exc)
            return
        if not meta.mc_version:
            self._fail("整合包缺少 Minecraft 版本信息，无法导入。")
            return
        self._install_pack(meta)

    # ------------------------------------------------------------------
    def _install_pack(self, meta) -> None:
        slug_base = re.sub(r"[^\w\-]+", "-", (meta.name or self.path.stem).lower()).strip("-")[:36]
        slug = f"{slug_base or 'modpack'}-{abs(hash(str(self.path))) % 10000:04d}"
        target = INSTANCES_DIR / slug
        target.mkdir(parents=True, exist_ok=True)
        installer = self._make_installer(target, 0.05, 0.4)
        try:
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
            version_id = self._install_loader_if_needed(
                installer, target, mc_version, meta.loader, meta.loader_version, mc_version
            )
            self._emit(0.6, "下载整合包内容…")
            self.ctx.content.install_modpack_files(
                self.path,
                meta,
                target,
                log=self.log.emit,
                cancel=self.cancel_event,
                progress=lambda value, detail: self._emit(0.6 + value * 0.35, detail),
                pause=self.pause_event,
            )
            instance = self.ctx.config.add_instance(
                meta.name or self.path.stem,
                str(target),
                version_id=version_id,
                loader=meta.loader,
                mc_version=meta.mc_version,
                modpack=meta.name or self.path.stem,
                loader_version=meta.loader_version,
            )
            write_instance_manifest(instance, target)
            self.ctx.config.select_instance(instance.id)
            self.ctx.config.save()
            self.ctx.bus.instances_changed.emit()
            self._emit(1.0, "整合包导入完成")
            self.done.emit(f"整合包「{instance.name}」已导入并切换为当前实例。")
        except ContentError as exc:
            self._fail(str(exc), exc)
        except Exception as exc:  # noqa: BLE001
            self._fail(f"整合包导入失败：{exc}", exc)

    def _restore(self, data: dict) -> None:
        """从 instance.json 恢复实例：解压覆盖文件并补装缺失的基础版本与加载器。"""
        try:
            name = str(data.get("name") or self.path.stem)
            mc_version = str(data.get("mc_version") or "")
            if not mc_version:
                raise ContentError("instance.json 缺少 Minecraft 版本信息，无法恢复。")
            loader = str(data.get("loader") or "")
            loader_version = str(data.get("loader_version") or "")
            version_id = str(data.get("version_id") or mc_version)
            slug_base = re.sub(r"[^\w\-]+", "-", name.lower()).strip("-")[:36]
            slug = f"{slug_base or 'instance'}-{abs(hash(str(self.path))) % 10000:04d}"
            target = INSTANCES_DIR / slug
            target.mkdir(parents=True, exist_ok=True)
            self._emit(0.05, "恢复实例文件…")
            self.log.emit(f"[恢复] 从 {self.path.name} 解压实例文件…")
            if self.path.is_dir():
                source = self.path / "overrides" if (self.path / "overrides").is_dir() else self.path
                shutil.copytree(source, target, dirs_exist_ok=True)
            else:
                with zipfile.ZipFile(self.path) as archive:
                    names = [name.replace("\\", "/") for name in archive.namelist()]
                    prefix = "overrides/" if any(n.startswith("overrides/") for n in names) else ""
                    _safe_extract(archive, target, prefix)
            installer = self._make_installer(target, 0.2, 0.35)
            if not (target / "versions" / mc_version / f"{mc_version}.json").is_file():
                self.log.emit(f"[恢复] 安装基础版本 {mc_version}…")
                payload, _n, _c = self.ctx.sources.get_manifest()
                entries = payload.get("data", {}).get("versions", [])
                entry = next((v for v in entries if str(v.get("id")) == mc_version), None)
                if entry is None:
                    raise ContentError(f"版本清单中找不到 Minecraft {mc_version}。")
                installer.install_version(entry)
            version_id = self._install_loader_if_needed(
                installer, target, mc_version, loader, loader_version, version_id
            )
            instance = self.ctx.config.add_instance(
                name,
                str(target),
                version_id=version_id,
                loader=loader,
                mc_version=mc_version,
                modpack=str(data.get("modpack") or name),
                loader_version=loader_version,
                memory_mb=int(data.get("memory_mb") or 0),
                window_title=str(data.get("window_title") or ""),
                extra_jvm_args=str(data.get("extra_jvm_args") or ""),
            )
            write_instance_manifest(instance, target)
            self.ctx.config.select_instance(instance.id)
            self.ctx.config.save()
            self.ctx.bus.instances_changed.emit()
            self._emit(1.0, "实例恢复完成")
            self.done.emit(f"实例「{instance.name}」已恢复并切换为当前实例。")
        except ContentError as exc:
            self._fail(str(exc), exc)
        except Exception as exc:  # noqa: BLE001
            self._fail(f"实例恢复失败：{exc}", exc)


class DropDialog(QDialog):
    """确认拖入内容与安装目标。"""

    def __init__(self, items: list[tuple[Path, str]], targets: list[dict], parent=None):
        super().__init__(parent)
        self.selected_target: dict | None = None
        self.setObjectName("Root")
        self.setWindowTitle("导入拖入的文件")
        self.setModal(True)
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        title = QLabel(f"检测到 {len(items)} 个可导入的内容")
        title.setObjectName("CardTitle")
        layout.addWidget(title)

        card = Card(margins=12, spacing=6)
        for path, kind in items[:12]:
            row = QHBoxLayout()
            row.setSpacing(8)
            row.addWidget(Badge(KIND_LABELS.get(kind, kind), "blue"), 0, Qt.AlignVCenter)
            label = QLabel(path.name)
            label.setToolTip(str(path))
            row.addWidget(label, 1)
            card.body.addLayout(row)
        if len(items) > 12:
            more = QLabel(f"…以及另外 {len(items) - 12} 个文件")
            more.setObjectName("Tiny")
            card.body.addWidget(more)
        layout.addWidget(card)

        target_row = QHBoxLayout()
        target_row.setSpacing(10)
        caption = QLabel("安装到")
        caption.setObjectName("Muted")
        target_row.addWidget(caption)
        self.target_combo = QComboBox()
        for target in targets:
            self.target_combo.addItem(str(target.get("label") or "未命名目标"), target)
        target_row.addWidget(self.target_combo, 1)
        layout.addLayout(target_row)

        hint = QLabel(
            "Mod / 资源包 / 光影包 / 世界存档会安装到所选版本（遵循版本隔离设置）；"
            "整合包会自动创建独立实例，无需选择目标。"
        )
        hint.setObjectName("Tiny")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("取消")
        cancel.setObjectName("Ghost")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        confirm = QPushButton("开始导入")
        confirm.setObjectName("Primary")
        confirm.clicked.connect(self._accept)
        buttons.addWidget(confirm)
        layout.addLayout(buttons)

    def _accept(self) -> None:
        target = self.target_combo.currentData()
        if not isinstance(target, dict):
            QMessageBox.information(self, "请选择目标", "请选择要安装到的版本。")
            return
        self.selected_target = target
        self.accept()


def handle_dropped_paths(parent, ctx: AppContext, paths: list[Path]) -> None:
    """识别并安装拖入的文件/文件夹。"""
    from .page_content import scan_targets

    items: list[tuple[Path, str]] = []
    unknown: list[str] = []
    for path in paths:
        kind = detect_path(path)
        if kind:
            items.append((path, kind))
        else:
            unknown.append(path.name)
    if unknown:
        QMessageBox.warning(
            parent,
            "无法识别",
            "以下内容无法识别为 Mod、整合包、资源包、光影包或世界存档：\n" + "\n".join(unknown[:8]),
        )
    if not items:
        return
    dialog = DropDialog(items, scan_targets(ctx), parent)
    if dialog.exec() != QDialog.Accepted or dialog.selected_target is None:
        return
    target = dialog.selected_target

    workers: list[QThread] = []
    remaining = [len(items)]
    handled: set[str] = set()

    def copy_failure_log(message: str, detail: str = "") -> None:
        text = message if not detail else f"{message}\n\n{detail}"
        QGuiApplication.clipboard().setText(text)
        ctx.bus.log.emit(f"[错误] {text}")

    def finish(worker: QThread, task_id: str, message: str, ok: bool = True) -> None:
        if not task_id or task_id in handled:
            return
        handled.add(task_id)
        ctx.downloads.finish(task_id, ok, message)
        if ok:
            ctx.bus.log.emit(f"[导入] {message}")
            ctx.bus.toast.emit(message)
        else:
            detail = str(getattr(worker, "failure_detail", "") or "")
            copy_failure_log(message, detail)
            QMessageBox.warning(
                parent,
                "导入失败",
                f"{message}\n\n日志已复制到剪贴板，请反馈给开发者。",
            )
        remaining[0] -= 1
        if remaining[0] <= 0:
            ctx.bus.toast.emit("拖入内容已全部处理完成。")

    def link(worker: QThread, task_id: str) -> None:
        worker.started.connect(lambda tid=task_id: ctx.downloads.update(tid, status="安装中"))
        if isinstance(worker, ModpackDropWorker):
            worker.log.connect(lambda message: ctx.bus.log.emit(message))
            worker.progress.connect(
                lambda value, detail, tid=task_id: ctx.downloads.update(
                    tid, percent=value, detail=detail
                )
            )
        worker.done.connect(
            lambda message, tid=task_id, w=worker: finish(w, tid, message, True)
        )
        worker.failed.connect(
            lambda message, tid=task_id, w=worker: finish(w, tid, message, False)
        )

    fallback_dir = str(Path(str(target.get("game_dir") or ctx.config.game_path)))

    for path, kind in items:
        if kind == "modpack":
            label = "整合包"
            pause = threading.Event()
            holder: dict[str, QThread] = {}

            def make_modpack(_task, path=path, pause=pause, holder=holder) -> QThread:
                worker = ModpackDropWorker(ctx, path)
                worker.pause_event = pause
                holder["worker"] = worker
                link(worker, _task.id)
                handled.discard(_task.id)
                workers.append(worker)
                return worker

            def cancel_modpack(holder=holder) -> None:
                worker = holder.get("worker")
                if worker is not None:
                    worker.cancel_event.set()

            ctx.downloads.submit(
                label,
                path.name,
                make_modpack,
                cancel=cancel_modpack,
                pause=pause,
                rebuild=make_modpack,
                target_dir=fallback_dir,
                detail="准备导入整合包",
            )
            continue

        label = KIND_LABELS.get(kind, kind)

        def make_file(_task, path=path, kind=kind) -> QThread:
            worker = FileDropWorker(ctx, path, kind, target)
            link(worker, _task.id)
            handled.discard(_task.id)
            workers.append(worker)
            return worker

        ctx.downloads.submit(
            label,
            path.name,
            make_file,
            rebuild=make_file,
            target_dir=fallback_dir,
        )
