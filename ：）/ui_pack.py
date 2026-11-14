"""UI 材质包：按游戏版本生成「半透明毛玻璃」界面资源包。

避免凭空画界面（布局会错），改为「从客户端 jar 里取出原版 GUI 贴图，
统一做半透明 + 冷色磨砂处理」，这样任何版本的按钮、输入框、滑块、
九宫格切图的尺寸与 .mcmeta 都保持原样，只改变观感：
界面按钮 / 输入框 / 滑块 / 背包与箱子面板 / 快捷栏都会变成半透明磨砂。

* 1.0–1.5.2：纹理包（texturepacks/ + pack.txt + gui/*）
* 1.6.1–1.20.1：资源包（assets/minecraft/textures/gui/widgets.png 等）
* 1.20.2+：资源包（gui/sprites/widget/* 九宫格 sprites，连同 .mcmeta 一起覆盖）
* 菜单平铺背景（options_background / menu_background）改用程序生成的
  无缝磨砂玻璃瓦片，不依赖原版泥土贴图。
"""

from __future__ import annotations

import io
import json
import math
import re
import zipfile
from pathlib import Path

from .skinpack import _mcmeta, pack_info

UI_PACK_NAME = "MikanCL-毛玻璃UI"
UI_PACK_VERSION = 1

# 需要做半透明处理的 GUI 贴图（匹配 jar 内小写路径）
_TRANSFORM_KEYS = (
    "/gui/widgets.png",
    "/gui/gui.png",
    "/gui/options_background.png",
    "/gui/menu_background.png",
    "/gui/sprites/widget/",
    "/gui/sprites/menu/",
    "/gui/sprites/menu_background.png",
    "/gui/sprites/options_background.png",
    "/gui/sprites/hud/hotbar",
    "/gui/container/",
)
_BACKGROUND_NAMES = {"options_background.png", "menu_background.png", "background.png"}
# 1.5.2 及更早的纹理包直接镜像 jar 根目录结构（没有 textures/ 前缀）
_LEGACY_FILES = {
    "gui/gui.png",
    "gui/background.png",
    "gui/inventory.png",
    "gui/container.png",
    "gui/crafting.png",
    "gui/furnace.png",
    "gui/trap.png",
    "gui/enchant.png",
    "gui/alchemy.png",
    "gui/book.png",
    "gui/trading.png",
}
# 容器 / 背包面板（老版本没有 container/ 目录，只能按文件名判断）
_CONTAINER_NAMES = {
    "inventory.png",
    "container.png",
    "crafting.png",
    "furnace.png",
    "trap.png",
    "enchant.png",
    "alchemy.png",
    "book.png",
    "trading.png",
    "beacon.png",
    "brewing.png",
    "hopper.png",
    "anvil.png",
    "dispenser.png",
    "generic_54.png",
    "shulker_box.png",
    "smithing.png",
    "stonecutter.png",
    "cartography.png",
}
# 图标类贴图不参与磨砂，避免功能图标变糊
_SKIP_NAMES = {"stats_icons.png"}

_VERSION_RE = re.compile(r"^(\d+(?:\.\d+)+)")


class UiPackError(Exception):
    pass


# ----------------------------------------------------------------------
# Qt 图像处理（项目本身强依赖 PySide6，这里按需惰性导入）
def _qimage_from_png(data: bytes):
    from PySide6.QtGui import QImage

    image = QImage()
    if not image.loadFromData(data, "PNG"):
        return None
    return image.convertToFormat(QImage.Format_ARGB32)


def _png_bytes(image) -> bytes:
    from PySide6.QtCore import QBuffer, QIODevice

    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise UiPackError("无法编码 PNG 贴图。")
    return bytes(buffer.data())


def _clamp(value: float, low: int = 0, high: int = 255) -> int:
    return max(low, min(high, int(round(value))))


