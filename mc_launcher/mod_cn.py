"""Mod / 整合包的中文译名词表。

Modrinth 与 CurseForge 只提供英文项目名，中文用户既看不懂列表也很难用中文搜索。
这里维护一份常用项目的官方/社区通用中文译名与一句话简介：

* 界面展示：列表、详情页优先显示中文名，英文原名保留在提示框里；
* 中文搜索：用户输入中文关键词时，映射为对应英文项目名再向平台检索。

词表以「规范化英文标题」为键，调用方不需要关心大小写、括号后缀与标点差异。
"""

from __future__ import annotations

import re

# PCL 风格的「用途分类」：界面按这个顺序展示筛选按钮
CATEGORY_LABELS: dict[str, str] = {
    "optimization": "优化",
    "utility": "辅助",
    "library": "前置",
    "decoration": "装饰",
    "tech": "科技",
    "magic": "魔法",
    "adventure": "冒险",
    "farming": "农业",
    "worldgen": "世界生成",
    "modpack": "整合包",
    "resourcepack": "资源包",
    "shader": "光影",
}

# 关键词表：标题 / 中文简介 / 平台标签里命中任一关键词即归入该分类。
# 中英文都收录，因为未收录进词表的项目只有平台返回的英文标题与简介。
CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "optimization": (
        "优化", "性能", "帧率", "卡顿", "内存", "启动速度", "剔除", "渲染", "光照", "加载",
        "optimiz", "performance", "fps", "lag", "memory", "render", "cull", "light",
    ),
    "utility": (
        "管理", "信息", "显示", "地图", "界面", "操作", "按键", "配置", "整理", "提示",
        "hud", "tooltip", "minimap", "overlay", "config", "utility", "screen", "menu", "map",
    ),
    "library": (
        "前置", "依赖", "开发", "库", "api", "kotlin", "library", "framework", "lib",
    ),
    "decoration": (
        "装饰", "家具", "建筑", "美化", "外观", "decor", "furniture", "cosmetic",
    ),
    "tech": (
        "科技", "机械", "电力", "能源", "自动化", "机器", "工业", "存储", "物流", "反应堆",
        "tech", "machine", "energy", "automation", "storage", "power", "factory", "reactor",
    ),
    "magic": (
        "魔法", "神秘", "法术", "符文", "附魔", "咒语", "magic", "spell", "rune", "arcane",
        "enchant", "mystic",
    ),
    "adventure": (
        "冒险", "地牢", "探索", "战斗", "生物", "维度", "神话", "boss", "怪物",
        "adventure", "dungeon", "explore", "combat", "mob", "dimension", "creature",
    ),
    "farming": (
        "农业", "种植", "作物", "料理", "食物", "村民", "蜜蜂", "钓鱼", "食谱",
        "farm", "crop", "food", "cooking", "recipe", "villager", "bee", "agriculture",
    ),
    "worldgen": (
        "世界生成", "地形", "群系", "生物群系", "区块", "结构", "世界",
        "worldgen", "biome", "terrain", "chunk", "world generation", "structure",
    ),
    "modpack": (
        "整合包", "任务书", "modpack", "quest",
    ),
    "resourcepack": (
        "资源包", "材质", "贴图", "resource pack", "resourcepack", "texture",
    ),
    "shader": (
        "光影", "着色器", "shader",
    ),
}

# 平台自带标签 → 本地分类（Modrinth 用 categories，CurseForge 用分类名）
PLATFORM_CATEGORY_MAP: dict[str, str] = {
    "optimization": "optimization",
    "technology": "tech",
    "tech": "tech",
    "magic": "magic",
    "adventure": "adventure",
    "decoration": "decoration",
    "cosmetic": "decoration",
    "worldgen": "worldgen",
    "food": "farming",
    "farming": "farming",
    "library": "library",
    "utility": "utility",
    "storage": "tech",
    "equipment": "adventure",
    "mobs": "adventure",
    "quests": "modpack",
    "shaders": "shader",
    "resource packs": "resourcepack",
    "fonts": "resourcepack",
}

