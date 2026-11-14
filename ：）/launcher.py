"""启动参数构建（兼容 HMCL/官方版本 JSON）与游戏进程管理。"""

from __future__ import annotations

import hashlib
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import APP_NAME, APP_VERSION
from .auth import offline_uuid
from .config import LOG_DIR
from .java import JavaInfo
from .jvm import memory_warning, smart_jvm_args, version_jvm_args
from .version import MergedVersion, VersionError, client_jar_path, logging_file_path

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
CLASSPATH_SEP = ";" if sys.platform == "win32" else ":"


def offline_access_token() -> str:
    return uuid.uuid4().hex


@dataclass
class LaunchOptions:
    version: MergedVersion
    game_dir: Path
    player_name: str
    java: JavaInfo
    root_dir: Path | None = None
    memory_mb: int = 4096
    smart_jvm: bool = True
    pre_touch: bool = True
    fixed_heap: bool = False
    width: int = 0
    height: int = 0
    extra_jvm_args: str = ""
    extra_game_args: str = ""
    uuid: str = ""
    access_token: str = ""
    user_type: str = "legacy"
    authlib_jar: str = ""
    auth_server: str = ""
    auto_connect: bool = False
    server: str = ""
    server_port: int = 25565
    proxy_url: str = ""
    window_title: str = ""
    priority: str = "normal"
    offline: bool = True


def split_server(value: str, default_port: int = 25565) -> tuple[str, int]:
    """解析 ``host`` / ``host:port`` / ``https://host:port`` 形式的服务器地址。"""
    text = (value or "").strip()
    if not text:
        return "", default_port
    if "://" in text:
        text = text.split("://", 1)[1]
    text = text.strip().strip("/")
    if text.startswith("["):
        end = text.find("]")
        if end > 0:
            host = text[1:end]
            rest = text[end + 1:].lstrip(":")
            if rest.isdigit():
                return host, int(rest)
            return host, default_port
    if text.count(":") == 1:
        host, port_text = text.rsplit(":", 1)
        if port_text.isdigit():
            return host, int(port_text)
    return text, default_port


@dataclass
class LaunchPlan:
    command: list[str]
    cwd: Path
    log_path: Path
    classpath: list[str]
    warnings: list[str] = field(default_factory=list)
    summary: str = ""


_GC_SELECTORS = ("G1GC", "ZGC", "ShenandoahGC", "ParallelGC", "SerialGC", "EpsilonGC")


def _has_custom_gc(text: str) -> bool:
    value = text or ""
    return any(
        f"-XX:+Use{gc}" in value or f"-XX:-Use{gc}" in value for gc in _GC_SELECTORS
    )


def _launch_summary(options: LaunchOptions, memory: int, tune_args: list[str]) -> str:
    """用本次实际生效的参数生成一句启动说明（供启动成功提示）。"""
    parts = ["已启用智能 JVM" if options.smart_jvm else "未启用智能 JVM"]
    custom_gc = _has_custom_gc(options.extra_jvm_args)
    if options.smart_jvm:
        gc_flag = next(
            (
                arg[len("-XX:+Use"):]
                for arg in tune_args
                if arg.startswith("-XX:+Use") and arg.endswith("GC")
            ),
            "",
        )
        if custom_gc:
            parts.append("检测到自定义 GC 参数，已跳过自动 GC 覆盖")
        elif gc_flag:
            parts.append(f"使用 {gc_flag}")
        else:
            parts.append("未追加 GC 调优参数")
    else:
        parts.append(
            "使用你自定义的 GC 参数" if custom_gc else "未启用 GC 调优"
        )
    parts.append(f"分配 {memory} MB")
    parts.append("固定堆大小（Xms = Xmx）" if options.fixed_heap else "堆大小可动态扩展")
    return "本次启动：" + "，".join(parts) + "。"


