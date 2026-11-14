"""物品 ID 扫描器：内置清单 + 已安装版本 jar + 模组 jar 的语言文件。

Minecraft 物品在语言文件里以 ``item.<namespace>.<path>`` /
``block.<namespace>.<path>`` 出现，把它们还原成 ``namespace:path`` 即可得到
可直接写入 NBT 的命名空间 ID。扫描结果会按 jar 修改时间缓存。
"""

from __future__ import annotations

import hashlib
import json
import time
import zipfile
from pathlib import Path

from .config import CACHE_DIR
from .creator_schema import LEGACY_ITEM_IDS

# 内置补充：不在旧数字 ID 表里、但常用的现代物品/方块
_EXTRA_ITEMS: dict[str, str] = {
    "minecraft:command_block": "命令方块",
    "minecraft:chain_command_block": "连锁命令方块",
    "minecraft:repeating_command_block": "循环命令方块",
    "minecraft:structure_block": "结构方块",
    "minecraft:barrier": "屏障",
    "minecraft:light": "光源方块",
    "minecraft:debug_stick": "调试棒",
    "minecraft:knowledge_book": "知识之书",
    "minecraft:netherite_sword": "下界合金剑",
    "minecraft:netherite_pickaxe": "下界合金镐",
    "minecraft:netherite_axe": "下界合金斧",
    "minecraft:netherite_shovel": "下界合金锹",
    "minecraft:netherite_helmet": "下界合金头盔",
    "minecraft:netherite_chestplate": "下界合金胸甲",
    "minecraft:netherite_leggings": "下界合金护腿",
    "minecraft:netherite_boots": "下界合金靴子",
    "minecraft:shulker_box": "潜影盒",
    "minecraft:elytra": "鞘翅",
    "minecraft:totem_of_undying": "不死图腾",
    "minecraft:enchanted_golden_apple": "附魔金苹果",
    "minecraft:end_crystal": "末地水晶",
    "minecraft:respawn_anchor": "重生锚",
    "minecraft:lodestone": "磁石",
    "minecraft:ancient_debris": "远古残骸",
    "minecraft:netherite_ingot": "下界合金锭",
    "minecraft:netherite_scrap": "下界合金碎片",
    "minecraft:amethyst_shard": "紫水晶碎片",
    "minecraft:echo_shard": "回响碎片",
    "minecraft:recovery_compass": "追溯指针",
    "minecraft:goat_horn": "山羊角",
    "minecraft:music_disc_pigstep": "音乐唱片",
    "minecraft:trident": "三叉戟",
    "minecraft:crossbow": "弩",
    "minecraft:shield": "盾牌",
    "minecraft:turtle_helmet": "海龟壳",
    "minecraft:saddle": "鞍",
    "minecraft:oak_boat": "橡木船",
    "minecraft:minecart": "矿车",
    "minecraft:hopper": "漏斗",
    "minecraft:observer": "侦测器",
    "minecraft:piston": "活塞",
    "minecraft:sticky_piston": "黏性活塞",
    "minecraft:dispenser": "发射器",
    "minecraft:dropper": "投掷器",
    "minecraft:redstone_block": "红石块",
    "minecraft:redstone_repeater": "红石中继器",
    "minecraft:redstone_comparator": "红石比较器",
    "minecraft:daylight_detector": " daylight detector",
    "minecraft:target": "标靶",
    "minecraft:note_block": "音符盒",
    "minecraft:jukebox": "唱片机",
    "minecraft:bedrock": "基岩",
    "minecraft:spawner": "刷怪笼",
    "minecraft:end_portal_frame": "末地传送门框架",
}

_ITEM_PREFIXES = ("item.", "block.", "itemGroup.")
_CACHE_VERSION = 1


def builtin_items() -> list[dict]:
    """内置物品清单，保证离线时也有可用候选。"""
    result: dict[str, dict] = {}
    for item_id in LEGACY_ITEM_IDS:
        result[item_id] = {
            "id": item_id,
            "name": item_id.split(":", 1)[-1].replace("_", " "),
            "namespace": item_id.split(":", 1)[0],
            "source": "内置",
        }
    for item_id, name in _EXTRA_ITEMS.items():
        result[item_id] = {
            "id": item_id,
            "name": name,
            "namespace": item_id.split(":", 1)[0],
            "source": "内置",
        }
    return list(result.values())


