"""HTTP 访问与下载源管理：官方源、BMCLAPI、自定义源（含 API Key）。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from . import USER_AGENT
from .config import (
    BMCLAPI_BASE,
    CACHE_DIR,
    Config,
    DownloadSource,
    OFFICIAL_MANIFEST,
)

_USER_HEADERS = {"User-Agent": USER_AGENT, "Accept": "*/*"}

# Mojang 资源所在的域名（BMCLAPI 等镜像支持对这些域名做替换）
_REWRITABLE_HOSTS = {
    "launchermeta.mojang.com": "root",
    "piston-meta.mojang.com": "root",
    "piston-data.mojang.com": "root",
    "launcher.mojang.com": "root",
    "resources.download.minecraft.net": "assets",
    "libraries.minecraft.net": "maven",
}

_SSL_CONTEXT = ssl.create_default_context()

# 多个版本并发安装时，同一个依赖 / 资源文件可能被不同线程同时请求：
# 按目标路径加可重入锁，避免两个线程同时写同一个 .part 文件造成损坏。
_PATH_LOCKS: dict[str, threading.RLock] = {}
_PATH_LOCKS_GUARD = threading.Lock()


# ---- 全局下载线程预算 ----
# 所有文件下载（分段下载的每个分段、单流下载）共享同一个上限，
# 避免多个任务/多个版本同时安装时线程数无上限膨胀。
MAX_DOWNLOAD_THREADS = 328
_DOWNLOAD_SLOTS = threading.BoundedSemaphore(MAX_DOWNLOAD_THREADS)
_default_download_workers = 16


def set_default_download_workers(count: int) -> None:
    """由配置里的「下载线程数」设置单个文件默认使用的分段线程数。"""
    global _default_download_workers
    try:
        value = int(count)
    except (TypeError, ValueError):
        return
    if value > 0:
        _default_download_workers = max(1, min(value, MAX_DOWNLOAD_THREADS))


def default_download_workers() -> int:
    return _default_download_workers


# ---- 全局下载限速（令牌桶）----
# 限速对所有下载线程生效，按字节数预约时间片；0 表示不限速。
_SPEED_LIMIT_KBPS = 0
_SPEED_NEXT_ALLOWED = 0.0
_SPEED_LOCK = threading.Lock()


def set_download_speed_limit(kb_per_second: int) -> None:
    """设置全局下载带宽上限（KB/s），0 表示不限速。"""
    global _SPEED_LIMIT_KBPS, _SPEED_NEXT_ALLOWED
    try:
        value = int(kb_per_second)
    except (TypeError, ValueError):
        return
    with _SPEED_LOCK:
        _SPEED_LIMIT_KBPS = max(0, value)
        _SPEED_NEXT_ALLOWED = 0.0


def download_speed_limit() -> int:
    return _SPEED_LIMIT_KBPS


def _throttle_bytes(count: int) -> None:
    """按全局带宽预约本次读取的时间片，超额时短暂休眠。"""
    global _SPEED_NEXT_ALLOWED
    limit = _SPEED_LIMIT_KBPS
    if limit <= 0 or count <= 0:
        return
    now = time.monotonic()
    slot = count / (limit * 1024.0)
    with _SPEED_LOCK:
        start = max(now, _SPEED_NEXT_ALLOWED)
        _SPEED_NEXT_ALLOWED = start + slot
    wait = start - now
    if wait > 0:
        time.sleep(min(wait, 2.0))


def download_slot() -> threading.BoundedSemaphore:
    """供包内其它下载实现（如基岩版分块下载）复用的全局 328 线程预算。"""
    return _DOWNLOAD_SLOTS


def _download_lock(dest: Path) -> threading.RLock:
    try:
        key = str(dest.resolve()).lower()
    except OSError:
        key = str(dest).lower()
    with _PATH_LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(key, threading.RLock())


# 部分国内镜像的 CDN 节点证书链不完整（缺中间证书），校验会报 unable to get local issuer
# certificate；这类请求在证书校验失败时回退到不校验模式，否则镜像整条链路不可用。
_UNVERIFIED_SSL_CONTEXT: ssl.SSLContext | None = None

# ---- 全局代理 ----
_PROXY_LOCK = threading.Lock()
_PROXY_URL = ""
_OPENER: urllib.request.OpenerDirector | None = None


def normalize_proxy(proxy_url: str) -> str:
    text = (proxy_url or "").strip()
    if not text:
        return ""
    if not re.match(r"^[a-zA-Z][\w+.-]*://", text):
        text = "http://" + text
    return text


def apply_proxy(proxy_url: str) -> None:
    """配置全局 HTTP 代理；传入空字符串表示直连。"""
    global _PROXY_URL, _OPENER
    normalized = normalize_proxy(proxy_url)
    with _PROXY_LOCK:
        _PROXY_URL = normalized
        _OPENER = None


def proxy_opener() -> urllib.request.OpenerDirector:
    global _OPENER
    with _PROXY_LOCK:
        if _OPENER is None:
            proxies = {}
            if _PROXY_URL:
                proxies = {"http": _PROXY_URL, "https": _PROXY_URL}
            _OPENER = urllib.request.build_opener(
                urllib.request.ProxyHandler(proxies),
                urllib.request.HTTPSHandler(context=_SSL_CONTEXT),
            )
        return _OPENER


def _unverified_context() -> ssl.SSLContext:
    global _UNVERIFIED_SSL_CONTEXT
    with _PROXY_LOCK:
        if _UNVERIFIED_SSL_CONTEXT is None:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            _UNVERIFIED_SSL_CONTEXT = context
        return _UNVERIFIED_SSL_CONTEXT


def _is_cert_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "certificate_verify_failed" in text or "certificate verify failed" in text


def open_with_ssl_fallback(
    request: urllib.request.Request, timeout: float
):
    """打开请求；仅在证书链校验失败（镜像 CDN 缺中间证书）时退回不校验重试一次。"""
    try:
        return proxy_opener().open(request, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        if not _is_cert_error(exc):
            raise
        proxies = {}
        with _PROXY_LOCK:
            if _PROXY_URL:
                proxies = {"http": _PROXY_URL, "https": _PROXY_URL}
        fallback = urllib.request.build_opener(
            urllib.request.ProxyHandler(proxies),
            urllib.request.HTTPSHandler(context=_unverified_context()),
        )
        return fallback.open(request, timeout=timeout)



class Cancelled(Exception):
    """用户取消了任务。"""


class DownloadError(Exception):
    """所有候选地址均下载失败。"""


@dataclass
class Candidate:
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    source_id: str = ""
    source_name: str = ""


def _norm_base(base: str) -> str:
    base = (base or "").strip().rstrip("/")
    if base and not re.match(r"^https?://", base, re.I):
        base = "https://" + base
    return base


def rewrite_url(url: str, source: DownloadSource) -> str | None:
    """把 Mojang 地址按源配置改写；无法改写时返回 None。"""
    if source.mapping == "none" or not source.download_base:
        return None
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").lower()
    base = _norm_base(source.download_base)
    if not base:
        return None
    parsed_base = urllib.parse.urlsplit(base)
    prefix = parsed_base.path.rstrip("/")

    new_path = parsed.path
    if source.mapping == "bmclapi":
        kind = _REWRITABLE_HOSTS.get(host)
        if kind is None:
            return None
        if kind == "assets":
            new_path = "/assets" + parsed.path
        elif kind == "maven":
            new_path = "/maven" + parsed.path
        else:
            new_path = parsed.path
    elif source.mapping == "direct":
        if host not in _REWRITABLE_HOSTS:
            return None
        new_path = parsed.path
    else:
        return None

    path = prefix + new_path
    return urllib.parse.urlunsplit(
        (parsed_base.scheme, parsed_base.netloc, path, parsed.query, "")
    )


def _headers_of(source: DownloadSource) -> dict[str, str]:
    headers = dict(_USER_HEADERS)
    headers.update(source.request_headers())
    return headers


class SourceManager:
    def __init__(self, config: Config):
        self.config = config
        self._manifest_lock = threading.Lock()

    # ---------- 候选地址 ----------
    def manifest_candidates(self, preferred_id: str = "") -> list[Candidate]:
        result: list[Candidate] = []
        for source in self.config.source_list():
            result.append(
                Candidate(source.manifest_url, _headers_of(source), source.id, source.name)
            )
        if preferred_id:
            result.sort(key=lambda c: 0 if c.source_id == preferred_id else 1)
        if not result:
            result.append(Candidate(OFFICIAL_MANIFEST, dict(_USER_HEADERS), "official", "Mojang 官方源"))
        return result

    def resource_candidates(self, url: str) -> list[Candidate]:
        result: list[Candidate] = []
        seen: set[str] = set()
        for source in self.config.source_list():
            rewritten = rewrite_url(url, source)
            if rewritten and rewritten not in seen:
                seen.add(rewritten)
                result.append(Candidate(rewritten, _headers_of(source), source.id, source.name))
        if url not in seen:
            seen.add(url)
            official = self.config.get_source("official")
            headers = _headers_of(official) if official else dict(_USER_HEADERS)
            result.append(Candidate(url, headers, "official", "Mojang 官方源"))
        return result

    # ---------- 版本清单 ----------
    def _cache_file(self, source_id: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", source_id or "unknown")
        return CACHE_DIR / f"manifest_{safe}.json"

    def cached_manifest(self, source_id: str) -> dict | None:
        path = self._cache_file(source_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            data = payload.get("data")
            if isinstance(data, dict) and isinstance(data.get("versions"), list):
                return payload
        except (OSError, ValueError):
            return None
        return None

    def get_manifest(self, force: bool = False, preferred_id: str = "") -> tuple[dict, str, bool]:
        """返回 (manifest, 源名称, 是否来自缓存)。全部失败时抛出 DownloadError。"""
        errors: list[str] = []
        for candidate in self.manifest_candidates(preferred_id):
            cached = self.cached_manifest(candidate.source_id)
            if cached and not force:
                return cached, str(cached.get("source_name", candidate.source_name)), True
            try:
                data = Http(timeout=25).get_json(candidate)
                if not isinstance(data.get("versions"), list):
                    raise ValueError("清单格式不正确")
                payload = {
                    "fetched_at": int(time.time()),
                    "source_id": candidate.source_id,
                    "source_name": candidate.source_name,
                    "data": data,
                }
                tmp = self._cache_file(candidate.source_id).with_suffix(".json.tmp")
                with self._manifest_lock:
                    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                    os.replace(tmp, self._cache_file(candidate.source_id))
                return payload, candidate.source_name, False
            except (DownloadError, ValueError, OSError) as exc:
                errors.append(f"{candidate.source_name}: {exc}")

        # 全部在线源失败，退回任意可用缓存
        for source in self.config.source_list():
            cached = self.cached_manifest(source.id)
            if cached:
                return cached, str(cached.get("source_name", source.name)), True
        raise DownloadError("无法获取版本清单，请检查网络或下载源设置。\n" + "\n".join(errors[:4]))


# ---- 多线程分段下载（所有大文件下载都可调用） ----
# 小于该阈值的文件（游戏资源、小 mod 等）分段的额外请求开销大于收益，仍走单流下载。
PARALLEL_MIN_SIZE = 4 * 1024 * 1024


def _probe_download_range(
    candidate: Candidate, timeout: int = 20
) -> tuple[int, bool]:
    """用 Range: bytes=0-0 探测 (总大小, 是否支持分段)。探测失败返回 (0, False)。"""
    headers = dict(candidate.headers)
    headers["Range"] = "bytes=0-0"
    request = urllib.request.Request(candidate.url, headers=headers)
    try:
        with open_with_ssl_fallback(request, timeout) as response:
            status = int(getattr(response, "status", 200) or 200)
            content_range = response.headers.get("Content-Range") or ""
            match = re.search(r"/(\d+)", content_range)
            total = int(match.group(1)) if match else 0
            if not total:
                length = response.headers.get("Content-Length") or "0"
                total = int(length) if length.isdigit() else 0
            accept = (response.headers.get("Accept-Ranges") or "").lower()
            return total, status == 206 and total > 0 and accept != "none"
    except Exception:  # noqa: BLE001 - 探测失败时退回单流下载
        return 0, False


def probe_download_size(url: str, headers: dict[str, str] | None = None) -> tuple[int, bool]:
    """探测直链的文件大小与是否支持分段，供「下载加速」页显示进度。"""
    candidate = Candidate(url=url, headers=dict(headers or {}), source_name="探测")
    return _probe_download_range(candidate)


def _segmented_download(
    candidate: Candidate,
    dest: Path,
    size: int | None = 0,
    cancel: threading.Event | None = None,
    on_bytes: Callable[[int], None] | None = None,
    pause: threading.Event | None = None,
    workers: int = 0,
) -> int:
    """把文件切成多段并发下载、落盘后合并；支持暂停、取消与断点续传。

    size 可为 None（未知总长），内部统一按 0 处理，真实长度以服务器探测值为准。
    on_bytes 收到的是「本次新增字节数」，调用方应累加；断点续传时先补一次已下载量。
    """
    size = int(size or 0)
    total, ranged = _probe_download_range(candidate)
    if not ranged or total <= 0:
        raise DownloadError("服务器不支持分段下载")
    if size <= 0:
        size = total
    # 上次合并中途被打断时残留的 .merge 文件直接丢弃，尽早释放磁盘
    dest.with_name(dest.name + ".merge").unlink(missing_ok=True)

    worker_count = int(workers or _default_download_workers)
    worker_count = max(1, min(worker_count, MAX_DOWNLOAD_THREADS))
    segment_count = min(worker_count, max(1, total // (1024 * 1024)))
    segment_count = max(1, segment_count)
    span = total // segment_count
    ranges: list[tuple[int, int]] = []
    parts: list[Path] = []
    for index in range(segment_count):
        start = index * span
        end = total - 1 if index == segment_count - 1 else start + span - 1
        ranges.append((start, end))
        parts.append(dest.with_name(f"{dest.name}.part{index}"))

    resumed = 0
    for part, (start, end) in zip(parts, ranges):
        if not part.exists():
            continue
        expected = end - start + 1
        length = part.stat().st_size
        if length > expected:
            try:
                with open(part, "r+b") as fh:
                    fh.truncate(expected)
            except OSError:
                pass
            length = expected
        resumed += length
    if resumed and on_bytes:
        on_bytes(resumed)

    def check() -> None:
        while pause is not None and pause.is_set():
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            time.sleep(0.2)
        if cancel is not None and cancel.is_set():
            raise Cancelled()

    def check_in_slot() -> None:
        """已持有全局预算时检查暂停：暂停期间先让出预算，避免其它下载被饿死。"""
        if pause is not None and pause.is_set():
            _DOWNLOAD_SLOTS.release()
            try:
                check()
            finally:
                _DOWNLOAD_SLOTS.acquire()
            return
        if cancel is not None and cancel.is_set():
            raise Cancelled()

    def segment(part: Path, start: int, end: int) -> None:
        expected = end - start + 1
        offset = part.stat().st_size if part.exists() else 0
        if offset >= expected:
            return
        headers = dict(candidate.headers)
        headers["Range"] = f"bytes={start + offset}-{end}"
        attempt = 0
        while True:
            check()
            request = urllib.request.Request(candidate.url, headers=headers)
            _DOWNLOAD_SLOTS.acquire()
            try:
                with open_with_ssl_fallback(request, 60) as response:
                    status = int(getattr(response, "status", 200) or 200)
                    if status not in (200, 206):
                        raise DownloadError(f"HTTP {status}")
                    with open(part, "ab") as fh:
                        while True:
                            check_in_slot()
                            chunk = response.read(65536)
                            if not chunk:
                                break
                            fh.write(chunk)
                            _throttle_bytes(len(chunk))
                            if on_bytes:
                                on_bytes(len(chunk))
            except Cancelled:
                raise
            except Exception:  # noqa: BLE001
                attempt += 1
                if attempt > 6:
                    raise
                check()
                time.sleep(1.0)
            finally:
                _DOWNLOAD_SLOTS.release()
            if part.stat().st_size >= expected:
                return
            # 连接提前断开：按已写长度继续请求剩余区间
            offset = part.stat().st_size
            headers["Range"] = f"bytes={start + offset}-{end}"
            attempt += 1
            if attempt > 6:
                raise DownloadError("分段下载中断次数过多")

    with ThreadPoolExecutor(max_workers=segment_count) as pool:
        futures = [
            pool.submit(segment, part, start, end)
            for part, (start, end) in zip(parts, ranges)
        ]
        for future in futures:
            future.result()

    combined = dest.with_name(dest.name + ".merge")
    with open(combined, "wb") as out:
        for part, (start, end) in zip(parts, ranges):
            expected = end - start + 1
            if part.exists() and part.stat().st_size > expected:
                try:
                    with open(part, "r+b") as fh:
                        fh.truncate(expected)
                except OSError:
                    pass
            if part.exists():
                with open(part, "rb") as fh:
                    shutil.copyfileobj(fh, out, 1024 * 1024)
    actual = combined.stat().st_size
    if total and actual != total:
        combined.unlink(missing_ok=True)
        raise DownloadError(f"文件长度不符（{actual}/{total}）")
    os.replace(combined, dest)
    for part in parts:
        part.unlink(missing_ok=True)
    return dest.stat().st_size


class Http:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    @staticmethod
    def _open(
        candidate: Candidate,
        timeout: int,
        extra_headers: dict[str, str] | None = None,
    ):
        headers = dict(candidate.headers)
        if extra_headers:
            headers.update(extra_headers)
        request = urllib.request.Request(candidate.url, headers=headers)
        return open_with_ssl_fallback(request, timeout)

    def request(
        self,
        url: str,
        method: str = "GET",
        json_body: dict | list | None = None,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> bytes:
        """通用 HTTP 请求，返回原始字节；失败时抛出 DownloadError。"""
        merged = dict(_USER_HEADERS)
        merged.update({str(k): str(v) for k, v in (headers or {}).items()})
        data = None
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            merged.setdefault("Content-Type", "application/json")
        request = urllib.request.Request(
            url, data=data, headers=merged, method=method.upper()
        )
        try:
            with open_with_ssl_fallback(
                request, timeout or self.timeout
            ) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:300]
            except Exception:  # noqa: BLE001
                pass
            raise DownloadError(f"HTTP {exc.code}：{detail or exc.reason}") from exc
        except Exception as exc:  # noqa: BLE001
            raise DownloadError(str(exc)) from exc

    def get_json_url(
        self, url: str, headers: dict[str, str] | None = None, timeout: int | None = None
    ) -> dict | list:
        raw = self.request(url, "GET", headers=headers, timeout=timeout)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise DownloadError("返回内容不是有效的 JSON") from exc

    def post_json_url(
        self,
        url: str,
        payload: dict | list,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> dict | list:
        raw = self.request(url, "POST", payload, headers=headers, timeout=timeout)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise DownloadError("返回内容不是有效的 JSON") from exc

    def post_form_url(
        self,
        url: str,
        fields: dict[str, str],
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> dict | list:
        """以 application/x-www-form-urlencoded 提交表单（微软 OAuth 端点要求）。"""
        merged = dict(_USER_HEADERS)
        merged["Content-Type"] = "application/x-www-form-urlencoded"
        merged.update({str(k): str(v) for k, v in (headers or {}).items()})
        data = urllib.parse.urlencode({str(k): str(v) for k, v in fields.items()}).encode("utf-8")
        return self._post_raw(url, data, merged, timeout)

    def post_multipart_url(
        self,
        url: str,
        fields: dict[str, str],
        files: dict[str, tuple[str, bytes, str]],
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> dict | list:
        """以 multipart/form-data 上传文件（皮肤上传等）。"""
        boundary = "----MikanCL" + uuid.uuid4().hex
        body = bytearray()
        for key, value in fields.items():
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8")
            )
            body.extend(str(value).encode("utf-8"))
            body.extend(b"\r\n")
        for key, (filename, content, content_type) in files.items():
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(
                (
                    f'Content-Disposition: form-data; name="{key}"; filename="{filename}"\r\n'
                    f"Content-Type: {content_type}\r\n\r\n"
                ).encode("utf-8")
            )
            body.extend(content)
            body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode("utf-8"))
        merged = dict(_USER_HEADERS)
        merged["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        merged.update({str(k): str(v) for k, v in (headers or {}).items()})
        return self._post_raw(url, bytes(body), merged, timeout)

    def _post_raw(
        self,
        url: str,
        data: bytes,
        headers: dict[str, str],
        timeout: int | None = None,
    ) -> dict | list:
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with open_with_ssl_fallback(
                request, timeout or self.timeout
            ) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:  # noqa: BLE001
                pass
            raise DownloadError(f"HTTP {exc.code}：{detail or exc.reason}") from exc
        except Exception as exc:  # noqa: BLE001
            raise DownloadError(str(exc)) from exc
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise DownloadError("返回内容不是有效的 JSON") from exc

    def get_json(self, candidate: Candidate, timeout: int | None = None) -> dict:
        try:
            with self._open(candidate, timeout or self.timeout) as response:
                raw = response.read()
        except Exception as exc:  # noqa: BLE001 - 汇总为 DownloadError
            raise DownloadError(f"{exc}") from exc
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise DownloadError("返回内容不是有效的 JSON") from exc
        if not isinstance(data, dict):
            raise DownloadError("返回内容不是 JSON 对象")
        return data

    def download(
        self,
        candidates: Iterable[Candidate],
        dest: Path,
        size: int | None = None,
        sha1: str | None = None,
        cancel: threading.Event | None = None,
        on_bytes: Callable[[int], None] | None = None,
        pause: threading.Event | None = None,
        parallel: bool | None = None,
        workers: int = 0,
    ) -> int:
        """下载到 dest，自动尝试多个源。返回文件大小；支持 .part 断点续传与暂停。

        parallel=True / workers 指定时，大文件会走多线程分段下载；默认按文件大小
        自动判断（≥ PARALLEL_MIN_SIZE 且服务器支持 Range 时启用）。

        on_bytes 回调收到的是「本次新增字节数」（增量语义），调用方应累加到自己的
        进度变量；单流续传与分段续传都会在开始时先补一次已下载量，因此无需额外处理。
        """
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        # 并发安装时同一个文件可能被多个 worker 请求：按目标路径串行化，
        # 拿到锁后再检查一次，避免重复下载与 .part 写冲突。
        with _download_lock(dest):
            if dest.exists() and self._valid(dest, size, sha1):
                return dest.stat().st_size
            return self._download_with_sources(
                candidates,
                dest,
                size,
                sha1,
                cancel,
                on_bytes,
                pause,
                parallel,
                workers,
            )

    def _download_with_sources(
        self,
        candidates: Iterable[Candidate],
        dest: Path,
        size: int | None,
        sha1: str | None,
        cancel: threading.Event | None,
        on_bytes: Callable[[int], None] | None,
        pause: threading.Event | None,
        parallel: bool | None = None,
        workers: int = 0,
    ) -> int:
        def wait_if_paused() -> None:
            while pause is not None and pause.is_set():
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                time.sleep(0.5)

        tmp = dest.with_name(dest.name + ".part")
        errors: list[str] = []

        def retry_sleep(seconds: float = 1.0) -> None:
            """重试前等待 1 秒；等待期间被取消立即抛出，暂停中则继续等待。"""
            deadline = time.monotonic() + seconds
            while True:
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                if pause is not None and pause.is_set():
                    time.sleep(0.2)
                    continue
                if time.monotonic() >= deadline:
                    return
                time.sleep(0.1)

        for candidate in candidates:
            # 大文件优先走多线程分段下载（所有资源通用）；不支持分段或失败时退回单流。
            want_parallel = parallel if parallel is not None else (
                size is not None and size >= PARALLEL_MIN_SIZE
            )
            if want_parallel and not tmp.exists() and (size is None or size >= 1024 * 1024):
                try:
                    total = _segmented_download(
                        candidate, dest, size, cancel, on_bytes, pause, workers
                    )
                    if sha1 and self._sha1(dest) != sha1.lower():
                        dest.unlink(missing_ok=True)
                        for part in dest.parent.glob(dest.name + ".part*"):
                            part.unlink(missing_ok=True)
                        raise OSError("SHA1 校验失败")
                    return total
                except Cancelled:
                    raise
                except Exception as exc:  # noqa: BLE001 - 分段失败退回单流
                    errors.append(
                        f"{candidate.source_name} {candidate.url}: 分段下载失败 {exc}"
                    )
            for attempt in range(3):  # 连接被中止/超时最多重试 3 次
                wait_if_paused()
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                try:
                    existing = tmp.stat().st_size if tmp.exists() else 0
                    if existing and (size is not None and existing >= size):
                        existing = 0
                    headers = {"Range": f"bytes={existing}-"} if existing > 0 else None
                    # 单次读取的空闲超时：连接假死（长时间读不到数据）时尽快断开重试，
                    # 否则线程会一直挂在 response.read() 上，整批下载卡住。
                    read_timeout = min(self.timeout, 20)
                    _DOWNLOAD_SLOTS.acquire()
                    try:
                        with self._open(candidate, read_timeout, headers) as response:
                            status = int(getattr(response, "status", 200) or 200)
                            if existing and status != 206:
                                existing = 0  # 服务器不支持续传，从头下载
                            expected = size
                            if expected is None:
                                header_size = response.headers.get("Content-Length")
                                length = int(header_size) if header_size and header_size.isdigit() else 0
                                expected = existing + length if length else None
                            downloaded = existing
                            with open(tmp, "ab" if existing else "wb") as fh:
                                while True:
                                    wait_if_paused()
                                    if cancel is not None and cancel.is_set():
                                        raise Cancelled()
                                    chunk = response.read(65536)
                                    if not chunk:
                                        break
                                    fh.write(chunk)
                                    _throttle_bytes(len(chunk))
                                    downloaded += len(chunk)
                                    if on_bytes:
                                        on_bytes(len(chunk))
                            if expected is not None and downloaded != expected:
                                raise OSError(f"文件长度不符（{downloaded}/{expected}）")
                    finally:
                        _DOWNLOAD_SLOTS.release()
                    if sha1 and self._sha1(tmp) != sha1.lower():
                        raise OSError("SHA1 校验失败")
                    os.replace(tmp, dest)
                    # 分段失败退回单流并成功时，清掉本次弃用的 .partN，避免残留占盘
                    for part in dest.parent.glob(dest.name + ".part*"):
                        part.unlink(missing_ok=True)
                    return dest.stat().st_size
                except Cancelled:
                    # 取消时保留 .part：重新下载可走 Range 断点续传
                    raise
                except Exception as exc:  # noqa: BLE001
                    # 校验/长度错误说明已下载内容不可信，删除 .part；网络中断则保留以便续传
                    text = str(exc)
                    if "SHA1" in text or "长度不符" in text:
                        tmp.unlink(missing_ok=True)
                    errors.append(f"{candidate.source_name} {candidate.url}: {exc}")
                    retryable = (
                        isinstance(exc, (urllib.error.URLError, ConnectionError))
                        or "10053" in text
                        or "10054" in text
                        or "timed out" in text.lower()
                        or "aborted" in text.lower()
                        or "reset" in text.lower()
                        or "connection" in text.lower()
                    )
                    if not retryable or attempt >= 2:
                        break  # 非连接类错误不重试；连接类最多 3 次
                    retry_sleep(1.0)
        raise DownloadError(f"下载失败：{dest.name}\n" + "\n".join(errors[-4:]))

    def download_to_path(
        self,
        candidates: Iterable[Candidate],
        dest_path: Path,
        size: int = 0,
        sha1: str = "",
        cancel: threading.Event | None = None,
        pause: threading.Event | None = None,
        log: Callable[[str], None] | None = None,
        on_bytes: Callable[[int], None] | None = None,
    ) -> Path:
        """只把源文件保存到 dest_path（不解压、不拼目录），保留 .part 续传语义。"""
        dest = Path(dest_path)
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise DownloadError(f"无法创建保存目录 {dest.parent}：{exc}") from exc
        if log:
            log(f"[下载] 保存到 {dest}")
        self.download(
            candidates,
            dest,
            size=size or None,
            sha1=sha1 or None,
            cancel=cancel,
            on_bytes=on_bytes,
            pause=pause,
        )
        if log:
            log(f"[下载] 已保存 {dest}")
        return dest

    def is_valid(self, path: Path, size: int | None = None, sha1: str | None = None) -> bool:
        return self._valid(Path(path), size, sha1)

    @staticmethod
    def _sha1(path: Path) -> str:
        digest = hashlib.sha1()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _valid(self, path: Path, size: int | None, sha1: str | None) -> bool:
        try:
            stat = path.stat()
        except OSError:
            return False
        if stat.st_size <= 0:
            return False
        if size is not None and stat.st_size != size:
            return False
        if sha1:
            try:
                return self._sha1(path) == sha1.lower()
            except OSError:
                return False
        return True


def test_source(source: DownloadSource, timeout: int = 15) -> tuple[bool, str]:
    """测试源是否可用，返回 (成功, 描述)。"""
    started = time.time()
    try:
        candidate = Candidate(source.manifest_url, _headers_of(source), source.id, source.name)
        data = Http(timeout=timeout).get_json(candidate)
        versions = data.get("versions")
        if not isinstance(versions, list):
            return False, "返回数据不含版本列表"
        elapsed = int((time.time() - started) * 1000)
        return True, f"连接成功，{len(versions)} 个版本，{elapsed} ms"
    except Exception as exc:  # noqa: BLE001
        return False, f"连接失败：{exc}"