def _frost(
    image,
    alpha_scale: float = 0.42,
    tint: tuple[int, int, int] = (226, 238, 255),
    tint_mix: float = 0.32,
    desat: float = 0.26,
):
    """把原版 GUI 贴图变成半透明冷色磨砂玻璃，保留原布局与像素边界。"""
    from PySide6.QtGui import QImage

    image = image.convertToFormat(QImage.Format_ARGB32)
    try:
        view = memoryview(image.bits())
    except TypeError:
        view = None
    tint_r, tint_g, tint_b = tint
    keep = 1.0 - tint_mix
    if view is not None and not getattr(view, "readonly", False):
        total = image.width() * image.height() * 4
        # Windows 小端：Format_ARGB32 的内存顺序是 B, G, R, A
        for index in range(0, total, 4):
            blue = view[index]
            green = view[index + 1]
            red = view[index + 2]
            alpha = view[index + 3]
            if alpha == 0:
                continue
            lum = (red * 77 + green * 150 + blue * 29) >> 8
            red = _clamp((red + (lum - red) * desat) * keep + tint_r * tint_mix)
            green = _clamp((green + (lum - green) * desat) * keep + tint_g * tint_mix)
            blue = _clamp((blue + (lum - blue) * desat) * keep + tint_b * tint_mix)
            alpha = int(alpha * alpha_scale)
            if alpha < 16:
                alpha = 16
            view[index] = blue
            view[index + 1] = green
            view[index + 2] = red
            view[index + 3] = alpha
        return image
    # 兜底：逐像素 API（较慢，仅当内存视图不可写时使用）
    from PySide6.QtGui import QColor

    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if color.alpha() == 0:
                continue
            lum = (color.red() * 77 + color.green() * 150 + color.blue() * 29) >> 8
            red = _clamp((color.red() + (lum - color.red()) * desat) * keep + tint_r * tint_mix)
            green = _clamp((color.green() + (lum - color.green()) * desat) * keep + tint_g * tint_mix)
            blue = _clamp((color.blue() + (lum - color.blue()) * desat) * keep + tint_b * tint_mix)
            alpha = max(16, int(color.alpha() * alpha_scale))
            image.setPixelColor(x, y, QColor(red, green, blue, alpha))
    return image


def _glass_tile(
    size: int = 64,
    base: tuple[int, int, int] = (26, 34, 50),
    alpha: int = 108,
    diagonal: bool = False,
):
    """生成可无缝平铺的磨砂玻璃瓦片（正弦叠加保证左右上下接缝一致）。"""
    from PySide6.QtGui import QColor, QImage

    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(0)
    for y in range(size):
        v = 2 * math.pi * y / size
        for x in range(size):
            u = 2 * math.pi * x / size
            noise = (
                math.sin(u * 2 + 0.6) * 0.45
                + math.sin(v * 3 + 1.7) * 0.30
                + math.sin((u + v) * 2 + 3.1) * 0.25
            )
            level = (noise + 1) / 2  # 0..1
            factor = 0.82 + 0.30 * level
            if diagonal:
                factor *= 1.0 + 0.35 * (1.0 - (x + y) / (size * 2))
            red = _clamp(base[0] * factor + 210 * 0.05 * level)
            green = _clamp(base[1] * factor + 225 * 0.05 * level)
            blue = _clamp(base[2] * factor + 245 * 0.05 * level)
            tile_alpha = _clamp(alpha * (0.78 + 0.22 * level))
            image.setPixelColor(x, y, QColor(red, green, blue, tile_alpha))
    return image


def _icon_png() -> bytes:
    image = _glass_tile(128, base=(28, 37, 54), alpha=255, diagonal=True)
    return _png_bytes(image)


