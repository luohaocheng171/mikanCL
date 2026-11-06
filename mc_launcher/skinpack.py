"""皮肤包：按目标玩家生成 / 安装皮肤，并按游戏版本适配资源包格式。

要点：
- 原版资源包只能全局替换默认皮肤，会让服务器上所有默认皮肤玩家一起变成这张皮肤。
  想要「只有某个玩家有皮肤」，必须通过 CustomSkinLoader 的 LocalSkin 按用户名加载；
  本模块写入 LocalSkin/skins/<玩家名>.png 并合并 CustomSkinLoader.json 的 loadlist。
- 资源包 / 纹理包仅作为没有 CustomSkinLoader 时的兜底，默认只写入不自动启用。
- 版本适配：
  * 1.0–1.5.2：纹理包（texturepacks/ + pack.txt + textures/entity/*.png）
  * 1.6.1–1.21.8：资源包（pack.mcmeta 的 pack_format + supported_formats 1–99）
  * 1.21.9+（含 26.x）：资源包（min_format / max_format）
- 资源包沿用旧版写法，同时写入新旧两套皮肤路径（textures/entity/steve.png、alex.png
  与 textures/entity/player/wide/steve.png、slim/alex.png），任一版本都能命中；
  导出的皮肤包本身就是一个可直接放进 resourcepacks / texturepacks 的资源包。
"""

from __future__ import annotations

import io
import json
import re
import time
import zipfile
from pathlib import Path

SKIN_PACK_FORMAT = "MikanCL-SkinPack"
SKIN_PACK_VERSION = 1
MODEL_LABELS = {"classic": "Steve（经典）", "slim": "Alex（纤细）"}

# (起始版本, pack_format)：按版本升序查找，取不大于目标版本的最后一档
_PACK_FORMATS: tuple[tuple[tuple[int, int, int], int], ...] = (
    ((1, 6, 1), 1),
    ((1, 9, 0), 2),
    ((1, 11, 0), 3),
    ((1, 13, 0), 4),
    ((1, 15, 0), 5),
    ((1, 16, 2), 6),
    ((1, 17, 0), 7),
    ((1, 18, 0), 8),
    ((1, 19, 0), 9),
    ((1, 19, 3), 12),
    ((1, 19, 4), 13),
    ((1, 20, 0), 15),
    ((1, 20, 2), 18),
    ((1, 20, 3), 22),
    ((1, 20, 5), 32),
    ((1, 21, 0), 34),
    ((1, 21, 2), 42),
    ((1, 21, 4), 46),
    ((1, 21, 5), 55),
    ((1, 21, 6), 63),
    ((1, 21, 7), 64),
    ((1, 21, 9), 69),
    ((1, 21, 11), 75),
    ((26, 1, 0), 84),
    ((26, 2, 0), 88),
    ((26, 3, 0), 97),
)
_LATEST_PACK_FORMAT = _PACK_FORMATS[-1][1]
_MODERN_SINCE = (1, 21, 9)

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?")


class SkinPackError(Exception):
    pass


def version_tuple(version_id: str) -> tuple[int, int, int] | None:
    """从版本 ID 中提取主版本号，兼容 "1.20.1-forge-47.2.0"、"26.4-snapshot"。"""
    match = _VERSION_RE.match((version_id or "").strip())
    if not match:
        return None
    return (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3) or 0),
    )