def _split_extra_args(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    try:
        parts = shlex.split(text, posix=False)
    except ValueError:
        parts = text.split()
    cleaned = []
    for part in parts:
        if len(part) >= 2 and part[0] == part[-1] and part[0] in "\"'":
            part = part[1:-1]
        if part:
            cleaned.append(part)
    return cleaned


def _substitute(token: str, values: dict[str, str], warnings: list[str]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in values:
            return values[key]
        warnings.append(f"未识别的启动变量：${{{key}}}")
        return ""

    return re.sub(r"\$\{([^}]+)\}", repl, token)


def proxy_jvm_args(proxy_url: str) -> list[str]:
    """把 HTTP 代理转换为 JVM 参数，让游戏内网络请求也走代理。"""
    text = (proxy_url or "").strip()
    if not text:
        return []
    if "://" not in text:
        text = "http://" + text
    try:
        parsed = urllib.parse.urlsplit(text)
        host = parsed.hostname or ""
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        return []
    if not host:
        return []
    args = ["-Djava.net.useSystemProxies=false"]
    for scheme in ("http", "https"):
        args.append(f"-D{scheme}.proxyHost={host}")
        args.append(f"-D{scheme}.proxyPort={int(port)}")
    if parsed.username:
        user = urllib.parse.unquote(parsed.username)
        password = urllib.parse.unquote(parsed.password or "")
        args.extend(
            [
                f"-Dhttp.proxyUser={user}",
                f"-Dhttp.proxyPassword={password}",
                f"-Dhttps.proxyUser={user}",
                f"-Dhttps.proxyPassword={password}",
            ]
        )
    return args


ISOLATION_MODES = {"mods": {"mods"}, "saves": {"saves"}, "all": {"*"}}
_SHARED_SKIP = {"versions", "libraries", "assets", "logs"}
# 全部隔离时仍需写两份的共享文件夹（皮肤/登录注入器）
_SHARED_FOLDERS = {"customskinloader", "authlib-injector", "libraries"}


def _same_path(a: Path, b: Path) -> bool:
    try:
        left = os.path.normcase(os.path.abspath(a))
        right = os.path.normcase(os.path.abspath(b))
    except OSError:
        return False
    return left == right


def _create_junction(src: Path, dst: Path) -> bool:
    """Windows 下无需管理员权限的目录联接。"""
    try:
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(dst), str(src)],
            capture_output=True,
            creationflags=CREATE_NO_WINDOW,
        )
        return result.returncode == 0 and dst.exists()
    except OSError:
        return False


def _link_shared(src: Path, dst: Path) -> None:
    if dst.exists() or dst.is_symlink():
        return
    try:
        if src.is_dir():
            try:
                os.symlink(src, dst, target_is_directory=True)
            except OSError:
                _create_junction(src, dst)
            return
        try:
            os.link(src, dst)
        except OSError:
            shutil.copy2(src, dst)
    except OSError:
        pass


def isolated_game_dir(root: Path, version_id: str, mode: str) -> Path:
    """返回指定隔离模式下的游戏目录（不会创建文件）。"""
    if mode not in ISOLATION_MODES:
        return root
    return root / "versions" / version_id / "game"


def _ensure_isolated_dirs(root: Path, base: Path, names: set[str]) -> None:
    """确保隔离目录真实存在；若之前被链接到共享目录则先断开。"""
    for name in names:
        target = base / name
        source = root / name
        if target.exists() or target.is_symlink():
            try:
                linked = _same_path(
                    Path(os.path.realpath(target)), Path(os.path.realpath(source))
                )
            except OSError:
                linked = False
            if not linked:
                continue
            try:
                if target.is_symlink():
                    target.unlink()
                else:
                    os.rmdir(target)
            except OSError:
                continue
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass


def prepare_isolated_dir(root: Path, version_id: str, mode: str) -> Path:
    """按隔离模式准备游戏目录；未被隔离的模组/存档等与原目录共享。"""
    if mode not in ISOLATION_MODES:
        return root
    base = isolated_game_dir(root, version_id, mode)
    base.mkdir(parents=True, exist_ok=True)
    if mode == "all":
        return base
    isolated = ISOLATION_MODES[mode]
    _ensure_isolated_dirs(root, base, isolated)
    try:
        entries = list(root.iterdir())
    except OSError:
        return base
    for entry in entries:
        if entry.name in isolated or entry.name in _SHARED_SKIP:
            continue
        if _same_path(entry, base):
            continue
        _link_shared(entry, base / entry.name)
    return base


