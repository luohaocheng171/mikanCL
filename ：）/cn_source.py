"""MC百科在线译名词典：按需获取 Mod / 整合包的中文名，并缓存到本地。

Modrinth 与 CurseForge 只提供英文项目名，本地词表（mod_cn）覆盖有限。这里把
MC百科（mcmod.cn）当作中文译名来源：

* 英文项目名 → 搜索结果里的「中文名 (English Name)」→ 用于界面展示；
* 中文关键词 → 搜索结果的英文项目名 → 用于把中文搜索翻译成平台可检索的词；
* 所有结果写入 CACHE_DIR/cn_names.json，之后离线也能用；网络失败时静默降级。
"""

from __future__ import annotations

import html
import json
import os
import re
import threading
import time
import urllib.parse

from . import mod_cn
from .config import CACHE_DIR
from .net import Http

SEARCH_URL = "https://search.mcmod.cn/s?key={}"
CACHE_FILE = CACHE_DIR / "cn_names.json"

# MC百科会拦截非浏览器 UA，这里固定使用浏览器标识
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _BROWSER_UA,
    "Referer": "https://www.mcmod.cn/",
    "Accept": "text/html,application/xhtml+xml,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

_LINK_RE = re.compile(
    r'href="(https?://www\.mcmod\.cn/(class|modpack)/\d+\.html)"[^>]*>(.*?)</a>', re.S
)
_PAIR_RE = re.compile(r"^(?P<cn>.*?)[（(](?P<en>[^（）()]+)[)）]\s*$")
_ABBR_RE = re.compile(r"^(?:\[[^\]]{1,12}\]\s*)+")
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

_lock = threading.RLock()
_loaded = False
_names: dict[str, str] = {}
_queries: dict[str, list[str]] = {}
_failed_until: dict[str, float] = {}
_last_request = 0.0


# ----------------------------------------------------------------------
# 缓存
def _ensure_loaded() -> None:
    global _loaded
    with _lock:
        if _loaded:
            return
        _loaded = True
        try:
            payload = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        names = payload.get("names") if isinstance(payload, dict) else None
        if isinstance(names, dict):
            for key, value in names.items():
                if isinstance(key, str) and isinstance(value, str) and value:
                    _names[key] = value
        queries = payload.get("queries") if isinstance(payload, dict) else None
        if isinstance(queries, dict):
            for key, value in queries.items():
                if isinstance(key, str) and isinstance(value, list) and value:
                    _queries[key] = [str(v) for v in value if isinstance(v, str)]


def _save_locked() -> None:
    payload = {"version": 1, "names": _names, "queries": _queries}
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=0), encoding="utf-8")
        os.replace(tmp, CACHE_FILE)
    except OSError:
        pass


def _key(title: str) -> str:
    """英文项目名比对键：忽略大小写、空格、括号与标点差异。"""
    return mod_cn.normalize_title(title).replace(" ", "")


def cached_name(title: str) -> str:
    """只查本地缓存（不发起网络请求），用于界面即时展示。"""
    key = _key(title)
    if not key:
        return ""
    _ensure_loaded()
    with _lock:
        return _names.get(key, "")


# ----------------------------------------------------------------------
# 抓取与解析
def _fetch(keyword: str) -> str | None:
    text = (keyword or "").strip()
    if not text:
        return None
    global _last_request
    now = time.time()
    with _lock:
        if _failed_until.get(text, 0.0) > now:
            return None
        wait = 1.0 - (now - _last_request)
    if wait > 0:
        time.sleep(min(wait, 2.0))
    url = SEARCH_URL.format(urllib.parse.quote(text))
    ok = False
    try:
        raw = Http(timeout=8).request(url, headers=_HEADERS)
        ok = True
    except Exception:  # noqa: BLE001 - 网络受限时按失败处理，稍后不再重试
        raw = b""
    finally:
        with _lock:
            _last_request = time.time()
            if not ok:
                _failed_until[text] = time.time() + 600
    return raw.decode("utf-8", errors="replace") if ok else None


def _clean(text: str) -> str:
    text = _TAG_RE.sub("", text or "")
    text = html.unescape(text).replace("\u00a0", " ")
    return _SPACE_RE.sub(" ", text).strip()


def _split_label(label: str) -> tuple[str, str]:
    """把「[JEI] 物品管理器 (Just Enough Items)」拆成 (中文名, 英文名)。"""
    text = _ABBR_RE.sub("", (label or "").strip()).strip()
    match = _PAIR_RE.match(text)
    if match:
        cn = match.group("cn").strip(" -·")
        en = match.group("en").strip()
        return cn, en
    if _CJK_RE.search(text):
        return text, ""
    return "", text


def _parse(text: str) -> list[tuple[str, str, str]]:
    """解析搜索结果，返回 [(kind, 中文名, 英文名)]，按页面排序。"""
    entries: list[tuple[str, str, str]] = []
    for chunk in (text or "").split('class="result-item"')[1:]:
        # 只取每条结果的标题区，避免把页面底部的地址等信息一起解析进来
        head = chunk.split('<div class="body">')[0]
        for link in _LINK_RE.finditer(head):
            label = _clean(link.group(3))
            if not label or "mcmod.cn" in label:
                continue
            cn, en = _split_label(label)
            entries.append((link.group(2), cn, en))
            break
    return entries


# ----------------------------------------------------------------------
# 对外接口
def lookup_name(title: str) -> str:
    """查英文项目名的中文译名（可能发起一次网络请求）；失败返回空字符串。"""
    key = _key(title)
    if not key:
        return ""
    _ensure_loaded()
    with _lock:
        if key in _names:
            return _names[key]
    page = _fetch(title)
    if page is None:
        return ""
    found = ""
    for _kind, cn, en in _parse(page):
        # 只接受英文名完全一致的结果，避免把「GTNH 版」等衍生条目当成主条目
        if cn and _CJK_RE.search(cn) and _key(en) == key:
            found = cn
            break
    if found:
        with _lock:
            _names[key] = found
            _save_locked()
    else:
        # 站点没有该条目时，短时间内不再重复请求
        with _lock:
            _failed_until[title] = time.time() + 1800
    return found


def lookup_query(query: str) -> list[str]:
    """把中文关键词翻译成平台上的英文项目名（最多两个）。"""
    text = (query or "").strip()
    if not text:
        return []
    _ensure_loaded()
    with _lock:
        if text in _queries:
            return list(_queries[text])
    page = _fetch(text)
    if page is None:
        return []
    results: list[str] = []
    seen: set[str] = set()
    for _kind, _cn, en in _parse(page):
        en = en.strip()
        if len(en) < 2 or _CJK_RE.search(en):
            continue
        lowered = en.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        results.append(en)
        if len(results) >= 2:
            break
    if not results:
        with _lock:
            _failed_until[text] = time.time() + 600
        return []
    with _lock:
        _queries[text] = results
        _save_locked()
    return results


def prefetch(titles: list[str], limit: int = 12, deadline: float = 10.0) -> None:
    """批量补齐译名（后台线程用）；超过时间预算就停下，避免卡住界面。"""
    started = time.time()
    done = 0
    for title in titles:
        if done >= limit or time.time() - started > deadline:
            return
        if cached_name(title):
            continue
        if lookup_name(title):
            done += 1
