"""全局配置、目录与下载源定义。"""

from __future__ import annotations

import copy
import json
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import APP_NAME, APP_VERSION

if getattr(sys, "frozen", False):
    APP_ROOT = Path(sys.executable).resolve().parent
else:
    APP_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = APP_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
LOG_DIR = DATA_DIR / "logs"
BROWSER_DIR = DATA_DIR / "browser"
INSTANCES_DIR = DATA_DIR / "instances"
CONFIG_PATH = DATA_DIR / "config.json"

for _d in (DATA_DIR, CACHE_DIR, LOG_DIR, BROWSER_DIR, INSTANCES_DIR):
    _d.mkdir(parents=True, exist_ok=True)

OFFICIAL_MANIFEST = "https://launchermeta.mojang.com/mc/game/version_manifest_v2.json"
BMCLAPI_BASE = "https://bmclapi2.bangbang93.com"
BMCLAPI_MANIFEST = f"{BMCLAPI_BASE}/mc/game/version_manifest_v2.json"

# 内容平台（Modrinth / CurseForge）默认地址与镜像
MODRINTH_API_BASE = "https://api.modrinth.com/v2"
MODRINTH_CDN_BASE = "https://cdn.modrinth.com"
CURSEFORGE_API_BASE = "https://api.curseforge.com/v1"
CURSEFORGE_CDN_HOSTS = ("edge.forgecdn.net", "mediafilez.forgecdn.net")
DEFAULT_CURSEFORGE_API_KEY = (
    "$2a$10$/UCgt8suCFEwQ.BcCi.Wp..QgRMI35CEL2tIVCn9iQZr7yGhbUnNy"
)
DEFAULT_MICROSOFT_CLIENT_ID = "00000000402b5328"
AUTHLIB_INJECTOR_LATEST = "https://authlib-injector.yushi.moe/artifact/latest.json"

SOURCE_MAPPINGS = {
    "bmclapi": "BMCLAPI 兼容（推荐）",
    "direct": "同路径镜像",
    "none": "不重写（仅用于清单）",
}


def default_game_dir() -> Path:
    """默认使用官方/HMCL 通用的 %APPDATA%\\.minecraft。"""
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / ".minecraft"
    return Path.home() / ".minecraft"


@dataclass
class DownloadSource:
    id: str
    name: str
    manifest_url: str
    mapping: str = "none"
    download_base: str = ""
    api_key_header: str = "X-API-Key"
    api_key: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    priority: int = 100
    builtin: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "manifest_url": self.manifest_url,
            "mapping": self.mapping,
            "download_base": self.download_base,
            "api_key_header": self.api_key_header,
            "api_key": self.api_key,
            "headers": dict(self.headers),
            "enabled": self.enabled,
            "priority": self.priority,
            "builtin": self.builtin,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], fallback_id: str = "") -> "DownloadSource":
        headers = data.get("headers") or {}
        if not isinstance(headers, dict):
            headers = {}
        return cls(
            id=str(data.get("id") or fallback_id),
            name=str(data.get("name") or "未命名源"),
            manifest_url=str(data.get("manifest_url") or ""),
            mapping=str(data.get("mapping") or "none"),
            download_base=str(data.get("download_base") or ""),
            api_key_header=str(data.get("api_key_header") or "X-API-Key"),
            api_key=str(data.get("api_key") or ""),
            headers={str(k): str(v) for k, v in headers.items()},
            enabled=bool(data.get("enabled", True)),
            priority=int(data.get("priority", 100) or 100),
            builtin=bool(data.get("builtin", False)),
        )

    def request_headers(self) -> dict[str, str]:
        headers = {str(k): str(v) for k, v in self.headers.items()}
        if self.api_key.strip():
            headers[self.api_key_header.strip() or "X-API-Key"] = self.api_key.strip()
        return headers

    def copy_new_id(self, new_id: str) -> "DownloadSource":
        data = self.to_dict()
        data.update({"id": new_id, "builtin": False})
        return DownloadSource.from_dict(data, new_id)