@dataclass(frozen=True)
class GameDirs:
    """一个版本需要写入的全部目录（主目录 + 隔离目录）。

    隔离判断原来散落在 launcher / page_control / page_download，皮肤、Mod、
    存档、导出脚本各自 if isolation_for(...) 一遍，很容易漏改。
    统一走这里之后，「全部隔离时皮肤要写两份」这类规则只需要写一次。
    """

    root: Path
    version_id: str
    mode: str

    @property
    def isolated(self) -> Path | None:
        if self.mode not in ISOLATION_MODES:
            return None
        return isolated_game_dir(self.root, self.version_id, self.mode)

    @property
    def primary(self) -> Path:
        """启动时作为 --gameDir 使用的目录。"""
        return self.isolated or self.root

    def write_targets(self) -> list[Path]:
        """所有可能需要写入的根目录（主目录 + 隔离目录）。"""
        isolated = self.isolated
        if isolated is None:
            return [self.root]
        return [self.root, isolated]

    def targets(self, folder: str) -> list[Path]:
        """返回某类内容需要写入的子目录。

        全部隔离时，游戏实际只读取隔离目录；只有 CustomSkinLoader 这类
        需要被其他实例共享的内容才同时写主目录一份。
        """
        folder = folder.strip("/\\")
        isolated = self.isolated
        if isolated is None:
            return [self.root / folder]
        if self.mode == "all":
            head = folder.split("/")[0].lower()
            if head in _SHARED_FOLDERS:
                return [self.root / folder, isolated / folder]
            return [isolated / folder]
        scopes = ISOLATION_MODES.get(self.mode, set())
        if folder.split("/")[0].lower() in scopes:
            return [isolated / folder]
        return [self.root / folder]

    def skin_targets(self) -> list[Path]:
        """皮肤写入目标：全部隔离时主目录与隔离目录各一份，其余情况只写主目录。"""
        return self.write_targets() if self.mode == "all" else [self.root]

    def ensure(self) -> Path:
        """按隔离模式创建/链接目录，返回启动目录。"""
        return prepare_isolated_dir(self.root, self.version_id, self.mode)


def resolve_game_dirs(root: Path, version_id: str, mode: str = "none") -> GameDirs:
    """构造 GameDirs；mode 非法时按不隔离处理。"""
    return GameDirs(Path(root), version_id, mode if mode in ISOLATION_MODES else "none")


_WIN_PRIORITIES = {
    "high": 0x80,
    "above_normal": 0x8000,
    "normal": 0x20,
    "below_normal": 0x4000,
    "low": 0x40,
}


def apply_process_priority(pid: int, priority: str) -> bool:
    """调整游戏进程优先级（仅 Windows）。"""
    target = _WIN_PRIORITIES.get(priority or "")
    if sys.platform != "win32" or target is None:
        return False
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x0200, False, int(pid))
        if not handle:
            return False
        try:
            return bool(kernel32.SetPriorityClass(handle, target))
        finally:
            kernel32.CloseHandle(handle)
    except Exception:  # noqa: BLE001
        return False


def rename_game_window(pid: int, title: str, timeout: float = 180.0) -> bool:
    """等待游戏窗口出现后修改其标题（仅 Windows）。"""
    if sys.platform != "win32" or not title:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        matched: dict[str, int] = {}

        def callback(hwnd, _lparam):
            proc_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc_id))
            if proc_id.value == int(pid) and user32.IsWindowVisible(hwnd):
                matched["hwnd"] = int(hwnd or 0)
                return False
            return True

        callback_ref = enum_proc(callback)
        deadline = time.time() + timeout
        while time.time() < deadline:
            user32.EnumWindows(callback_ref, 0)
            hwnd = matched.get("hwnd")
            if hwnd:
                user32.SetWindowTextW(hwnd, title)
                return True
            time.sleep(0.5)
    except Exception:  # noqa: BLE001
        return False
    return False


def has_game_window(pid: int) -> bool:
    """检测该进程是否已创建可见窗口（仅 Windows）。

    非 Windows 或检测出错时返回 True（视为已就绪），避免启动看门狗误报卡死。
    """
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        matched: dict[str, int] = {}

        def callback(hwnd, _lparam):
            proc_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc_id))
            if proc_id.value == int(pid) and user32.IsWindowVisible(hwnd):
                matched["hwnd"] = int(hwnd or 0)
                return False
            return True

        user32.EnumWindows(enum_proc(callback), 0)
        return bool(matched.get("hwnd"))
    except Exception:  # noqa: BLE001
        return True


def process_cpu_seconds(pid: int) -> float | None:
    """读取进程累计 CPU 时间（秒）；非 Windows 或读取失败返回 None。"""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x0400, False, int(pid))  # PROCESS_QUERY_INFORMATION
        if not handle:
            return None
        try:
            created = wintypes.FILETIME()
            exited = wintypes.FILETIME()
            kernel = wintypes.FILETIME()
            user = wintypes.FILETIME()
            ok = kernel32.GetProcessTimes(
                handle,
                ctypes.byref(created),
                ctypes.byref(exited),
                ctypes.byref(kernel),
                ctypes.byref(user),
            )
            if not ok:
                return None
            total = 0
            for item in (kernel, user):
                total += (int(item.dwHighDateTime) << 32) + int(item.dwLowDateTime)
            return total / 10_000_000  # FILETIME 以 100ns 为单位
        finally:
            kernel32.CloseHandle(handle)
    except Exception:  # noqa: BLE001
        return None


