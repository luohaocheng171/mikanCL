"""Edge WebView2 内核封装。

QtWebEngine 的官方构建不含 H.264/AAC 等专有编解码器，B 站一类的站点会直接提示
「您当前的浏览器不支持 HTML5 播放器」。这里用 ctypes 直接托管 Windows 自带的
Edge WebView2 组件（Windows 10/11 均已预装），内核是完整版 Chromium，视频可以
在启动器内部直接播放，不需要用户切到系统浏览器。

要点：
* WebView2 的回调里给出的接口指针是「借用引用」，必须自己 AddRef 才能长期持有，
  否则后续调用会读到已释放对象并返回毫无意义的 HRESULT；
* 绝对不要在 WebView2 事件回调里同步调用其它 WebView2 方法，回调只取参数，
  其余工作统统用 QTimer 延后到事件循环里执行；
* vtable 里 IUnknown 占前 3 个槽位，接口方法索引要 +3。
"""

from __future__ import annotations

import ctypes
import sys
import uuid
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QEvent, QTimer, Qt, Signal
from PySide6.QtWidgets import QWidget

from ..config import BROWSER_DIR

HRESULT = ctypes.c_long
WINFUN = ctypes.WINFUNCTYPE
S_OK = 0
E_NOINTERFACE = 0x80004002
RPC_E_CHANGED_MODE = 0x80010106


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _iid(text: str) -> _GUID:
    return _GUID.from_buffer_copy(uuid.UUID(text).bytes_le)


_IID_UNKNOWN = _iid("00000000-0000-0000-c000-000000000046")
# 统一用「元组」存一类事件所需的 IID（可能多版本并存），_ComHandler 只认展平后的字节
_IID_ENV_DONE = (_iid("4E8A3389-C9D8-4BD2-B6B5-124FEE6CC14D"),)
_IID_CTRL_DONE = (_iid("6C4819F3-C9B7-4260-8127-C9F5BDE7F68C"),)
_IID_NAV_START = (_iid("9ADBE429-F36D-432B-9DDC-F8881FBD76E3"),)
_IID_NAV_DONE = (_iid("D33A35BF-1C49-4F98-93AB-006E0533FE1C"),
                 _iid("C79A1DE3-D63B-4823-8D03-241D91BECB0F"))
_IID_SOURCE = (_iid("3C067F9F-5388-4772-8B48-79F7EF1AB37C"),
               _iid("A0D6DF20-3B95-416D-AA4C-19C3DCF3D8C8"))
_IID_TITLE = (_iid("F5F2B923-953E-4042-9F95-F3A118E1AFD4"),)
_IID_NEW_WINDOW = (_iid("D4C185FE-C81C-4989-97AF-2D3FA7AB5651"),)
_IID_FULLSCREEN = (_iid("E45D98B1-AFEF-45BE-8BAF-6C7728867F73"),)
_IID_WINDOW_CLOSE = (_iid("5C19E9E0-092F-486B-AFFA-CA8231913039"),)
_IID_PROCESS_FAILED = (_iid("79E0AEA4-990B-42D9-AA1D-0FCC2E5BC7F1"),)
_IID_ACCEL_KEY = (_iid("B29C7E28-FA79-41A8-8E44-65811C76DCB2"),)

_WEBVIEW2_PRODUCT = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def resources_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "resources"


def _loader_path() -> Path:
    return resources_dir() / "WebView2Loader.dll"