def builtin_sources() -> list[DownloadSource]:
    return [
        DownloadSource(
            id="official",
            name="Mojang 官方源",
            manifest_url=OFFICIAL_MANIFEST,
            mapping="none",
            priority=10,
            builtin=True,
        ),
        DownloadSource(
            id="bmclapi",
            name="BMCLAPI 镜像（国内加速）",
            manifest_url=BMCLAPI_MANIFEST,
            mapping="bmclapi",
            download_base=BMCLAPI_BASE,
            priority=20,
            builtin=True,
        ),
    ]


ISOLATION_LABELS = {
    "none": "不隔离（共用模组与存档）",
    "mods": "仅隔离模组（mods 独立）",
    "saves": "仅隔离存档（saves 独立）",
    "all": "全部隔离（独立游戏目录）",
}
PROCESS_PRIORITIES = {
    "high": "高",
    "above_normal": "高于正常",
    "normal": "正常",
    "below_normal": "低于正常",
    "low": "低",
}
AFTER_LAUNCH_ACTIONS = {
    "nothing": "启动后保持显示",
    "hide": "启动后隐藏启动器",
    "close": "启动后关闭启动器",
}


@dataclass
class GameDir:
    """一个 Minecraft 数据目录（可添加多个并快速切换）。"""

    id: str
    name: str
    path: str

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "path": self.path}

    @classmethod
    def from_dict(cls, data: dict[str, Any], fallback_id: str = "") -> "GameDir":
        return cls(
            id=str(data.get("id") or fallback_id),
            name=str(data.get("name") or "未命名目录"),
            path=str(data.get("path") or ""),
        )


@dataclass
class VersionSettings:
    """单个 Minecraft 版本的启动覆盖项，空值表示跟随全局设置。"""

    isolation: str = ""
    extra_jvm_args: str = ""
    extra_game_args: str = ""
    auto_connect: bool = False
    server: str = ""
    port: int = 25565
    window_title: str = ""
    memory_mb: int = 0
    priority: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "isolation": self.isolation,
            "extra_jvm_args": self.extra_jvm_args,
            "extra_game_args": self.extra_game_args,
            "auto_connect": bool(self.auto_connect),
            "server": self.server,
            "port": int(self.port),
            "window_title": self.window_title,
            "memory_mb": int(self.memory_mb),
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VersionSettings":
        try:
            port = int(data.get("port") or 25565)
        except (TypeError, ValueError):
            port = 25565
        try:
            memory = int(data.get("memory_mb") or 0)
        except (TypeError, ValueError):
            memory = 0
        return cls(
            isolation=str(data.get("isolation") or ""),
            extra_jvm_args=str(data.get("extra_jvm_args") or ""),
            extra_game_args=str(data.get("extra_game_args") or ""),
            auto_connect=bool(data.get("auto_connect", False)),
            server=str(data.get("server") or ""),
            port=port,
            window_title=str(data.get("window_title") or ""),
            memory_mb=max(0, memory),
            priority=str(data.get("priority") or ""),
        )


@dataclass
class Instance:
    """独立游戏实例（整合包或手动创建），拥有自己的 .minecraft 目录结构。"""

    id: str
    name: str
    game_dir: str
    version_id: str = ""
    loader: str = ""
    mc_version: str = ""
    modpack: str = ""
    loader_version: str = ""
    memory_mb: int = 0
    window_title: str = ""
    extra_jvm_args: str = ""
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "game_dir": self.game_dir,
            "version_id": self.version_id,
            "loader": self.loader,
            "mc_version": self.mc_version,
            "modpack": self.modpack,
            "loader_version": self.loader_version,
            "memory_mb": int(self.memory_mb),
            "window_title": self.window_title,
            "extra_jvm_args": self.extra_jvm_args,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], fallback_id: str = "") -> "Instance":
        try:
            memory_mb = int(data.get("memory_mb") or 0)
        except (TypeError, ValueError):
            memory_mb = 0
        return cls(
            id=str(data.get("id") or fallback_id),
            name=str(data.get("name") or "未命名实例"),
            game_dir=str(data.get("game_dir") or ""),
            version_id=str(data.get("version_id") or ""),
            loader=str(data.get("loader") or ""),
            mc_version=str(data.get("mc_version") or ""),
            modpack=str(data.get("modpack") or ""),
            loader_version=str(data.get("loader_version") or ""),
            memory_mb=memory_mb,
            window_title=str(data.get("window_title") or ""),
            extra_jvm_args=str(data.get("extra_jvm_args") or ""),
            created_at=float(data.get("created_at") or 0.0),
        )