# 键：规范化后的英文项目名（小写、去括号、去标点）；值：(中文名, 中文简介)
CN_PROJECTS: dict[str, tuple[str, str]] = {
    # ---- 物品与配方 ----
    "just enough items": ("物品管理器", "在物品栏中查看全部物品与合成配方。"),
    "jei": ("物品管理器", "在物品栏中查看全部物品与合成配方。"),
    "roughly enough items": ("REI 物品管理器", "查看物品与合成配方，常与 Fabric 搭配。"),
    "rei": ("REI 物品管理器", "查看物品与合成配方，常与 Fabric 搭配。"),
    "emi": ("EMI 物品管理器", "现代化配方查看器，支持合成树与搜索。"),
    # ---- 性能优化 ----
    "sodium": ("钠", "高性能渲染优化，显著提升帧率。"),
    "iris shaders": ("虹膜光影", "让 Fabric 支持 OptiFine 风格光影。"),
    "oculus": ("眼睛", "Forge 端光影支持（Iris 移植）。"),
    "embeddium": ("嵌入式优化", "Forge 端 Sodium 移植，提升渲染性能。"),
    "rubidium": ("铷", "Forge 端渲染优化（Sodium 移植旧称）。"),
    "lithium": ("锂", "逻辑运算优化，减少卡顿。"),
    "phosphor": ("磷", "旧版光照引擎优化。"),
    "starlight": ("星光", "重写光照引擎，提升光照与区块性能。"),
    "krypton": ("氪", "网络栈优化，降低联机延迟。"),
    "ferritecore": ("铁氧体核心", "降低内存占用。"),
    "modernfix": ("现代修复", "启动速度与内存综合优化。"),
    "canary": ("金丝雀", "区块与生物 AI 优化。"),
    "saturn": ("土星", "内存与垃圾回收优化。"),
    "debugify": ("调试修复", "修复大量原版小问题。"),
    "crash assistant": ("崩溃助手", "崩溃时给出原因与修复建议。"),
    "entity culling": ("实体渲染剔除", "不渲染视野外的实体，提升帧率。"),
    "more culling": ("更多剔除", "剔除不可见的方块面与实体。"),
    "cull leaves": ("树木剔除", "优化树叶渲染。"),
    "dynamic fps": ("动态帧率", "窗口失焦时自动降低帧率。"),
    "badoptimizations": ("优化补丁", "一系列客户端微优化。"),
    "noisium": ("区块生成优化", "加速世界生成。"),
    "fastload": ("快速加载", "大幅缩短启动时间。"),
    "chunky": ("区块预生成", "提前生成区块以减少卡顿。"),
    "indium": ("铟", "Sodium 的 Fabric 渲染 API 兼容层。"),
    "continuity": ("连接纹理", "支持 OptiFine 连接纹理。"),
    "animatica": ("动画纹理", "支持 OptiFine 动画纹理。"),
    "sodium extra": ("钠：附加", "钠的额外画面设置。"),
    "reeses sodium options": ("钠选项增强", "重新整理钠的设置界面。"),
    "sodium dynamic lights": ("钠：动态光源", "手持光源照亮周围。"),
    "optifine": ("高清修复", "光影、动态光源与性能优化（旧版）。"),
    # ---- 基础库与界面 ----
    "fabric api": ("Fabric API", "Fabric 模组的基础 API。"),
    "architectury api": ("Architectury API", "跨加载器模组开发 API。"),
    "cloth config api": ("布料配置", "模组配置界面库。"),
    "cloth config": ("布料配置", "模组配置界面库。"),
    "mod menu": ("Mod 菜单", "在游戏内查看与管理已装模组。"),
    "fabric language kotlin": ("Fabric Kotlin 支持", "运行 Kotlin 模组所需的前置。"),
    "geckolib": ("GeckoLib", "实体与方块动画库。"),
    "patchouli": ("帕秋莉手册", "游戏内说明书。"),
    "curios api": ("饰品栏 API", "增加饰品装备栏。"),
    "trinkets": ("饰品", "Fabric 端饰品装备栏。"),
    # ---- 信息显示 ----
    "mouse tweaks": ("鼠标操作增强", "改进物品栏拖拽与滚轮操作。"),
    "controlling": ("按键冲突查询", "搜索按键绑定并提示冲突。"),
    "appleskin": ("苹果皮", "显示饱和度与食物回复预估。"),
    "jade": ("玉（方块信息）", "准星指向方块时显示详细信息。"),
    "wthit": ("方块信息显示", "准星指向方块时显示详细信息。"),
    "journeymap": ("旅行地图", "全屏地图与路径点。"),
    "xaeros minimap": ("Xaero 的小地图", "小地图与路径点。"),
    "xaeros world map": ("Xaero 的世界地图", "全屏世界地图。"),
    "waystones": ("传送石碑", "放置石碑进行快速传送。"),
    "shulker box tooltip": ("潜影盒提示", "悬停预览潜影盒内容。"),
    "inventory hud": ("物品栏 HUD+", "屏幕上显示装备与背包。"),
    "inventory profiles next": ("物品栏配置", "一键整理与排序物品栏。"),
    # ---- 玩法大修 ----
    "apotheosis": ("神化", "附魔、刷怪与战利品大修。"),
    "create": ("机械动力", "以齿轮与转轴为核心的机械自动化。"),
    "create crafts additions": ("机械动力：电力附加", "为机械动力增加电动机与电力设备。"),
    "farmers delight": ("农夫乐事", "增加农作物与料理。"),
    "twilight forest": ("暮色森林", "探索型维度模组。"),
    "the aether": ("天境", "天空维度冒险模组。"),
    "botania": ("植物魔法", "以花朵产能的魔法科技。"),
    "thermal expansion": ("热力膨胀", "经典科技模组。"),
    "immersive engineering": ("沉浸工程", "现实主义风格科技模组。"),
    "mekanism": ("通用机械", "电力、化工与核能科技。"),
    "applied energistics 2": ("应用能源 2", "ME 网络存储与自动化。"),
    "ae2": ("应用能源 2", "ME 网络存储与自动化。"),
    "refined storage": ("精致存储", "简洁的网络存储方案。"),
    "storage drawers": ("储物抽屉", "大容量方块存储。"),
    "iron chests": ("铁箱子", "更多材质的箱子。"),
    "sophisticated backpacks": ("精致背包", "可升级的背包。"),
    "travelers backpack": ("旅行者背包", "轻量背包。"),
    "quark": ("夸克", "大量原版风格的小功能。"),
    "supplementaries": ("补充", "丰富原版细节的小物件。"),
    "simple voice chat": ("简单语音聊天", "游戏内近距离语音。"),
    "distant horizons": ("遥远地平线", "超远渲染距离的地形 LOD。"),
    "better combat": ("更好的战斗", "双持与战斗动画。"),
    "first person model": ("第一人称模型", "第一人称下显示玩家身体。"),
    "not enough animations": ("更多动画", "补全玩家动作动画。"),
    "sound physics remastered": ("声音物理重制", "真实的声音遮挡与混响。"),
    "ambientsounds": ("环境音效", "按生物群系播放环境音。"),
    "falling leaves": ("落叶", "树叶飘落粒子效果。"),
    "corpse": ("尸体", "死亡后在原地保存物品。"),
    "graves": ("墓碑", "死亡后生成墓碑保存物品。"),
    "carry on": ("搬运", "空手搬起箱子与生物。"),
    "easy villagers": ("简易村民", "便捷的村民交易与繁殖。"),
    "tinkers construct": ("匠魂", "自定义工具与冶炼。"),
    "forestry": ("林业", "蜜蜂与树木育种。"),
    "biomes o plenty": ("丰富的生物群系", "新增大量生物群系。"),
    "terralith": ("地形改造", "用原版方块生成壮丽地形。"),
    "oh the biomes youll go": ("你将去的生物群系", "大量新群系与树木。"),
    "betterend": ("更好的末地", "重制末地群系与内容。"),
    "betternether": ("更好的下界", "重制下界群系与内容。"),
    "alexs mobs": ("Alex 的生物", "新增大量真实风格生物。"),
    "ice and fire": ("冰与火之歌", "巨龙与神话生物。"),
    "mystical agriculture": ("神秘农业", "用种子种植矿物。"),
    "projecte": ("等价交换", "物质转化与 EMC 系统。"),
    "kubejs": ("KubeJS 脚本", "用 JavaScript 自定义整合包内容。"),
    "crafttweaker": ("CraftTweaker 合成修改", "用脚本修改配方。"),
    "ftb quests": ("FTB 任务", "整合包任务与奖励系统。"),
    "cobblemon": ("方块宝可梦", "在 Minecraft 中捕捉宝可梦。"),
    "lootr": ("战利品", "每个玩家独立的战利品箱。"),
    # ---- 整合包 ----
    "rlcraft": ("RLCraft", "高难度硬核生存整合包。"),
    "all the mods 9": ("ATM9 整合包", "全模组科技整合包。"),
    "all the mods 10": ("ATM10 整合包", "ATM 系列最新整合包。"),
    "atm9": ("ATM9 整合包", "全模组科技整合包。"),
    "better mc": ("更好的 MC", "优化与原版增强整合包。"),
    "stoneblock": ("石头世界", "从石头中开始生存的整合包。"),
    "skyfactory": ("空岛工厂", "经典空岛科技整合包。"),
    "enigmatica": ("神秘整合包", "循序渐进的科技整合包。"),
    "vault hunters": ("金库猎人", "地牢探索与战利品整合包。"),
    "cottage witch": ("乡间女巫", "田园魔法生活整合包。"),
    "create above and beyond": ("机械动力：超越", "机械动力主题任务整合包。"),
    "fabulously optimized": ("极致优化", "基于 Fabric 的优化整合包。"),
    "simply optimized": ("简单优化", "轻量优化整合包。"),
    "all of fabric": ("AOF 整合包", "Fabric 全模组整合包。"),
    "sevtech ages": ("科技时代", "按时代推进的科技整合包。"),
    "ftb academy": ("FTB 学院", "新手教学整合包。"),
    "ftb skies": ("FTB 天空", "FTB 空岛整合包。"),
    "prominence ii": ("Prominence II", "冒险与科技整合包。"),
    "dawncraft": ("DawnCraft", "动作冒险整合包。"),
    "rad": ("冒险与地牢", "Roguelike 冒险整合包。"),
}

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