def _runtime_installed() -> bool:
    """检查系统是否装了 WebView2 运行时（注册表为主，目录为辅）。"""
    try:
        import winreg
    except ImportError:
        return False
    bases = (
        (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\WOW6432Node\\Microsoft\\EdgeUpdate\\Clients\\" + _WEBVIEW2_PRODUCT),
        (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\Microsoft\\EdgeUpdate\\Clients\\" + _WEBVIEW2_PRODUCT),
        (winreg.HKEY_CURRENT_USER, "Software\\Microsoft\\EdgeUpdate\\Clients\\" + _WEBVIEW2_PRODUCT),
    )
    for root, path in bases:
        try:
            with winreg.OpenKey(root, path) as key:
                version, _ = winreg.QueryValueEx(key, "pv")
                if str(version).strip():
                    return True
        except OSError:
            continue
    for folder in (r"C:\Program Files (x86)", r"C:\Program Files"):
        base = Path(folder) / "Microsoft" / "EdgeWebView" / "Application"
        try:
            if any((child / "msedgewebview2.exe").is_file() for child in base.iterdir()):
                return True
        except OSError:
            continue
    return False


def webview2_available() -> bool:
    """同步判断能否使用 WebView2：DLL 已随包分发，且系统装了运行时。"""
    if sys.platform != "win32":
        return False
    return _loader_path().is_file() and _runtime_installed()


def _vt_call(iface: int, index: int, argtypes: list, *args):
    table = ctypes.cast(ctypes.cast(iface, ctypes.POINTER(ctypes.c_void_p))[0],
                        ctypes.POINTER(ctypes.c_void_p))
    fn = WINFUN(HRESULT, ctypes.c_void_p, *argtypes)(table[index + 3])
    return fn(iface, *args)


def _add_ref(iface: int) -> int:
    table = ctypes.cast(ctypes.cast(iface, ctypes.POINTER(ctypes.c_void_p))[0],
                        ctypes.POINTER(ctypes.c_void_p))
    fn = WINFUN(ctypes.c_ulong, ctypes.c_void_p)(table[1])
    return int(fn(iface) or 0)


def _hex(hr) -> str:
    return "0x%08X" % (int(hr) & 0xFFFFFFFF)


class _ComHandler:
    """最小 COM 事件处理器：IUnknown 三个槽 + 一个 Invoke。"""

    def __init__(self, target_iids, invoke_types: list, invoke_fn):
        # 目标 IID 一律是 ctypes 结构体序列，统一转成 16 字节用于线性比对
        self._iids = {ctypes.string_at(ctypes.byref(i), 16) for i in target_iids}
        self._iids.add(ctypes.string_at(ctypes.byref(_IID_UNKNOWN), 16))
        self._query_fn = WINFUN(
            HRESULT, ctypes.c_void_p, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)
        )(self._query)
        self._addref_fn = WINFUN(ctypes.c_ulong, ctypes.c_void_p)(lambda _this: 2)
        self._release_fn = WINFUN(ctypes.c_ulong, ctypes.c_void_p)(lambda _this: 1)
        self._invoke_fn = WINFUN(HRESULT, ctypes.c_void_p, *invoke_types)(invoke_fn)
        slots = [self._query_fn, self._addref_fn, self._release_fn, self._invoke_fn]
        self._table = (ctypes.c_void_p * 4)(
            *[ctypes.cast(fn, ctypes.c_void_p).value for fn in slots]
        )
        self._iface = (ctypes.c_void_p * 1)(ctypes.cast(self._table, ctypes.c_void_p).value)

    def _query(self, this, riid, ppv):
        # riid 本身已是 POINTER(_GUID)，直接按地址读 16 字节，避免多一次指针宽度转换
        wanted = ctypes.string_at(riid, 16)
        if wanted in self._iids:
            ppv[0] = ctypes.cast(self._iface, ctypes.c_void_p).value
            return S_OK
        return ctypes.c_long(E_NOINTERFACE).value

    def ptr(self) -> int:
        return ctypes.cast(self._iface, ctypes.c_void_p).value


class _Environment:
    """全局唯一的 WebView2 环境（同一用户数据目录，多个标签页共用）."""

    _instance: "_Environment | None" = None

    @classmethod
    def instance(cls) -> "_Environment":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.state = "idle"  # idle -> creating -> ready / failed
        self.pointer = 0
        self.error = 0
        self.version = ""
        self._waiters: list = []
        self._handler = None
        self._loader = None

    # ------------------------------------------------------------------
    def request(self, callback) -> None:
        """拿到可用的环境指针后回调 callback(pointer)，失败回调 callback(0)。"""
        if self.state == "ready":
            callback(self.pointer)
        elif self.state == "failed":
            callback(0)
        else:
            self._waiters.append(callback)
            if self.state == "idle":
                self._start()

    def _start(self) -> None:
        self.state = "creating"
        ole32 = ctypes.WinDLL("ole32")
        ole32.CoInitializeEx.restype = HRESULT
        ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        try:
            hr = int(ole32.CoInitializeEx(None, 2))  # COINIT_APARTMENTTHREADED
        except OSError:
            hr = -1
        if (hr & 0xFFFFFFFF) == RPC_E_CHANGED_MODE:
            self._finish(0, hr)
            return
        try:
            self._loader = ctypes.WinDLL(str(_loader_path()))
        except OSError:
            self._finish(0, -1)
            return
        create = self._loader.CreateCoreWebView2EnvironmentWithOptions
        create.restype = HRESULT
        create.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_void_p]
        data_dir = BROWSER_DIR / "webview2"
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        self._handler = _ComHandler(
            _IID_ENV_DONE, [HRESULT, ctypes.c_void_p],
            lambda _this, hr, env: self._on_env(hr, env),
        )
        create(None, str(data_dir), None, ctypes.c_void_p(self._handler.ptr()))

    def _on_env(self, hr, env):
        if hr == 0 and env:
            _add_ref(env)
            version = ctypes.c_wchar_p()
            _vt_call(env, 2, [ctypes.POINTER(ctypes.c_wchar_p)], ctypes.byref(version))
            self.version = version.value or ""
        self._finish(env if hr == 0 else 0, hr)
        return 0

    def _finish(self, pointer: int, hr) -> None:
        self.pointer = pointer
        self.error = int(hr)
        self.state = "ready" if pointer else "failed"
        pending, self._waiters = self._waiters, []
        # 环境回调可能仍然同步触发，延后再把环境交给各个标签页，避免重入
        for callback in pending:
            QTimer.singleShot(0, lambda cb=callback, p=pointer: cb(p))


