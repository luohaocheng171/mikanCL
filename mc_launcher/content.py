"""内容中心：Modrinth / CurseForge 的搜索、版本查询、下载与整合包安装。

支持 Mod、整合包、资源包、光影包；下载地址支持自定义镜像，整合包支持 mrpack 与
CurseForge 整合包 zip，安装时多线程下载并自动应用 overrides。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import time
import urllib.error
import urllib.parse
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import USER_AGENT
from . import mod_cn
from .config import (
    CACHE_DIR,
    CURSEFORGE_CDN_HOSTS,
    MODRINTH_CDN_BASE,
    Config,
)
from .net import Candidate, Cancelled, DownloadError, Http

PROJECT_TYPES = {
    "mod": "Mod",
    "modpack": "整合包",
    "resourcepack": "资源包",
    "texturepack": "材质包",
    "shader": "光影包",
}

SOURCE_LABELS = {"modrinth": "Modrinth", "curseforge": "CurseForge"}

CF_CLASS_IDS = {"mod": 6, "modpack": 4471, "resourcepack": 12, "shader": 6552, "texturepack": 12}
CF_LOADER_TYPES = {"forge": 1, "liteloader": 3, "fabric": 4, "quilt": 5, "neoforge": 6}
MODRINTH_LOADERS = {"forge", "fabric", "quilt", "neoforge"}

CF_FILE_BASE = "https://mediafilez.forgecdn.net/files/{a}/{b}/{name}"

DEPENDENCY_REQUIRED = "required"
DEPENDENCY_OPTIONAL = "optional"

# CurseForge 依赖关系：2 = OptionalDependency，3 = RequiredDependency
CF_RELATION_OPTIONAL = 2
CF_RELATION_REQUIRED = 3
CF_RELATION_LABELS = {
    CF_RELATION_OPTIONAL: DEPENDENCY_OPTIONAL,
    CF_RELATION_REQUIRED: DEPENDENCY_REQUIRED,
}

# Modrinth 资源包若带分辨率分类，基本都是改材质的材质包；不带分辨率的多为
# 数据包、字体包、语言包等。用于「材质包」这一独立搜索项。
TEXTURE_CATEGORIES = [
    "8x-",
    "16x",
    "32x",
    "48x",
    "64x",
    "128x",
    "256x",
    "512x+",
]

_CF_PROJECT_TYPES: dict[int, str] = {}
for _key, _value in CF_CLASS_IDS.items():
    # 同名类别（资源包 / 材质包共用 classId 12）保留第一个，避免反向映射被覆盖
    _CF_PROJECT_TYPES.setdefault(_value, _key)


@dataclass
class ContentProject:
    source: str
    id: str
    title: str
    description: str = ""
    project_type: str = "mod"
    author: str = ""
    downloads: int = 0
    icon_url: str = ""
    categories: list[str] = field(default_factory=list)
    slug: str = ""
    page_url: str = ""

    @property
    def source_label(self) -> str:
        return SOURCE_LABELS.get(self.source, self.source)

    @property
    def type_label(self) -> str:
        return PROJECT_TYPES.get(self.project_type, self.project_type)

    @property
    def display_title(self) -> str:
        """界面展示名：词表命中时显示中文名，否则沿用英文原名。"""
        return mod_cn.cn_name(self.title) or self.title

    @property
    def display_description(self) -> str:
        """界面简述：优先使用中文简介，词表未收录时沿用平台原文。"""
        return mod_cn.cn_description(self.title) or self.description


@dataclass
class ContentFile:
    url: str
    filename: str
    size: int = 0
    sha1: str = ""
    primary: bool = True


@dataclass
class ContentVersion:
    id: str
    project_id: str
    name: str
    version_number: str
    game_versions: list[str] = field(default_factory=list)
    loaders: list[str] = field(default_factory=list)
    files: list[ContentFile] = field(default_factory=list)
    dependencies: list[dict] = field(default_factory=list)
    date: str = ""
    downloads: int = 0
    channel: str = ""

    @property
    def primary_file(self) -> ContentFile | None:
        for file in self.files:
            if file.primary:
                return file
        return self.files[0] if self.files else None

    @property
    def required_dependencies(self) -> list[dict]:
        """必装前置（已按平台格式归一化）。"""
        return [
            dep
            for dep in self.dependencies
            if dep.get("dependency_type") == DEPENDENCY_REQUIRED
        ]

    @property
    def optional_dependencies(self) -> list[dict]:
        """可选前置，界面上标记为「可选」。"""
        return [
            dep
            for dep in self.dependencies
            if dep.get("dependency_type") == DEPENDENCY_OPTIONAL
        ]

    @property
    def label(self) -> str:
        parts = [self.name or self.version_number]
        if self.game_versions:
            parts.append(self.game_versions[0])
        if self.loaders:
            parts.append("/".join(self.loaders))
        return " · ".join(parts)


@dataclass
class ModpackMeta:
    name: str
    mc_version: str
    loader: str
    loader_version: str
    files: list[tuple[str, ContentFile]] = field(default_factory=list)
    overrides: list[str] = field(default_factory=lambda: ["overrides"])
    pack_format: str = "mrpack"
    version: str = ""


def is_version_compatible(
    version: ContentVersion, mc_version: str = "", loader: str = ""
) -> bool:
    """判断文件是否声明支持目标 MC 版本与加载器（空条件视为不限）。"""
    if mc_version:
        exact = mc_version in version.game_versions
        related = any(v.startswith(mc_version + ".") for v in version.game_versions)
        if not exact and not related and version.game_versions:
            return False
    if loader and version.loaders:
        if not any(item.lower() == loader.lower() for item in version.loaders):
            return False
    return True


def score_version(
    version: ContentVersion, mc_version: str = "", loader: str = "", keyword: str = ""
) -> int:
    """给候选文件打分：MC 版本、加载器、文件名关键词匹配。"""
    score = 0
    if mc_version:
        if mc_version in version.game_versions:
            score += 6
        elif any(v.startswith(mc_version + ".") for v in version.game_versions):
            score += 3
    if loader:
        if any(item.lower() == loader.lower() for item in version.loaders):
            score += 5
        elif version.loaders:
            score -= 20
    if keyword:
        haystack = " ".join(
            [version.name, version.version_number]
            + [file.filename for file in version.files]
        ).lower()
        if keyword.lower() in haystack:
            score += 4
    return score


def pick_best_version(
    versions: list[ContentVersion],
    mc_version: str = "",
    loader: str = "",
    keyword: str = "",
) -> ContentVersion | None:
    """按匹配度挑选最合适的文件；同分时保留列表中靠前（通常是最新）的版本。"""
    best: ContentVersion | None = None
    best_score = -10**9
    for version in versions:
        if version.primary_file is None:
            continue
        value = score_version(version, mc_version, loader, keyword)
        if value > best_score:
            best, best_score = version, value
    return best


class ContentError(Exception):
    pass


def rewrite_download_url(url: str, source: str, config: Config) -> str:
    """按镜像设置改写内容下载地址。"""
    if not url:
        return url
    if source == "modrinth" and config.modrinth_cdn_mirror.strip():
        mirror = config.modrinth_cdn_mirror.strip().rstrip("/")
        if url.startswith(MODRINTH_CDN_BASE):
            return mirror + url[len(MODRINTH_CDN_BASE):]
        return url
    if source == "curseforge" and config.curseforge_cdn_mirror.strip():
        mirror = config.curseforge_cdn_mirror.strip().rstrip("/")
        parsed = urllib.parse.urlsplit(url)
        if (parsed.hostname or "").lower() in CURSEFORGE_CDN_HOSTS:
            return mirror + parsed.path + (("?" + parsed.query) if parsed.query else "")
    return url


def _cf_file_url(file_id: int, filename: str) -> str:
    # 文件名可能含空格、引号、方括号等字符，必须先转义否则 urllib 会拒绝请求
    return CF_FILE_BASE.format(
        a=file_id // 1000, b=file_id % 1000, name=urllib.parse.quote(filename, safe="")
    )


def _lower_list(values) -> list[str]:
    return [str(v).lower() for v in (values or [])]


def _guess_loaders(game_versions: list[str]) -> list[str]:
    result = []
    for value in game_versions:
        key = value.strip().lower().replace(" ", "")
        if key in CF_LOADER_TYPES:
            result.append(key)
    return result


def _normalize_mc_versions(values: list[str]) -> list[str]:
    return [v for v in values if re.fullmatch(r"\d+\.\d+(\.\d+)?", str(v).strip())]


def _modrinth_dependencies(raw: dict) -> list[dict]:
    """把 Modrinth 的 dependencies 归一化为统一结构，只保留必装/可选前置。"""
    result: list[dict] = []
    for item in raw.get("dependencies") or []:
        if not isinstance(item, dict):
            continue
        dep_type = str(item.get("dependency_type") or DEPENDENCY_REQUIRED).lower()
        if dep_type not in (DEPENDENCY_REQUIRED, DEPENDENCY_OPTIONAL):
            continue
        project_id = str(item.get("project_id") or "")
        if not project_id:
            continue
        result.append(
            {
                "project_id": project_id,
                "version_id": str(item.get("version_id") or ""),
                "dependency_type": dep_type,
            }
        )
    return result


def _curseforge_dependencies(raw: dict) -> list[dict]:
    """把 CurseForge 的 dependencies 归一化为统一结构，只保留必装/可选前置。"""
    result: list[dict] = []
    for item in raw.get("dependencies") or []:
        if not isinstance(item, dict):
            continue
        try:
            relation = int(item.get("relationType"))
        except (TypeError, ValueError):
            continue
        dep_type = CF_RELATION_LABELS.get(relation)
        if dep_type is None:
            continue
        mod_id = str(item.get("modId") or "")
        if not mod_id:
            continue
        result.append(
            {
                "project_id": mod_id,
                # 兼容 content.py 内部安装流程沿用的字段名
                "modId": mod_id,
                "dependency_type": dep_type,
                "relation_type": relation,
            }
        )
    return result


def _project_from_modrinth(raw: dict, project_type: str = "mod") -> ContentProject | None:
    project_id = str(raw.get("id") or raw.get("project_id") or "")
    if not project_id:
        return None
    slug = str(raw.get("slug") or project_id)
    kind = str(raw.get("project_type") or project_type)
    return ContentProject(
        source="modrinth",
        id=project_id,
        title=str(raw.get("title") or slug),
        description=str(raw.get("description") or ""),
        project_type=kind,
        author="",
        downloads=int(raw.get("downloads") or 0),
        icon_url=str(raw.get("icon_url") or ""),
        categories=[str(c) for c in (raw.get("categories") or [])],
        slug=slug,
        page_url=f"https://modrinth.com/{kind}/{slug}",
    )


def _project_from_curseforge(raw: dict, project_type: str = "mod") -> ContentProject | None:
    mod_id = str(raw.get("id") or "")
    if not mod_id:
        return None
    links = raw.get("links") if isinstance(raw.get("links"), dict) else {}
    logo = raw.get("logo") if isinstance(raw.get("logo"), dict) else {}
    authors = raw.get("authors") or []
    author = ""
    if isinstance(authors, list) and authors and isinstance(authors[0], dict):
        author = str(authors[0].get("name") or "")
    try:
        kind = _CF_PROJECT_TYPES.get(int(raw.get("classId") or 0), project_type)
    except (TypeError, ValueError):
        kind = project_type
    return ContentProject(
        source="curseforge",
        id=mod_id,
        title=str(raw.get("name") or mod_id),
        description=str(raw.get("summary") or ""),
        project_type=kind,
        author=author,
        downloads=int(raw.get("downloadCount") or 0),
        icon_url=str(logo.get("thumbnailUrl") or logo.get("url") or ""),
        categories=[
            str(c.get("name")) for c in (raw.get("categories") or []) if isinstance(c, dict)
        ],
        slug=str(raw.get("slug") or mod_id),
        page_url=str(links.get("websiteUrl") or ""),
    )


def _dependency_project_id(dep: dict) -> str:
    """从归一化（或旧格式）依赖里取前置项目 id。"""
    return str(dep.get("project_id") or dep.get("modId") or "")


def mc_version_key(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in re.split(r"[.\-]", str(value)):
        parts.append(int(piece) if piece.isdigit() else 0)
    return tuple(parts)


class ContentClient:
    def __init__(self, config: Config):
        self.config = config
        self.http = Http(timeout=35)

    def _request_retry(self, fn: Callable[[], dict | list], label: str) -> dict | list:
        """网络请求重试：遇连接类异常（URLError / ConnectionError / 10053 / 10054 / timed out）
        最多重试 3 次（间隔 1~2 秒），重试耗尽抛 DownloadError；其余异常原样抛出。"""
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                return fn()
            except urllib.error.HTTPError:
                raise  # HTTP 状态类错误（404 等）不重试
            except Exception as exc:  # noqa: BLE001 - 仅连接类异常重试
                text = str(exc)
                retryable = (
                    isinstance(exc, (urllib.error.URLError, ConnectionError, OSError))
                    or "10053" in text
                    or "10054" in text
                    or "timed out" in text.lower()
                )
                if not retryable:
                    raise
                last_error = exc
            if attempt < 2:
                time.sleep(1 + attempt)
        raise DownloadError(f"{label}连续重试 3 次仍失败：{last_error}") from last_error

    # ------------------------------------------------------------------
    # 平台请求
    def _modrinth(self, path: str, params: dict | None = None) -> dict | list:
        base = (self.config.modrinth_api_base or "https://api.modrinth.com/v2").rstrip("/")
        url = base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        return self._request_retry(
            lambda: self.http.get_json_url(url, headers={"User-Agent": USER_AGENT}),
            "Modrinth 请求",
        )

    def _curseforge(self, path: str, params: dict | None = None) -> dict | list:
        base = (self.config.curseforge_api_base or "https://api.curseforge.com/v1").rstrip("/")
        url = base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        key = (self.config.curseforge_api_key or "").strip()
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        if key:
            headers["x-api-key"] = key
        return self._request_retry(
            lambda: self.http.get_json_url(url, headers=headers),
            "CurseForge 请求",
        )

    def _curseforge_post(self, path: str, payload: dict) -> dict | list:
        base = (self.config.curseforge_api_base or "https://api.curseforge.com/v1").rstrip("/")
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        key = (self.config.curseforge_api_key or "").strip()
        if key:
            headers["x-api-key"] = key
        return self._request_retry(
            lambda: self.http.post_json_url(base + path, payload, headers=headers),
            "CurseForge 请求",
        )

    # ------------------------------------------------------------------
    def search(
        self,
        source: str,
        project_type: str,
        query: str = "",
        game_version: str = "",
        loader: str = "",
        offset: int = 0,
        limit: int = 20,
    ) -> list[ContentProject]:
        """平台搜索。中文关键词会先映射为常用英文项目名，再分别检索并合并去重。"""
        queries = [query]
        if query and mod_cn.has_chinese(query):
            translated = mod_cn.translate_query(query)
            if translated:
                queries = translated
        if len(queries) == 1:
            return self._search_one(
                source, project_type, queries[0], game_version, loader, offset, limit
            )
        merged: list[ContentProject] = []
        seen: set[tuple[str, str]] = set()
        first_error: ContentError | None = None
        for item in queries:
            try:
                rows = self._search_one(
                    source, project_type, item, game_version, loader, offset, limit
                )
            except ContentError as exc:
                first_error = first_error or exc
                continue
            for project in rows:
                key = (project.source, project.id)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(project)
        if not merged and first_error is not None:
            raise first_error
        if not merged:
            # 译名没有命中时退回原始关键词，避免中文项目名被完全过滤掉
            return self._search_one(
                source, project_type, query, game_version, loader, offset, limit
            )
        return merged[: max(1, min(50, limit))]

    def _search_one(
        self,
        source: str,
        project_type: str,
        query: str,
        game_version: str,
        loader: str,
        offset: int,
        limit: int,
    ) -> list[ContentProject]:
        if source == "curseforge":
            return self._search_curseforge(project_type, query, game_version, loader, offset, limit)
        return self._search_modrinth(project_type, query, game_version, loader, offset, limit)

    def _search_modrinth(
        self,
        project_type: str,
        query: str,
        game_version: str,
        loader: str,
        offset: int,
        limit: int,
    ) -> list[ContentProject]:
        # 「材质包」在 Modrinth 里仍属于 resourcepack，用分辨率分类筛掉数据包/字体包等
        modrinth_type = "resourcepack" if project_type == "texturepack" else project_type
        facets: list[list[str]] = [[f"project_type:{modrinth_type}"]]
        if project_type == "texturepack":
            facets.append([f"categories:{name}" for name in TEXTURE_CATEGORIES])
        if game_version:
            facets.append([f"versions:{game_version}"])
        if loader and loader in MODRINTH_LOADERS:
            facets.append([f"categories:{loader}"])
        params = {
            "query": query or "",
            "facets": json.dumps(facets, separators=(",", ":")),
            "limit": max(1, min(50, limit)),
            "offset": max(0, offset),
        }
        try:
            data = self._modrinth("/search", params)
        except DownloadError as exc:
            raise ContentError(f"Modrinth 搜索失败：{exc}") from exc
        hits = data.get("hits") if isinstance(data, dict) else None
        projects: list[ContentProject] = []
        for hit in hits or []:
            if not isinstance(hit, dict):
                continue
            project_id = str(hit.get("project_id") or "")
            slug = str(hit.get("slug") or project_id)
            projects.append(
                ContentProject(
                    source="modrinth",
                    id=project_id,
                    title=str(hit.get("title") or slug),
                    description=str(hit.get("description") or ""),
                    project_type=(
                        project_type
                        if project_type == "texturepack"
                        else str(hit.get("project_type") or project_type)
                    ),
                    author=str(hit.get("author") or ""),
                    downloads=int(hit.get("downloads") or 0),
                    icon_url=str(hit.get("icon_url") or ""),
                    categories=[str(c) for c in (hit.get("categories") or [])],
                    slug=slug,
                    page_url=f"https://modrinth.com/{modrinth_type}/{slug}",
                )
            )
        return projects

    def _search_curseforge(
        self,
        project_type: str,
        query: str,
        game_version: str,
        loader: str,
        offset: int,
        limit: int,
    ) -> list[ContentProject]:
        params = {
            "gameId": 432,
            "classId": CF_CLASS_IDS.get(project_type, 6),
            "searchFilter": query or "",
            "index": max(0, offset),
            "pageSize": max(1, min(50, limit)),
            "sortField": 2,
            "sortOrder": "desc",
        }
        if game_version:
            params["gameVersion"] = game_version
        if loader and loader in CF_LOADER_TYPES:
            params["modLoaderType"] = CF_LOADER_TYPES[loader]
        try:
            data = self._curseforge("/mods/search", params)
        except DownloadError as exc:
            raise ContentError(
                f"CurseForge 搜索失败：{exc}\n请在设置中检查 CurseForge API Key 或镜像地址。"
            ) from exc
        rows = data.get("data") if isinstance(data, dict) else None
        projects: list[ContentProject] = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            links = row.get("links") if isinstance(row.get("links"), dict) else {}
            logo = row.get("logo") if isinstance(row.get("logo"), dict) else {}
            authors = row.get("authors") or []
            author = ""
            if isinstance(authors, list) and authors and isinstance(authors[0], dict):
                author = str(authors[0].get("name") or "")
            categories = [
                str(c.get("name"))
                for c in (row.get("categories") or [])
                if isinstance(c, dict)
            ]
            projects.append(
                ContentProject(
                    source="curseforge",
                    id=str(row.get("id") or ""),
                    title=str(row.get("name") or ""),
                    description=str(row.get("summary") or ""),
                    project_type=project_type,
                    author=author,
                    downloads=int(row.get("downloadCount") or 0),
                    icon_url=str(logo.get("thumbnailUrl") or logo.get("url") or ""),
                    categories=categories,
                    slug=str(row.get("slug") or row.get("id") or ""),
                    page_url=str(links.get("websiteUrl") or ""),
                )
            )
        return projects

    # ------------------------------------------------------------------
    def project_game_versions(self, source: str, project_id: str) -> list[str]:
        """轻量获取项目支持的 Minecraft 版本（不拉取全部文件列表）。"""
        if source == "curseforge":
            return self._curseforge_project_versions(project_id)
        return self._modrinth_project_versions(project_id)

    def _modrinth_project_versions(self, project_id: str) -> list[str]:
        try:
            data = self._modrinth(f"/project/{project_id}")
        except DownloadError as exc:
            raise ContentError(f"获取 Modrinth 项目信息失败：{exc}") from exc
        values = data.get("game_versions") if isinstance(data, dict) else None
        versions = sorted(
            {str(v) for v in (values or []) if re.fullmatch(r"\d+\.\d+(\.\d+)?", str(v))},
            key=mc_version_key,
            reverse=True,
        )
        return versions

    def _curseforge_project_versions(self, project_id: str) -> list[str]:
        try:
            data = self._curseforge(f"/mods/{project_id}")
        except DownloadError as exc:
            raise ContentError(f"获取 CurseForge 项目信息失败：{exc}") from exc
        row = data.get("data") if isinstance(data, dict) else None
        found: set[str] = set()
        if isinstance(row, dict):
            for item in row.get("latestFilesIndexes") or []:
                if isinstance(item, dict):
                    value = str(item.get("gameVersion") or "")
                    if re.fullmatch(r"\d+\.\d+(\.\d+)?", value):
                        found.add(value)
            for value in _normalize_mc_versions([str(v) for v in (row.get("gameVersions") or [])]):
                found.add(value)
        return sorted(found, key=mc_version_key, reverse=True)

    def versions(
        self, source: str, project_id: str, game_version: str = "", loader: str = ""
    ) -> list[ContentVersion]:
        if source == "curseforge":
            return self._curseforge_versions(project_id, game_version, loader)
        return self._modrinth_versions(project_id, game_version, loader)

    def _modrinth_versions(
        self, project_id: str, game_version: str = "", loader: str = ""
    ) -> list[ContentVersion]:
        params: dict = {}
        if game_version:
            params["game_versions"] = json.dumps([game_version])
        if loader and loader in MODRINTH_LOADERS:
            params["loaders"] = json.dumps([loader])
        try:
            data = self._modrinth(f"/project/{project_id}/version", params or None)
        except DownloadError as exc:
            raise ContentError(f"获取 Modrinth 版本失败：{exc}") from exc
        versions: list[ContentVersion] = []
        for row in data if isinstance(data, list) else []:
            if not isinstance(row, dict):
                continue
            files = []
            for file in row.get("files") or []:
                if not isinstance(file, dict):
                    continue
                hashes = file.get("hashes") if isinstance(file.get("hashes"), dict) else {}
                files.append(
                    ContentFile(
                        url=str(file.get("url") or ""),
                        filename=str(file.get("filename") or "download.bin"),
                        size=int(file.get("size") or 0),
                        sha1=str(hashes.get("sha1") or ""),
                        primary=bool(file.get("primary", False)),
                    )
                )
            versions.append(
                ContentVersion(
                    id=str(row.get("id") or ""),
                    project_id=str(row.get("project_id") or project_id),
                    name=str(row.get("name") or ""),
                    version_number=str(row.get("version_number") or ""),
                    game_versions=[str(v) for v in (row.get("game_versions") or [])],
                    loaders=[str(v) for v in (row.get("loaders") or [])],
                    files=files,
                    dependencies=_modrinth_dependencies(row),
                    date=str(row.get("date_published") or "")[:19].replace("T", " "),
                    downloads=int(row.get("downloads") or 0),
                    channel=str(row.get("version_type") or ""),
                )
            )
        return versions

    def _curseforge_versions(
        self, project_id: str, game_version: str = "", loader: str = ""
    ) -> list[ContentVersion]:
        params: dict = {"pageSize": 50}
        if game_version:
            params["gameVersion"] = game_version
        if loader and loader in CF_LOADER_TYPES:
            params["modLoaderType"] = CF_LOADER_TYPES[loader]
        rows: list[dict] = []
        index = 0
        try:
            while index < 3000:
                page_params = dict(params)
                page_params["index"] = index
                data = self._curseforge(f"/mods/{project_id}/files", page_params)
                page = data.get("data") if isinstance(data, dict) else None
                page_rows = [r for r in (page or []) if isinstance(r, dict)]
                rows.extend(page_rows)
                pagination = data.get("pagination") if isinstance(data, dict) else None
                total = 0
                if isinstance(pagination, dict):
                    try:
                        total = int(pagination.get("totalCount") or 0)
                    except (TypeError, ValueError):
                        total = 0
                index += len(page_rows)
                if len(page_rows) < int(params["pageSize"]):
                    break
                if total and index >= total:
                    break
        except DownloadError as exc:
            raise ContentError(f"获取 CurseForge 文件失败：{exc}") from exc
        versions: list[ContentVersion] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            file_id = int(row.get("id") or 0)
            filename = str(row.get("fileName") or f"{file_id}.jar")
            url = str(row.get("downloadUrl") or "") or _cf_file_url(file_id, filename)
            sha1 = ""
            for item in row.get("hashes") or []:
                if isinstance(item, dict) and int(item.get("algo") or 0) == 1:
                    sha1 = str(item.get("value") or "")
            game_values = [str(v) for v in (row.get("gameVersions") or [])]
            mc_versions = _normalize_mc_versions(game_values)
            versions.append(
                ContentVersion(
                    id=str(file_id),
                    project_id=str(project_id),
                    name=str(row.get("displayName") or filename),
                    version_number=str(row.get("displayName") or filename),
                    game_versions=mc_versions or game_values,
                    loaders=_guess_loaders(game_values),
                    files=[
                        ContentFile(
                            url=url,
                            filename=filename,
                            size=int(row.get("fileLength") or 0),
                            sha1=sha1,
                        )
                    ],
                    dependencies=_curseforge_dependencies(row),
                    date=str(row.get("fileDate") or "")[:19].replace("T", " "),
                    downloads=int(row.get("downloadCount") or 0),
                    channel=str(row.get("releaseType") or ""),
                )
            )
        return versions

    def _modrinth_version(self, version_id: str) -> ContentVersion | None:
        try:
            row = self._modrinth(f"/version/{version_id}")
        except DownloadError:
            return None
        if not isinstance(row, dict):
            return None
        files = []
        for file in row.get("files") or []:
            if not isinstance(file, dict):
                continue
            hashes = file.get("hashes") if isinstance(file.get("hashes"), dict) else {}
            files.append(
                ContentFile(
                    url=str(file.get("url") or ""),
                    filename=str(file.get("filename") or "download.bin"),
                    size=int(file.get("size") or 0),
                    sha1=str(hashes.get("sha1") or ""),
                    primary=bool(file.get("primary", False)),
                )
            )
        return ContentVersion(
            id=str(row.get("id") or ""),
            project_id=str(row.get("project_id") or ""),
            name=str(row.get("name") or ""),
            version_number=str(row.get("version_number") or ""),
            game_versions=[str(v) for v in (row.get("game_versions") or [])],
            loaders=[str(v) for v in (row.get("loaders") or [])],
            files=files,
            dependencies=_modrinth_dependencies(row),
            date=str(row.get("date_published") or "")[:19].replace("T", " "),
            downloads=int(row.get("downloads") or 0),
        )

    # ------------------------------------------------------------------
    def fetch_projects_by_ids(
        self,
        source: str,
        ids: list[str],
        log: Callable[[str], None] | None = None,
    ) -> list[ContentProject]:
        """按项目 id 批量解析前置 Mod 的项目信息。

        网络失败、id 非法或平台不支持时一律跳过对应条目（返回空列表而不抛异常），
        保证详情页的前置区块可以安全降级。
        """
        wanted: list[str] = []
        seen: set[str] = set()
        for item in ids or []:
            value = str(item or "").strip()
            if value and value not in seen:
                seen.add(value)
                wanted.append(value)
        if not wanted:
            return []
        if source == "curseforge":
            return self._curseforge_projects_by_ids(wanted, log)
        if source == "modrinth":
            return self._modrinth_projects_by_ids(wanted, log)
        return []

    def _modrinth_projects_by_ids(
        self, ids: list[str], log: Callable[[str], None] | None = None
    ) -> list[ContentProject]:
        def fetch(project_id: str) -> ContentProject | None:
            try:
                data = self._modrinth(f"/project/{project_id}")
            except Exception as exc:  # noqa: BLE001 - 单个前置解析失败不应影响整块展示
                if log:
                    log(f"[前置] 解析 Modrinth 项目 {project_id} 失败：{exc}")
                return None
            return _project_from_modrinth(data, "mod") if isinstance(data, dict) else None

        projects: list[ContentProject] = []
        with ThreadPoolExecutor(max_workers=max(1, min(4, len(ids)))) as pool:
            for project in pool.map(fetch, ids):
                if project is not None:
                    projects.append(project)
        return projects

    def _curseforge_projects_by_ids(
        self, ids: list[str], log: Callable[[str], None] | None = None
    ) -> list[ContentProject]:
        projects: list[ContentProject] = []
        for start in range(0, len(ids), 100):
            chunk = ids[start:start + 100]
            numeric: list[int] = []
            for value in chunk:
                try:
                    numeric.append(int(value))
                except (TypeError, ValueError):
                    continue
            rows: list[dict] = []
            if numeric:
                try:
                    data = self._curseforge_post("/mods", {"modIds": numeric})
                    page = data.get("data") if isinstance(data, dict) else None
                    rows = [row for row in (page or []) if isinstance(row, dict)]
                except Exception as exc:  # noqa: BLE001 - 批量失败时退回逐个查询
                    if log:
                        log(f"[前置] CurseForge 批量解析失败，改为逐个查询：{exc}")
            if not rows and numeric:
                for mod_id in numeric:
                    try:
                        data = self._curseforge(f"/mods/{mod_id}")
                    except Exception:  # noqa: BLE001 - 单个前置解析失败直接跳过
                        continue
                    row = data.get("data") if isinstance(data, dict) else None
                    if isinstance(row, dict):
                        rows.append(row)
            for row in rows:
                project = _project_from_curseforge(row)
                if project is not None:
                    projects.append(project)
        return projects

    # ------------------------------------------------------------------
    def check_mod_updates(
        self,
        jars: list[Path],
        game_version: str = "",
        loader: str = "",
        log: Callable[[str], None] | None = None,
    ) -> list[tuple[Path, ContentVersion]]:
        """通过 Modrinth 哈希接口识别本地 Mod，再查询各自的最新兼容版本。"""
        digests: dict[str, Path] = {}
        for path in jars:
            try:
                digest = hashlib.sha1()
                with path.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 256), b""):
                        digest.update(chunk)
                digests[digest.hexdigest()] = path
            except OSError:
                continue
        if not digests:
            return []
        base = (self.config.modrinth_api_base or "https://api.modrinth.com/v2").rstrip("/")
        try:
            matched = self.http.post_json_url(
                base + "/version_files",
                {"hashes": list(digests), "algorithm": "sha1"},
                headers={"User-Agent": USER_AGENT},
            )
        except DownloadError as exc:
            raise ContentError(f"检查更新失败：{exc}") from exc

        current: dict[str, tuple[Path, str]] = {}
        for digest, row in (matched or {}).items() if isinstance(matched, dict) else []:
            if not isinstance(row, dict):
                continue
            path = digests.get(digest)
            if path is None:
                continue
            project_id = str(row.get("project_id") or "")
            if project_id:
                current.setdefault(project_id, (path, str(row.get("version_number") or "")))

        updates: list[tuple[Path, ContentVersion]] = []

        def fetch(item: tuple[str, tuple[Path, str]]) -> tuple[Path, ContentVersion] | None:
            project_id, (path, installed_number) = item
            try:
                versions = self._modrinth_versions(project_id, game_version, loader)
            except ContentError:
                return None
            if not versions:
                return None
            latest = versions[0]
            if latest.version_number and latest.version_number == installed_number:
                return None
            return path, latest

        if current:
            with ThreadPoolExecutor(max_workers=min(4, len(current))) as pool:
                for result in pool.map(fetch, list(current.items())):
                    if result is not None:
                        updates.append(result)
        if log:
            log(f"[更新] 已检查 {len(current)} 个 Mod，发现 {len(updates)} 个可更新。")
        return updates

    def _download_single(
        self,
        source: str,
        file: ContentFile,
        dest: Path,
        cancel: threading.Event | None = None,
        pause: threading.Event | None = None,
    ) -> Path:
        candidates = []
        rewritten = rewrite_download_url(file.url, source, self.config)
        if rewritten and rewritten != file.url:
            candidates.append(Candidate(rewritten, {"User-Agent": USER_AGENT}, source, "镜像"))
        candidates.append(Candidate(file.url, {"User-Agent": USER_AGENT}, source, source))
        if source == "curseforge":
            # CurseForge 两个 CDN 节点偶尔返回 403/404，互为备份可显著提升成功率
            parsed = urllib.parse.urlsplit(file.url)
            host = (parsed.hostname or "").lower()
            alternate = ""
            if host.endswith("edge.forgecdn.net"):
                alternate = "mediafilez.forgecdn.net"
            elif host.endswith("mediafilez.forgecdn.net"):
                alternate = "edge.forgecdn.net"
            if alternate:
                alt_url = urllib.parse.urlunsplit(
                    (parsed.scheme, alternate, parsed.path, parsed.query, "")
                )
                candidates.append(Candidate(alt_url, {"User-Agent": USER_AGENT}, source, "备用 CDN"))
        # 连接类异常最多重试 3 次；取消时立即退出
        last_error: Exception | None = None
        for attempt in range(3):
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            try:
                self.http.download(
                    candidates,
                    dest,
                    size=file.size or None,
                    sha1=file.sha1 or None,
                    cancel=cancel,
                    pause=pause,
                )
                return dest
            except Cancelled:
                raise
            except Exception as exc:  # noqa: BLE001 - 仅连接类异常重试
                text = str(exc)
                retryable = (
                    isinstance(exc, (urllib.error.URLError, ConnectionError, OSError))
                    or "10053" in text
                    or "10054" in text
                    or "timed out" in text.lower()
                )
                if not retryable:
                    raise ContentError(f"下载 {file.filename} 失败：{exc}") from exc
                last_error = exc
            if attempt < 2:
                time.sleep(1 + attempt)
        raise ContentError(
            f"下载 {file.filename} 失败（重试 3 次仍失败）：{last_error}"
        ) from last_error

    def download_to(
        self,
        source: str,
        file: ContentFile,
        directory: Path,
        cancel: threading.Event | None = None,
        pause: threading.Event | None = None,
    ) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        return self._download_single(source, file, directory / file.filename, cancel, pause)

    def download_many(
        self,
        tasks: list[tuple[str, ContentFile, Path]],
        log: Callable[[str], None] | None = None,
        cancel: threading.Event | None = None,
        workers: int | None = None,
        pause: threading.Event | None = None,
        progress: Callable[[int, int], None] | None = None,
    ) -> list[str]:
        """多线程下载 [(source, file, dest)]，返回失败描述列表。"""
        if not tasks:
            return []
        workers = workers or max(4, int(self.config.download_threads))
        failures: list[str] = []
        succeeded = 0

        def work(task: tuple[str, ContentFile, Path]) -> str:
            source, file, dest = task
            if cancel is not None and cancel.is_set():
                return ""
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                self._download_single(source, file, dest, cancel, pause)
                return ""
            except ContentError as exc:
                return str(exc)

        with ThreadPoolExecutor(max_workers=max(1, min(workers, len(tasks)))) as pool:
            futures = {pool.submit(work, task): task for task in tasks}
            for future in as_completed(futures):
                message = future.result()
                if message:
                    failures.append(message)
                    if log:
                        log(f"[下载] {message}")
                elif progress is not None:
                    succeeded += 1
                    progress(succeeded, len(tasks))
        return failures

    # ------------------------------------------------------------------
    def install_content(
        self,
        project: ContentProject,
        version: ContentVersion,
        game_dir: Path,
        log: Callable[[str], None] | None = None,
        cancel: threading.Event | None = None,
        install_dependencies: bool = True,
        pause: threading.Event | None = None,
    ) -> list[Path]:
        """安装单个 Mod / 资源包 / 光影包到指定游戏目录。"""
        targets = {
            "mod": "mods",
            "resourcepack": "resourcepacks",
            "texturepack": "resourcepacks",
            "shader": "shaderpacks",
        }
        folder = targets.get(project.project_type, "mods")
        file = version.primary_file
        if file is None:
            raise ContentError("该版本没有可下载的文件。")
        if log:
            log(f"[内容] 安装 {project.title} · {version.version_number} → {folder}/")
        installed = [self.download_to(project.source, file, game_dir / folder, cancel, pause)]
        if project.project_type == "mod" and install_dependencies:
            installed.extend(
                self._install_dependencies(project, version, game_dir, log, cancel, depth=0, pause=pause)
            )
        return installed

    def _install_dependencies(
        self,
        project: ContentProject,
        version: ContentVersion,
        game_dir: Path,
        log: Callable[[str], None] | None,
        cancel: threading.Event | None,
        depth: int,
        visited: set[str] | None = None,
        pause: threading.Event | None = None,
    ) -> list[Path]:
        if depth >= 3 or not version.dependencies:
            return []
        visited = visited or {project.id}
        installed: list[Path] = []
        for dep in version.dependencies:
            if dep.get("dependency_type") not in (None, "required", 3):
                continue
            dep_version: ContentVersion | None = None
            dep_project_id = ""
            if project.source == "modrinth":
                dep_project_id = str(dep.get("project_id") or "")
                version_id = str(dep.get("version_id") or "")
                if version_id:
                    dep_version = self._modrinth_version(version_id)
                elif dep_project_id:
                    try:
                        candidates = self._modrinth_versions(dep_project_id)
                    except ContentError:
                        continue
                    dep_version = self._pick_compatible(candidates, version)
            else:
                mod_id = dep.get("modId")
                dep_project_id = str(mod_id or "")
                if not dep_project_id:
                    continue
                try:
                    candidates = self._curseforge_versions(
                        dep_project_id,
                        version.game_versions[0] if version.game_versions else "",
                        version.loaders[0] if version.loaders else "",
                    )
                except ContentError:
                    continue
                dep_version = candidates[0] if candidates else None
            if not dep_version or dep_project_id in visited:
                continue
            dep_file = dep_version.primary_file
            if dep_file is None:
                continue
            visited.add(dep_project_id)
            if log:
                log(f"[内容] 自动安装依赖：{dep_file.filename}")
            installed.append(
                self.download_to(project.source, dep_file, game_dir / "mods", cancel, pause)
            )
        return installed

    @staticmethod
    def _pick_compatible(
        candidates: list[ContentVersion], base: ContentVersion
    ) -> ContentVersion | None:
        for candidate in candidates:
            if base.game_versions and candidate.game_versions:
                if not set(base.game_versions) & set(candidate.game_versions):
                    continue
            if base.loaders and candidate.loaders:
                if not set(base.loaders) & set(candidate.loaders):
                    continue
            return candidate
        return candidates[0] if candidates else None

    # ------------------------------------------------------------------
    # 整合包
    def prepare_modpack(
        self,
        project: ContentProject,
        version: ContentVersion,
        log: Callable[[str], None] | None = None,
        cancel: threading.Event | None = None,
        pause: threading.Event | None = None,
    ) -> tuple[Path, ModpackMeta]:
        file = version.primary_file
        if file is None:
            raise ContentError("该整合包版本没有可下载的文件。")
        cache = CACHE_DIR / "modpacks"
        cache.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^\w.\-]+", "_", file.filename) or "modpack.zip"
        dest = cache / f"{project.source}-{version.id}-{safe_name}"
        if not (dest.exists() and dest.stat().st_size > 0):
            if log:
                log(f"[整合包] 正在下载 {file.filename}…")
            self._download_single(project.source, file, dest, cancel, pause)
        meta = self.parse_modpack(dest, log)
        return dest, meta

    def parse_modpack(self, path: Path, log: Callable[[str], None] | None = None) -> ModpackMeta:
        try:
            with zipfile.ZipFile(path) as archive:
                names = [name.replace("\\", "/") for name in archive.namelist()]
                index_name = self._locate_member(names, "modrinth.index.json")
                if index_name:
                    raw = json.loads(archive.read(index_name).decode("utf-8"))
                    return self._parse_mrpack(raw, self._relative_names(names, index_name))
                manifest_name = self._locate_member(names, "manifest.json", suffix=True)
                if manifest_name:
                    raw = json.loads(archive.read(manifest_name).decode("utf-8"))
                    return self._parse_cf_pack(raw, log)
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            raise ContentError(f"整合包文件无法解析：{exc}") from exc
        raise ContentError("无法识别的整合包格式（缺少 modrinth.index.json 或 manifest.json）。")

    @staticmethod
    def _locate_member(names: list[str], filename: str, suffix: bool = False) -> str:
        """优先在根目录查找，其次在第一层子目录（如 MyPack/manifest.json）查找。"""
        files = [name for name in names if name and not name.endswith("/")]
        lowered = [(name, name.lower()) for name in files]
        for name, low in lowered:
            if low == filename:
                return name
        for name, low in lowered:
            parts = low.split("/")
            if len(parts) == 2 and (parts[1].endswith(filename) if suffix else parts[1] == filename):
                return name
        if suffix:
            for name, low in lowered:
                if low.endswith(filename):
                    return name
        return ""

    @staticmethod
    def _relative_names(names: list[str], member: str) -> set[str]:
        """把清单所在子目录作为基准，返回相对路径集合，便于识别 overrides 目录。"""
        base = member.rsplit("/", 1)[0] + "/" if "/" in member else ""
        if not base:
            return set(names)
        return {name[len(base):] for name in names if name.startswith(base)}

    def _parse_mrpack(self, raw: dict, names: set[str]) -> ModpackMeta:
        dependencies = raw.get("dependencies") if isinstance(raw.get("dependencies"), dict) else {}
        loader = ""
        loader_version = ""
        mapping = {
            "forge": "forge",
            "neoforge": "neoforge",
            "fabric-loader": "fabric",
            "quilt-loader": "quilt",
        }
        for key, label in mapping.items():
            if dependencies.get(key):
                loader = label
                loader_version = str(dependencies[key])
                break
        files: list[tuple[str, ContentFile]] = []
        for item in raw.get("files") or []:
            if not isinstance(item, dict):
                continue
            env = item.get("env") if isinstance(item.get("env"), dict) else {}
            if str(env.get("client") or "required") == "unsupported":
                continue
            downloads = item.get("downloads") or []
            if not downloads:
                continue
            hashes = item.get("hashes") if isinstance(item.get("hashes"), dict) else {}
            rel = str(item.get("path") or "").replace("\\", "/").lstrip("/")
            if not rel:
                continue
            files.append(
                (
                    rel,
                    ContentFile(
                        url=str(downloads[0]),
                        filename=Path(rel).name,
                        size=int(item.get("fileSize") or 0),
                        sha1=str(hashes.get("sha1") or ""),
                    ),
                )
            )
        overrides = ["overrides"]
        if any(n.startswith("client-overrides/") for n in names):
            overrides.append("client-overrides")
        return ModpackMeta(
            name=str(raw.get("name") or "Modrinth 整合包"),
            mc_version=str(dependencies.get("minecraft") or ""),
            loader=loader,
            loader_version=loader_version,
            files=files,
            overrides=overrides,
            pack_format="mrpack",
            version=str(raw.get("versionId") or ""),
        )

    def _parse_cf_pack(self, raw: dict, log: Callable[[str], None] | None = None) -> ModpackMeta:
        minecraft = raw.get("minecraft") if isinstance(raw.get("minecraft"), dict) else {}
        mc_version = str(minecraft.get("version") or "")
        loader = ""
        loader_version = ""
        for item in minecraft.get("modLoaders") or []:
            if not isinstance(item, dict):
                continue
            if not item.get("primary") and loader:
                continue
            loader_id = str(item.get("id") or "")
            for key in ("neoforge", "forge", "fabric", "quilt", "liteloader"):
                if loader_id.lower().startswith(key):
                    loader = key
                    loader_version = loader_id[len(key):].lstrip("-")
                    break
            if loader:
                break
        file_ids: list[int] = []
        for item in raw.get("files") or []:
            if not isinstance(item, dict):
                continue
            if not item.get("required", True):
                continue
            try:
                file_ids.append(int(item.get("fileID") or 0))
            except (TypeError, ValueError):
                continue
        files: list[tuple[str, ContentFile]] = []
        if file_ids:
            resolved = self._resolve_cf_file_ids(file_ids, log)
            for file_id, entry in resolved.items():
                filename = str(entry.get("fileName") or f"{file_id}.jar")
                url = str(entry.get("downloadUrl") or "") or _cf_file_url(file_id, filename)
                sha1 = ""
                for item in entry.get("hashes") or []:
                    if isinstance(item, dict) and int(item.get("algo") or 0) == 1:
                        sha1 = str(item.get("value") or "")
                files.append(
                    (
                        f"mods/{filename}",
                        ContentFile(
                            url=url,
                            filename=filename,
                            size=int(entry.get("fileLength") or 0),
                            sha1=sha1,
                        ),
                    )
                )
        overrides = str(raw.get("overrides") or "overrides").strip("/") or "overrides"
        return ModpackMeta(
            name=str(raw.get("name") or "CurseForge 整合包"),
            mc_version=mc_version,
            loader=loader,
            loader_version=loader_version,
            files=files,
            overrides=[overrides],
            pack_format="curseforge",
            version=str(raw.get("version") or ""),
        )

    def _resolve_cf_file_ids(
        self, file_ids: list[int], log: Callable[[str], None] | None = None
    ) -> dict[int, dict]:
        """批量解析 CurseForge 文件 ID；某一批失败时记录日志并跳过，不阻断安装。"""
        result: dict[int, dict] = {}
        for start in range(0, len(file_ids), 100):
            chunk = file_ids[start:start + 100]
            try:
                data = self._curseforge_post("/mods/files", {"fileIds": chunk})
            except DownloadError as exc:
                if log:
                    log(f"[整合包] 解析 CurseForge 文件失败，已跳过 {len(chunk)} 个文件：{exc}")
                continue
            except Exception as exc:  # noqa: BLE001 - 单个批次失败不应阻断整个整合包
                if log:
                    log(f"[整合包] 解析 CurseForge 文件异常，已跳过 {len(chunk)} 个文件：{exc}")
                continue
            rows = data.get("data") if isinstance(data, dict) else None
            for row in rows or []:
                if isinstance(row, dict):
                    try:
                        result[int(row.get("id") or 0)] = row
                    except (TypeError, ValueError):
                        continue
        return result

    def install_modpack_files(
        self,
        zip_path: Path,
        meta: ModpackMeta,
        instance_dir: Path,
        log: Callable[[str], None] | None = None,
        cancel: threading.Event | None = None,
        progress: Callable[[float, str], None] | None = None,
        pause: threading.Event | None = None,
        files_progress: Callable[[int, int], None] | None = None,
    ) -> None:
        """下载整合包内所有文件并解压 overrides。

        progress(percent, message) 驱动总体进度；files_progress(done, total)
        用于在下载清单上显示「已完成/总文件数」。
        """
        instance_dir.mkdir(parents=True, exist_ok=True)
        tasks: list[tuple[str, ContentFile, Path]] = []
        for rel, file in meta.files:
            safe = self._safe_path(instance_dir, rel)
            if safe is None:
                continue
            tasks.append(("curseforge" if meta.pack_format == "curseforge" else "modrinth", file, safe))
        if log:
            log(f"[整合包] 需要下载 {len(tasks)} 个文件，overrides：{', '.join(meta.overrides)}")
        if files_progress is not None:
            files_progress(0, len(tasks))
        failures = self.download_many(
            tasks, log=log, cancel=cancel, pause=pause, progress=files_progress
        )
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        missing = self._collect_missing(tasks, failures, instance_dir, log)
        if progress:
            progress(0.9, "下载完成，正在解压 overrides…")
        self._extract_overrides(zip_path, meta.overrides, instance_dir, log, cancel)
        if progress:
            progress(1.0, "整合包文件安装完成" + (f"（{len(missing)} 个文件缺失）" if missing else ""))

    def _collect_missing(
        self,
        tasks: list[tuple[str, ContentFile, Path]],
        failures: list[str],
        instance_dir: Path,
        log: Callable[[str], None] | None = None,
    ) -> list[ContentFile]:
        """把下载失败的文件记录到 missing_mods.txt，允许其余内容继续安装。"""
        missing: list[ContentFile] = []
        for _source, file, dest in tasks:
            try:
                if dest.is_file() and dest.stat().st_size > 0:
                    continue
            except OSError:
                pass
            missing.append(file)
        if not missing:
            return []
        path = instance_dir / "missing_mods.txt"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(f"# 下载失败的文件（{time.strftime('%Y-%m-%d %H:%M:%S')}）\n")
                handle.write("# 可在「整合包」页点击“修复”重试\n")
                for file in missing:
                    handle.write(f"{file.filename}\t{file.url}\n")
        except OSError as exc:
            if log:
                log(f"[整合包] 写入缺失清单失败：{exc}")
        if log:
            log(
                f"[警告] {len(missing)} 个整合包文件下载失败，已记录到 missing_mods.txt，"
                "其余内容继续安装。"
            )
            for message in failures[:10]:
                log(f"[警告] {message}")
        return missing

    @staticmethod
    def _safe_path(root: Path, rel: str) -> Path | None:
        target = (root / rel.replace("\\", "/")).resolve()
        try:
            if not target.is_relative_to(root.resolve()):
                return None
        except AttributeError:
            if not str(target).startswith(str(root.resolve())):
                return None
        return target

    def _extract_overrides(
        self,
        zip_path: Path,
        prefixes: list[str],
        instance_dir: Path,
        log: Callable[[str], None] | None,
        cancel: threading.Event | None = None,
    ) -> None:
        extracted = 0
        checked = 0
        if isinstance(prefixes, str):
            prefixes = [prefixes] if prefixes else []
        prefixes = [str(item).strip("/") for item in prefixes if str(item).strip("/")]
        try:
            with zipfile.ZipFile(zip_path) as archive:
                for info in archive.infolist():
                    checked += 1
                    if cancel is not None and checked % 50 == 0 and cancel.is_set():
                        raise Cancelled()
                    if info.is_dir():
                        continue
                    name = info.filename.replace("\\", "/")
                    matched_len = 0
                    for prefix in prefixes:
                        if name.startswith(prefix + "/"):
                            matched_len = len(prefix) + 1
                            break
                        # 兼容「MyPack/overrides/…」这种多一层目录的整合包
                        marker = f"/{prefix}/"
                        position = name.find(marker)
                        if position >= 0 and name.count("/", 0, position) <= 1:
                            matched_len = position + len(prefix) + 2
                            break
                    if not matched_len:
                        continue
                    rel = name[matched_len:]
                    if not rel or rel.startswith("../") or "/../" in rel:
                        continue
                    target = instance_dir / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    extracted += 1
        except (OSError, zipfile.BadZipFile) as exc:
            raise ContentError(f"解压整合包 overrides 失败：{exc}") from exc
        if log:
            log(f"[整合包] 已应用 {extracted} 个 overrides 文件")


# ---------------------------------------------------------------------------
# Mod 元数据扫描与冲突/依赖检测（只读纯函数，不联网、不写文件）
# ---------------------------------------------------------------------------
def scan_mod_metadata(mods_dir) -> dict[Path, dict]:
    """扫描 mods 目录下的 .jar，解析 Fabric / Forge / NeoForge / LiteLoader 元数据。

    返回 {jar_path: {modid, name, version, loader, depends}}；
    解析失败的文件保留基础记录（modid 取文件名，loader=unknown），不抛异常。
    """
    result: dict[Path, dict] = {}
    mods_dir = Path(mods_dir)
    try:
        if not mods_dir.is_dir():
            return result
        jars = sorted(
            path for path in mods_dir.iterdir()
            if path.is_file() and path.suffix.lower() == ".jar"
        )
    except OSError:
        return result
    for jar in jars:
        result[jar] = _read_mod_metadata(jar)
    return result


def _read_mod_metadata(jar: Path) -> dict:
    """读取单个 jar 的 mod 元数据；解析失败时返回基础记录。"""
    stem = jar.stem
    record = {"modid": stem, "name": stem, "version": "", "loader": "unknown", "depends": []}
    try:
        with zipfile.ZipFile(jar) as archive:
            names = {name.replace("\\", "/") for name in archive.namelist()}
            # Fabric：fabric.mod.json
            if "fabric.mod.json" in names:
                raw = json.loads(archive.read("fabric.mod.json").decode("utf-8", errors="replace"))
                if isinstance(raw, dict):
                    modid = str(raw.get("id") or stem)
                    record.update(
                        {
                            "modid": modid,
                            "name": str(raw.get("name") or modid),
                            "version": str(raw.get("version") or ""),
                            "loader": "fabric",
                            "depends": _fabric_depends(raw),
                        }
                    )
                    return record
            # Forge / NeoForge：META-INF/mods.toml
            if "META-INF/mods.toml" in names:
                text = archive.read("META-INF/mods.toml").decode("utf-8", errors="replace")
                mods, depends, loader = _parse_mods_toml(text)
                if mods:
                    first = mods[0]
                    modid = str(first.get("modId") or stem)
                    record.update(
                        {
                            "modid": modid,
                            "name": str(first.get("displayName") or modid),
                            "version": str(first.get("version") or ""),
                            "loader": loader,
                            "depends": depends,
                        }
                    )
                    return record
            # LiteLoader / 旧版：mcmod.info
            if "mcmod.info" in names:
                raw = json.loads(archive.read("mcmod.info").decode("utf-8", errors="replace"))
                items = raw if isinstance(raw, list) else ([raw] if isinstance(raw, dict) else [])
                if items and isinstance(items[0], dict):
                    item = items[0]
                    modid = str(item.get("modid") or stem)
                    record.update(
                        {
                            "modid": modid,
                            "name": str(item.get("name") or modid),
                            "version": str(item.get("version") or ""),
                            "loader": "liteloader",
                            "depends": [
                                {"modid": str(value), "version_range": "", "type": "required"}
                                for value in (item.get("requiredMods") or [])
                                if str(value)
                            ],
                        }
                    )
                    return record
    except Exception as exc:  # noqa: BLE001 - 解析失败保留基础记录，不阻断扫描
        pass
    return record


def _fabric_depends(raw: dict) -> list[dict]:
    """fabric.mod.json 的 depends：全部按 required 记录。"""
    depends = raw.get("depends") if isinstance(raw.get("depends"), dict) else {}
    result: list[dict] = []
    for key, value in depends.items():
        if isinstance(value, list):
            value = ", ".join(str(item) for item in value)
        result.append({"modid": str(key), "version_range": str(value or ""), "type": "required"})
    return result


def _parse_mods_toml(text: str) -> tuple[list[dict], list[dict], str]:
    """简易解析 mods.toml，返回 (mods 列表, depends 列表, loader)。

    依赖段只保留 mandatory=true（REQUIRED）的条目；loader 依据依赖里
    出现的 neoforge / forge 判定。
    """
    mods: list[dict] = []
    deps: list[dict] = []
    current_mod: dict | None = None
    current_dep: dict | None = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^\[\[(mods|dependencies\.[A-Za-z0-9_.\-]+)\]\]$", line)
        if match:
            header = match.group(1)
            if header == "mods":
                current_mod = {}
                mods.append(current_mod)
                current_dep = None
            else:
                current_dep = {}
                deps.append(current_dep)
                current_mod = None
            continue
        kv = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"(.*)"\s*$', line)
        if not kv:
            # TOML 布尔/数字等无引号值（如 mandatory=true）
            kv = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^\s#]+)', line)
        if not kv:
            continue
        key, value = kv.group(1), kv.group(2)
        if current_dep is not None:
            current_dep[key] = value
        elif current_mod is not None:
            current_mod[key] = value
    loader = "unknown"
    for dep in deps:
        dep_modid = str(dep.get("modId") or "").lower()
        if dep_modid == "neoforge":
            loader = "neoforge"
        elif dep_modid == "forge" and loader != "neoforge":
            loader = "forge"
    depends = []
    for dep in deps:
        mandatory = str(dep.get("mandatory") or "").strip().lower()
        if mandatory not in ("true", "1", "yes"):
            continue
        depends.append(
            {
                "modid": str(dep.get("modId") or ""),
                "version_range": str(dep.get("versionRange") or ""),
                "type": "required",
            }
        )
    return mods, depends, loader


def detect_mod_conflicts(metadata: dict[Path, dict]) -> list[dict]:
    """检测重复 Mod ID、缺少前置依赖、前置版本不匹配；只读纯函数。

    返回列表可空，每条含 type / modid / files / detail。
    """
    issues: list[dict] = []
    by_modid: dict[str, list[Path]] = {}
    for path, meta in metadata.items():
        modid = str(meta.get("modid") or "")
        if modid:
            by_modid.setdefault(modid, []).append(path)
    installed: dict[str, dict] = {}
    for modid, paths in by_modid.items():
        installed[modid] = metadata[paths[0]]
        if len(paths) > 1:
            issues.append(
                {
                    "type": "duplicate_modid",
                    "modid": modid,
                    "files": list(paths),
                    "detail": f"重复的 Mod ID：{modid}，请禁用其中一个",
                }
            )
    for path, meta in metadata.items():
        for dep in meta.get("depends") or []:
            if str(dep.get("type") or "required") != "required":
                continue
            dep_modid = str(dep.get("modid") or "")
            if not dep_modid:
                continue
            if dep_modid not in installed:
                issues.append(
                    {
                        "type": "missing_dependency",
                        "modid": dep_modid,
                        "files": [path],
                        "detail": f"缺少前置依赖：{dep_modid}",
                    }
                )
                continue
            installed_version = str(installed[dep_modid].get("version") or "")
            range_text = str(dep.get("version_range") or "").strip()
            if range_text and _version_in_range(installed_version, range_text) is False:
                issues.append(
                    {
                        "type": "version_mismatch",
                        "modid": dep_modid,
                        "files": [path],
                        "detail": (
                            f"前置依赖 {dep_modid} 版本不满足：需要 {range_text}，"
                            f"已安装 {installed_version or '未知'}"
                        ),
                    }
                )
    return issues


def _parse_version(text: str) -> tuple[int, ...] | None:
    """把版本字符串转成可比较的数值元组；无法解析返回 None。"""
    parts = re.split(r"[.\-+_]", str(text).strip())
    result: list[int] = []
    for part in parts:
        if not part:
            continue
        if part.isdigit():
            result.append(int(part))
        else:
            match = re.match(r"(\d+)", part)
            if match is None:
                return None
            result.append(int(match.group(1)))
    return tuple(result) if result else None


def _version_in_range(version: str, range_text: str) -> bool | None:
    """packaging 风格版本范围判断；无法解析返回 None（跳过，不误报）。"""
    installed = _parse_version(version)
    if installed is None:
        return None
    text = str(range_text).strip()
    if not text:
        return True
    # [1.2,3) / (1.2,3.4] / [1.2,] / [,3) 形式
    match = re.match(r"^([\[(])\s*([^,]*?)\s*,\s*([^)\]]*?)\s*([\])])$", text)
    if match:
        left_bracket, lower_text, upper_text, right_bracket = match.groups()
        if lower_text:
            lower = _parse_version(lower_text)
            if lower is None:
                return None
            if left_bracket == "[":
                if installed < lower:
                    return False
            elif installed <= lower:
                return False
        if upper_text:
            upper = _parse_version(upper_text)
            if upper is None:
                return None
            if right_bracket == "]":
                if installed > upper:
                    return False
            elif installed >= upper:
                return False
        return True
    # 1.2.3+ 形式（>=）
    if text.endswith("+"):
        base = _parse_version(text[:-1])
        if base is None:
            return None
        return installed >= base
    # ~1.2.3 / ~=1.2.3 形式（>=1.2.3 且 <1.3）
    if text.startswith("~"):
        raw = text[2:] if text.startswith("~=") else text[1:]
        base = _parse_version(raw)
        if base is None:
            return None
        if installed < base:
            return False
        if base:
            upper = base[:-1] + (base[-1] + 1,)
            if installed >= upper:
                return False
        return True
    # == / >= / > / <= / < / != 前缀
    match = re.match(r"^(==|>=|>|<=|<|!=)\s*(.+)$", text)
    if match:
        op, raw = match.groups()
        target = _parse_version(raw)
        if target is None:
            return None
        if op == "==":
            return installed == target
        if op == ">=":
            return installed >= target
        if op == ">":
            return installed > target
        if op == "<=":
            return installed <= target
        if op == "<":
            return installed < target
        return installed != target
    # 纯版本号：要求相等
    exact = _parse_version(text)
    if exact is None:
        return None
    return installed == exact