# ----------------------------------------------------------------------
def find_client_jar(game_root: str | Path, version_id: str) -> Path | None:
    """找到该版本实际使用的原版客户端 jar（加载器版本回退到基础版本）。"""
    root = Path(game_root)
    versions = root / "versions"
    version_id = (version_id or "").strip()
    names: list[str] = []
    if version_id:
        names.append(version_id)
    match = _VERSION_RE.match(version_id)
    if match:
        base = match.group(1)
        if base not in names:
            names.append(base)
        if base.count(".") == 1 and f"{base}.0" not in names:
            names.append(f"{base}.0")
    for name in names:
        folder = versions / name
        if not folder.is_dir():
            continue
        jar = folder / f"{name}.jar"
        if jar.is_file():
            return jar
        try:
            jars = sorted(
                (
                    item
                    for item in folder.iterdir()
                    if item.is_file() and item.suffix.lower() == ".jar"
                ),
                key=lambda item: item.stat().st_size,
                reverse=True,
            )
        except OSError:
            jars = []
        if jars:
            return jars[0]
    return None


def _jar_textures(jar: Path, legacy: bool) -> dict[str, tuple[bytes, bytes]]:
    """读取 jar 内需要覆盖的 GUI 贴图，并带上同名 .mcmeta（九宫格信息）。"""
    result: dict[str, tuple[bytes, bytes]] = {}
    try:
        with zipfile.ZipFile(jar) as archive:
            names = set(archive.namelist())
            for name in archive.namelist():
                low = name.lower()
                if not low.endswith(".png"):
                    continue
                if legacy:
                    if low not in _LEGACY_FILES:
                        continue
                else:
                    if not low.startswith("assets/minecraft/textures/gui/"):
                        continue
                    if not any(key in low for key in _TRANSFORM_KEYS):
                        continue
                try:
                    data = archive.read(name)
                except (KeyError, OSError):
                    continue
                meta = b""
                if name + ".mcmeta" in names:
                    meta = archive.read(name + ".mcmeta")
                result[name] = (data, meta)
    except (OSError, zipfile.BadZipFile):
        return {}
    return result


def _pack_description(version_id: str) -> str:
    return f"MikanCL 毛玻璃 UI · {version_id or '通用'}"


def build_ui_pack(version_id: str, jar_path: str | Path | None = None) -> bytes:
    """生成适用于指定版本的 UI 材质包 zip 内容。"""
    info = pack_info(version_id)
    legacy = info["kind"] == "legacy"
    files: dict[str, bytes] = {}
    if legacy:
        files["gui/background.png"] = _png_bytes(_glass_tile(64))
    else:
        files["assets/minecraft/textures/gui/options_background.png"] = _png_bytes(
            _glass_tile(64)
        )

    jar = Path(jar_path) if jar_path else None
    if jar is not None and jar.is_file():
        for name, (data, meta) in _jar_textures(jar, legacy).items():
            image = _qimage_from_png(data)
            if image is None:
                continue
            base_name = name.rsplit("/", 1)[-1].lower()
            lowered = name.lower()
            if base_name in _SKIP_NAMES:
                continue
            if base_name in _BACKGROUND_NAMES:
                # 平铺背景直接换成无缝玻璃瓦片，避免原版泥土纹理透出来
                files[name] = _png_bytes(_glass_tile(64))
            elif "/sprites/hud/" in lowered:
                # 快捷栏保持一定辨识度，只做轻微磨砂
                files[name] = _png_bytes(
                    _frost(image, alpha_scale=0.56, tint_mix=0.16, desat=0.10)
                )
            elif "/container/" in lowered or base_name in _CONTAINER_NAMES:
                # 背包 / 箱子面板：透明度略保守，保证物品格看得清
                files[name] = _png_bytes(
                    _frost(image, alpha_scale=0.72, tint_mix=0.26, desat=0.22)
                )
            else:
                files[name] = _png_bytes(_frost(image))
            if meta:
                files[name + ".mcmeta"] = meta

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        if legacy:
            archive.writestr("pack.txt", f"{_pack_description(version_id)}\n1\n")
        else:
            archive.writestr(
                "pack.mcmeta",
                json.dumps(_mcmeta(_pack_description(version_id), info), ensure_ascii=False, indent=2),
            )
        archive.writestr("pack.png", _icon_png())
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def ui_pack_filename(version_id: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z._-]", "_", (version_id or "").strip()) or "generic"
    return f"{UI_PACK_NAME}-{safe}.zip"