def pack_info(version_id: str) -> dict:
    """返回该版本的皮肤包格式信息。

    kind: legacy（纹理包）/ format（单一 pack_format）/ range（min_format+max_format）
    """
    parsed = version_tuple(version_id)
    # 无法识别的快照（如 24w14a）按最新格式生成一个宽范围，保证能加载
    if parsed is None:
        return {
            "kind": "range",
            "pack_format": _LATEST_PACK_FORMAT,
            "label": "未知版本（按最新格式生成宽范围）",
        }
    if parsed < (1, 6, 1):
        return {"kind": "legacy", "pack_format": 0, "label": "纹理包（1.5.2 及更早）"}
    selected = _PACK_FORMATS[0][1]
    for since, number in _PACK_FORMATS:
        if parsed >= since:
            selected = number
        else:
            break
    if parsed >= _MODERN_SINCE:
        return {
            "kind": "range",
            "pack_format": selected,
            "label": f"min_format={selected} / max_format=999（1.21.9+ / 26.x）",
        }
    return {
        "kind": "format",
        "pack_format": selected,
        "label": f"pack_format={selected}",
    }


def texture_paths(version_id: str, model: str) -> list[str]:
    """返回玩家默认皮肤纹理路径。

    沿用旧版皮肤包的写法：新旧两套路径同时写入，避免因版本分界判断偏差
    （1.19.3 / 1.20.2 等）导致资源包在游戏里不生效；1.5.2 及更早是纹理包路径。
    """
    parsed = version_tuple(version_id)
    if parsed is not None and parsed < (1, 6, 1):
        return ["textures/entity/steve.png", "textures/entity/alex.png"]
    return [
        "assets/minecraft/textures/entity/steve.png",
        "assets/minecraft/textures/entity/alex.png",
        "assets/minecraft/textures/entity/player/wide/steve.png",
        "assets/minecraft/textures/entity/player/slim/alex.png",
    ]


def _mcmeta(description: str, info: dict) -> dict:
    pack: dict = {"description": description}
    if info["kind"] == "range":
        pack["min_format"] = [int(info["pack_format"]), 0]
        pack["max_format"] = [999, 0]
    else:
        # 旧包写法：pack_format 仅表示起始格式，supported_formats 放宽到 1–99，
        # 让相邻版本的格式差异不会把资源包判为不兼容。
        pack["pack_format"] = int(info["pack_format"])
        pack["supported_formats"] = {
            "min_inclusive": 1,
            "max_inclusive": 99,
        }
    return {"pack": pack}


def resourcepack_bytes(image: bytes, version_id: str, model: str, description: str) -> bytes:
    """生成适用于指定版本的资源包 / 纹理包 zip 内容。"""
    info = pack_info(version_id)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        if info["kind"] == "legacy":
            archive.writestr("pack.txt", description)
        else:
            archive.writestr(
                "pack.mcmeta", json.dumps(_mcmeta(description, info), ensure_ascii=False, indent=2)
            )
            archive.writestr("pack.png", image)
        for name in texture_paths(version_id, model):
            archive.writestr(name, image)
    return buffer.getvalue()


def pack_filename(player: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]", "_", player or "").strip("_") or "Player"
    return f"MikanCL-{safe}-皮肤包.zip"