def post_launch(process: subprocess.Popen, priority: str = "normal", title: str = "") -> None:
    """启动后应用进程优先级与自定义窗口标题。"""
    apply_process_priority(process.pid, priority)
    if title:
        threading.Thread(
            target=rename_game_window, args=(process.pid, title), daemon=True
        ).start()


_LOADER_CACHE_DIRS = (".fabric", ".quilt")


def clean_loader_cache_temp(*game_dirs: Path) -> tuple[int, int]:
    """清理模组加载器上次中断留下的反混淆临时文件。

    Fabric / Quilt 生成重映射 jar 时先写 ``client-intermediary.jar.tmp``，成功后再
    改名成正式文件。如果上一次启动在重映射阶段被强制结束（点停止、启动器被关、
    断电），``.tmp`` 会留在 ``.fabric/remappedJars`` 里；下次启动 tinyremapper 以
    CREATE_NEW 打开同名文件就会直接抛 ``FileAlreadyExistsException``，表现为
    “error remapping game jars” 导致游戏起不来。

    返回 ``(已删除数量, 被占用数量)``；被占用的通常说明还有残留 Java 进程。
    """
    removed = 0
    failed = 0
    seen: set[str] = set()
    for game_dir in game_dirs:
        for cache_name in _LOADER_CACHE_DIRS:
            folder = Path(game_dir) / cache_name / "remappedJars"
            key = str(folder).lower()
            if key in seen or not folder.is_dir():
                continue
            seen.add(key)
            for temp in folder.rglob("*.tmp"):
                try:
                    temp.unlink()
                except FileNotFoundError:
                    continue
                except OSError:
                    failed += 1
                    continue
                removed += 1
    return removed, failed