# 这些词泛指一整类内容，映射到某个具体项目反而误导搜索结果
_GENERIC_TERMS = {"整合包", "模组", "光影", "资源包", "地图", "优化", "前置", "插件"}


def has_chinese(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


def normalize_title(title: str) -> str:
    """规范化英文标题：小写、去掉括号备注与标点，便于与词表比对。"""
    text = (title or "").lower()
    text = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", text)
    text = text.replace("'", "").replace("’", "")
    text = re.sub(r"[^0-9a-z]+", " ", text)
    return " ".join(text.split())


def cn_name(title: str) -> str:
    """返回项目的中文名：先查本地词表，再查 MC百科在线译名缓存。"""
    entry = CN_PROJECTS.get(normalize_title(title))
    if entry:
        return entry[0]
    try:
        from .cn_source import cached_name

        return cached_name(title)
    except Exception:  # noqa: BLE001 - 在线词典不可用时退回英文原名
        return ""


def cn_description(title: str) -> str:
    entry = CN_PROJECTS.get(normalize_title(title))
    return entry[1] if entry else ""


def categories_for(
    title: str,
    description: str = "",
    platform_categories: list[str] | None = None,
    project_type: str = "mod",
) -> list[str]:
    """按用途给项目归类（PCL 风格）。

    判定顺序：平台标签 → 词表中文名/简介 → 标题与简介关键词。
    返回的分类键按 ``CATEGORY_LABELS`` 的顺序排列，未命中任何分类时返回空列表。
    """
    kind = str(project_type or "mod")
    entry = CN_PROJECTS.get(normalize_title(title))
    parts = [title or "", description or "", " ".join(platform_categories or [])]
    if entry:
        parts.extend(entry)
    text = " ".join(parts).lower()

    found: set[str] = set()
    for key, words in CATEGORY_KEYWORDS.items():
        if any(word in text for word in words):
            found.add(key)
    for raw in platform_categories or []:
        mapped = PLATFORM_CATEGORY_MAP.get(str(raw).strip().lower())
        if mapped:
            found.add(mapped)

    if kind == "modpack":
        found.add("modpack")
    elif kind in ("resourcepack", "texturepack"):
        found.add("resourcepack")
    elif kind == "shader":
        found.add("shader")
        # 光影包常被平台同时标成资源包，按类型只保留「光影」
        found.discard("resourcepack")

    # 「前置」类项目往往也会命中「辅助」的关键词，只保留更具体的「前置」
    if "library" in found and "utility" in found:
        found.discard("utility")

    return [key for key in CATEGORY_LABELS if key in found]


def category_label(key: str) -> str:
    return CATEGORY_LABELS.get(key, key)


def translate_query(query: str) -> list[str]:
    """把中文搜索词映射为英文项目名列表（按匹配度排序，最多两个）。

    仅当查询包含中文时才需要翻译；英文查询返回空列表，调用方沿用原查询。
    """
    text = (query or "").strip()
    if not text or not has_chinese(text):
        return []
    compact = re.sub(r"\s+", "", text)
    if compact in _GENERIC_TERMS:
        return []
    hits: list[tuple[int, str]] = []
    for key, (name, _desc) in CN_PROJECTS.items():
        if name in _GENERIC_TERMS:
            continue
        candidate = re.sub(r"\s+", "", name)
        if len(compact) < 2 and compact != candidate:
            continue
        if len(candidate) < 2 and compact != candidate:
            continue
        if candidate in compact or compact in candidate:
            hits.append((abs(len(candidate) - len(compact)), key))
    hits.sort()
    if not hits:
        # 本地词表没有命中时，交给 MC百科在线词典翻译中文关键词
        try:
            from .cn_source import lookup_query

            return lookup_query(text)[:2]
        except Exception:  # noqa: BLE001 - 网络不可用时沿用原查询
            return []
    result: list[str] = []
    seen_names: set[str] = set()
    for _, key in hits:
        name = CN_PROJECTS[key][0]
        if name in seen_names:
            continue
        seen_names.add(name)
        result.append(key)
    return result[:2]
