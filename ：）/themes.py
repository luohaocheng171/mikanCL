"""主题注册表：内置多套主题 + 用户可自定义的 JSON 主题。

用户主题放在 ``data/themes/*.json``，最少只需 ``{"name": "我的主题", "accent": "#65d46e"}``，
其余颜色留空时按背景色自动推导；插件也可以通过 ``register()`` 写入主题。
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import DATA_DIR

THEME_DIR = DATA_DIR / "themes"
SAFE_NAME = re.compile(r"[^\w\u4e00-\u9fff-]+")


@dataclass
class Theme:
    name: str
    accent: str = "#65d46e"
    background: str = ""
    card: str = ""
    text: str = ""
    muted: str = ""


# 内置主题：前 8 套为深色，后 3 套为明亮模式；靠色相与底色差异区分
BUILTIN: list[Theme] = [
    Theme("森林绿", "#65d46e"),
    Theme("海蓝", "#4ea6e6", "#0a1420", "#121f2e", "#e6f0fa", "#8fa8bf"),
    Theme("暮紫", "#a37bf0", "#120f1e", "#1a1630", "#f0eaff", "#a99cc4"),
    Theme("赤红", "#e8636f", "#1a0d10", "#241317", "#fae8ea", "#c4a0a6"),
    Theme("琥珀", "#e8a83f", "#171207", "#211a0d", "#faf2e0", "#c4b08a"),
    Theme("青碧", "#45d6c0", "#071716", "#0d2220", "#e0faf6", "#8ac2b8"),
    Theme("樱花粉", "#f28bb4", "#1a1016", "#241720", "#fbe9f1", "#c9a3b4"),
    Theme("极夜蓝", "#6f8dff", "#0a0d1a", "#121830", "#e6eaff", "#9aa4c9"),
    Theme("晨光", "#4a8ff0", "#edf1f7", "#ffffff", "#1b2733", "#5c6f85"),
    Theme("米白", "#c98a3f", "#f5f0e7", "#fffdf8", "#2c2620", "#7a6b5c"),
    Theme("薄荷浅", "#2fa97d", "#eaf6f1", "#ffffff", "#173029", "#587d71"),
]


def _to_rgb(color: str) -> tuple[int, int, int]:
    text = color.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    try:
        return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
    except ValueError:
        return 0x0C, 0x13, 0x10


def _to_hex(rgb: tuple[float, float, float]) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(v))) for v in rgb)


def mix(color_a: str, color_b: str, ratio: float) -> str:
    """把两个颜色按比例混合，ratio=0 返回 A，1 返回 B。"""
    a, b = _to_rgb(color_a), _to_rgb(color_b)
    return _to_hex(tuple(x + (y - x) * ratio for x, y in zip(a, b)))


def relight(color: str, delta: int) -> str:
    """delta>0 向白色提亮，delta<0 向黑色压暗（范围 -100..100）。"""
    white_or_black = "#ffffff" if delta > 0 else "#000000"
    return mix(color, white_or_black, min(100, abs(delta)) / 100)


def luminance(color: str) -> float:
    """相对亮度（0 全黑，1 全白），用于判断明亮 / 黑暗主题。"""
    r, g, b = _to_rgb(color)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


def is_light(theme: Theme) -> bool:
    return luminance(theme.background or "#0c1310") > 0.55


def palette(theme: Theme) -> dict[str, str]:
    """把主题展开成样式表需要的完整调色板（缺省色自动推导，明暗自动适配）。"""
    background = theme.background or "#0c1310"
    light = is_light(theme)
    card = theme.card or relight(background, 12 if light else 10)
    text = theme.text or ("#1b2733" if light else "#e8f1ea")
    muted = theme.muted or mix(background, text, 0.55)
    accent = theme.accent or "#65d46e"
    return {
        "background": background,
        "sidebar": relight(background, -8 if light else -6),
        "card": card,
        "hover": relight(card, -5 if light else 7),
        "selected": mix(card, accent, 0.22),
        "border": relight(background, -14 if light else 15),
        "text": text,
        "muted": muted,
        "muted_dim": mix(background, muted, 0.65),
        "accent": accent,
        "accent_text": relight(accent, -18 if light else 22),
    }


def first_of_mode(mode: str) -> str:
    """取指定模式（light/dark）的第一套内置主题名，作为切换兜底。"""
    want_light = str(mode or "").lower() == "light"
    for theme in BUILTIN:
        if is_light(theme) == want_light:
            return theme.name
    return BUILTIN[0].name


def _parse(item: dict) -> Theme | None:
    name = str(item.get("name") or "").strip()
    if not name:
        return None
    accent = str(item.get("accent") or "").strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", accent):
        accent = ""
    return Theme(
        name=name,
        accent=accent,
        background=str(item.get("background") or "").strip(),
        card=str(item.get("card") or "").strip(),
        text=str(item.get("text") or "").strip(),
        muted=str(item.get("muted") or "").strip(),
    )


def user_themes() -> list[Theme]:
    """读取 data/themes/*.json；坏文件直接跳过，不影响启动。"""
    result: list[Theme] = []
    try:
        files = sorted(THEME_DIR.glob("*.json"))
    except OSError:
        return result
    for path in files:
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(item, dict):
            parsed = _parse(item)
            if parsed is not None:
                result.append(parsed)
    return result


def all_themes() -> dict[str, Theme]:
    """内置 + 用户主题；用户主题同名时覆盖内置。"""
    merged = {theme.name: theme for theme in BUILTIN}
    for theme in user_themes():
        merged[theme.name] = theme
    return merged


def get(name: str) -> Theme:
    return all_themes().get(name) or BUILTIN[0]


def overrides_for(name: str) -> dict[str, str] | None:
    """返回样式表覆盖色；默认「森林绿」走原有色相旋转，保持旧观感。"""
    theme = all_themes().get(name)
    if theme is None:
        return None
    if theme.name == BUILTIN[0].name and not any(
        (theme.background, theme.card, theme.text, theme.muted)
    ):
        return None
    return palette(theme)


def register(theme: Theme | dict) -> Theme | None:
    """注册（并落盘）一个用户主题，供插件与自定义主题使用。"""
    if isinstance(theme, dict):
        parsed = _parse(theme)
    else:
        parsed = theme
    if parsed is None or not parsed.name:
        return None
    try:
        THEME_DIR.mkdir(parents=True, exist_ok=True)
        filename = SAFE_NAME.sub("_", parsed.name).strip("_") or "theme"
        (THEME_DIR / f"{filename}.json").write_text(
            json.dumps(asdict(parsed), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass
    return parsed


def write_template(path: str | Path) -> None:
    """导出可编辑的主题模板（包含全部字段示例）。"""
    template = {
        "name": "我的主题",
        "accent": "#65d46e",
        "background": "#0c1310",
        "card": "#121d16",
        "text": "#e8f1ea",
        "muted": "#8aa192",
    }
    Path(path).write_text(
        json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8"
    )
