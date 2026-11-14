"""MikanCL Electron 独立内核的后端服务。

Electron 主进程通过 stdio 与这里通信，协议是逐行 JSON：
- Electron -> Python：{"id": "...", "method": "...", "args": [...]}
- Python -> Electron：{"id": "...", "ok": true, "result": ...}
- Python -> Electron：{"host": "...", "op": "...", "args": {...}}  （请求原生能力）
- Electron -> Python：{"host_result": "...", "ok": true, "result": ...}

前端完全复用 mc_launcher/ui_web/web 下的同一套 HTML/JS/CSS；preload 把
window.pywebview.api 映射到这里的 RPC，所以不需要为 Electron 重写界面。
"""

from __future__ import annotations

import json
import os
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor


class HostBridge:
    """Python 侧调用 Electron 原生能力的桥（文件对话框、窗口、剪贴板等）。"""

    def __init__(self, writer) -> None:
        self._write = writer
        self._lock = threading.Lock()
        self._pending: dict[str, list] = {}
        self._seq = 0

    def _next_id(self) -> str:
        with self._lock:
            self._seq += 1
            return f"h{self._seq}"

    def call(self, op: str, payload: dict | None = None, timeout: float = 30.0):
        """请求 Electron 执行原生操作并等待结果；失败或超时返回 None。"""
        request_id = self._next_id()
        event = threading.Event()
        slot = [event, None, False]
        with self._lock:
            self._pending[request_id] = slot
        self._write({"host": request_id, "op": op, "args": payload or {}})
        if not event.wait(timeout):
            with self._lock:
                self._pending.pop(request_id, None)
            return None
        with self._lock:
            self._pending.pop(request_id, None)
        return slot[1] if slot[2] else None

    def notify(self, op: str, payload: dict | None = None) -> None:
        """单向通知，不等待回执（关闭窗口、重启、写剪贴板）。"""
        self._write({"host": self._next_id(), "op": op, "args": payload or {}})

    def resolve(self, request_id: str, ok: bool, result=None) -> None:
        with self._lock:
            slot = self._pending.get(request_id)
        if slot is None:
            return
        slot[1] = result
        slot[2] = bool(ok)
        slot[0].set()


def _open_protocol_stream():
    """独立占有一个 stdout 句柄，避免后端代码里的 print 污染协议。"""
    try:
        return os.fdopen(os.dup(1), "wb", buffering=0)
    except Exception:  # noqa: BLE001 - 极端环境下退回 sys.stdout
        return sys.stdout.buffer


def _open_stdin():
    try:
        return os.fdopen(os.dup(0), "rb", buffering=0)
    except Exception:  # noqa: BLE001
        return sys.stdin.buffer


class Backend:
    def __init__(self) -> None:
        self._write_lock = threading.Lock()
        self._stream = _open_protocol_stream()
        self._pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="mikan-rpc")
        self.host = HostBridge(self._send)

    def _send(self, message: dict) -> None:
        line = json.dumps(message, ensure_ascii=False, default=str, separators=(",", ":"))
        with self._write_lock:
            try:
                self._stream.write(line.encode("utf-8") + b"\n")
                self._stream.flush()
            except (BrokenPipeError, OSError, ValueError):
                # Electron 已退出，后端随之结束
                os._exit(0)

    def _handle_call(self, api, message: dict) -> None:
        request_id = str(message.get("id") or "")
        method = str(message.get("method") or "")
        args = message.get("args") or []
        if not isinstance(args, list):
            args = [args]
        try:
            if not method or method.startswith("_"):
                raise AttributeError(f"未知接口：{method}")
            function = getattr(api, method, None)
            if not callable(function):
                raise AttributeError(f"未知接口：{method}")
            result = function(*args)
            self._send({"id": request_id, "ok": True, "result": result})
        except Exception as exc:  # noqa: BLE001 - 单个调用失败不能拖垮内核
            try:
                traceback.print_exc(file=sys.stderr)
            except Exception:  # noqa: BLE001
                pass
            self._send({"id": request_id, "ok": False, "error": f"{exc}"})

    def serve(self, api) -> int:
        config = api.config
        self._send({"event": "ready", "pid": os.getpid()})
        reader = _open_stdin()
        while True:
            raw = reader.readline()
            if not raw:
                break
            try:
                message = json.loads(raw.decode("utf-8", errors="replace"))
            except ValueError:
                continue
            if not isinstance(message, dict):
                continue
            if "host_result" in message:
                self.host.resolve(
                    str(message.get("host_result") or ""),
                    bool(message.get("ok")),
                    message.get("result"),
                )
                continue
            if message.get("event") == "shutdown":
                break
            if "method" in message:
                self._pool.submit(self._handle_call, api, message)
        self._pool.shutdown(wait=False)
        try:
            config.cancel_debounced_save()
            config.save()
        except Exception:  # noqa: BLE001 - 退出阶段不再抛异常
            pass
        # 直接结束，避免后台线程拖住进程
        os._exit(0)


def _prepare_cwd() -> None:
    if getattr(sys, "frozen", False):
        from ..config import APP_ROOT

        try:
            os.chdir(APP_ROOT)
        except OSError:
            pass


def main() -> int:
    _prepare_cwd()
    # 协议只走私有 stdout；其余 print 统一进 stderr，避免污染 JSON 行。
    try:
        sys.stdout = sys.stderr
    except Exception:  # noqa: BLE001
        pass

    from ..config import Config
    from .shell import WebApi

    config = Config.load()
    api = WebApi(config)
    backend = Backend()
    api.host = backend.host
    return backend.serve(api)


if __name__ == "__main__":
    raise SystemExit(main())
