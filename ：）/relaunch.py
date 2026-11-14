"""重启启动器：用干净环境拉起新实例，再让当前进程退出。

PyInstaller 6 的 onefile 引导器会把自己的解包目录写进环境变量
``_PYI_APPLICATION_HOME_DIR``（还有 ``_PYI_ARCHIVE_FILE`` /
``_PYI_PARENT_PROCESS_LEVEL`` / ``_PYI_SPLASH_IPC``）。这些变量会被子进程继承，
新实例的引导器据此认为自己是同一个 onefile 进程的子进程，直接复用父进程的
``_MEIxxxx`` 临时目录；父进程退出时该目录被删除，新实例于是弹出

    Failed to load Python DLL '...\\_MEIxxxx\\python315.dll'
    LoadLibrary: 找不到指定的模块。

手动双击 exe 之所以正常，是因为资源管理器给的是干净环境。所以「程序内重启」
「独立版交还主启动器」等所有交接路径都必须先清掉这些变量。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# PyInstaller onefile 的运行时变量；_MEIPASS2 是旧版本 / 其他打包工具的写法
RUNTIME_ENV_KEYS = (
    "_PYI_APPLICATION_HOME_DIR",
    "_PYI_ARCHIVE_FILE",
    "_PYI_PARENT_PROCESS_LEVEL",
    "_PYI_SPLASH_IPC",
    "_MEIPASS",
    "_MEIPASS2",
)


def clean_env(source: dict[str, str] | None = None) -> dict[str, str]:
    """返回剔除 onefile 运行时变量后的环境副本。"""
    env = dict(os.environ if source is None else source)
    for key in RUNTIME_ENV_KEYS:
        env.pop(key, None)
    if getattr(sys, "frozen", False):
        # 打包后不能把父进程的 Python 路径带给新进程
        for key in ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP"):
            env.pop(key, None)
    return env


def launch_command() -> tuple[list[str], str]:
    """返回（启动命令行, 工作目录）。打包后是自身 exe，源码运行是 python run.py。"""
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        return [str(exe), *sys.argv[1:]], str(exe.parent)
    root = Path(__file__).resolve().parent.parent
    return [sys.executable, str(root / "run.py"), *sys.argv[1:]], str(root)


def spawn_restart(delay: float = 2.5) -> bool:
    """延迟拉起新实例，避开单实例锁竞争；返回是否已提交启动请求。

    单文件 exe 退出时还要清理几百 MB 的临时解包目录，锁释放得比普通程序晚，
    所以默认留 3 秒再拉起新实例。
    """
    target, cwd = launch_command()
    env = clean_env()
    if os.name == "nt":
        # ping 每秒一次当延时用（timeout 依赖控制台输入，在分离进程里会失败）。
        # start 后面必须是带引号的空标题 ""，否则第一个参数会被当成要运行的程序。
        count = max(2, int(round(delay)) + 1)
        command = (
            f'cmd /c ping -n {count} 127.0.0.1 >nul & start "" '
            + subprocess.list2cmdline(target)
        )
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
        try:
            subprocess.Popen(
                command, cwd=cwd, env=env, close_fds=True, creationflags=flags
            )
        except OSError:
            return False
        return True
    try:
        subprocess.Popen(
            target, cwd=cwd, env=env, start_new_session=True, close_fds=True
        )
    except OSError:
        return False
    return True