class WebView2View(QWidget):
    """一个标签页 = 一个 WebView2 控制器，接口与 QtWebEngine 版保持一致。"""

    titleChanged = Signal(str)
    urlChanged = Signal(str)
    loadProgress = Signal(int)
    loadFinished = Signal(bool)
    newWindowRequested = Signal(str)
    fullscreenChanged = Signal(bool)
    closeRequested = Signal()
    newTabShortcut = Signal()
    closeTabShortcut = Signal()
    failed = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_NativeWindow, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self._env = _Environment.instance()

        self._env_pointer = 0
        self._ctrl = 0
        self._web = 0
        self._ready = False
        self._starting = False
        self._dead = False
        self._pending_url: str | None = None
        self._pending_html: str | None = None
        self._handlers: list[_ComHandler] = []
        self._filtered_window = None

    # ------------------------------------------------------------------
    # 生命周期
    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        if not self._ready and not self._starting:
            self._start()
        elif self._ready and self._ctrl:
            self._ctrl_call(1, [wintypes.BOOL], wintypes.BOOL(1))
            self._update_bounds()

    def hideEvent(self, event):  # noqa: N802
        super().hideEvent(event)
        if self._ready and self._ctrl:
            self._ctrl_call(1, [wintypes.BOOL], wintypes.BOOL(0))

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._update_bounds()

    def eventFilter(self, obj, event):  # noqa: N802
        # 顶级窗口移动后 WebView2 需要知道新的相对位置，否则右键菜单/下载浮层会错位
        if event.type() == QEvent.Move and self._ready and self._ctrl:
            self._ctrl_call(20, [])
        return False

    def _start(self) -> None:
        self._starting = True
        self._env.request(self._on_environment)

    def _on_environment(self, pointer: int) -> None:
        if self._dead:
            return
        if not pointer:
            self._starting = False
            self.failed.emit("WebView2 内核初始化失败（错误码 %s）" % _hex(self._env.error))
            return
        self._env_pointer = pointer
        hwnd = int(self.winId())
        handler = _ComHandler(
            _IID_CTRL_DONE, [HRESULT, ctypes.c_void_p],
            lambda _this, hr, ctrl: self._on_controller(hr, ctrl),
        )
        self._handlers.append(handler)
        hr = _vt_call(self._env_pointer, 0, [ctypes.c_void_p, ctypes.c_void_p],
                      ctypes.c_void_p(hwnd), ctypes.c_void_p(handler.ptr()))
        if hr != 0:
            self._starting = False
            self.failed.emit("WebView2 控制器创建失败（%s）" % _hex(hr))

    def _on_controller(self, hr, ctrl):
        if self._dead:
            return 0
        if hr != 0 or not ctrl:
            self._starting = False
            QTimer.singleShot(0, lambda: self.failed.emit(
                "WebView2 控制器创建失败（%s）" % _hex(hr)))
            return 0
        _add_ref(ctrl)
        self._ctrl = ctrl
        QTimer.singleShot(0, self._configure)
        return 0

    def _configure(self) -> None:
        if self._dead or not self._ctrl:
            return
        self._update_bounds()
        self._ctrl_call(1, [wintypes.BOOL], wintypes.BOOL(1))
        pointer = (ctypes.c_void_p)()
        if _vt_call(self._ctrl, 22, [ctypes.POINTER(ctypes.c_void_p)],
                    ctypes.byref(pointer)) != 0 or not pointer.value:
            self.failed.emit("WebView2 内核不可用")
            return
        self._web = pointer.value

        settings = (ctypes.c_void_p)()
        if _vt_call(self._web, 0, [ctypes.POINTER(ctypes.c_void_p)],
                    ctypes.byref(settings)) == 0 and settings.value:
            _vt_call(settings.value, 7, [wintypes.BOOL], wintypes.BOOL(0))   # 状态栏
            _vt_call(settings.value, 17, [wintypes.BOOL], wintypes.BOOL(1))  # 内置错误页

        self._subscribe(self._web, 4, _IID_NAV_START, self._on_navigation_starting)
        self._subscribe(self._web, 8, _IID_SOURCE, self._on_source_changed)
        self._subscribe(self._web, 12, _IID_NAV_DONE, self._on_navigation_completed)
        self._subscribe(self._web, 41, _IID_NEW_WINDOW, self._on_new_window)
        self._subscribe(self._web, 43, _IID_TITLE, self._on_title_changed)
        self._subscribe(self._web, 49, _IID_FULLSCREEN, self._on_fullscreen)
        self._subscribe(self._web, 56, _IID_WINDOW_CLOSE, self._on_window_close)
        self._subscribe(self._web, 22, _IID_PROCESS_FAILED, self._on_process_failed)
        self._subscribe(self._ctrl, 16, _IID_ACCEL_KEY, self._on_accelerator_key)

        window = self.window()
        if window is not None and window is not self._filtered_window:
            window.installEventFilter(self)
            self._filtered_window = window

        self._ready = True
        self._starting = False
        if self._pending_html is not None:
            html, self._pending_html = self._pending_html, None
            self._web_call(3, [ctypes.c_wchar_p], html)
        elif self._pending_url is not None:
            url, self._pending_url = self._pending_url, None
            self._web_call(2, [ctypes.c_wchar_p], url)

    def shutdown(self) -> None:
        """退出前关闭控制器，避免 WebView2 子进程残留。"""
        self._dead = True
        if self._ctrl:
            try:
                self._ctrl_call(21, [])
            except (OSError, ValueError):
                pass
        self._ctrl = 0
        self._web = 0
        self._ready = False
        if self._filtered_window is not None:
            try:
                self._filtered_window.removeEventFilter(self)
            except RuntimeError:
                pass
            self._filtered_window = None

    # ------------------------------------------------------------------
    # 底层调用
    def _ctrl_call(self, index: int, argtypes: list, *args):
        if not self._ctrl:
            return -1
        return _vt_call(self._ctrl, index, argtypes, *args)

    def _web_call(self, index: int, argtypes: list, *args):
        if not self._web:
            return -1
        return _vt_call(self._web, index, argtypes, *args)

    def _update_bounds(self) -> None:
        if not self._ctrl:
            return
        ratio = self.devicePixelRatioF()
        rect = RECT(0, 0, max(1, int(self.width() * ratio)),
                    max(1, int(self.height() * ratio)))
        self._ctrl_call(3, [ctypes.POINTER(RECT)], ctypes.byref(rect))

    def _subscribe(self, target: int, index: int, iids, callback) -> None:
        handler = _ComHandler(list(iids), [ctypes.c_void_p], callback)
        self._handlers.append(handler)
        token = ctypes.c_ulonglong()
        _vt_call(target, index, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulonglong)],
                 ctypes.c_void_p(handler.ptr()), ctypes.byref(token))

    def _later(self, func) -> None:
        """把回调里的后续动作推迟到 Qt 事件循环，避免在 WebView2 回调内重入。"""
        def run():
            if self._dead:
                return
            try:
                func()
            except RuntimeError:
                pass
        QTimer.singleShot(0, run)

    # ------------------------------------------------------------------
    # 事件回调：只读参数，其余延后
    def _on_navigation_starting(self, _this, _args):
        self._later(lambda: self.loadProgress.emit(0))
        return 0

    def _on_source_changed(self, _this, _args):
        self._later(lambda: self.urlChanged.emit(self.url()))
        return 0

    def _on_navigation_completed(self, _this, args):
        ok = wintypes.BOOL()
        _vt_call(args, 0, [ctypes.POINTER(wintypes.BOOL)], ctypes.byref(ok))
        success = bool(ok.value)
        self._later(lambda: self.loadFinished.emit(success))
        return 0

    def _on_title_changed(self, _this, _args):
        self._later(lambda: self.titleChanged.emit(self.title()))
        return 0

    def _on_new_window(self, _this, args):
        uri = ctypes.c_wchar_p()
        _vt_call(args, 0, [ctypes.POINTER(ctypes.c_wchar_p)], ctypes.byref(uri))
        _vt_call(args, 3, [wintypes.BOOL], wintypes.BOOL(1))  # put_Handled
        target = uri.value or ""
        if target:
            self._later(lambda: self.newWindowRequested.emit(target))
        return 0

    def _on_fullscreen(self, _this, _args):
        self._later(self._emit_fullscreen)
        return 0

    def _emit_fullscreen(self) -> None:
        state = wintypes.BOOL()
        self._web_call(51, [ctypes.POINTER(wintypes.BOOL)], ctypes.byref(state))
        self.fullscreenChanged.emit(bool(state.value))

    def _on_window_close(self, _this, _args):
        self._later(self.closeRequested.emit)
        return 0

    def _on_process_failed(self, _this, _args):
        # 渲染进程崩溃（多为显存/驱动引起），直接重新加载页面试图自愈
        self._later(lambda: self._web_call(28, []))
        return 0

    def _on_accelerator_key(self, _this, args):
        kind = ctypes.c_int()
        key = ctypes.c_uint()
        _vt_call(args, 0, [ctypes.POINTER(ctypes.c_int)], ctypes.byref(kind))
        _vt_call(args, 1, [ctypes.POINTER(ctypes.c_uint)], ctypes.byref(key))
        if kind.value != 0:  # 0 = KeyDown
            return 0
        try:
            control_down = ctypes.windll.user32.GetKeyState(0x11) & 0x8000
        except OSError:
            control_down = 0
        if not control_down:
            return 0
        signal = {0x54: self.newTabShortcut, 0x57: self.closeTabShortcut}.get(key.value)
        if signal is None:
            return 0
        _vt_call(args, 5, [wintypes.BOOL], wintypes.BOOL(1))  # put_Handled
        self._later(signal.emit)
        return 0

    # ------------------------------------------------------------------
    # 对外接口
    def load(self, url: str) -> None:
        self._pending_html = None
        if self._ready:
            self._web_call(2, [ctypes.c_wchar_p], url)
        else:
            self._pending_url = url
            if not self._starting and not self._dead:
                self._start()

    def set_html(self, html: str) -> None:
        self._pending_url = None
        if self._ready:
            self._web_call(3, [ctypes.c_wchar_p], html)
        else:
            self._pending_html = html
            if not self._starting and not self._dead:
                self._start()

    def url(self) -> str:
        if not self._ready:
            return self._pending_url or ""
        source = ctypes.c_wchar_p()
        if self._web_call(1, [ctypes.POINTER(ctypes.c_wchar_p)], ctypes.byref(source)) != 0:
            return ""
        return source.value or ""

    def title(self) -> str:
        if not self._ready:
            return ""
        title = ctypes.c_wchar_p()
        if self._web_call(45, [ctypes.POINTER(ctypes.c_wchar_p)], ctypes.byref(title)) != 0:
            return ""
        return title.value or ""

    def back(self) -> None:
        self._web_call(37, [])

    def forward(self) -> None:
        self._web_call(38, [])

    def reload(self) -> None:
        self._web_call(28, [])

    def stop(self) -> None:
        self._web_call(40, [])

    def focus_in(self) -> None:
        self._ctrl_call(9, [ctypes.c_int], ctypes.c_int(0))
        try:
            ctypes.windll.user32.SetFocus(int(self.winId()))
        except OSError:
            pass