@dataclass
class ServerEntry:
    """收藏的服务器地址，供主页快速选择并自动连接。"""

    id: str
    name: str
    host: str
    port: int = 25565
    note: str = ""
    favorite: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "host": self.host,
            "port": int(self.port),
            "note": self.note,
            "favorite": bool(self.favorite),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], fallback_id: str = "") -> "ServerEntry":
        try:
            port = int(data.get("port") or 25565)
        except (TypeError, ValueError):
            port = 25565
        return cls(
            id=str(data.get("id") or fallback_id),
            name=str(data.get("name") or data.get("host") or "未命名服务器"),
            host=str(data.get("host") or ""),
            port=min(65535, max(1, port)),
            note=str(data.get("note") or ""),
            favorite=bool(data.get("favorite", False)),
        )


@dataclass
class Config:
    game_dir: str = field(default_factory=lambda: str(default_game_dir()))
    game_dirs: list[GameDir] = field(
        default_factory=lambda: [
            GameDir(id="default", name="默认目录", path=str(default_game_dir()))
        ]
    )
    active_game_dir: str = "default"
    player_name: str = "Steve"
    java_path: str = ""
    memory_mb: int = 4096
    width: int = 0
    height: int = 0
    extra_jvm_args: str = ""
    extra_game_args: str = ""
    hide_after_launch: bool = False
    after_launch_action: str = "nothing"
    keep_launcher_on_game_exit: bool = True
    close_to_tray: bool = False
    selected_source_id: str = "official"
    sources: list[DownloadSource] = field(default_factory=builtin_sources)

    # ---- 版本隔离与单版本设置 ----
    isolation_mode: str = "none"
    process_priority: str = "normal"
    window_title: str = ""
    version_settings: dict[str, VersionSettings] = field(default_factory=dict)

    # ---- 代理 ----
    proxy_enabled: bool = False
    proxy_url: str = ""
    proxy_jvm: bool = True

    # ---- 多人游戏 / 自动连服 ----
    auto_connect_enabled: bool = False
    auto_connect_server: str = ""
    auto_connect_port: int = 25565
    servers: list[ServerEntry] = field(default_factory=list)
    active_server_id: str = ""

    # ---- 内容平台与镜像 ----
    modrinth_api_base: str = MODRINTH_API_BASE
    modrinth_cdn_mirror: str = ""
    curseforge_api_base: str = CURSEFORGE_API_BASE
    curseforge_api_key: str = DEFAULT_CURSEFORGE_API_KEY
    curseforge_cdn_mirror: str = ""
    download_threads: int = 16

    # ---- 账号 / 外置登录 ----
    selected_account_id: str = ""
    microsoft_client_id: str = DEFAULT_MICROSOFT_CLIENT_ID
    authlib_injector_url: str = AUTHLIB_INJECTOR_LATEST
    authlib_injector_path: str = ""

    # ---- 实例 ----
    instances: list[Instance] = field(default_factory=list)
    selected_instance_id: str = "default"
    default_version_id: str = ""

    # ---- 运行时 ----
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def source_list(self) -> list[DownloadSource]:
        """启用中的源，按 priority 升序。"""
        return sorted(
            [s for s in self.sources if s.enabled and s.manifest_url],
            key=lambda s: (s.priority, s.name),
        )

    def get_source(self, source_id: str) -> DownloadSource | None:
        for source in self.sources:
            if source.id == source_id:
                return source
        return None

    def select_source(self, source_id: str) -> None:
        if self.get_source(source_id):
            self.selected_source_id = source_id
            self.save()

    @property
    def game_path(self) -> Path:
        return Path(os.path.expandvars(self.game_dir)).expanduser()

    @property
    def versions_path(self) -> Path:
        return self.game_path / "versions"

    @property
    def libraries_path(self) -> Path:
        return self.game_path / "libraries"

    @property
    def assets_path(self) -> Path:
        return self.game_path / "assets"

    # ------------------------------------------------------------------
    # 数据目录切换
    def active_game_entry(self) -> GameDir:
        for entry in self.game_dirs:
            if entry.id == self.active_game_dir:
                return entry
        if self.game_dirs:
            return self.game_dirs[0]
        entry = GameDir(id="default", name="默认目录", path=str(default_game_dir()))
        self.game_dirs = [entry]
        return entry

    def select_game_dir(self, dir_id: str) -> bool:
        for entry in self.game_dirs:
            if entry.id == dir_id and entry.path:
                self.active_game_dir = dir_id
                self.game_dir = entry.path
                self.save()
                return True
        return False

    def new_game_dir_id(self) -> str:
        used = {entry.id for entry in self.game_dirs}
        n = 1
        while f"dir_{n}" in used:
            n += 1
        return f"dir_{n}"

    def add_game_dir(self, name: str, path: str) -> GameDir:
        entry = GameDir(id=self.new_game_dir_id(), name=name or "新目录", path=str(Path(path)))
        self.game_dirs.append(entry)
        self.save()
        return entry

    def remove_game_dir(self, dir_id: str) -> bool:
        if len(self.game_dirs) <= 1:
            return False
        remaining = [entry for entry in self.game_dirs if entry.id != dir_id]
        if len(remaining) == len(self.game_dirs):
            return False
        self.game_dirs = remaining
        if self.active_game_dir == dir_id:
            self.active_game_dir = remaining[0].id
            self.game_dir = remaining[0].path
        self.save()
        return True

    # ------------------------------------------------------------------
    # 单版本设置
    def version_setting(self, version_id: str) -> VersionSettings:
        return self.version_settings.get(version_id) or VersionSettings()

    def ensure_version_setting(self, version_id: str) -> VersionSettings:
        setting = self.version_settings.get(version_id)
        if setting is None:
            setting = VersionSettings()
            self.version_settings[version_id] = setting
        return setting

    def isolation_for(self, version_id: str) -> str:
        setting = self.version_settings.get(version_id)
        mode = (setting.isolation if setting and setting.isolation else self.isolation_mode) or "none"
        return mode if mode in ISOLATION_LABELS else "none"

    @property
    def effective_proxy(self) -> str:
        return self.proxy_url.strip() if self.proxy_enabled else ""

    # ------------------------------------------------------------------
    # 服务器列表
    def new_server_id(self) -> str:
        used = {entry.id for entry in self.servers}
        n = 1
        while f"server_{n}" in used:
            n += 1
        return f"server_{n}"

    def add_server(self, name: str, host: str, port: int = 25565, note: str = "") -> ServerEntry:
        entry = ServerEntry(
            id=self.new_server_id(),
            name=name or host or "新服务器",
            host=(host or "").strip(),
            port=int(port or 25565),
            note=note,
        )
        self.servers.append(entry)
        self.save()
        return entry

    def remove_server(self, server_id: str) -> bool:
        remaining = [entry for entry in self.servers if entry.id != server_id]
        if len(remaining) == len(self.servers):
            return False
        self.servers = remaining
        if self.active_server_id == server_id:
            self.active_server_id = ""
        self.save()
        return True

    def active_server(self) -> ServerEntry | None:
        for entry in self.servers:
            if entry.id == self.active_server_id:
                return entry
        return None

    # ------------------------------------------------------------------
    # 实例
    def default_instance(self) -> Instance:
        return Instance(
            id="default",
            name="默认实例",
            game_dir=str(self.game_path),
            version_id=self.default_version_id,
            modpack="",
        )

    def instance_list(self) -> list[Instance]:
        result = [self.default_instance()]
        result.extend(i for i in self.instances if i.id != "default" and i.game_dir)
        return result

    def get_instance(self, instance_id: str) -> Instance | None:
        for instance in self.instance_list():
            if instance.id == instance_id:
                return instance
        return None

    def selected_instance(self) -> Instance:
        return self.get_instance(self.selected_instance_id) or self.default_instance()

    def instance_path(self, instance_id: str) -> Path:
        instance = self.get_instance(instance_id)
        if instance:
            return Path(os.path.expandvars(instance.game_dir)).expanduser()
        return self.game_path

    def select_instance(self, instance_id: str) -> None:
        if self.get_instance(instance_id):
            self.selected_instance_id = instance_id
            self.save()

    def new_instance_id(self) -> str:
        used = {"default"} | {i.id for i in self.instances}
        n = 1
        while f"instance_{n}" in used:
            n += 1
        return f"instance_{n}"

    def add_instance(
        self,
        name: str,
        game_dir: str,
        version_id: str = "",
        loader: str = "",
        mc_version: str = "",
        modpack: str = "",
        loader_version: str = "",
        memory_mb: int = 0,
        window_title: str = "",
        extra_jvm_args: str = "",
    ) -> Instance:
        instance = Instance(
            id=self.new_instance_id(),
            name=name or "新实例",
            game_dir=str(Path(game_dir)),
            version_id=version_id,
            loader=loader,
            mc_version=mc_version,
            modpack=modpack,
            loader_version=loader_version,
            memory_mb=int(memory_mb or 0),
            window_title=window_title,
            extra_jvm_args=extra_jvm_args,
            created_at=time.time(),
        )
        self.instances.append(instance)
        self.save()
        return instance

    def remove_instance(self, instance_id: str) -> None:
        if instance_id == "default":
            return
        self.instances = [i for i in self.instances if i.id != instance_id]
        if self.selected_instance_id == instance_id:
            self.selected_instance_id = "default"
        self.save()

    def with_game_dir(self, game_dir: str | Path) -> "Config":
        """复制一份配置用于指定目录的安装，不影响当前选择。"""
        clone = Config(
            game_dir=str(game_dir),
            game_dirs=[GameDir(id="default", name="安装目标", path=str(game_dir))],
            active_game_dir="default",
            player_name=self.player_name,
            java_path=self.java_path,
            memory_mb=self.memory_mb,
            width=self.width,
            height=self.height,
            extra_jvm_args=self.extra_jvm_args,
            extra_game_args=self.extra_game_args,
            hide_after_launch=self.hide_after_launch,
            after_launch_action=self.after_launch_action,
            keep_launcher_on_game_exit=self.keep_launcher_on_game_exit,
            close_to_tray=self.close_to_tray,
            selected_source_id=self.selected_source_id,
            sources=list(self.sources),
            isolation_mode=self.isolation_mode,
            process_priority=self.process_priority,
            window_title=self.window_title,
            proxy_enabled=self.proxy_enabled,
            proxy_url=self.proxy_url,
            proxy_jvm=self.proxy_jvm,
            auto_connect_enabled=self.auto_connect_enabled,
            auto_connect_server=self.auto_connect_server,
            auto_connect_port=self.auto_connect_port,
            modrinth_api_base=self.modrinth_api_base,
            modrinth_cdn_mirror=self.modrinth_cdn_mirror,
            curseforge_api_base=self.curseforge_api_base,
            curseforge_api_key=self.curseforge_api_key,
            curseforge_cdn_mirror=self.curseforge_cdn_mirror,
            download_threads=self.download_threads,
            selected_account_id=self.selected_account_id,
            microsoft_client_id=self.microsoft_client_id,
            authlib_injector_url=self.authlib_injector_url,
            authlib_injector_path=self.authlib_injector_path,
        )
        return clone

    def save(self) -> None:
        with self._lock:
            data = {
                "config_version": 3,
                "app_version": APP_VERSION,
                "game_dir": self.game_dir,
                "game_dirs": [entry.to_dict() for entry in self.game_dirs],
                "active_game_dir": self.active_game_dir,
                "player_name": self.player_name,
                "java_path": self.java_path,
                "memory_mb": int(self.memory_mb),
                "width": int(self.width),
                "height": int(self.height),
                "extra_jvm_args": self.extra_jvm_args,
                "extra_game_args": self.extra_game_args,
                "hide_after_launch": bool(self.hide_after_launch),
                "after_launch_action": self.after_launch_action,
                "keep_launcher_on_game_exit": bool(self.keep_launcher_on_game_exit),
                "close_to_tray": bool(self.close_to_tray),
                "selected_source_id": self.selected_source_id,
                "sources": [s.to_dict() for s in self.sources],
                "isolation_mode": self.isolation_mode,
                "process_priority": self.process_priority,
                "window_title": self.window_title,
                "version_settings": {
                    str(key): value.to_dict()
                    for key, value in self.version_settings.items()
                },
                "proxy_enabled": bool(self.proxy_enabled),
                "proxy_url": self.proxy_url,
                "proxy_jvm": bool(self.proxy_jvm),
                "auto_connect_enabled": bool(self.auto_connect_enabled),
                "auto_connect_server": self.auto_connect_server,
                "auto_connect_port": int(self.auto_connect_port),
                "servers": [entry.to_dict() for entry in self.servers],
                "active_server_id": self.active_server_id,
                "modrinth_api_base": self.modrinth_api_base,
                "modrinth_cdn_mirror": self.modrinth_cdn_mirror,
                "curseforge_api_base": self.curseforge_api_base,
                "curseforge_api_key": self.curseforge_api_key,
                "curseforge_cdn_mirror": self.curseforge_cdn_mirror,
                "download_threads": int(self.download_threads),
                "selected_account_id": self.selected_account_id,
                "microsoft_client_id": self.microsoft_client_id,
                "authlib_injector_url": self.authlib_injector_url,
                "authlib_injector_path": self.authlib_injector_path,
                "instances": [i.to_dict() for i in self.instances],
                "selected_instance_id": self.selected_instance_id,
                "default_version_id": self.default_version_id,
            }
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = CONFIG_PATH.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, CONFIG_PATH)

    def save_debounced(self, delay: float = 0.4) -> None:
        """高频设置变更（输入框、滑块）合并写盘，退出时仍用同步 save()。"""
        timer = getattr(self, "_save_timer", None)
        if timer is not None:
            timer.cancel()
        timer = threading.Timer(delay, self.save)
        timer.daemon = True
        self._save_timer = timer
        timer.start()

    @classmethod
    def load(cls) -> "Config":
        cfg = cls()
        if not CONFIG_PATH.exists():
            cfg.save()
            return cfg
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cfg

        cfg.game_dir = str(data.get("game_dir") or cfg.game_dir)
        raw_dirs = data.get("game_dirs")
        loaded_dirs: list[GameDir] = []
        if isinstance(raw_dirs, list):
            for index, raw in enumerate(raw_dirs):
                if isinstance(raw, dict) and str(raw.get("path") or "").strip():
                    loaded_dirs.append(GameDir.from_dict(raw, fallback_id=f"dir_{index + 1}"))
        if not loaded_dirs:
            loaded_dirs = [GameDir(id="default", name="默认目录", path=cfg.game_dir)]
        # 去重并保证 id 唯一
        seen_ids: set[str] = set()
        seen_paths: set[str] = set()
        unique_dirs: list[GameDir] = []
        for entry in loaded_dirs:
            key = os.path.normcase(os.path.normpath(entry.path))
            if key in seen_paths:
                continue
            base_id = entry.id or f"dir_{len(unique_dirs) + 1}"
            new_id = base_id
            suffix = 1
            while new_id in seen_ids:
                suffix += 1
                new_id = f"{base_id}_{suffix}"
            entry.id = new_id
            seen_ids.add(new_id)
            seen_paths.add(key)
            unique_dirs.append(entry)
        cfg.game_dirs = unique_dirs
        cfg.active_game_dir = str(data.get("active_game_dir") or unique_dirs[0].id)
        active = next(
            (entry for entry in unique_dirs if entry.id == cfg.active_game_dir), unique_dirs[0]
        )
        cfg.active_game_dir = active.id
        cfg.game_dir = active.path
        cfg.player_name = str(data.get("player_name") or cfg.player_name)
        cfg.java_path = str(data.get("java_path") or "")
        try:
            cfg.memory_mb = max(512, int(data.get("memory_mb", cfg.memory_mb)))
        except (TypeError, ValueError):
            cfg.memory_mb = 4096
        cfg.width = int(data.get("width") or 0)
        cfg.height = int(data.get("height") or 0)
        cfg.extra_jvm_args = str(data.get("extra_jvm_args") or "")
        cfg.extra_game_args = str(data.get("extra_game_args") or "")
        cfg.hide_after_launch = bool(data.get("hide_after_launch", False))
        cfg.keep_launcher_on_game_exit = bool(data.get("keep_launcher_on_game_exit", True))
        cfg.close_to_tray = bool(data.get("close_to_tray", False))
        cfg.after_launch_action = str(data.get("after_launch_action") or "")
        if cfg.after_launch_action not in AFTER_LAUNCH_ACTIONS:
            cfg.after_launch_action = "hide" if cfg.hide_after_launch else "nothing"
        cfg.isolation_mode = str(data.get("isolation_mode") or "none")
        if cfg.isolation_mode not in ISOLATION_LABELS:
            cfg.isolation_mode = "none"
        cfg.process_priority = str(data.get("process_priority") or "normal")
        if cfg.process_priority not in PROCESS_PRIORITIES:
            cfg.process_priority = "normal"
        cfg.window_title = str(data.get("window_title") or "")
        cfg.proxy_enabled = bool(data.get("proxy_enabled", False))
        cfg.proxy_url = str(data.get("proxy_url") or "")
        cfg.proxy_jvm = bool(data.get("proxy_jvm", True))
        raw_version_settings = data.get("version_settings")
        if isinstance(raw_version_settings, dict):
            for key, raw in raw_version_settings.items():
                if isinstance(raw, dict):
                    cfg.version_settings[str(key)] = VersionSettings.from_dict(raw)
        cfg.selected_source_id = str(data.get("selected_source_id") or "official")

        cfg.auto_connect_enabled = bool(data.get("auto_connect_enabled", False))
        cfg.auto_connect_server = str(data.get("auto_connect_server") or "")
        try:
            cfg.auto_connect_port = int(data.get("auto_connect_port") or 25565)
        except (TypeError, ValueError):
            cfg.auto_connect_port = 25565

        raw_servers = data.get("servers")
        loaded_servers: list[ServerEntry] = []
        if isinstance(raw_servers, list):
            for index, raw in enumerate(raw_servers):
                if isinstance(raw, dict) and str(raw.get("host") or "").strip():
                    loaded_servers.append(
                        ServerEntry.from_dict(raw, fallback_id=f"server_{index + 1}")
                    )
        cfg.servers = loaded_servers
        cfg.active_server_id = str(data.get("active_server_id") or "")
        if cfg.active_server_id and cfg.active_server() is None:
            cfg.active_server_id = ""

        cfg.modrinth_api_base = str(data.get("modrinth_api_base") or MODRINTH_API_BASE)
        cfg.modrinth_cdn_mirror = str(data.get("modrinth_cdn_mirror") or "")
        cfg.curseforge_api_base = str(data.get("curseforge_api_base") or CURSEFORGE_API_BASE)
        cfg.curseforge_api_key = str(
            data.get("curseforge_api_key") or DEFAULT_CURSEFORGE_API_KEY
        )
        cfg.curseforge_cdn_mirror = str(data.get("curseforge_cdn_mirror") or "")
        try:
            cfg.download_threads = max(1, min(64, int(data.get("download_threads") or 16)))
        except (TypeError, ValueError):
            cfg.download_threads = 16

        cfg.selected_account_id = str(data.get("selected_account_id") or "")
        cfg.microsoft_client_id = str(
            data.get("microsoft_client_id") or DEFAULT_MICROSOFT_CLIENT_ID
        )
        cfg.authlib_injector_url = str(
            data.get("authlib_injector_url") or AUTHLIB_INJECTOR_LATEST
        )
        cfg.authlib_injector_path = str(data.get("authlib_injector_path") or "")

        raw_instances = data.get("instances")
        if isinstance(raw_instances, list):
            for i, raw in enumerate(raw_instances):
                if isinstance(raw, dict) and raw.get("id") != "default":
                    cfg.instances.append(
                        Instance.from_dict(raw, fallback_id=f"instance_{i + 1}")
                    )
        cfg.selected_instance_id = str(data.get("selected_instance_id") or "default")
        cfg.default_version_id = str(data.get("default_version_id") or "")
        if not cfg.get_instance(cfg.selected_instance_id):
            cfg.selected_instance_id = "default"

        loaded_sources: list[DownloadSource] = []
        raw_sources = data.get("sources")
        if isinstance(raw_sources, list):
            for i, raw in enumerate(raw_sources):
                if not isinstance(raw, dict):
                    continue
                source = DownloadSource.from_dict(raw, fallback_id=f"custom_{i + 1}")
                source.builtin = source.id in {"official", "bmclapi"}
                if source.builtin:
                    if source.id == "official":
                        source.manifest_url = source.manifest_url or OFFICIAL_MANIFEST
                        source.mapping = "none"
                        source.name = "Mojang 官方源" if source.id == "official" else source.name
                    else:
                        source.manifest_url = source.manifest_url or BMCLAPI_MANIFEST
                        source.mapping = "bmclapi"
                        source.download_base = source.download_base or BMCLAPI_BASE
                        source.name = source.name or "BMCLAPI 镜像（国内加速）"
                loaded_sources.append(source)
        cfg.sources = loaded_sources or builtin_sources()

        # 补齐内置源，避免用户误删后失去官方/镜像能力
        for builtin in builtin_sources():
            if not any(s.id == builtin.id for s in cfg.sources):
                cfg.sources.insert(0, builtin)

        # 保证优先级唯一且递增，便于排序显示
        cfg.sources.sort(key=lambda s: s.priority)
        for index, source in enumerate(cfg.sources, start=1):
            if source.priority <= 0 or source.priority > 999:
                source.priority = index * 10
        if not cfg.get_source(cfg.selected_source_id):
            cfg.selected_source_id = cfg.sources[0].id if cfg.sources else "official"
        return cfg

    def new_source_id(self) -> str:
        used = {s.id for s in self.sources}
        n = 1
        while f"custom_{n}" in used:
            n += 1
        return f"custom_{n}"

    def clone_source(self, source: DownloadSource) -> DownloadSource:
        data = copy.deepcopy(source.to_dict())
        data.update({"id": self.new_source_id(), "name": source.name + " 副本", "builtin": False})
        return DownloadSource.from_dict(data)