def build_launch_plan(options: LaunchOptions) -> LaunchPlan:
    version = options.version
    game_dir = options.game_dir
    root_dir = Path(options.root_dir) if options.root_dir else game_dir
    libraries_dir = root_dir / "libraries"
    assets_dir = root_dir / "assets"
    natives_dir = root_dir / "versions" / version.id / "natives"
    natives_dir.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    # 启动前清掉加载器反混淆缓存里的 .tmp，避免上次异常退出导致本次必崩
    cleaned, locked = clean_loader_cache_temp(game_dir, root_dir)
    if cleaned:
        warnings.append(
            f"已清理上次启动中断残留的加载器临时缓存（{cleaned} 个），本次启动会重新反混淆。"
        )
    if locked:
        warnings.append(
            f"有 {locked} 个加载器缓存临时文件仍被占用：可能还有游戏进程在运行，"
            "请先关闭残留的 Java 进程再启动。"
        )
    classpath: list[str] = []
    missing: list[str] = []
    for lib in version.libraries:
        path = libraries_dir / lib.path
        if path.exists():
            classpath.append(str(path))
        else:
            missing.append(str(path))
    jar = client_jar_path(root_dir, version.jar_id)
    if jar.exists():
        classpath.append(str(jar))
    else:
        missing.append(str(jar))
    if missing:
        preview = "\n".join(missing[:6])
        raise VersionError(
            "启动所需文件缺失，请先在下载页补全或重新安装：\n"
            f"{preview}" + ("\n…" if len(missing) > 6 else "")
        )

    features = {
        "is_demo_user": False,
        "has_custom_resolution": bool(options.width > 0 and options.height > 0),
        "has_quick_plays_support": False,
        "is_quick_play_singleplayer": False,
        "is_quick_play_multiplayer": False,
        "is_quick_play_realms": False,
    }

    asset_index_id = str(version.asset_index.get("id")) if version.asset_index else version.assets_id
    game_assets = assets_dir / "virtual" / asset_index_id
    log_file = logging_file_path(root_dir, version.logging)

    player_uuid = options.uuid or offline_uuid(options.player_name)
    access_token = options.access_token or offline_access_token()
    user_type = options.user_type or ("legacy" if options.offline else "msa")

    values = {
        "auth_player_name": options.player_name,
        "version_name": version.id,
        "game_directory": str(game_dir),
        "assets_root": str(assets_dir),
        "game_assets": str(game_assets if game_assets.exists() else assets_dir),
        "assets_index_name": asset_index_id,
        "auth_uuid": player_uuid,
        "auth_access_token": access_token,
        "auth_session": f"token:{access_token}:{player_uuid}",
        "clientid": "",
        "auth_xuid": "",
        "user_type": user_type,
        "version_type": version.type,
        "natives_directory": str(natives_dir),
        "launcher_name": APP_NAME,
        "launcher_version": APP_VERSION,
        "classpath": CLASSPATH_SEP.join(classpath),
        "classpath_separator": CLASSPATH_SEP,
        "library_directory": str(libraries_dir),
        "resolution_width": str(options.width or 854),
        "resolution_height": str(options.height or 480),
        "path": str(log_file),
    }

    game_args = version.game_args(features)
    if not game_args:
        game_args = [
            "--username", "${auth_player_name}",
            "--version", "${version_name}",
            "--gameDir", "${game_directory}",
            "--assetsDir", "${assets_root}",
            "--assetIndex", "${assets_index_name}",
            "--uuid", "${auth_uuid}",
            "--accessToken", "${auth_access_token}",
            "--userType", "${user_type}",
            "--versionType", "${version_type}",
        ]
    game_args = [_substitute(arg, values, warnings) for arg in game_args]
    game_args.extend(_split_extra_args(options.extra_game_args))

    if options.auto_connect and options.server:
        if "--server" not in game_args:
            game_args.extend(["--server", options.server, "--port", str(options.server_port)])
        else:
            warnings.append("游戏参数已包含 --server，已跳过多服务器自动连接参数。")

    jvm_args = version.jvm_args(features)
    if not jvm_args:
        jvm_args = [
            "-Djava.library.path=${natives_directory}",
            "-cp", "${classpath}",
        ]
    jvm_args = [_substitute(arg, values, warnings) for arg in jvm_args]
    if version.logging and not any("log4j.configurationFile" in arg for arg in jvm_args):
        argument = str(version.logging.get("argument") or "-Dlog4j.configurationFile=${path}")
        if log_file.exists():
            jvm_args.append(_substitute(argument, values, warnings))
        else:
            warnings.append("日志配置文件缺失，未添加 log4j 配置参数（不影响大多数版本）。")

    if not any(arg in ("-cp", "-classpath") for arg in jvm_args):
        jvm_args.extend(["-cp", values["classpath"]])
    if not any(arg.startswith("-Djava.library.path") for arg in jvm_args):
        jvm_args.insert(0, f"-Djava.library.path={natives_dir}")

    memory = max(512, int(options.memory_mb))
    if options.smart_jvm:
        warning = memory_warning(memory)
        if warning:
            warnings.append(warning)
    # 小堆不用把 Xms 拉满，避免启动时一次性提交过多内存；大堆保持较大初始值减少扩容
    # 勾选「固定堆大小」后 Xms 直接等于 Xmx，运行期不再扩堆
    xms = memory if options.fixed_heap else min(memory, 2048)
    heap_args = [f"-Xmx{memory}M", f"-Xms{xms}M"]
    tune_args = (
        smart_jvm_args(
            options.java.major,
            memory,
            options.extra_jvm_args,
            version.id,
            pre_touch=options.pre_touch,
        )
        if options.smart_jvm
        else []
    )
    # 版本兼容参数（旧版栈大小、legacy 排序、Forge 校验、Java 9+ add-opens）始终生效
    compat_args = version_jvm_args(version.id, options.java.major, options.extra_jvm_args)
    agent_args: list[str] = []
    if options.authlib_jar and options.auth_server:
        agent_args = [
            f"-javaagent:{options.authlib_jar}={options.auth_server}",
            "-Dauthlibinjector.side=client",
        ]
    else:
        if options.auth_server and not options.authlib_jar:
            warnings.append("未找到 authlib-injector，外置登录可能无法生效。")
    jvm_args = agent_args + heap_args + tune_args + compat_args + [
        "-Dfile.encoding=UTF-8",
        "-Dstdout.encoding=UTF-8",
        "-Dstderr.encoding=UTF-8",
        "-Dlog4j2.formatMsgNoLookups=true",
        f"-Dminecraft.launcher.brand={APP_NAME}",
        f"-Dminecraft.launcher.version={APP_VERSION}",
    ] + proxy_jvm_args(options.proxy_url) + jvm_args + _split_extra_args(options.extra_jvm_args)

    command = [options.java.path, *jvm_args, version.main_class, *game_args]

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = LOG_DIR / f"game-{version.id}-{stamp}.log"

    return LaunchPlan(
        command=command,
        cwd=game_dir,
        log_path=log_path,
        classpath=classpath,
        warnings=warnings,
        summary=_launch_summary(options, memory, tune_args),
    )


