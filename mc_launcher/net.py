"""HTTP 访问与下载源管理：官方源、BMCLAPI、自定义源（含 API Key）。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
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
    ) -> int:
        """下载到 dest，自动尝试多个源。返回文件大小；支持 .part 断点续传与暂停。"""
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)

        if dest.exists() and self._valid(dest, size, sha1):
            return dest.stat().st_size

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
                                downloaded += len(chunk)
                                if on_bytes:
                                    on_bytes(len(chunk))
                        if expected is not None and downloaded != expected:
                            raise OSError(f"文件长度不符（{downloaded}/{expected}）")
                    if sha1 and self._sha1(tmp) != sha1.lower():
                        raise OSError("SHA1 校验失败")
                    os.replace(tmp, dest)
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
