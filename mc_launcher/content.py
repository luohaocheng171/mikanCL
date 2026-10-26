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
import urllib.parse
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import USER_AGENT
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
    "shader": "光影包",
}

SOURCE_LABELS = {"modrinth": "Modrinth", "curseforge": "CurseForge"}

CF_CLASS_IDS = {"mod": 6, "modpack": 4471, "resourcepack": 12, "shader": 6552}
CF_LOADER_TYPES = {"forge": 1, "liteloader": 3, "fabric": 4, "quilt": 5, "neoforge": 6}
MODRINTH_LOADERS = {"forge", "fabric", "quilt", "neoforge"}

CF_FILE_BASE = "https://mediafilez.forgecdn.net/files/{a}/{b}/{name}"


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
    return CF_FILE_BASE.format(a=file_id // 1000, b=file_id % 1000, name=filename)


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


def mc_version_key(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in re.split(r"[.\-]", str(value)):
        parts.append(int(piece) if piece.isdigit() else 0)
    return tuple(parts)


class ContentClient:
    def __init__(self, config: Config):
        self.config = config
        self.http = Http(timeout=35)

    # ------------------------------------------------------------------
    # 平台请求
    def _modrinth(self, path: str, params: dict | None = None) -> dict | list:
        base = (self.config.modrinth_api_base or "https://api.modrinth.com/v2").rstrip("/")
        url = base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        return self.http.get_json_url(url, headers={"User-Agent": USER_AGENT})

    def _curseforge(self, path: str, params: dict | None = None) -> dict | list:
        base = (self.config.curseforge_api_base or "https://api.curseforge.com/v1").rstrip("/")
        url = base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        key = (self.config.curseforge_api_key or "").strip()
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        if key:
            headers["x-api-key"] = key
        return self.http.get_json_url(url, headers=headers)

    def _curseforge_post(self, path: str, payload: dict) -> dict | list:
        base = (self.config.curseforge_api_base or "https://api.curseforge.com/v1").rstrip("/")
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        key = (self.config.curseforge_api_key or "").strip()
        if key:
            headers["x-api-key"] = key
        return self.http.post_json_url(base + path, payload, headers=headers)

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
        facets: list[list[str]] = [[f"project_type:{project_type}"]]
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
                    project_type=str(hit.get("project_type") or project_type),
                    author=str(hit.get("author") or ""),
                    downloads=int(hit.get("downloads") or 0),
                    icon_url=str(hit.get("icon_url") or ""),
                    categories=[str(c) for c in (hit.get("categories") or [])],
                    slug=slug,
                    page_url=f"https://modrinth.com/{project_type}/{slug}",
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
                    dependencies=[
                        d for d in (row.get("dependencies") or []) if isinstance(d, dict)
                    ],
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
                    dependencies=[
                        d for d in (row.get("dependencies") or []) if isinstance(d, dict)
                    ],
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
            dependencies=[d for d in (row.get("dependencies") or []) if isinstance(d, dict)],
            date=str(row.get("date_published") or "")[:19].replace("T", " "),
            downloads=int(row.get("downloads") or 0),
        )

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
        try:
            self.http.download(
                candidates,
                dest,
                size=file.size or None,
                sha1=file.sha1 or None,
                cancel=cancel,
                pause=pause,
            )
        except DownloadError as exc:
            raise ContentError(f"下载 {file.filename} 失败：{exc}") from exc
        return dest

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
    ) -> list[str]:
        """多线程下载 [(source, file, dest)]，返回失败描述列表。"""
        if not tasks:
            return []
        workers = workers or max(4, int(self.config.download_threads))
        failures: list[str] = []

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
        targets = {"mod": "mods", "resourcepack": "resourcepacks", "shader": "shaderpacks"}
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
    ) -> None:
        """下载整合包内所有文件并解压 overrides。"""
        instance_dir.mkdir(parents=True, exist_ok=True)
        tasks: list[tuple[str, ContentFile, Path]] = []
        for rel, file in meta.files:
            safe = self._safe_path(instance_dir, rel)
            if safe is None:
                continue
            tasks.append(("curseforge" if meta.pack_format == "curseforge" else "modrinth", file, safe))
        if log:
            log(f"[整合包] 需要下载 {len(tasks)} 个文件，overrides：{', '.join(meta.overrides)}")
        failures = self.download_many(tasks, log=log, cancel=cancel, pause=pause)
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
