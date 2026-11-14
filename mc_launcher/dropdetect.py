"""拖拽内容识别与导入（不依赖 Qt）。

从 ui/dropinstall.py 抽出的纯逻辑：识别 Mod、整合包、资源包、光影包与世界存档，
并完成文件复制 / 解压。经典版、美化版和 Electron 独立内核共用这一份实现，
避免 Electron 后端为了识别一个文件被迫打包整个 Qt 界面。
"""

from __future__ import annotations

import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from .config import LOG_DIR
from .content import ContentError
from .launcher import prepare_isolated_dir

KIND_LABELS = {
    "mod": "Mod",
    "modpack": "整合包",
    "resourcepack": "资源包",
    "shader": "光影包",
    "world": "世界存档",
}
_KIND_FOLDERS = {"mod": "mods", "resourcepack": "resourcepacks", "shader": "shaderpacks"}


def _zip_names(path: Path) -> list[str]:
    try:
        with zipfile.ZipFile(path) as archive:
            return [name.replace("\\", "/") for name in archive.namelist()]
    except (OSError, zipfile.BadZipFile):
        return []


def _single_root_prefix(names: list[str]) -> str:
    """压缩包内所有文件都在同一个顶层目录时返回该目录前缀。"""
    files = [name for name in names if name and not name.endswith("/")]
    if not files:
        return ""
    first = files[0].split("/")[0] + "/"
    if all(name.startswith(first) for name in files):
        return first
    return ""


def write_install_error_log(title: str, detail: str) -> Path | None:
    """把安装失败的详细信息追加写入 data/logs/install_error.log。"""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = LOG_DIR / "install_error.log"
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(f"\n==== {datetime.now():%Y-%m-%d %H:%M:%S} · {title} ====\n{detail}\n")
        return path
    except OSError:
        return None


def detect_path(path: Path) -> str:
    """根据文件后缀与内部结构判断拖入内容类型。"""
    if path.is_dir():
        if (path / "level.dat").is_file():
            return "world"
        if any(
            (path / marker).is_file()
            for marker in (
                "manifest.json",
                "modrinth.index.json",
                "mmc-pack.json",
                "instance.cfg",
                "instance.json",
            )
        ):
            return "modpack"
        return ""
    suffix = path.suffix.lower()
    if suffix == ".jar":
        return "mod"
    if suffix in (".mrpack", ".mikan"):
        return "modpack"
    if suffix != ".zip":
        return ""
    names = _zip_names(path)
    if not names:
        return ""
    lowered = [name.lower() for name in names]
    if any(name.endswith("level.dat") for name in lowered):
        return "world"
    if any(
        name.endswith("modrinth.index.json") or name.endswith("mmc-pack.json")
        or name.endswith("instance.cfg") or name == "instance.json"
        for name in lowered
    ):
        return "modpack"
    if any(name.endswith("manifest.json") for name in lowered):
        return "modpack"
    if any(name.startswith("shaders/") or "/shaders/" in name for name in lowered):
        return "shader"
    if any(name.endswith("pack.mcmeta") for name in lowered):
        return "resourcepack"
    if any(name.endswith(".jar") for name in lowered):
        return "modpack"
    if any(
        name.startswith("mods/") or "/mods/" in name
        or name.startswith("config/") or "/config/" in name
        for name in lowered
    ):
        # 没有清单、但带 mods/ 或 config/ 的压缩包：按“直装包”处理
        return "modpack"
    return ""


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    index = 2
    while True:
        candidate = path.with_name(f"{stem} ({index}){suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def _safe_extract(archive: zipfile.ZipFile, target: Path, prefix: str = "") -> int:
    count = 0
    for info in archive.infolist():
        if info.is_dir():
            continue
        name = info.filename.replace("\\", "/")
        if prefix:
            if not name.startswith(prefix):
                continue
            name = name[len(prefix):]
        if not name or name.startswith("/") or ".." in Path(name).parts:
            continue
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as source, open(destination, "wb") as output:
            shutil.copyfileobj(source, output)
        count += 1
    return count


def _world_zip_prefix(names: list[str]) -> str:
    tops: set[str] = set()
    for name in names:
        clean = name.strip("/")
        if not clean:
            continue
        tops.add(clean.split("/", 1)[0])
    if len(tops) == 1:
        top = tops.pop()
        if any(name.startswith(top + "/level.dat") for name in names):
            return top + "/"
    return ""


def install_world(path: Path, game_dir: Path, log=None) -> str:
    saves = game_dir / "saves"
    saves.mkdir(parents=True, exist_ok=True)
    if path.is_dir():
        destination = _unique_path(saves / path.name)
        shutil.copytree(path, destination)
        return str(destination)
    destination = _unique_path(saves / path.stem)
    destination.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(path) as archive:
            names = [name.replace("\\", "/") for name in archive.namelist()]
            prefix = _world_zip_prefix(names)
            _safe_extract(archive, destination, prefix)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ContentError(f"世界存档解压失败：{exc}") from exc
    return str(destination)


def install_file(ctx, path: Path, kind: str, target: dict, log=None) -> str:
    root = Path(str(target.get("game_dir") or ctx.config.game_path))
    version_id = str(target.get("version_id") or "")
    mode = ctx.config.isolation_for(version_id) if version_id else "none"
    game_dir = prepare_isolated_dir(root, version_id, mode) if version_id else root
    if kind == "world":
        return install_world(path, game_dir, log)
    folder = _KIND_FOLDERS.get(kind)
    if folder is None:
        raise ContentError(f"暂不支持导入类型：{kind}")
    destination_dir = game_dir / folder
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = _unique_path(destination_dir / path.name)
    shutil.copy2(path, destination)
    return str(destination)


def _expand_dropped_paths(paths: list[Path]) -> list[Path]:
    """把「整个 mods 文件夹」展开成其中的 jar，其余文件夹原样保留。"""
    expanded: list[Path] = []
    for path in paths:
        if path.is_dir() and detect_path(path) not in ("modpack", "world"):
            jars = sorted(path.glob("*.jar"))
            if not jars:
                nested = path / "mods"
                if nested.is_dir():
                    jars = sorted(nested.glob("*.jar"))
            if jars:
                expanded.extend(jars[:200])
                continue
        expanded.append(path)
    return expanded
