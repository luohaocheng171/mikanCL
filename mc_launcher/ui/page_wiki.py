"""教程中心：内置 Markdown Wiki，支持搜索与按标题浏览。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..config import WIKI_DIR
from ..context import AppContext
from ..i18n import t
from .widgets import Card, page_header
from .dialog_nbt import NbtEditorDialog

# 内置教程正文：首次运行时写入 WIKI_DIR，打包时也不会遗漏
DEFAULT_WIKI: dict[str, str] = {
    "01_install_forge.md": """# 安装 Forge

## 前置
- 已安装对应版本的 Minecraft 原版
- 已安装 Java 8 / 17 / 21（按 MC 版本选择）

## 步骤
1. 打开「下载安装」页
2. 选择目标 Minecraft 版本
3. 在"Mod 加载器"里选 Forge
4. 选择 Forge 版本（推荐最新的稳定版）
5. 点击"安装所选版本"

## 常见问题
- 卡在"下载安装器"：网络问题，去设置里启用 BMCLAPI 镜像
- 安装器退出码非 0：通常是 Java 版本不匹配，检查 Java
- 找不到生成的版本：检查 `versions/<版本ID>/<版本ID>.json` 是否存在
""",
    "02_install_fabric.md": """# 安装 Fabric

## 与 Forge 的区别
- Fabric 更轻量，启动更快
- Fabric 的 Mod 生态更偏向"新版本 + 轻改"
- 大部分优化类 Mod（钠、锂）都是 Fabric 优先

## 步骤
1. 打开「下载安装」页
2. 选择 Minecraft 版本
3. 加载器选 Fabric
4. 安装（会自动附带 Fabric API）

## 注意
- Fabric API 是大部分 Fabric Mod 的前置，安装 Fabric 时已自动附带
- Quilt 是 Fabric 的衍生，大部分 Fabric Mod 能在 Quilt 上跑
""",
    "03_install_shader.md": """# 安装光影

## 前置
- 加载器：Fabric 需装 Iris，Forge 需装 Oculus
- 推荐：OptiFine（旧版本）或 Iris + Sodium（新版本）

## 步骤
1. 在「内容中心」搜 "Iris" 或 "Oculus"，安装到实例
2. 把光影包（.zip）放进 `shaderpacks/` 目录
3. 启动游戏，选项 → 视频设置 → 光影 → 选择光影包

## 性能提示
- 光影很吃显卡，集成显卡慎用
- 启动预检会在检测到"核显 + 光影"时给出警告
""",
    "04_memory_issue.md": """# 内存不足

## 症状
- 游戏卡顿、掉帧
- 日志里出现 OutOfMemoryError
- 启动预检提示"分配内存超过物理内存 70%"

## 解决方案
1. 打开「版本设置」→「游戏设置」
2. 把"最大内存"调到合理值：
   - 原版：2-4 GB
   - 轻量 Mod：4-6 GB
   - 大型整合包：6-8 GB
3. 不要超过物理内存的 70%

## 注意
- 内存不是越大越好，过大会拖慢系统
- 32 位 Java 最多只能用 1.5 GB，请确认用 64 位
""",
    "05_mod_conflict.md": """# Mod 冲突

## 症状
- 游戏启动崩溃
- 日志里出现 NoSuchMethodError / ClassNotFoundException
- 启动预检提示"检测到 N 个 Mod 冲突"

## 排查步骤
1. 打开「版本设置」→「模组管理」
2. 看红色标记的 Mod（冲突项）
3. 常见冲突：
   - 同一个 Mod 装了多个版本（重复 modid）
   - 缺少前置（missing dependency）
   - 版本范围不满足（version mismatch）

## 解决方案
- 重复 modid：禁用其中一个
- 缺少前置：去内容中心搜前置名，安装
- 版本不满足：升级或降级对应 Mod
""",
    "06_java_version.md": """# Java 版本选择

## 对照表

| Minecraft 版本 | Java 版本 |
|---|---|
| 1.0 - 1.16.5 | Java 8 |
| 1.17 - 1.20.4 | Java 17 |
| 1.20.5+ | Java 21 |

## 检查当前 Java
- 设置页 → Java 运行时，会列出所有检测到的 Java
- 双击一行可设为默认

## 安装 Java
- 打开「Java 中心」，选发行版和主版本，下载
- 推荐 Adoptium Temurin（社区最广）
""",
    "07_nbt_editor.md": """# NBT 编辑器使用

## 什么是 NBT
NBT（Named Binary Tag）是 Minecraft 的存档数据格式，`level.dat`、`playerdata/*.dat` 都是 NBT。

## 入口
- 教程中心顶部"🔧 打开 NBT 编辑器"
- 版本设置 → 版本管理 → "编辑 level.dat"
- 主页工具区的"NBT 编辑器…"

## 常见用途
- 改世界种子：编辑 `level.dat` 的 `Data.WorldGenSettings.seed`
- 改游戏模式：编辑 `playerdata/<uuid>.dat` 的 `playerGameType`
- 改坐标：编辑 `Pos` 数组

## 操作说明
- 双击"值"列可编辑叶子节点（字符串 / 数字）
- 右键可"添加子标签"或"删除标签"（根节点不可删除）
- 复合类型（TAG_Compound）只能展开，不能直接改值

