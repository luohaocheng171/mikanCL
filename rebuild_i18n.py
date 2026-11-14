"""重建 Qt 翻译文件（.ts / .qm）。

源码里使用自定义的 ``t(context, text)`` 与 ``self.tr(text)``，Qt 自带的 lupdate
无法直接识别，因此这里用 AST 精确提取上下文与原文，再从现有 .qm 里取回已有
译文，最后调用 lrelease 重新编译。

用法：python rebuild_i18n.py
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent
TRANSLATIONS = ROOT / "mc_launcher" / "translations"
LANGUAGES = ["zh_CN", "en_US", "ja_JP", "ru_RU", "fr_FR"]

# v5.1.0 新增字符串的英文译文（旧 .qm 中没有，按 (context, source) 补入）。
# 其他语言未覆盖的条目回退为原文（中文），与既有策略一致。
EN_SUPPLEMENTS: dict[str, dict[str, str]] = {
    "UiModeDialog": {
        "选择界面运行模式": "Choose UI Mode",
        "两种模式使用同一个 Qt 引擎，无需下载额外组件；之后可在「设置 → 界面效果」随时切换。"
        "低配电脑建议经典模式，想要毛玻璃与更强视觉层次则选视觉增强。": "Both modes run on the same Qt engine with no extra downloads. "
        "You can switch anytime in Settings → UI Effects. Classic is recommended for low-end PCs; choose Visual for acrylic blur and richer depth.",
        "经典模式": "Classic",
        "稳定 · 低占用 · 快速启动": "Stable · low resource · fast start",
        "纯 Qt 自绘，不启用系统毛玻璃合成": "Pure Qt painting, no system acrylic composition",
        "内存与 GPU 占用最低，适合低配机 / 远程桌面": "Lowest memory and GPU usage; ideal for low-end PCs and remote desktop",
        "侧边栏磁贴导航，深色磨砂质感": "Tile navigation with a dark frosted finish",
        "视觉增强": "Visual",
        "毛玻璃 · 磁贴 · 参考 iOS / BakaXL": "Acrylic · tiles · inspired by iOS / BakaXL",
        "调用 Windows 10/11 原生 DWM 亚克力，背景与按钮半透明": "Uses native Windows 10/11 DWM acrylic for translucent background and buttons",
        "保留品牌绿色点缀，卡片层级更接近 iOS 控制中心": "Keeps the brand green accent with iOS Control Center-like depth",
        "支持背景图 + 毛玻璃叠加，可随时关闭": "Supports wallpaper + acrylic overlay, can be disabled anytime",
        "说明：没有改用 Electron / Tauri / Flutter —— 它们的内存占用更高，且无法直接调用"
        " Windows 原生亚克力。当前 Qt + DWM 方案更轻，效果也更接近系统原生。": "Note: Electron / Tauri / Flutter were not adopted: they use more memory and cannot use native Windows acrylic directly. "
        "The current Qt + DWM approach is lighter and closer to the native system look.",
        "返回": "Back",
        "使用此模式": "Use this mode",
    },
    "GalleryPage": {
        "截图图库": "Screenshots",
        "浏览当前实例的 screenshots/，支持预览、打包 zip、打开与删除。": "Browse screenshots/ of the current instance; preview, zip, open and delete.",
        "刷新": "Refresh",
        "打开目录": "Open folder",
        "打包所选": "Zip selected",
        "删除所选": "Delete selected",
        "文件": "File",
        "修改时间": "Modified",
        "大小": "Size",
        "选择一张截图以预览": "Select a screenshot to preview",
        "用默认看图工具打开": "Open with default viewer",
        "还没有可打包的截图。": "No screenshots to zip yet.",
        "导出截图压缩包": "Export screenshots",
        "导出失败": "Export failed",
        "删除截图": "Delete screenshots",
        "确定删除选中的 {0} 个文件？此操作不可撤销。": "Delete the {0} selected file(s)? This cannot be undone.",
        "有 {0} 个文件删除失败。": "{0} file(s) could not be deleted.",
        "无法读取该图片": "Cannot read this image",
        "已导出 {0} 张截图。": "Exported {0} screenshot(s).",
    },
    "CrashReportPage": {
        "崩溃报告": "Crash reports",
        "启动器会把游戏异常退出的日志归档到这里，方便排查或反馈问题。": "Logs from abnormal game exits are archived here for troubleshooting.",
        "刷新": "Refresh",
        "打开目录": "Open folder",
        "复制摘要": "Copy summary",
        "删除所选": "Delete selected",
        "日志文件": "Log file",
        "时间": "Time",
        "大小": "Size",
        "选择一份崩溃日志查看内容…": "Select a crash log to view its contents…",
        "崩溃报告": "Crash reports",
        "删除崩溃报告": "Delete crash reports",
        "确定删除选中的 {0} 份日志？": "Delete the {0} selected log(s)?",
        "有 {0} 个文件删除失败。": "{0} file(s) could not be deleted.",
        "崩溃摘要已复制到剪贴板。": "Crash summary copied to clipboard.",
    },
    "MainWindow": {
        "Minecraft 菜单": "Minecraft menu",
        "单人游戏（存档管理）": "Singleplayer (saves)",
        "多人游戏（服务器列表）": "Multiplayer (servers)",
        "资源包 / 光影包": "Resource / shader packs",
        "截图图库": "Screenshots",
        "崩溃报告": "Crash reports",
        "选项…（设置）": "Options… (Settings)",
        "Java 与运行环境": "Java & runtime",
        "退出启动器": "Quit launcher",
        "截图图库": "Screenshots",
        "崩溃报告": "Crash reports",
        "启动": "Launch",
        "下载": "Download",
        "内容": "Content",
        "联机": "Online",
        "工具": "Tools",
        "设置": "Settings",
        "Mod 关系网": "Mod graph",
        "关系网": "Graph",
    },
    "SettingsPage": {
        "运行模式": "UI mode",
        "经典模式（稳定 · 低占用）": "Classic (stable · low resource)",
        "视觉增强（毛玻璃 · 磁贴）": "Visual (acrylic · tiles)",
        "已切换到视觉增强模式。": "Switched to Visual mode.",
        "已切换到经典模式。": "Switched to Classic mode.",
        "游戏优化": "Game optimization",
        "全部为开关键，改动立即生效，下次启动游戏时应用": "All toggles apply immediately and take effect on the next launch",
        "智能 JVM 参数（自动启用 G1GC 等调优，减少卡顿）": "Smart JVM args (auto G1GC tuning to reduce stutter)",
        "按 Java 版本与内存自动追加 Aikar 风格 G1GC 参数；已自定义 GC 参数时自动跳过。": "Adds Aikar-style G1GC args based on Java version and heap; skipped if you already set GC flags.",
        "大堆预触碰（AlwaysPreTouch，稳定内存占用）": "Pre-touch large heap (AlwaysPreTouch, steadier memory)",
        "仅在分配内存 ≥ 4 GB 时追加，启动稍慢一点，但运行中更少卡顿。": "Applied only when heap ≥ 4 GB; slightly slower startup, fewer in-game hitches.",
        "固定堆大小（-Xms 与 -Xmx 相同）": "Fixed heap (-Xms equals -Xmx)",
        "启动时一次性占满分配内存，避免运行中扩堆；内存紧张的老机器不建议开启。": "Reserves the full heap at startup to avoid runtime growth; not recommended on low-RAM machines.",
        "这些开关只影响启动参数，不改动游戏内的画面设置。\n"
        "老机器建议只开「智能 JVM 参数」，其余按需开启。": "These toggles only affect launch arguments, not in-game video settings.\n"
        "On older PCs, enable only Smart JVM args and turn the rest on as needed.",
        "主题方案": "Theme",
        "导入主题…": "Import theme…",
        "导出模板…": "Export template…",
        "自定义主题是 data/themes/*.json，改完点「导入主题」即可生效；只换主题色时用下方色块。": "Custom themes are data/themes/*.json; import to apply. Use the swatches below to change only the accent color.",
        "界面框架": "UI framework",
        "经典版（Qt，功能完整）": "Classic (Qt, full features)",
        "经典版（Qt，省内存）": "Classic (Qt, low memory)",
        "美化版（pywebview + WebView2）": "Enhanced (pywebview + WebView2)",
        "美化版（pywebview + WebView2，推荐）": "Enhanced (pywebview + WebView2, recommended)",
        "独立版（Electron，自带 Chromium，占用较高）": "Standalone (Electron, bundled Chromium, higher resource use)",
        "经典版 / 美化版 / 独立版可随时切换，三套界面共用同一套启动、下载、账号与联机内核；"
        "修改后重启启动器生效，不会丢失下载进度或设置。"
        "独立版自带 Chromium、不依赖 WebView2，占用更高；单文件版已内置独立版，首次切换会自动释放。": "Classic / Enhanced / Standalone can be switched anytime; all three share the same launch, download, account and multiplayer engine. "
        "Restart the launcher to apply, without losing download progress or settings. "
        "Standalone bundles Chromium and needs no WebView2; the single-file build includes it and extracts on first switch.",
        "未检测到独立版（Electron）。\n"
        "单文件版应已内置独立版，第一次切换会自动释放；"
        "若使用源码运行，请先运行 build_electron.py --all 生成。\n\n"
        "仍要切换吗？": "No standalone (Electron) build was found.\n"
        "The single-file build should include it and extract on first switch.\n"
        "When running from source, run build_electron.py --all first.\n\n"
        "Switch anyway?",
        "美化版用 Edge WebView2（Chromium）渲染玻璃拟态界面。"
        "选定美化版后框架即锁定，不能切回经典版；缺少运行时启动时会引导安装。": "The enhanced UI renders with Edge WebView2 (Chromium) glassmorphism. "
        "Choosing it locks the framework; you cannot switch back to Classic. Missing runtime is handled with an install prompt at startup.",
        "美化版用 Edge WebView2（Chromium）渲染玻璃拟态界面，需重启启动器生效；"
        "选定后框架锁定，不能切回经典版。": "The enhanced UI renders with Edge WebView2 (Chromium); restart to apply. "
        "The framework is locked after choosing; you cannot switch back to Classic.",
        "未检测到 WebView2 Runtime，美化版可能无法启动。\n"
        "选择美化版后会锁定框架、不能切回经典版。仍要切换吗？\n"
        "（启动时会引导安装 WebView2 Runtime）": "WebView2 Runtime was not detected; the enhanced UI may fail to start.\n"
        "Choosing it locks the framework permanently. Switch anyway?\n"
        "(Startup will guide you through installing WebView2 Runtime.)",
        "选择美化版后将锁定界面框架，不能再切回经典版。\n确认继续吗？": "Choosing the enhanced UI locks the framework permanently; you cannot switch back to Classic.\nContinue?",
        "界面框架已保存，重启启动器后生效。": "UI framework saved. Restart the launcher to apply.",
        "毛玻璃强度": "Glass intensity",
    },
    "FrameModeDialog": {
        "选择界面框架": "Choose UI framework",
        "两套界面共用同一套启动、下载、账号与联机内核，功能完全对齐。"
        "只加载所选框架，未选中的模块不会占用内存。"
        "注意：选择美化版后会锁定框架，不能切回经典版。": "Both UIs share the same launch, download, account and multiplayer engine with full feature parity. "
        "Only the selected framework is loaded, so the other does not use memory. "
        "Note: choosing the enhanced UI locks the framework; you cannot switch back to Classic.",
        "经典版 · Qt": "Classic · Qt",
        "稳定 · 省内存 · 功能完整": "Stable · low memory · complete",
        "纯 Qt 绘制，不依赖任何浏览器运行时": "Pure Qt painting with no browser runtime dependency",
        "所有页面（下载、内容、联机、工具、设置）全部可用": "All pages (downloads, content, multiplayer, tools, settings) are available",
        "启动最快，适合 4 代 i5 / 核显等老机器": "Fastest startup; ideal for older PCs",
        "美化版 · pywebview": "Enhanced · pywebview",
        "美化版 · pywebview（推荐）": "Enhanced · pywebview (recommended)",
        "独立版 · Electron": "Standalone · Electron",
        "脱离依赖 · 自带 Chromium · 占用较高": "No runtime dependency · bundled Chromium · higher resource use",
        "自带 Chromium 内核，不依赖 WebView2，装不上运行时的电脑也能用": "Bundles its own Chromium, needs no WebView2, works on PCs where the runtime cannot be installed",
        "界面与美化版完全一致，共用同一套 HTML / CSS / JS": "Identical to the enhanced UI, sharing the same HTML / CSS / JS",
        "缺点：安装包与内存占用都比前两种更高": "Trade-off: larger installer and higher memory use than the other two",
        "独立版已内置，首次切换会自动释放": "Standalone is bundled and extracts on first switch",
        "未检测到独立版（源码运行需先构建，缺失时自动退回）": "No standalone build found (build it when running from source; falls back automatically)",
        "Chromium 渲染 · 玻璃拟态 · 参考主流启动器": "Chromium rendering · glassmorphism · inspired by popular launchers",
        "Edge WebView2（Chromium）渲染，CSS 动画与视觉上限更高": "Rendered by Edge WebView2 (Chromium) with higher CSS/animation ceiling",
        "竖排图标侧栏 + 悬浮玻璃卡片，前端可深度定制主题": "Vertical icon rail + floating glass cards; deeply customizable themes",
        "下载、内容、账号、联机、工具、设置与经典版功能一致": "Downloads, content, accounts, multiplayer, tools and settings match the classic UI",
        "选定后锁定框架，不能切回经典版；缺少运行时按提示安装": "Framework locks after choosing; missing runtime is installed per the prompt",
        "已检测到 WebView2 Runtime": "WebView2 Runtime detected",
        "未检测到 WebView2 Runtime（首次使用会引导安装）": "WebView2 Runtime not found (first use will guide installation)",
        "美化版依赖 WebView2 Runtime。Win10/11 通常随 Edge 预装；缺失时启动器会引导下载并退出，"
        "也可把运行时解包到安装目录 webview2 文件夹使用内置版本。": "The enhanced UI requires WebView2 Runtime. It ships with Edge on most Win10/11 PCs; if missing the launcher guides you to download and then exits. "
        "You can also unpack a runtime into the webview2 folder next to the executable.",
        "默认推荐美化版：Chromium 渲染，视觉与动画更完整；经典版更省内存；"
        "独立版自带 Chromium，完全不依赖系统组件，但占用更高。"
        "三套界面共用同一套启动、下载、账号与联机内核，随时可在设置页切换。": "Enhanced is recommended by default: Chromium rendering with richer visuals and animation. Classic uses less memory. "
        "Standalone bundles Chromium and depends on nothing, at the cost of higher resource use. "
        "All three share the same launch, download, account and multiplayer engine and can be switched in Settings.",
        "美化版依赖 WebView2 Runtime。Win10/11 通常随 Edge 预装；缺失时启动器会引导下载并退出，"
        "也可把运行时解包到安装目录 webview2 文件夹使用内置版本。"
        "独立版不需要 WebView2。单文件版已内置独立版，选中后会释放到 data/electron/app，之后直接复用。": "The enhanced UI requires WebView2 Runtime. It ships with Edge on most Win10/11 PCs; if missing the launcher guides you to download and then exits. "
        "You can also unpack a runtime into the webview2 folder next to the executable. "
        "Standalone needs no WebView2; the single-file build includes it and extracts it to data/electron/app on first use.",
        "使用此框架": "Use this framework",
    },
    "MainWindow": {
        "点击快速切换皮肤": "Click to switch skin",
        "还没有历史皮肤": "No skin history yet",
        "导入新皮肤…": "Import new skin…",
        "打开皮肤库": "Open skin library",
        "选择本地皮肤": "Choose a local skin",
        "已切换到皮肤「{0}」": "Switched to skin {0}",
        "应用皮肤失败：{0}": "Failed to apply skin: {0}",
        "读取皮肤失败：{0}": "Failed to read skin: {0}",
    },
    "ModGraphPage": {
        "Mod 关系网": "Mod graph",
        "把 mods/ 的前置依赖画成一张网：红色=缺少前置，橙色=循环依赖": "Draws mod dependencies as a network: red = missing dependency, orange = dependency cycle",
        "游戏版本": "Game version",
        "重新扫描": "Rescan",
        "适配视图": "Fit view",
        "图例：红色节点 = 缺少前置（没装进 mods/）；橙色边框/连线 = 循环依赖；"
        "滚轮缩放，按住空白处拖动平移": "Legend: red node = missing dependency (not in mods/); orange border/edge = dependency cycle; "
        "scroll to zoom, drag empty space to pan",
        "提示：只解析 jar 内 fabric.mod.json / mods.toml / mcmod.info 的前置信息；解析失败的文件按文件名显示。": "Note: only dependency metadata from fabric.mod.json / mods.toml / mcmod.info is parsed; unreadable files are shown by filename.",
        "未检测到已安装的版本，请先在「下载安装」中安装游戏。": "No installed version found. Install a game version first in Downloads.",
        "正在扫描 {0} …": "Scanning {0} …",
        "{0} 个 Mod": "{0} mods",
        "{0} 条依赖": "{0} dependencies",
        "{0} 个缺少前置": "{0} missing dependencies",
        "{0} 组循环依赖": "{0} dependency cycles",
        "扫描失败：{0}": "Scan failed: {0}",
    },
}


def _str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def extract() -> dict[str, list[str]]:
    """返回 {context: [source, ...]}，按源码出现顺序去重。"""
    messages: dict[str, list[str]] = {}
    seen: set[tuple[str, str]] = set()

    def add(context: str, text: str) -> None:
        if not context or not text:
            return
        key = (context, text)
        if key in seen:
            return
        seen.add(key)
        messages.setdefault(context, []).append(text)

    for path in list((ROOT / "mc_launcher").rglob("*.py")) + [ROOT / "run.py"]:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        # 每个类节点记录类名，用于 self.tr 的上下文
        parents: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent

        def context_of(node: ast.AST) -> str:
            current = node
            while current is not None:
                if isinstance(current, ast.ClassDef):
                    return current.name
                current = parents.get(current)
            return ""

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name) and func.id == "t" and len(node.args) >= 2:
                ctx = _str(node.args[0])
                text = _str(node.args[1])
                if ctx and text:
                    add(ctx, text)
            elif isinstance(func, ast.Attribute) and func.attr == "tr" and node.args:
                text = _str(node.args[0])
                if text:
                    add(context_of(node), text)
            elif isinstance(func, ast.Attribute) and func.attr == "translate" and len(node.args) >= 2:
                ctx = _str(node.args[0])
                text = _str(node.args[1])
                if ctx and text:
                    add(ctx, text)
    return messages


def build_ts(messages: dict[str, list[str]]) -> dict[str, dict[tuple[str, str], str]]:
    """用现有 .qm 查回译文，返回 {lang: {(context, source): translation}}。"""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QCoreApplication, QTranslator

    app = QCoreApplication.instance() or QCoreApplication([])
    recovered: dict[str, dict[tuple[str, str], str]] = {}
    for lang in LANGUAGES:
        qm_file = TRANSLATIONS / f"mikancl_{lang}.qm"
        mapping: dict[tuple[str, str], str] = {}
        translator = QTranslator(app)
        if qm_file.is_file() and translator.load(str(qm_file)):
            app.installTranslator(translator)
            for context, sources in messages.items():
                for source in sources:
                    translated = translator.translate(context, source, None)
                    if translated and translated != source:
                        mapping[(context, source)] = translated
            app.removeTranslator(translator)
        recovered[lang] = mapping
    return recovered


def write_ts(lang: str, messages: dict[str, list[str]], mapping: dict[tuple[str, str], str]) -> Path:
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<!DOCTYPE TS>',
        f'<TS version="2.1" language="{lang}">',
    ]
    for context, sources in messages.items():
        lines.append("    <context>")
        lines.append(f"        <name>{escape(context)}</name>")
        for source in sources:
            lines.append("        <message>")
            lines.append(f"            <source>{escape(source)}</source>")
            text = mapping.get((context, source), source)
            lines.append(f"            <translation>{escape(text)}</translation>")
            lines.append("        </message>")
        lines.append("    </context>")
    lines.append("</TS>")
    target = TRANSLATIONS / f"mikancl_{lang}.ts"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def main() -> int:
    messages = extract()
    total = sum(len(items) for items in messages.values())
    print(f"提取到 {total} 条字符串，{len(messages)} 个上下文")
    recovered = build_ts(messages)
    for context, mapping in EN_SUPPLEMENTS.items():
        for source, text in mapping.items():
            recovered["en_US"].setdefault((context, source), text)
    for lang in LANGUAGES:
        ts_file = write_ts(lang, messages, recovered[lang])
        print(f"写入 {ts_file.name}：{len(recovered[lang])} 条已有译文")

    import shutil

    lrelease = shutil.which("pyside6-lrelease") or str(
        Path(sys.executable).parent / "Scripts" / "pyside6-lrelease.exe"
    )
    if Path(lrelease).is_file():
        subprocess.call(
            [str(lrelease)]
            + [str(TRANSLATIONS / f"mikancl_{lang}.ts") for lang in LANGUAGES]
        )
        print("已重新编译 .qm")
    else:
        print("未找到 pyside6-lrelease，跳过 .qm 编译")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