def export_skin_pack(
    dest: str | Path,
    skin_path: str | Path,
    player: str,
    model: str,
    version_id: str,
) -> Path:
    """把皮肤导出成可分享的皮肤包（含目标玩家、模型、版本适配资源包）。"""
    source = Path(skin_path)
    if not source.is_file():
        raise SkinPackError("找不到皮肤文件。")
    target = Path(dest)
    target.parent.mkdir(parents=True, exist_ok=True)
    image = source.read_bytes()
    name = player.strip()
    if not name:
        raise SkinPackError("请填写目标玩家名。")
    info = pack_info(version_id)
    meta = {
        "format": SKIN_PACK_FORMAT,
        "version": SKIN_PACK_VERSION,
        "player": name,
        "model": model or "classic",
        "target_version": version_id,
        "pack_format": info["pack_format"],
        "pack_kind": info["kind"],
        "skin": "skin.png",
        "requires": "CustomSkinLoader",
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    readme = (
        "MikanCL 皮肤包\n"
        f"目标玩家：{name}\n"
        f"手臂模型：{MODEL_LABELS.get(model or 'classic', model)}\n"
        f"适配版本：{version_id or '通用'}（{info['label']}）\n\n"
        "本文件本身就是一个资源包：\n"
        "  1.6.1 及以后：直接放进 .minecraft/resourcepacks 并在游戏内启用；\n"
        "  1.5.2 及更早：直接放进 .minecraft/texturepacks。\n"
        "也可以在启动器的「皮肤包」页导入，会自动写入\n"
        "CustomSkinLoader/LocalSkin/skins/<玩家名>.png。\n"
        "只有安装 CustomSkinLoader Mod 后才会按玩家名生效，不会影响服务器其他玩家。\n"
    )
    try:
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("pack.json", json.dumps(meta, ensure_ascii=False, indent=2))
            archive.writestr("skin.png", image)
            archive.writestr("README.txt", readme)
            # 与安装到游戏目录的兜底包完全一致，导出文件可直接当资源包加载
            pack_bytes = resourcepack_bytes(
                image, version_id, model or "classic", f"MikanCL 皮肤包 · {name}"
            )
            with zipfile.ZipFile(io.BytesIO(pack_bytes)) as inner:
                for entry in inner.infolist():
                    archive.writestr(entry.filename, inner.read(entry.filename))
    except (OSError, ValueError) as exc:
        raise SkinPackError(f"写入皮肤包失败：{exc}") from exc
    return target


def read_skin_pack(path: str | Path) -> dict:
    """读取皮肤包（zip）或直接读取 PNG，返回 player/model/target_version/image。"""
    source = Path(path)
    if not source.is_file():
        raise SkinPackError("找不到皮肤包文件。")
    if source.suffix.lower() == ".png":
        return {
            "player": "",
            "model": "",
            "target_version": "",
            "image": source.read_bytes(),
            "source": str(source),
        }
    try:
        with zipfile.ZipFile(source) as archive:
            names = archive.namelist()
            meta: dict = {}
            if "pack.json" in names:
                try:
                    meta = json.loads(archive.read("pack.json").decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    meta = {}
            skin_name = str(meta.get("skin") or "")
            if skin_name not in names:
                candidates = [n for n in names if n.lower().endswith(".png") and "/" not in n]
                skin_name = candidates[0] if candidates else ""
            if not skin_name:
                raise SkinPackError("皮肤包里没有皮肤图片。")
            image = archive.read(skin_name)
    except zipfile.BadZipFile as exc:
        raise SkinPackError("皮肤包不是有效的 zip 文件。") from exc
    except OSError as exc:
        raise SkinPackError(f"读取皮肤包失败：{exc}") from exc
    if not image:
        raise SkinPackError("皮肤包里的图片为空。")
    return {
        "player": str(meta.get("player") or ""),
        "model": str(meta.get("model") or ""),
        "target_version": str(meta.get("target_version") or ""),
        "image": image,
        "source": str(source),
    }


def _merge_custom_skin_loader(root: Path) -> Path:
    """把 LocalSkin 源写入 CustomSkinLoader.json，保留用户已有的其它皮肤源。"""
    config_dir = root / "CustomSkinLoader"
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / "CustomSkinLoader.json"
    data: dict = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, ValueError):
            data = {}
    data.setdefault("version", "15.0.0")
    loadlist = data.get("loadlist")
    if not isinstance(loadlist, list):
        loadlist = []
    entry = {
        "name": "LocalSkin",
        "type": "Legacy",
        "checkPNG": False,
        "skin": "LocalSkin/skins/{USERNAME}.png",
        "model": "auto",
        "cape": "LocalSkin/capes/{USERNAME}.png",
        "elytra": "LocalSkin/elytra/{USERNAME}.png",
    }
    replaced = False
    for index, item in enumerate(loadlist):
        if isinstance(item, dict) and str(item.get("name") or "") == entry["name"]:
            merged = dict(item)
            merged.update(entry)
            loadlist[index] = merged
            replaced = True
            break
    if not replaced:
        loadlist.insert(0, entry)
    data["loadlist"] = loadlist
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def _enable_resource_pack(root: Path, name: str) -> None:
    """写入 options.txt 的已启用资源包列表（仅 1.6.1+ 资源包）。"""
    options = root / "options.txt"
    entry = f"file/{name}"
    try:
        lines = options.read_text(encoding="utf-8", errors="replace").splitlines() if options.is_file() else []
        result: list[str] = []
        updated = False
        for line in lines:
            if not line.startswith("resourcePacks:"):
                result.append(line)
                continue
            try:
                packs = json.loads(line.split(":", 1)[1])
            except ValueError:
                packs = []
            if not isinstance(packs, list):
                packs = []
            if entry not in packs:
                packs.append(entry)
            result.append("resourcePacks:" + json.dumps(packs, ensure_ascii=False))
            updated = True
        if not updated:
            result.append("resourcePacks:" + json.dumps(["vanilla", entry], ensure_ascii=False))
        options.write_text("\n".join(result) + "\n", encoding="utf-8")
    except OSError:
        pass


def _drop_legacy_pack(root: Path) -> None:
    """移除旧版全局皮肤资源包，避免升级后仍然替换服务器所有默认皮肤。"""
    legacy = root / "resourcepacks" / "MikanCL-离线皮肤.zip"
    try:
        if legacy.is_file():
            legacy.unlink()
    except OSError:
        pass
    options = root / "options.txt"
    entry = "file/MikanCL-离线皮肤.zip"
    if not options.is_file():
        return
    try:
        lines = options.read_text(encoding="utf-8", errors="replace").splitlines()
        result: list[str] = []
        for line in lines:
            if not line.startswith("resourcePacks:"):
                result.append(line)
                continue
            try:
                packs = json.loads(line.split(":", 1)[1])
            except ValueError:
                result.append(line)
                continue
            if isinstance(packs, list) and entry in packs:
                packs = [item for item in packs if item != entry]
                result.append("resourcePacks:" + json.dumps(packs, ensure_ascii=False))
            else:
                result.append(line)
        options.write_text("\n".join(result) + "\n", encoding="utf-8")
    except OSError:
        pass


def purge_old_packs(game_dir: str | Path) -> list[str]:
    """清理目录里所有旧的 MikanCL 皮肤包（含旧版全局包），并移除其启用项。

    旧包残留时游戏仍可能加载旧皮肤，导致以为新皮肤没生效；安装新包前统一清理，
    保证同一时间只有一个 MikanCL 兜底资源包。
    返回被删除的包文件（相对路径）。
    """
    root = Path(game_dir)
    removed: list[str] = []
    for folder_name in ("resourcepacks", "texturepacks"):
        folder = root / folder_name
        if not folder.is_dir():
            continue
        try:
            items = list(folder.iterdir())
        except OSError:
            continue
        for item in items:
            if not item.is_file() or item.suffix.lower() != ".zip":
                continue
            if not item.name.startswith("MikanCL-"):
                continue
            try:
                item.unlink()
            except OSError:
                continue
            removed.append(f"{folder_name}/{item.name}")

    options = root / "options.txt"
    if not options.is_file():
        return removed
    try:
        lines = options.read_text(encoding="utf-8", errors="replace").splitlines()
        result: list[str] = []
        changed = False
        for line in lines:
            if not line.startswith("resourcePacks:"):
                result.append(line)
                continue
            try:
                packs = json.loads(line.split(":", 1)[1])
            except ValueError:
                result.append(line)
                continue
            if not isinstance(packs, list):
                result.append(line)
                continue
            kept = [
                entry
                for entry in packs
                if not (
                    str(entry).startswith("file/MikanCL-")
                    and str(entry).lower().endswith(".zip")
                )
            ]
            if len(kept) != len(packs):
                changed = True
                result.append("resourcePacks:" + json.dumps(kept, ensure_ascii=False))
            else:
                result.append(line)
        if changed:
            options.write_text("\n".join(result) + "\n", encoding="utf-8")
    except OSError:
        pass
    return removed


def apply_player_skin_bytes(
    image: bytes,
    player: str,
    model: str,
    game_dir: str | Path,
    version_id: str = "",
    install_pack: bool = True,
    enable_pack: bool = False,
) -> dict:
    """按玩家名写入本地皮肤，并生成版本适配的兜底资源包。"""
    name = (player or "").strip()
    if not name:
        raise SkinPackError("请填写目标玩家名。")
    if len(name) > 16:
        raise SkinPackError("玩家名不能超过 16 个字符。")
    if not image:
        raise SkinPackError("皮肤图片为空。")
    root = Path(game_dir)
    model = "slim" if (model or "").lower() == "slim" else "classic"
    paths: list[str] = []

    folder = root / "CustomSkinLoader" / "LocalSkin" / "skins"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{name}.png"
    try:
        target.write_bytes(image)
        paths.append(str(target))
    except OSError as exc:
        raise SkinPackError(f"写入本地皮肤失败：{exc}") from exc
    # 记录模型，便于下次重新打包时沿用
    (folder / f"{name}.model.json").write_text(
        json.dumps({"model": model}, ensure_ascii=False), encoding="utf-8"
    )
    try:
        paths.append(str(_merge_custom_skin_loader(root)))
    except OSError:
        pass

    if not install_pack:
        return {"skin": str(target), "paths": paths, "model": model, "pack": ""}

    # 先清掉旧包（含旧版全局 MikanCL-离线皮肤.zip），再写入新包，避免旧包残留被误认为已生效
    purge_old_packs(root)
    info = pack_info(version_id)
    filename = pack_filename(name)
    if info["kind"] == "legacy":
        folder_pack = root / "texturepacks"
    else:
        folder_pack = root / "resourcepacks"
    folder_pack.mkdir(parents=True, exist_ok=True)
    pack_path = folder_pack / filename
    try:
        pack_path.write_bytes(
            resourcepack_bytes(image, version_id, model, f"MikanCL 皮肤包 · {name}")
        )
        paths.append(str(pack_path))
    except OSError as exc:
        raise SkinPackError(f"生成资源包失败：{exc}") from exc
    if enable_pack and info["kind"] != "legacy":
        _enable_resource_pack(root, filename)
    _drop_legacy_pack(root)
    return {"skin": str(target), "paths": paths, "model": model, "pack": str(pack_path)}


def apply_player_skin(
    skin_path: str | Path,
    player: str,
    model: str,
    game_dir: str | Path,
    version_id: str = "",
    install_pack: bool = True,
    enable_pack: bool = False,
) -> dict:
    source = Path(skin_path)
    if not source.is_file():
        raise SkinPackError("找不到皮肤文件。")
    return apply_player_skin_bytes(
        source.read_bytes(), player, model, game_dir, version_id, install_pack, enable_pack
    )


def install_skin_pack(
    path: str | Path,
    game_dir: str | Path,
    player: str = "",
    model: str = "",
    version_id: str = "",
    enable_pack: bool = False,
) -> dict:
    """把皮肤包安装进游戏目录：LocalSkin + CustomSkinLoader.json + 兜底资源包。"""
    data = read_skin_pack(path)
    return apply_player_skin_bytes(
        data["image"],
        player or data["player"],
        model or data["model"] or "classic",
        game_dir,
        version_id or data["target_version"],
        install_pack=True,
        enable_pack=enable_pack,
    )


__all__ = [
    "MODEL_LABELS",
    "SKIN_PACK_FORMAT",
    "SkinPackError",
    "apply_player_skin",
    "apply_player_skin_bytes",
    "export_skin_pack",
    "install_skin_pack",
    "pack_filename",
    "pack_info",
    "purge_old_packs",
    "read_skin_pack",
    "resourcepack_bytes",
    "texture_paths",
    "version_tuple",
]