@dataclass
class GameSession:
    process: subprocess.Popen
    log_path: Path
    command: list[str]
    started_at: float = field(default_factory=time.time)
    launch_summary: str = ""
    _reader: threading.Thread | None = None
    _lines: list[str] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def lines(self) -> list[str]:
        with self._lock:
            return list(self._lines)

    def stop(self) -> None:
        if self.process.poll() is None:
            try:
                self.process.terminate()
            except OSError:
                pass


def start_game(
    plan: LaunchPlan,
    on_line: Callable[[str], None] | None = None,
) -> GameSession:
    log_path = plan.log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        process = subprocess.Popen(
            plan.command,
            cwd=str(plan.cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW,
        )
    except OSError as exc:
        raise VersionError(f"无法启动 Java：{exc}\n请检查 Java 路径：{plan.command[0]}") from exc

    session = GameSession(
        process=process,
        log_path=log_path,
        command=plan.command,
        launch_summary=plan.summary,
    )

    def reader() -> None:
        try:
            with open(log_path, "a", encoding="utf-8", errors="replace") as log_file:
                log_file.write(" ".join(plan.command) + "\n\n")
                log_file.flush()
                assert process.stdout is not None
                for raw in iter(process.stdout.readline, b""):
                    line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                    with session._lock:
                        session._lines.append(line)
                        if len(session._lines) > 4000:
                            del session._lines[:1000]
                    log_file.write(line + "\n")
                    log_file.flush()
                    if on_line:
                        try:
                            on_line(line)
                        except Exception:  # noqa: BLE001
                            pass
        except (OSError, ValueError):
            pass

    thread = threading.Thread(target=reader, name="mc-log-reader", daemon=True)
    thread.start()
    session._reader = thread
    return session


def archive_crash_log(session: GameSession, exit_code: int) -> Path | None:
    """游戏异常退出时把本次日志归档到 data/logs/crashes/，便于反馈问题。"""
    if exit_code == 0:
        return None
    try:
        crash_dir = LOG_DIR / "crashes"
        crash_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = crash_dir / f"crash-{stamp}-{session.log_path.stem}.log"
        shutil.copy2(session.log_path, target)
        return target
    except OSError:
        return None


def wait_early_exit(session: GameSession, seconds: float = 2.5) -> tuple[bool, str]:
    """等待片刻，用于捕获“瞬间闪退”（Java 版本错误等）。"""
    deadline = time.time() + seconds
    while time.time() < deadline:
        if session.process.poll() is not None:
            time.sleep(0.15)
            tail = "\n".join(session.lines()[-18:])
            return True, tail
        time.sleep(0.1)
    return False, ""


def crash_hint(exit_code: int, tail: str) -> str:
    hints: list[str] = []
    lower = tail.lower()
    if "unsupportedclassversionerror" in lower or "class file version" in lower:
        hints.append("Java 版本与游戏不匹配，请安装所需 Java（1.17+ 需要 Java 17，1.20.5+ 需要 Java 21）。")
    if "outofmemoryerror" in lower:
        hints.append("内存不足，请在设置中调低分配内存或关闭其他程序。")
    if "error remapping game jars" in lower or "filealreadyexistsexception" in lower:
        hints.append(
            "Fabric/Quilt 反混淆缓存被上次中断的启动占用：请关闭残留的 Java 进程后重试；"
            "启动器已会在启动前自动清理这类 .tmp 缓存。"
        )
    if "could not find or load main class" in lower:
        hints.append("客户端文件不完整或版本 JSON 损坏，请重新安装该版本。")
    if "glfw" in lower or "opengl" in lower or "pixel format" in lower:
        hints.append("显卡驱动可能不支持当前 OpenGL，请更新显卡驱动或更换 Java。")
    if "mod" in lower and ("mixin" in lower or "exception" in lower):
        hints.append("模组冲突或缺失前置，请检查 mods 文件夹。")
    if not hints:
        hints.append("请查看下方日志定位原因；也可尝试更换 Java 或重新补全文件。")
    return f"游戏退出（代码 {exit_code}）。\n" + "\n".join(f"· {h}" for h in hints)
