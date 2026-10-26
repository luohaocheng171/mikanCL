"""Forbric 安装后台线程：拉取安装器 → 下载 → 启动官方 GUI → 轮询版本文件。"""

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ..context import AppContext
from ..forbric import (
    FORBRIC_TIMEOUT,
    FORBRIC_VERSION_ID,
    download_installer,
    fetch_latest_installer,
    launch_installer,
    wait_for_version,
)


class ForbricWorker(QThread):
    log = Signal(str)
    progress = Signal(float, str)
    done = Signal(str)
    failed = Signal(str)

    def __init__(
        self, ctx: AppContext, instance_id: str, game_dir: str, java_path: str, parent=None
    ):
        super().__init__(parent)
        self.ctx = ctx
        self.instance_id = instance_id
        self.game_dir = game_dir
        self.java_path = java_path
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        """只标记取消事件，不杀进程（由 run 收尾清理）。"""
        self.cancel_event.set()

    def run(self) -> None:
        process: subprocess.Popen | None = None
        try:
            self.progress.emit(0.05, "获取最新安装器信息…")
            jar_url, bat_url = fetch_latest_installer()
            self.log.emit(f"[Forbric] 最新安装器：{jar_url}")

            self.progress.emit(0.1, "下载安装器中…")
            jar_path = download_installer(jar_url, bat_url, log=self.log.emit)
            self.progress.emit(0.4, "安装器下载完成")
            self.log.emit(f"[Forbric] 安装器已保存：{jar_path}")

            self.progress.emit(0.5, "官方安装器窗口已弹出，请在窗口里点击 Install")
            process = launch_installer(jar_path, self.java_path, log=self.log.emit)

            self.progress.emit(0.6, "等待官方安装器写入版本文件…")
            outcome: list = []

            def _wait() -> None:
                try:
                    outcome.append(
                        wait_for_version(
                            Path(self.game_dir), self.cancel_event, log=self.log.emit
                        )
                    )
                except Exception as exc:  # noqa: BLE001 - 转发给主线程统一处理
                    outcome.append(exc)

            threading.Thread(target=_wait, daemon=True).start()
            started = time.monotonic()
            while not outcome:
                if self.cancel_event.is_set():
                    if process is not None and process.poll() is None:
                        process.kill()
                    self.log.emit("[Forbric] 已取消安装。")
                    return
                elapsed = time.monotonic() - started
                fraction = min(0.35, elapsed / FORBRIC_TIMEOUT * 0.35)
                self.progress.emit(0.6 + fraction, f"等待安装器完成…（{int(elapsed)} 秒）")
                time.sleep(2)

            result = outcome[0]
            if isinstance(result, Exception):
                raise result
            if not result:  # 用户取消，安装器进程还在运行则收尾
                if process is not None and process.poll() is None:
                    process.kill()
                self.log.emit("[Forbric] 已取消安装。")
                return

            self.progress.emit(0.95, "版本文件已生成")
            self.log.emit(f"[Forbric] 安装完成，版本：{FORBRIC_VERSION_ID}")
            self.progress.emit(1.0, "安装完成")
            self.done.emit(FORBRIC_VERSION_ID)
        except Exception as exc:  # noqa: BLE001 - 统一反馈到界面
            if process is not None and process.poll() is None:
                process.kill()
            self.failed.emit(f"Forbric 安装失败：{exc}")
