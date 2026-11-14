"""插件系统：用 .py 文件给启动器扩展页面，并把启动器能力整理成 API。

插件放置位置：
- ``data/plugins/*.py``（用户插件，优先级最高）
- 程序目录下的 ``plugins/*.py``（可选的内置插件目录）

也可以直接把 ``.py`` 文件拖进启动器窗口，文件会被复制到 ``data/plugins`` 并立即加载。

每个插件是一个普通 Python 文件，必须提供 ``setup(api)`` 入口，可选提供
``PLUGIN_NAME`` 用于日志展示。插件通过 ``api.add_page(标题, QWidget)`` 增加侧边栏页面。

示例（data/plugins/hello.py）::

    from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

    PLUGIN_NAME = "你好插件"

    def setup(api):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("你好，" + api.app_name))
        api.add_page("你好", page)
        api.log("你好插件已加载")
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget

from . import APP_NAME, APP_VERSION
from .config import DATA_DIR
from .context import AppContext


@dataclass
class PluginPage:
    """插件注册的一个页面。"""

    plugin_id: str
    title: str
    widget: QWidget


class _TaskThread(QThread):
    """把插件里的耗时函数放到后台线程，避免卡住界面。"""

    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[[], object], parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:
        try:
            self.done.emit(self._fn())
        except Exception as exc:  # noqa: BLE001 - 插件异常不能影响启动器
            self.failed.emit(str(exc))


class PluginAPI:
    """传给插件 ``setup(api)`` 的接口对象。"""

    def __init__(self, manager: "PluginManager", ctx: AppContext, plugin_id: str):
        self._manager = manager
        self.ctx = ctx
        self.plugin_id = plugin_id
        self.pages: list[PluginPage] = []

    # ---------- 基本信息 ----------
    @property
    def app_name(self) -> str:
        return APP_NAME

    @property
    def app_version(self) -> str:
        return APP_VERSION

    @property
    def config(self):
        """当前的 Config 对象（可直接读写字段，改完调用 ``config.save()``）。"""
        return self.ctx.config

    @property
    def data_dir(self) -> Path:
        return DATA_DIR

    @property
    def plugins_dir(self) -> Path:
        return self._manager.plugins_dir

    # ---------- 页面 ----------
    def add_page(self, title: str, widget: QWidget) -> PluginPage:
        """在侧边栏新增一个插件页面。"""
        page = PluginPage(self.plugin_id, title, widget)
        self.pages.append(page)
        self._manager.register_page(page)
        return page

    # ---------- 交互 ----------
    def log(self, message: str) -> None:
        self.ctx.bus.log.emit(f"[插件 {self.plugin_id}] {message}")

    def toast(self, message: str) -> None:
        self.ctx.bus.toast.emit(message)

    def navigate(self, name: str) -> None:
        """跳转到内置页面：home / download / content / modpack / control / settings 等。"""
        self.ctx.bus.navigate.emit(name)

    def open_url(self, url: str) -> None:
        self.ctx.bus.open_browser.emit(url)

    def open_folder(self, path) -> None:
        target = Path(path)
        if target.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
        else:
            self.toast(f"目录不存在：{target}")

    # ---------- 数据查询 ----------
    def list_instances(self) -> list[dict]:
        cfg = self.ctx.config
        return [
            {
                "id": item.id,
                "name": item.name,
                "mc_version": item.mc_version,
                "loader": item.loader,
                "path": str(cfg.instance_path(item.id)),
                "selected": item.id == cfg.selected_instance_id,
            }
            for item in cfg.instance_list()
        ]

    def list_versions(self, instance_id: str = "default") -> list[dict]:
        from .version import scan_installed_versions

        game_dir = self.ctx.config.instance_path(instance_id)
        return [
            {
                "id": item.id,
                "type": item.display_type,
                "loader": item.loader,
                "base_version": item.base_version,
                "path": str(item.path),
            }
            for item in scan_installed_versions(game_dir)
        ]

    def current_account(self) -> dict | None:
        account = self.ctx.current_account()
        if account is None:
            return None
        return {
            "name": account.name,
            "uuid": getattr(account, "uuid", ""),
            "type": getattr(account, "type_label", ""),
        }

    def list_java(self) -> list[dict]:
        return [
            {
                "path": getattr(item, "path", ""),
                "version": getattr(item, "version", ""),
                "major": getattr(item, "major", 0),
            }
            for item in getattr(self.ctx, "javas", [])
        ]

    # ---------- 内容中心 ----------
    def search(
        self,
        query: str = "",
        project_type: str = "mod",
        source: str = "modrinth",
        game_version: str = "",
        loader: str = "",
        limit: int = 20,
    ) -> list[dict]:
        """调用 Modrinth / CurseForge 搜索，返回纯字典列表（同步，建议放进 background）。"""
        from .content import ContentClient

        client = ContentClient(self.ctx.config)
        projects = client.search(
            source, project_type, query, game_version, loader, 0, max(1, int(limit))
        )
        return [
            {
                "source": item.source,
                "id": item.id,
                "title": item.title,
                "cn_title": item.display_title,
                "description": item.description,
                "cn_description": item.display_description,
                "project_type": item.project_type,
                "author": item.author,
                "downloads": item.downloads,
                "page_url": item.page_url,
                "categories": list(item.categories),
            }
            for item in projects
        ]

    # ---------- 下载与安装 ----------
    def download_file(
        self,
        url: str,
        target_path,
        on_progress: Callable[[int], None] | None = None,
    ) -> str:
        """直接下载一个文件到目标路径（同步，建议放进 background）。"""
        from .net import Candidate, Http

        http = Http(timeout=40)
        saved = http.download_to_path(
            [Candidate(url)],
            Path(target_path),
            on_bytes=on_progress,
        )
        return str(saved)

    def install_version(
        self,
        mc_version: str,
        instance_id: str = "default",
        on_progress: Callable[[object], None] | None = None,
        on_done: Callable[[object], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        """后台安装一个原版 Minecraft 版本到指定实例。"""
        from .installer import GameInstaller

        def job():
            cfg = self.ctx.config
            game_dir = cfg.instance_path(instance_id)
            installer = GameInstaller(
                cfg.with_game_dir(game_dir),
                self.ctx.sources,
                progress_cb=on_progress,
            )
            payload, _name, _cached = self.ctx.sources.get_manifest()
            entries = payload.get("data", {}).get("versions", [])
            entry = next(
                (item for item in entries if str(item.get("id")) == str(mc_version)),
                None,
            )
            if entry is None:
                raise RuntimeError(f"版本清单中找不到 Minecraft {mc_version}")
            installer.install_version(entry)
            return mc_version

        self.background(job, on_done, on_error)

    # ---------- 线程 ----------
    def background(
        self,
        fn: Callable[[], object],
        on_done: Callable[[object], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> QThread:
        """在后台线程执行 ``fn``，结果通过回调回到 Qt 事件循环。"""
        return self._manager.run_background(fn, on_done, on_error)


class PluginManager:
    """扫描并加载插件，维护插件页面与后台线程。"""

    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self.plugins_dir = DATA_DIR / "plugins"
        self.pages: list[PluginPage] = []
        self.errors: list[tuple[str, str]] = []
        self._loaded_ids: set[str] = set()
        self.on_page_added: Callable[[PluginPage], None] | None = None
        self._threads: list[_TaskThread] = []

    # ------------------------------------------------------------------
    def search_dirs(self) -> list[Path]:
        dirs = [self.plugins_dir]
        bundled = Path(__file__).resolve().parent.parent / "plugins"
        if bundled.exists() and bundled != self.plugins_dir:
            dirs.append(bundled)
        frozen = getattr(sys, "_MEIPASS", "")
        if frozen:
            packed = Path(frozen) / "plugins"
            if packed.exists() and packed not in dirs:
                dirs.append(packed)
        return dirs

    def load(self) -> "PluginManager":
        try:
            self.plugins_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        seen: set[str] = set()
        for directory in self.search_dirs():
            if not directory.exists():
                continue
            for path in sorted(directory.glob("*.py")):
                if path.name.startswith("_"):
                    continue
                plugin_id = path.stem
                if plugin_id in seen:
                    continue
                seen.add(plugin_id)
                self._load_one(path, plugin_id)
        return self

    def install_file(self, path: Path) -> tuple[bool, str]:
        """把外部 .py 文件复制到插件目录并立即加载，返回 (是否成功, 提示语)。"""
        path = Path(path)
        if path.suffix.lower() != ".py" or not path.is_file():
            return False, f"{path.name} 不是 .py 插件文件"
        try:
            self.plugins_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return False, f"无法创建插件目录：{exc}"
        plugin_id = path.stem
        target = self.plugins_dir / path.name
        already = plugin_id in self._loaded_ids
        try:
            same_file = path.resolve() == target.resolve()
        except OSError:
            same_file = False
        if not same_file:
            if target.exists():
                try:
                    identical = target.read_bytes() == path.read_bytes()
                except OSError:
                    identical = False
                if not identical:
                    if already:
                        return True, f"插件 {plugin_id} 已在运行，替换文件后请重启启动器"
                    return False, f"插件目录已有同名文件 {path.name}，请先删除或改名"
            else:
                try:
                    shutil.copy2(path, target)
                except OSError as exc:
                    return False, f"复制插件失败：{exc}"
        if already:
            return True, f"插件 {plugin_id} 已在运行，替换文件后请重启启动器"
        before = len(self.errors)
        self._load_one(target, plugin_id)
        if len(self.errors) > before:
            detail = self.errors[-1][1].strip().splitlines()
            return False, f"插件 {plugin_id} 加载失败：{detail[-1] if detail else '未知错误'}"
        if not any(page.plugin_id == plugin_id for page in self.pages):
            return True, f"插件 {plugin_id} 已安装（未新增页面）"
        return True, f"插件 {plugin_id} 已加载"

    def _load_one(self, path: Path, plugin_id: str) -> None:
        api = PluginAPI(self, self.ctx, plugin_id)
        try:
            spec = importlib.util.spec_from_file_location(
                f"mikan_plugin_{plugin_id}", path
            )
            if spec is None or spec.loader is None:
                raise RuntimeError("无法读取插件文件")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            setup = getattr(module, "setup", None)
            if not callable(setup):
                raise RuntimeError("插件缺少 setup(api) 入口函数")
            setup(api)
            name = str(getattr(module, "PLUGIN_NAME", plugin_id))
            self._loaded_ids.add(plugin_id)
            self.ctx.bus.log.emit(f"[插件] 已加载 {name}（{path.name}）")
        except Exception:  # noqa: BLE001 - 单个插件失败不影响启动器
            detail = traceback.format_exc()
            self.errors.append((plugin_id, detail))
            last = detail.strip().splitlines()[-1] if detail.strip() else "未知错误"
            self.ctx.bus.log.emit(f"[插件] {plugin_id} 加载失败：{last}")

    # ------------------------------------------------------------------
    def register_page(self, page: PluginPage) -> None:
        self.pages.append(page)
        if self.on_page_added is not None:
            self.on_page_added(page)

    def run_background(
        self,
        fn: Callable[[], object],
        on_done: Callable[[object], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> QThread:
        thread = _TaskThread(fn)
        thread.done.connect(lambda result: on_done(result) if on_done else None)
        thread.failed.connect(lambda message: on_error(message) if on_error else None)
        thread.finished.connect(lambda: self._forget(thread))
        self._threads.append(thread)
        thread.start()
        return thread

    def _forget(self, thread: QThread) -> None:
        if thread in self._threads:
            self._threads.remove(thread)
        thread.deleteLater()

    def shutdown(self) -> None:
        for thread in list(self._threads):
            try:
                thread.wait(800)
            except Exception:  # noqa: BLE001
                pass
        self._threads.clear()