def _enable_resource_pack(root: Path, name: str) -> None:
    """把本包写进 options.txt 的启用列表，并清掉旧版本的 UI 包条目。"""
    options = root / "options.txt"
    wanted = f"file/{name}"
    try:
        lines = (
            options.read_text(encoding="utf-8", errors="replace").splitlines()
            if options.is_file()
            else []
        )
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
            packs = [
                entry
                for entry in packs
                if not (
                    isinstance(entry, str)
                    and entry.startswith(f"file/{UI_PACK_NAME}")
                )
            ]
            if wanted not in packs:
                packs.append(wanted)
            result.append("resourcePacks:" + json.dumps(packs, ensure_ascii=False))
            updated = True
        if not updated:
            result.append(
                "resourcePacks:" + json.dumps(["vanilla", wanted], ensure_ascii=False)
            )
        options.write_text("\n".join(result) + "\n", encoding="utf-8")
    except OSError:
        pass


def apply_ui_pack(
    config,
    version_id: str,
    enable: bool = True,
    jar_path: str | Path | None = None,
) -> dict:
    """生成 UI 材质包并写入该版本的游戏目录（按隔离模式选择位置）。"""
    version = (version_id or "").strip()
    if not version:
        raise UiPackError("请先选择要生成 UI 材质包的游戏版本。")
    info = pack_info(version)
    legacy = info["kind"] == "legacy"
    jar = Path(jar_path) if jar_path else find_client_jar(config.game_path, version)
    data = build_ui_pack(version, jar)
    folder = "texturepacks" if legacy else "resourcepacks"
    written: list[str] = []
    for pack_dir in config.resolve_game_dirs(version).targets(folder):
        try:
            pack_dir.mkdir(parents=True, exist_ok=True)
            target = pack_dir / ui_pack_filename(version)
            target.write_bytes(data)
        except OSError as exc:
            raise UiPackError(f"写入 UI 材质包失败：{exc}") from exc
        written.append(str(target))
        if enable and not legacy:
            _enable_resource_pack(pack_dir.parent, target.name)
    return {
        "paths": written,
        "legacy": legacy,
        "has_jar": bool(jar is not None and Path(jar).is_file()),
        "pack_format": info["pack_format"],
        "label": info["label"],
    }


def export_ui_pack(
    dest: str | Path,
    version_id: str,
    jar_path: str | Path | None = None,
    game_root: str | Path | None = None,
) -> Path:
    """把 UI 材质包导出为可分享的 zip。"""
    version = (version_id or "").strip()
    target = Path(dest)
    jar = Path(jar_path) if jar_path else None
    if jar is None and game_root is not None:
        jar = find_client_jar(game_root, version)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(build_ui_pack(version, jar))
    except OSError as exc:
        raise UiPackError(f"导出 UI 材质包失败：{exc}") from exc
    return target


def ui_pack_info(version_id: str) -> dict:
    """给界面用的版本适配说明。"""
    info = pack_info(version_id)
    if info["kind"] == "legacy":
        info = dict(info)
        info["hint"] = "1.0–1.5.2 生成 texturepacks 纹理包，进游戏在「材质包」里手动选中"
    elif info["kind"] == "range":
        info = dict(info)
        info["hint"] = f"1.21.9+ / 26.x：{info['label']}，安装后自动启用"
    else:
        info = dict(info)
        info["hint"] = f"1.6.1+ 资源包（{info['label']}），安装后自动启用"
    return info


__all__ = [
    "UI_PACK_NAME",
    "UiPackError",
    "apply_ui_pack",
    "build_ui_pack",
    "export_ui_pack",
    "find_client_jar",
    "ui_pack_filename",
    "ui_pack_info",
]