def _read_lang(zf: zipfile.ZipFile, name: str) -> dict:
    try:
        payload = zf.read(name)
    except (KeyError, OSError):
        return {}
    try:
        data = json.loads(payload.decode("utf-8", "replace"))
    except (ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _items_from_jar(path: Path) -> list[dict]:
    found: dict[str, dict] = {}
    try:
        with zipfile.ZipFile(path) as zf:
            names = [name for name in zf.namelist() if name.endswith("/lang/en_us.json")]
            for name in names:
                parts = name.split("/")
                if len(parts) < 4 or parts[0] != "assets":
                    continue
                namespace = parts[1]
                english = _read_lang(zf, name)
                chinese = _read_lang(zf, name.replace("/en_us.json", "/zh_cn.json"))
                if not english and not chinese:
                    continue
                keys = set(english) | set(chinese)
                for key in keys:
                    if not key.startswith(_ITEM_PREFIXES) or key.startswith("itemGroup."):
                        continue
                    segments = key.split(".")
                    if len(segments) < 3:
                        continue
                    # 语言键形如 item.<namespace>.<path>，命名空间以键为准
                    item_id = f"{segments[1]}:{'.'.join(segments[2:])}"
                    namespace = segments[1]
                    name_text = chinese.get(key) or english.get(key) or item_id
                    found[item_id] = {
                        "id": item_id,
                        "name": str(name_text),
                        "namespace": namespace,
                        "source": path.name,
                    }
    except (zipfile.BadZipFile, OSError, RuntimeError):
        return []
    return list(found.values())


def _candidate_jars(game_dir: Path, version_id: str) -> list[Path]:
    jars: list[Path] = []
    versions = game_dir / "versions"
    if versions.is_dir():
        if version_id:
            folder = versions / version_id
            jars.extend(sorted(folder.glob("*.jar")))
        else:
            jars.extend(sorted(versions.glob("*/*.jar")))
    mods = game_dir / "mods"
    if mods.is_dir():
        jars.extend(sorted(mods.glob("*.jar")))
    return [jar for jar in jars if jar.is_file()]


def _signature(jars: list[Path], version_id: str) -> str:
    parts = [f"v{_CACHE_VERSION}", version_id or ""]
    for jar in jars:
        try:
            stat = jar.stat()
        except OSError:
            continue
        parts.append(f"{jar}|{stat.st_mtime_ns}|{stat.st_size}")
    return "|".join(parts)


def _cache_path(cache_dir: Path, game_dir: Path, version_id: str, era: str = "") -> Path:
    # 用稳定哈希做文件名：内置 hash() 每个进程都会加盐，跨进程永远命中不了缓存。
    seed = f"{str(game_dir).lower()}|{version_id or ''}|{era}".encode("utf-8")
    stamp = hashlib.sha1(seed).hexdigest()[:16]
    return cache_dir / f"items-{stamp}.json"


def scan_item_ids(
    game_dir,
    *,
    version_id: str = "",
    era: str = "",
    use_cache: bool = True,
    cache_dir=None,
) -> list[dict]:
    """返回去重、排序后的物品候选列表（含 namespace 与来源）。

    ``era == "legacy"``（1.13 前）只能写数字 ID，因此只保留内置数字表里
    能安全映射的候选，避免选中后保存时才报错。
    """
    game = Path(game_dir)
    jars = _candidate_jars(game, version_id)
    signature = _signature(jars, version_id) + f"|{era}"
    cache_root = Path(cache_dir) if cache_dir else Path(CACHE_DIR) / "creator_items"
    cache_file = _cache_path(cache_root, game, version_id, era)

    if use_cache and cache_file.is_file():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if cached.get("signature") == signature and isinstance(cached.get("items"), list):
                return cached["items"]
        except (OSError, ValueError):
            pass

    merged: dict[str, dict] = {item["id"]: item for item in builtin_items()}
    for jar in jars:
        for item in _items_from_jar(jar):
            existing = merged.get(item["id"])
            if existing is None or existing.get("source") == "内置":
                merged[item["id"]] = item

    items = sorted(merged.values(), key=lambda item: item["id"])
    if era == "legacy":
        items = [item for item in items if item["id"] in LEGACY_ITEM_IDS]
    if use_cache:
        try:
            cache_root.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(
                json.dumps({"signature": signature, "items": items}, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass
    return items


def search_items(items: list[dict], query: str, limit: int = 200) -> list[dict]:
    """按 ID 或显示名做不区分大小写的包含匹配。"""
    text = str(query or "").strip().lower()
    if not text:
        return items[:limit]
    result = [
        item
        for item in items
        if text in item["id"].lower() or text in str(item.get("name", "")).lower()
    ]
    return result[:limit]