INSTANCE_MANIFEST = "instance.json"


def write_instance_manifest(instance: Instance, game_dir: str | Path) -> Path:
    """在实例目录写入可分享/恢复的 instance.json。"""
    folder = Path(game_dir)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / INSTANCE_MANIFEST
    payload = {"format": "mikan/1", "instance": instance.to_dict()}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def read_instance_manifest(folder: str | Path) -> dict[str, Any] | None:
    path = Path(folder) / INSTANCE_MANIFEST
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


__all__ = [
    "APP_ROOT",
    "DATA_DIR",
    "CACHE_DIR",
    "LOG_DIR",
    "BROWSER_DIR",
    "INSTANCES_DIR",
    "CONFIG_PATH",
    "INSTANCE_MANIFEST",
    "write_instance_manifest",
    "read_instance_manifest",
    "DownloadSource",
    "GameDir",
    "ServerEntry",
    "VersionSettings",
    "Instance",
    "Config",
    "builtin_sources",
    "default_game_dir",
    "ISOLATION_LABELS",
    "PROCESS_PRIORITIES",
    "AFTER_LAUNCH_ACTIONS",
    "OFFICIAL_MANIFEST",
    "BMCLAPI_BASE",
    "BMCLAPI_MANIFEST",
    "SOURCE_MAPPINGS",
    "MODRINTH_API_BASE",
    "MODRINTH_CDN_BASE",
    "CURSEFORGE_API_BASE",
    "CURSEFORGE_CDN_HOSTS",
    "DEFAULT_CURSEFORGE_API_KEY",
    "DEFAULT_MICROSOFT_CLIENT_ID",
    "AUTHLIB_INJECTOR_LATEST",
]