## 安全提示
- 首次保存会在同目录自动生成 `.bak` 备份
- 不确定的字段不要动
- 改坏了可以从备份恢复
""",
    "08_offline_skin.md": """# 离线皮肤

## 原理
离线账号没有 Mojang 皮肤服务，需要用 CustomSkinLoader Mod + 本地皮肤文件模拟。

## 步骤
1. 在「内容中心」搜 "CustomSkinLoader"，安装到实例
2. 打开「账号管理」→ 选中离线账号 → "使用本地皮肤…"
3. 选一张 64×64 或 64×32 的 PNG
4. 启动游戏，CustomSkinLoader 会自动应用

## 注意
- 皮肤文件会写入 `CustomSkinLoader/LocalSkin/skins/<玩家名>.png`
- 只有装了 CustomSkinLoader 才会生效
- 正版账号不需要这个，直接上传皮肤即可
""",
}


def ensure_default_wiki() -> None:
    """WIKI_DIR 为空或缺少内置教程时补齐默认内容（不覆盖用户自定义文件）。"""
    try:
        WIKI_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    for name, content in DEFAULT_WIKI.items():
        target = WIKI_DIR / name
        if target.exists():
            continue
        try:
            target.write_text(content, encoding="utf-8")
        except OSError:
            continue


def _titles_from_file(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if text.startswith("#"):
                return text.lstrip("#").strip()
    except OSError:
        pass
    return path.stem


class WikiPage(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self._entries: list[tuple[Path, str, str]] = []
        self._build()
        self.refresh()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(12)

        header, header_layout = page_header(
            self.tr("教程中心"), self.tr("内置攻略 Wiki：安装、排错与 NBT 编辑说明")
        )
        nbt_button = QPushButton(self.tr("🔧 打开 NBT 编辑器"))
        nbt_button.setObjectName("Chip")
        nbt_button.clicked.connect(self._open_nbt_editor)
        header_layout.addWidget(nbt_button)
        outer.addWidget(header)

        card = Card(margins=14, spacing=10)
        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(self.tr("搜索教程标题或内容…"))
        self.search_edit.textChanged.connect(self._apply_filter)
        search_row.addWidget(self.search_edit, 1)
        self.count_label = QLabel("")
        self.count_label.setObjectName("Tiny")
        search_row.addWidget(self.count_label)
        card.body.addLayout(search_row)

        body = QHBoxLayout()
        body.setSpacing(12)
        self.catalog = QListWidget()
        self.catalog.setFixedWidth(240)
        self.catalog.currentItemChanged.connect(self._on_item_changed)
        body.addWidget(self.catalog)

        self.browser = QTextBrowser()
        self.browser.setOpenLinks(False)
        self.browser.anchorClicked.connect(self._on_anchor_clicked)
        body.addWidget(self.browser, 1)
        card.body.addLayout(body, 1)

        outer.addWidget(card, 1)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        ensure_default_wiki()
        entries: list[tuple[Path, str, str]] = []
        try:
            files = sorted(WIKI_DIR.glob("*.md"))
        except OSError:
            files = []
        for path in files:
            title = _titles_from_file(path)
            try:
                content = path.read_text(encoding="utf-8")
            except OSError:
                content = ""
            entries.append((path, title, content))
        self._entries = entries
        self._rebuild_catalog()

    def _rebuild_catalog(self) -> None:
        keep = self.catalog.currentRow()
        self.catalog.blockSignals(True)
        self.catalog.clear()
        for index, (_path, title, _content) in enumerate(self._entries):
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, index)
            self.catalog.addItem(item)
        self.catalog.blockSignals(False)
        self._apply_filter(self.search_edit.text())
        if self._entries:
            row = keep if 0 <= keep < self.catalog.count() else 0
            self.catalog.setCurrentRow(row)

    def _apply_filter(self, text: str) -> None:
        needle = (text or "").strip().lower()
        visible = 0
        for index in range(self.catalog.count()):
            item = self.catalog.item(index)
            data_index = item.data(Qt.UserRole)
            _path, title, content = self._entries[data_index]
            match = (
                not needle
                or needle in title.lower()
                or needle in content.lower()
            )
            item.setHidden(not match)
            if match:
                visible += 1
        self.count_label.setText(t("WikiPage", "{0} / {1} 篇", visible, len(self._entries)))
        if visible == 0:
            self.browser.setHtml(
                f"<p style='color:#8aa192'>{self.tr('没有匹配的教程')}</p>"
            )

    def _on_item_changed(self, current: QListWidgetItem, _previous) -> None:
        if current is None:
            return
        data_index = current.data(Qt.UserRole)
        if not isinstance(data_index, int) or not (0 <= data_index < len(self._entries)):
            return
        _path, _title, content = self._entries[data_index]
        self.browser.setMarkdown(content)

    def _on_anchor_clicked(self, url: QUrl) -> None:
        if url.scheme() in ("http", "https"):
            QDesktopServices.openUrl(url)
            return
        fragment = url.fragment()
        if fragment:
            self.browser.scrollToAnchor(fragment)
            return
        target = url.toString()
        if target:
            QDesktopServices.openUrl(QUrl(target))

    def _open_nbt_editor(self) -> None:
        dialog = NbtEditorDialog(self.ctx, self)
        dialog.exec()

    # ------------------------------------------------------------------
    def shutdown(self) -> None:
        """教程页没有后台任务，保留接口供 MainWindow 统一调用。"""
