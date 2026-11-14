"""经典版「创世神面板」：离线深度编辑存档的五页界面。

所有业务判断都在 ``creator_service``，这里只负责收集表单、展示预览
和确认高危操作，保证 Qt 与 Web/Electron 的行为一致。
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..creator_schema import ENCHANTMENT_NAMES, VanillaCaps
from ..creator_service import CreatorError, CreatorService, PreviewExpired
from ..world_convert import COMMON_TARGETS


def _item_error(message: str) -> None:
    QMessageBox.warning(None, "创世神面板", str(message))


class ItemPicker(QDialog):
    """扫描到的物品 ID 选择器，支持按 ID / 名称过滤。"""

    def __init__(self, items: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择物品 ID")
        self.resize(560, 620)
        self._items = items
        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索 ID 或名称，例如 diamond / 钻石")
        layout.addWidget(self.search)
        self.list = QListWidget()
        layout.addWidget(self.list, 1)
        self.hint = QLabel("")
        self.hint.setObjectName("Muted")
        layout.addWidget(self.hint)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.search.textChanged.connect(self._reload)
        self.list.itemDoubleClicked.connect(lambda _item: self.accept())
        self._reload()

    def _reload(self) -> None:
        text = self.search.text().strip().lower()
        self.list.clear()
        shown = 0
        for item in self._items:
            if text and text not in item["id"].lower() and text not in str(item.get("name", "")).lower():
                continue
            node = QListWidgetItem(f"{item['id']}  ·  {item.get('name', '')}")
            node.setData(Qt.UserRole, item["id"])
            self.list.addItem(node)
            shown += 1
            if shown >= 800:
                break
        self.hint.setText(f"共 {len(self._items)} 个候选，当前显示 {shown} 个")

    def selected_id(self) -> str:
        node = self.list.currentItem()
        return str(node.data(Qt.UserRole)) if node else ""


class ItemEditor(QDialog):
    """单个物品：ID、槽位、数量、附魔与原始 NBT。"""

    def __init__(self, entry: dict, caps: dict, era: str, picker_items, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑物品")
        self.resize(620, 560)
        self.entry = dict(entry)
        self.caps = caps
        self.era = era
        self.items = picker_items
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.id_field = QLineEdit(str(entry.get("id", "")))
        self.id_field.setPlaceholderText("minecraft:diamond_sword")
        pick = QPushButton("扫描物品")
        pick.clicked.connect(self._pick)
        id_row = QHBoxLayout()
        id_row.addWidget(self.id_field, 1)
        id_row.addWidget(pick)
        form.addRow("物品 ID", id_row)
        self.slot = QSpinBox()
        self.slot.setRange(0, 255)
        self.slot.setValue(int(entry.get("slot", 0)))
        form.addRow("槽位", self.slot)
        self.count = QSpinBox()
        self.count.setRange(0, max(1, int(caps.get("max_count", 64))))
        self.count.setValue(min(int(entry.get("count", 1)), self.count.maximum()))
        form.addRow(f"数量（上限 {caps.get('max_count')}）", self.count)
        self.damage = QSpinBox()
        self.damage.setRange(0, 2**31 - 1)
        self.damage.setValue(int(entry.get("damage", 0) or 0))
        form.addRow("损伤值", self.damage)
        self.attrs = QLineEdit(
            ", ".join(
                f"{item.get('name', '')}:{item.get('amount', 0)}:{item.get('operation', 'add_value')}"
                for item in entry.get("attributes", [])
            )
        )
        self.attrs.setPlaceholderText(
            "minecraft:generic.attack_damage:100:add_value, minecraft:generic.armor:500:add_value"
        )
        form.addRow("属性修饰符（属性:数值:运算）", self.attrs)
        self.enchants = QLineEdit(
            ",".join(f"{item['id']}:{item['level']}" for item in entry.get("enchantments", []))
        )
        self.enchants.setPlaceholderText("sharpness:255,unbreaking:3")
        form.addRow(f"附魔（≤{caps.get('enchant_level', 255)} 级）", self.enchants)
        layout.addLayout(form)
        hint = QLabel("附魔格式：id:等级，多项用逗号分隔；命名空间可省略。")
        hint.setObjectName("Muted")
        layout.addWidget(hint)
        layout.addWidget(QLabel("原始 NBT（可选，带类型 JSON）"))
        self.raw = QPlainTextEdit()
        self.raw.setPlaceholderText('{"tag":10,"value":{"display":{"tag":10,"value":{...}}}}')
        if entry.get("tag_json"):
            self.raw.setPlainText(json.dumps(entry["tag_json"], ensure_ascii=False, indent=2))
        layout.addWidget(self.raw, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _pick(self) -> None:
        dialog = ItemPicker(self.items, self)
        if dialog.exec() == QDialog.Accepted and dialog.selected_id():
            self.id_field.setText(dialog.selected_id())

    def _accept(self) -> None:
        if not self.id_field.text().strip():
            QMessageBox.warning(self, "创世神面板", "物品 ID 不能为空")
            return
        enchantments = []
        for chunk in self.enchants.text().split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            if ":" not in chunk:
                QMessageBox.warning(self, "创世神面板", f"附魔「{chunk}」缺少等级")
                return
            name, level = chunk.rsplit(":", 1)
            try:
                level_value = int(level)
            except ValueError:
                QMessageBox.warning(self, "创世神面板", f"附魔「{chunk}」的等级不是整数")
                return
            if level_value < 0 or level_value > int(self.caps.get("enchant_level", 255)):
                QMessageBox.warning(
                    self,
                    "创世神面板",
                    f"附魔等级必须在 0 - {self.caps.get('enchant_level', 255)} 之间",
                )
                return
            enchantments.append({"id": name.strip(), "level": level_value})
        tag_json = None
        if self.raw.toPlainText().strip():
            try:
                tag_json = json.loads(self.raw.toPlainText())
            except ValueError as exc:
                QMessageBox.warning(self, "创世神面板", f"原始 NBT 不是合法 JSON：{exc}")
                return
        attributes = []
        buffer = ""
        depth = 0
        chunks = []
        for char in self.attrs.text():
            if char == "[":
                depth += 1
            elif char == "]":
                depth -= 1
            if char == "," and depth <= 0:
                chunks.append(buffer)
                buffer = ""
            else:
                buffer += char
        chunks.append(buffer)
        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue
            parts = chunk.rsplit(":", 2)
            if len(parts) < 2:
                QMessageBox.warning(self, "创世神面板", f"属性修饰符「{chunk}」缺少数值")
                return
            name = parts[0].strip()
            try:
                amount = float(parts[1])
            except ValueError:
                QMessageBox.warning(self, "创世神面板", f"属性修饰符「{chunk}」的数值不是数字")
                return
            operation = parts[2].strip() if len(parts) > 2 else "add_value"
            attributes.append({"name": name, "amount": amount, "operation": operation, "slot": "any"})
        self.entry = {
            "id": self.id_field.text().strip(),
            "slot": self.slot.value(),
            "count": self.count.value(),
            "damage": self.damage.value(),
            "enchantments": enchantments,
            "attributes": attributes,
            "tag_json": tag_json,
        }
        self.accept()


class CreatorPage(QWidget):
    """五子页：状态 / 背包 / 能力 / 世界 / 工具。"""

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.state: dict | None = None
        self.service: CreatorService | None = None
        self.caps: dict = {
            "health": VanillaCaps.health(),
            "xp_level": VanillaCaps.xp_level(),
            "enchant_level": VanillaCaps.enchant_level(),
            "max_count": 64,
            "border_size": VanillaCaps.world_border_size(),
            "random_tick_speed": VanillaCaps.random_tick_speed(),
        }
        self._items: list[dict] = []
        self._ender_items: list[dict] = []
        self._catalog: list[dict] = []
        self._build()
        self.refresh()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)

        title = QLabel("创世神面板")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        warning = QLabel(
            "离线深度编辑：请先完全关闭游戏。数值上限按原版理论值放开，"
            "保存前会强制备份；写入失败会按事务回滚。"
        )
        warning.setWordWrap(True)
        warning.setObjectName("Muted")
        layout.addWidget(warning)

        top = QHBoxLayout()
        self.world_combo = QComboBox()
        self.world_combo.setMinimumWidth(320)
        self.world_combo.currentIndexChanged.connect(self._load_world)
        reload_button = QPushButton("刷新存档")
        reload_button.clicked.connect(self.refresh)
        self.player_combo = QComboBox()
        self.player_combo.currentIndexChanged.connect(self._load_player)
        top.addWidget(QLabel("存档"))
        top.addWidget(self.world_combo, 1)
        top.addWidget(QLabel("玩家"))
        top.addWidget(self.player_combo)
        top.addWidget(reload_button)
        layout.addLayout(top)

        self.meta = QLabel("")
        self.meta.setObjectName("Muted")
        self.meta.setWordWrap(True)
        layout.addWidget(self.meta)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_status(), "状态")
        self.tabs.addTab(self._build_inventory(), "背包")
        self.tabs.addTab(self._build_ability(), "能力")
        self.tabs.addTab(self._build_world(), "世界")
        self.tabs.addTab(self._build_tools(), "工具")
        layout.addWidget(self.tabs, 1)

        footer = QHBoxLayout()
        self.status = QLabel("就绪")
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        save_button = QPushButton("预览并保存")
        save_button.setObjectName("PrimaryButton")
        save_button.clicked.connect(self._save)
        footer.addWidget(self.status, 1)
        footer.addWidget(save_button)
        layout.addLayout(footer)

    def _build_status(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        pos_row = QHBoxLayout()
        self.pos_x = QDoubleSpinBox()
        self.pos_y = QDoubleSpinBox()
        self.pos_z = QDoubleSpinBox()
        for field in (self.pos_x, self.pos_y, self.pos_z):
            field.setRange(-30000000.0, 30000000.0)
            field.setDecimals(3)
            pos_row.addWidget(field)
        form.addRow("坐标 X / Y / Z", pos_row)
        self.safe_tp = QCheckBox("安全传送（按目标 X/Z 的最高方块落点提示）")
        form.addRow("", self.safe_tp)
        self.health = QDoubleSpinBox()
        self.health.setRange(0.0, VanillaCaps.health())
        self.health.setDecimals(2)
        form.addRow(f"生命（原版上限 {VanillaCaps.health():g}）", self.health)
        self.food = QDoubleSpinBox()
        self.food.setRange(0.0, VanillaCaps.saturation())
        form.addRow("饱和度", self.food)
        self.food_level = QSpinBox()
        self.food_level.setRange(0, 20)
        form.addRow("饥饿值 foodLevel（原版上限 20）", self.food_level)
        self.xp_level = QSpinBox()
        self.xp_level.setRange(0, VanillaCaps.xp_level())
        form.addRow("经验等级", self.xp_level)
        self.game_mode = QComboBox()
        for index, label in enumerate(("生存", "创造", "冒险", "旁观")):
            self.game_mode.addItem(f"{index} · {label}", index)
        form.addRow("游戏模式", self.game_mode)
        self.dimension = QLineEdit()
        self.dimension.setPlaceholderText("minecraft:overworld / 模组维度")
        form.addRow("维度", self.dimension)
        layout.addLayout(form)
        layout.addStretch(1)
        return page

    def _build_inventory(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        row = QHBoxLayout()
        add = QPushButton("添加物品")
        edit = QPushButton("编辑选中")
        remove = QPushButton("删除选中")
        scan = QPushButton("扫描物品 ID")
        add.clicked.connect(lambda: self._edit_item(-1))
        edit.clicked.connect(lambda: self._edit_item(self.inventory.currentRow()))
        remove.clicked.connect(self._remove_item)
        scan.clicked.connect(self._scan_items)
        for widget in (add, edit, remove, scan):
            row.addWidget(widget)
        row.addStretch(1)
        layout.addLayout(row)
        self.inventory = QTableWidget(0, 5)
        self.inventory.setHorizontalHeaderLabels(["槽位", "物品 ID", "数量", "附魔", "属性 / Raw"])
        self.inventory.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.inventory.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.inventory.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.inventory.doubleClicked.connect(lambda _index: self._edit_item(self.inventory.currentRow()))
        layout.addWidget(self.inventory, 1)
        hint = QLabel("槽位 0-35 为主背包与快捷栏，36-39 为护甲，40 为副手。")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        ender_header = QHBoxLayout()
        ender_header.addWidget(QLabel("末影箱（槽位 0-26）"), 1)
        ender_add = QPushButton("添加末影箱物品")
        ender_edit = QPushButton("编辑选中")
        ender_remove = QPushButton("删除选中")
        ender_add.clicked.connect(lambda: self._edit_ender_item(-1))
        ender_edit.clicked.connect(lambda: self._edit_ender_item(self.ender.currentRow()))
        ender_remove.clicked.connect(self._remove_ender_item)
        for widget in (ender_add, ender_edit, ender_remove):
            ender_header.addWidget(widget)
        layout.addLayout(ender_header)
        self.ender = QTableWidget(0, 5)
        self.ender.setHorizontalHeaderLabels(["槽位", "物品 ID", "数量", "附魔", "属性"])
        self.ender.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.ender.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.ender.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ender.doubleClicked.connect(lambda _index: self._edit_ender_item(self.ender.currentRow()))
        layout.addWidget(self.ender, 1)
        return page

    def _build_ability(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        attributes_box = QGroupBox("Attributes / 修饰符")
        attributes_layout = QVBoxLayout(attributes_box)
        self.attributes = QTableWidget(0, 3)
        self.attributes.setHorizontalHeaderLabels(["属性名", "基础值", "修饰符（数值:运算，分号分隔）"])
        self.attributes.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.attributes.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        attributes_layout.addWidget(self.attributes)
        attr_row = QHBoxLayout()
        attr_add = QPushButton("添加属性")
        attr_remove = QPushButton("删除属性")
        attr_add.clicked.connect(self._add_attribute)
        attr_remove.clicked.connect(lambda: self.attributes.removeRow(self.attributes.currentRow()))
        attr_row.addWidget(attr_add)
        attr_row.addWidget(attr_remove)
        attr_row.addStretch(1)
        attributes_layout.addLayout(attr_row)
        layout.addWidget(attributes_box)

        effects_box = QGroupBox("状态效果")
        effects_layout = QVBoxLayout(effects_box)
        self.effects = QTableWidget(0, 4)
        self.effects.setHorizontalHeaderLabels(["效果 ID", "等级(Amplifier)", "持续时间(刻)", "粒子"])
        self.effects.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        effects_layout.addWidget(self.effects)
        effect_row = QHBoxLayout()
        effect_add = QPushButton("添加效果")
        effect_remove = QPushButton("删除效果")
        effect_add.clicked.connect(self._add_effect)
        effect_remove.clicked.connect(lambda: self.effects.removeRow(self.effects.currentRow()))
        effect_row.addWidget(effect_add)
        effect_row.addWidget(effect_remove)
        effect_row.addStretch(1)
        effects_layout.addLayout(effect_row)
        layout.addWidget(effects_box, 1)
        return page

    def _build_world(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        self.time = QLineEdit()
        self.time.setPlaceholderText("游戏时间（Long，可大于 24000）")
        form.addRow("世界时间", self.time)
        self.day_time = QLineEdit()
        self.day_time.setPlaceholderText("白天时间（决定昼夜）")
        form.addRow("DayTime", self.day_time)
        self.weather = QComboBox()
        self.weather.addItem("晴天", "clear")
        self.weather.addItem("下雨", "rain")
        self.weather.addItem("雷暴", "thunder")
        form.addRow("天气", self.weather)
        self.border_size = QDoubleSpinBox()
        self.border_size.setRange(1.0, VanillaCaps.world_border_size())
        self.border_size.setDecimals(2)
        form.addRow("世界边界尺寸", self.border_size)
        border_row = QHBoxLayout()
        self.border_x = QDoubleSpinBox()
        self.border_z = QDoubleSpinBox()
        for field in (self.border_x, self.border_z):
            field.setRange(-3.0e7, 3.0e7)
            field.setDecimals(2)
            border_row.addWidget(field)
        form.addRow("边界中心 X / Z", border_row)
        spawn_row = QHBoxLayout()
        self.spawn_x = QSpinBox()
        self.spawn_y = QSpinBox()
        self.spawn_z = QSpinBox()
        for field in (self.spawn_x, self.spawn_y, self.spawn_z):
            field.setRange(-30000000, 30000000)
            spawn_row.addWidget(field)
        form.addRow("出生点 X / Y / Z", spawn_row)
        layout.addLayout(form)

        rules_box = QGroupBox("GameRules")
        rules_layout = QFormLayout(rules_box)
        self.rule_keep_inventory = QCheckBox("死亡保留物品")
        self.rule_daylight = QCheckBox("昼夜循环")
        self.rule_mob_spawning = QCheckBox("自然生成怪物")
        self.rule_fire_tick = QCheckBox("火焰蔓延")
        self.rule_weather_cycle = QCheckBox("天气循环")
        self.rule_mob_loot = QCheckBox("生物掉落物")
        self.rule_tile_drops = QCheckBox("方块掉落物")
        self.rule_mob_griefing = QCheckBox("生物破坏方块")
        self.rule_natural_regen = QCheckBox("自然回血")
        self.rule_show_coordinates = QCheckBox("显示坐标")
        self.rule_announce_advancements = QCheckBox("广播成就")
        for widget in (
            self.rule_keep_inventory,
            self.rule_daylight,
            self.rule_mob_spawning,
            self.rule_fire_tick,
            self.rule_weather_cycle,
            self.rule_mob_loot,
            self.rule_tile_drops,
            self.rule_mob_griefing,
            self.rule_natural_regen,
            self.rule_show_coordinates,
            self.rule_announce_advancements,
        ):
            rules_layout.addRow(widget)
        self.random_tick = QSpinBox()
        self.random_tick.setRange(0, VanillaCaps.random_tick_speed())
        rules_layout.addRow("randomTickSpeed（原版默认 3）", self.random_tick)
        layout.addWidget(rules_box)
        layout.addStretch(1)
        return page

    def _build_tools(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        advance_box = QGroupBox("成就树")
        advance_layout = QVBoxLayout(advance_box)
        adv_head = QHBoxLayout()
        self.advance_info = QLabel("未加载")
        self.advance_info.setObjectName("Muted")
        select_all = QPushButton("全选")
        select_none = QPushButton("清空选择")
        advance_button = QPushButton("标记所选完成")
        select_all.clicked.connect(lambda: self._check_advancements(True))
        select_none.clicked.connect(lambda: self._check_advancements(False))
        advance_button.clicked.connect(self._complete_advancements)
        adv_head.addWidget(self.advance_info, 1)
        for widget in (select_all, select_none, advance_button):
            adv_head.addWidget(widget)
        advance_layout.addLayout(adv_head)
        self.advance_list = QListWidget()
        advance_layout.addWidget(self.advance_list)
        layout.addWidget(advance_box)

        convert_box = QGroupBox("旧格式转换（升级为 Anvil）")
        convert_layout = QVBoxLayout(convert_box)
        convert_row = QHBoxLayout()
        self.convert_source = QLineEdit()
        self.convert_source.setPlaceholderText("Classic / Indev / Alpha / McRegion 存档目录或 level.dat")
        self.convert_target = QComboBox()
        for version in COMMON_TARGETS:
            self.convert_target.addItem(version, version)
        self.convert_era = QComboBox()
        for era_id, label in (
            ("auto", "自动检测"),
            ("classic", "Classic 2009"),
            ("indev", "Indev 0.31"),
            ("alpha", "Infdev / Alpha / Beta 1.2"),
            ("mcregion", "Beta 1.3 – 1.2.5"),
            ("anvil", "Anvil（1.2+）"),
        ):
            self.convert_era.addItem(label, era_id)
        convert_button = QPushButton("开始转换")
        convert_button.clicked.connect(self._convert_world)
        convert_row.addWidget(self.convert_source, 2)
        convert_row.addWidget(self.convert_target)
        convert_row.addWidget(self.convert_era)
        convert_row.addWidget(convert_button)
        convert_layout.addLayout(convert_row)
        convert_hint = QLabel("1.13+ 目标会先输出 1.12.2 结构，由游戏本体在首次打开时完成扁平化升级。")
        convert_hint.setObjectName("Muted")
        convert_hint.setWordWrap(True)
        convert_layout.addWidget(convert_hint)
        layout.addWidget(convert_box)

        ops_box = QGroupBox("OP 管理（服务端 ops.json）")
        ops_layout = QVBoxLayout(ops_box)
        ops_row = QHBoxLayout()
        self.ops_dir = QLineEdit()
        self.ops_dir.setPlaceholderText("选择服务端目录（包含 ops.json）")
        browse = QPushButton("浏览")
        browse.clicked.connect(self._pick_ops_dir)
        load_ops = QPushButton("读取")
        load_ops.clicked.connect(self._load_ops)
        save_ops = QPushButton("保存 OP")
        save_ops.clicked.connect(self._save_ops)
        for widget in (self.ops_dir, browse, load_ops, save_ops):
            ops_row.addWidget(widget, 1 if widget is self.ops_dir else 0)
        ops_layout.addLayout(ops_row)
        self.ops_table = QTableWidget(0, 3)
        self.ops_table.setHorizontalHeaderLabels(["UUID", "名称", "等级 0-4"])
        self.ops_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        ops_layout.addWidget(self.ops_table)
        layout.addWidget(ops_box)

        region_box = QGroupBox("全局方块替换")
        region_layout = QVBoxLayout(region_box)
        region_row = QHBoxLayout()
        self.old_block = QLineEdit()
        self.old_block.setPlaceholderText("原方块：minecraft:stone 或 1")
        self.new_block = QLineEdit()
        self.new_block.setPlaceholderText("目标方块：minecraft:diamond_block 或 57")
        preview_button = QPushButton("预扫描")
        apply_button = QPushButton("执行替换")
        preview_button.clicked.connect(self._preview_region)
        apply_button.clicked.connect(self._apply_region)
        region_row.addWidget(self.old_block)
        region_row.addWidget(self.new_block)
        region_row.addWidget(preview_button)
        region_row.addWidget(apply_button)
        region_layout.addLayout(region_row)
        self.region_info = QLabel("先预扫描确认替换数量，再执行。")
        self.region_info.setObjectName("Muted")
        self.region_info.setWordWrap(True)
        region_layout.addWidget(self.region_info)
        layout.addWidget(region_box)

        backup_box = QGroupBox("备份")
        backup_layout = QHBoxLayout(backup_box)
        self.backup_info = QLabel("")
        self.backup_info.setObjectName("Muted")
        self.backup_info.setWordWrap(True)
        open_backup = QPushButton("打开备份目录")
        open_backup.clicked.connect(self._open_backup_dir)
        backup_layout.addWidget(self.backup_info, 1)
        backup_layout.addWidget(open_backup)
        layout.addWidget(backup_box)
        layout.addStretch(1)
        return page

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        self.world_combo.blockSignals(True)
        self.world_combo.clear()
        game_dir = self.ctx.config.game_path
        saves = game_dir / "saves"
        if saves.is_dir():
            for entry in sorted(saves.iterdir(), key=lambda item: item.name.lower()):
                if (entry / "level.dat").is_file():
                    self.world_combo.addItem(entry.name, str(entry))
        self.world_combo.blockSignals(False)
        if self.world_combo.count():
            self._load_world()
        else:
            self.meta.setText(f"在 {saves} 下没有找到可编辑的存档")

    def _version_id(self) -> str:
        try:
            return str(self.ctx.config.selected_instance().version_id or "")
        except AttributeError:
            return ""

    def _service_for(self) -> CreatorService:
        cfg = self.ctx.config
        return CreatorService(
            cfg.game_path, cfg.backup_root, backup_version=self._version_id()
        )

    def _load_world(self) -> None:
        world = self.world_combo.currentData()
        if not world:
            return
        try:
            service = self._service_for()
            state = service.open(world)
        except (CreatorError, OSError, ValueError) as exc:
            self.meta.setText(f"读取失败：{exc}")
            self.state = None
            return
        self.service = service
        self.state = state
        self.caps.update(state.get("vanilla_caps") or {})
        era_label = {
            "legacy": "1.13 前（数字 ID）",
            "flattened": "1.13+ 扁平化",
            "components": "1.20.5+ 组件化",
            "pre_anvil": "非 Anvil（只读）",
            "unknown": "未知（只读）",
        }.get(state["era"], state["era"])
        self.meta.setText(
            f"{state['name']} · DataVersion {state['data_version']} · {state['version_name']} · {era_label}"
            + ("" if state["editable"] else f" · 只读：{state['reason']}")
        )
        self.player_combo.blockSignals(True)
        self.player_combo.clear()
        for entry in state["players"]:
            self.player_combo.addItem(entry["name"], entry["uuid"])
        self.player_combo.blockSignals(False)
        self.backup_info.setText(f"备份目录：{state['backup_root']}")
        self.tabs.setEnabled(state["editable"])
        self._load_player()

    def _load_player(self) -> None:
        if not self.state or not self.service:
            return
        uuid = self.player_combo.currentData() or "level"
        try:
            player = self.service.read_player(self.state["world"], uuid)
        except (CreatorError, OSError, ValueError) as exc:
            self.status.setText(f"玩家数据读取失败：{exc}")
            return
        self.state["player_uuid"] = uuid
        self._fill_player(player)
        self._fill_level(self.state["level"])
        self._reload_advancements()

    def _fill_player(self, player: dict) -> None:
        pos = list(player.get("pos") or [0.0, 64.0, 0.0])
        while len(pos) < 3:
            pos.append(0.0)
        self.pos_x.setValue(float(pos[0]))
        self.pos_y.setValue(float(pos[1]))
        self.pos_z.setValue(float(pos[2]))
        self.health.setValue(float(player.get("health", 20.0)))
        self.food.setValue(float(player.get("food", 5.0)))
        self.food_level.setValue(int(player.get("food_level", 20)))
        self.xp_level.setValue(int(player.get("xp_level", 0)))
        self.game_mode.setCurrentIndex(max(0, min(3, int(player.get("game_type", 0)))))
        self.dimension.setText(str(player.get("dimension", "minecraft:overworld")))
        self.inventory.setRowCount(0)
        self._items = [dict(item) for item in player.get("inventory", [])]
        for item in self._items:
            self._append_item_row(item)
        self.ender.setRowCount(0)
        self._ender_items = [dict(item) for item in player.get("ender_items", [])]
        for item in self._ender_items:
            self._append_ender_row(item)
        self.attributes.setRowCount(0)
        for entry in player.get("attributes", []):
            row = self.attributes.rowCount()
            self.attributes.insertRow(row)
            self.attributes.setItem(row, 0, QTableWidgetItem(str(entry.get("name", ""))))
            self.attributes.setItem(row, 1, QTableWidgetItem(str(entry.get("base", 0))))
            modifiers = ";".join(
                f"{item.get('amount', 0)}:{item.get('operation', 'add_value')}"
                for item in entry.get("modifiers", [])
            )
            self.attributes.setItem(row, 2, QTableWidgetItem(modifiers))
        self.effects.setRowCount(0)
        for entry in player.get("effects", []):
            row = self.effects.rowCount()
            self.effects.insertRow(row)
            self.effects.setItem(row, 0, QTableWidgetItem(str(entry.get("id", 1))))
            self.effects.setItem(row, 1, QTableWidgetItem(str(entry.get("amplifier", 0))))
            self.effects.setItem(row, 2, QTableWidgetItem(str(entry.get("duration", 0))))
            self.effects.setItem(row, 3, QTableWidgetItem("开" if not entry.get("hide_particles") else "关"))

    def _fill_level(self, level: dict) -> None:
        self.time.setText(str(level.get("time", 0)))
        self.day_time.setText(str(level.get("day_time", 0)))
        weather = level.get("weather", "clear")
        index = max(0, self.weather.findData(weather))
        self.weather.setCurrentIndex(index)
        border = level.get("border") or {}
        self.border_size.setValue(float(border.get("size", 59999968.0)))
        self.border_x.setValue(float(border.get("center_x", 0.0)))
        self.border_z.setValue(float(border.get("center_z", 0.0)))
        spawn = list(level.get("spawn") or [0, 64, 0])
        while len(spawn) < 3:
            spawn.append(0)
        self.spawn_x.setValue(int(spawn[0]))
        self.spawn_y.setValue(int(spawn[1]))
        self.spawn_z.setValue(int(spawn[2]))
        rules = level.get("gamerules") or {}
        self.rule_keep_inventory.setChecked(rules.get("keepInventory") == "true")
        self.rule_daylight.setChecked(rules.get("doDaylightCycle") == "true")
        self.rule_mob_spawning.setChecked(rules.get("doMobSpawning") == "true")
        self.rule_fire_tick.setChecked(rules.get("doFireTick") == "true")
        self.rule_weather_cycle.setChecked(rules.get("doWeatherCycle") != "false")
        self.rule_mob_loot.setChecked(rules.get("doMobLoot") != "false")
        self.rule_tile_drops.setChecked(rules.get("doTileDrops") != "false")
        self.rule_mob_griefing.setChecked(rules.get("mobGriefing") != "false")
        self.rule_natural_regen.setChecked(rules.get("naturalRegeneration") != "false")
        self.rule_show_coordinates.setChecked(rules.get("showCoordinates") == "true")
        self.rule_announce_advancements.setChecked(rules.get("announceAdvancements") != "false")
        try:
            self.random_tick.setValue(int(rules.get("randomTickSpeed", "3")))
        except ValueError:
            self.random_tick.setValue(3)

    def _reload_advancements(self) -> None:
        if not self.state or not self.service:
            return
        try:
            report = self.service.read_advancements(self.state["world"], self.state.get("player_uuid", "level"))
        except (CreatorError, OSError, ValueError):
            report = {"entries": []}
        checked = {}
        for index in range(self.advance_list.count()):
            node = self.advance_list.item(index)
            checked[str(node.data(Qt.UserRole))] = node.checkState() == Qt.Checked
        self.advance_list.clear()
        for entry in report["entries"]:
            label = (
                f"{entry['id']} · {'已完成' if entry.get('done') else '未完成'}"
                f"（{entry.get('criteria', 0)} 个条件）"
            )
            node = QListWidgetItem(label)
            node.setFlags(node.flags() | Qt.ItemIsUserCheckable)
            node.setData(Qt.UserRole, entry["id"])
            state = checked.get(entry["id"], bool(entry.get("done")))
            node.setCheckState(Qt.Checked if state else Qt.Unchecked)
            self.advance_list.addItem(node)
        self.advance_info.setText(f"已有成就条目 {len(report['entries'])} 个")

    # ------------------------------------------------------------------
    @staticmethod
    def _item_summary(item: dict) -> str:
        attributes = ", ".join(
            f"{str(entry.get('name', '')).split(':')[-1]}:{entry.get('amount', 0)}"
            for entry in item.get("attributes", [])
        )
        if item.get("tag_json"):
            return (attributes + " · Raw").strip(" ·")
        return attributes

    def _append_item_row(self, item: dict) -> None:
        row = self.inventory.rowCount()
        self.inventory.insertRow(row)
        self.inventory.setItem(row, 0, QTableWidgetItem(str(item.get("slot", 0))))
        self.inventory.setItem(row, 1, QTableWidgetItem(str(item.get("id", ""))))
        self.inventory.setItem(row, 2, QTableWidgetItem(str(item.get("count", 1))))
        enchants = ",".join(f"{e['id']}:{e['level']}" for e in item.get("enchantments", []))
        self.inventory.setItem(row, 3, QTableWidgetItem(enchants))
        self.inventory.setItem(row, 4, QTableWidgetItem(self._item_summary(item)))

    def _append_ender_row(self, item: dict) -> None:
        row = self.ender.rowCount()
        self.ender.insertRow(row)
        self.ender.setItem(row, 0, QTableWidgetItem(str(item.get("slot", 0))))
        self.ender.setItem(row, 1, QTableWidgetItem(str(item.get("id", ""))))
        self.ender.setItem(row, 2, QTableWidgetItem(str(item.get("count", 1))))
        enchants = ",".join(f"{e['id']}:{e['level']}" for e in item.get("enchantments", []))
        self.ender.setItem(row, 3, QTableWidgetItem(enchants))
        self.ender.setItem(row, 4, QTableWidgetItem(self._item_summary(item)))

    def _edit_ender_item(self, row: int) -> None:
        entry = dict(self._ender_items[row]) if 0 <= row < len(self._ender_items) else {
            "slot": 0,
            "count": 1,
        }
        if not self._catalog:
            self._scan_items(silent=True)
        dialog = ItemEditor(
            entry, self.caps, self.state["era"] if self.state else "flattened", self._catalog, self
        )
        if dialog.exec() != QDialog.Accepted:
            return
        result = dialog.entry
        if row < 0:
            self._ender_items.append(result)
            self._append_ender_row(result)
        else:
            self._ender_items[row] = result
            self.ender.setItem(row, 0, QTableWidgetItem(str(result.get("slot", 0))))
            self.ender.setItem(row, 1, QTableWidgetItem(str(result.get("id", ""))))
            self.ender.setItem(row, 2, QTableWidgetItem(str(result.get("count", 1))))
            self.ender.setItem(
                row,
                3,
                QTableWidgetItem(
                    ",".join(f"{e['id']}:{e['level']}" for e in result.get("enchantments", []))
                ),
            )
            self.ender.setItem(row, 4, QTableWidgetItem(self._item_summary(result)))

    def _remove_ender_item(self) -> None:
        row = self.ender.currentRow()
        if row < 0:
            return
        self.ender.removeRow(row)
        if row < len(self._ender_items):
            self._ender_items.pop(row)

    def _edit_item(self, row: int) -> None:
        if row < 0 and self.inventory.rowCount() == 0:
            entry = {"slot": 0, "count": 1}
        elif row < 0:
            entry = {"slot": 0, "count": 1}
        else:
            entry = dict(self._items[row]) if row < len(self._items) else {"slot": 0, "count": 1}
        if not self._catalog:
            self._scan_items(silent=True)
        dialog = ItemEditor(entry, self.caps, self.state["era"] if self.state else "flattened", self._catalog, self)
        if dialog.exec() != QDialog.Accepted:
            return
        result = dialog.entry
        result["tag_json"] = result.get("tag_json")
        if row < 0:
            self._items.append(result)
            self._append_item_row(result)
        else:
            self._items[row] = result
            self.inventory.setItem(row, 0, QTableWidgetItem(str(result.get("slot", 0))))
            self.inventory.setItem(row, 1, QTableWidgetItem(str(result.get("id", ""))))
            self.inventory.setItem(row, 2, QTableWidgetItem(str(result.get("count", 1))))
            self.inventory.setItem(
                row,
                3,
                QTableWidgetItem(
                    ",".join(f"{e['id']}:{e['level']}" for e in result.get("enchantments", []))
                ),
            )
            self.inventory.setItem(row, 4, QTableWidgetItem(self._item_summary(result)))

    def _remove_item(self) -> None:
        row = self.inventory.currentRow()
        if row < 0:
            return
        self.inventory.removeRow(row)
        if row < len(self._items):
            self._items.pop(row)

    def _scan_items(self, silent: bool = False) -> None:
        if not self.service:
            return
        self.status.setText("正在扫描本地版本与模组的物品 ID…")
        _process_events()
        try:
            self._catalog = self.service.scan_items(
                self._version_id(), self.state["era"] if self.state else ""
            )
        except OSError as exc:
            self.status.setText(f"扫描失败：{exc}")
            return
        self.status.setText(f"已加载 {len(self._catalog)} 个物品 ID")
        if not silent:
            picker = ItemPicker(self._catalog, self)
            if picker.exec() == QDialog.Accepted and picker.selected_id():
                self._edit_item_prefill(picker.selected_id())

    def _edit_item_prefill(self, item_id: str) -> None:
        entry = {"id": item_id, "slot": 0, "count": 1}
        dialog = ItemEditor(
            entry, self.caps, self.state["era"] if self.state else "flattened", self._catalog, self
        )
        if dialog.exec() == QDialog.Accepted:
            self._items.append(dialog.entry)
            self._append_item_row(dialog.entry)

    def _add_attribute(self) -> None:
        row = self.attributes.rowCount()
        self.attributes.insertRow(row)
        self.attributes.setItem(row, 0, QTableWidgetItem("generic.max_health"))
        self.attributes.setItem(row, 1, QTableWidgetItem("20.0"))
        self.attributes.setItem(row, 2, QTableWidgetItem(""))

    def _add_effect(self) -> None:
        row = self.effects.rowCount()
        self.effects.insertRow(row)
        self.effects.setItem(row, 0, QTableWidgetItem("1"))
        self.effects.setItem(row, 1, QTableWidgetItem("0"))
        self.effects.setItem(row, 2, QTableWidgetItem("200"))
        self.effects.setItem(row, 3, QTableWidgetItem("开"))

    # ------------------------------------------------------------------
    def _collect_request(self) -> dict:
        for row in range(self.inventory.rowCount()):
            if row < len(self._items):
                try:
                    self._items[row]["slot"] = int(self.inventory.item(row, 0).text())
                    self._items[row]["count"] = int(self.inventory.item(row, 2).text())
                except (ValueError, AttributeError):
                    pass
        for row in range(self.ender.rowCount()):
            if row < len(self._ender_items):
                try:
                    self._ender_items[row]["slot"] = int(self.ender.item(row, 0).text())
                    self._ender_items[row]["count"] = int(self.ender.item(row, 2).text())
                except (ValueError, AttributeError):
                    pass
        attributes = []
        for row in range(self.attributes.rowCount()):
            name_item = self.attributes.item(row, 0)
            base_item = self.attributes.item(row, 1)
            modifier_item = self.attributes.item(row, 2)
            if not name_item or not name_item.text().strip():
                continue
            modifiers = []
            for chunk in (modifier_item.text() if modifier_item else "").split(";"):
                chunk = chunk.strip()
                if not chunk:
                    continue
                parts = chunk.rsplit(":", 1)
                try:
                    amount = float(parts[0])
                except ValueError:
                    continue
                operation = parts[1].strip() if len(parts) > 1 else "add_value"
                modifiers.append(
                    {"name": name_item.text().strip(), "amount": amount, "operation": operation}
                )
            attributes.append(
                {
                    "name": name_item.text().strip(),
                    "base": float(base_item.text() if base_item else 0),
                    "modifiers": modifiers,
                }
            )
        effects = []
        for row in range(self.effects.rowCount()):
            id_item = self.effects.item(row, 0)
            if not id_item:
                continue
            effects.append(
                {
                    "id": int(id_item.text() or 1),
                    "amplifier": int((self.effects.item(row, 1) or QTableWidgetItem("0")).text() or 0),
                    "duration": int((self.effects.item(row, 2) or QTableWidgetItem("0")).text() or 0),
                    "hide_particles": (self.effects.item(row, 3) or QTableWidgetItem("开")).text() == "关",
                }
            )
        player = {
            "health": self.health.value(),
            "food": self.food.value(),
            "food_level": self.food_level.value(),
            "safe_teleport": self.safe_tp.isChecked(),
            "xp_level": self.xp_level.value(),
            "pos": [self.pos_x.value(), self.pos_y.value(), self.pos_z.value()],
            "game_type": self.game_mode.currentData(),
            "dimension": self.dimension.text().strip() or "minecraft:overworld",
            "inventory": self._items,
            "ender_items": self._ender_items,
            "attributes": attributes,
            "effects": effects,
        }
        level = {
            "time": int(self.time.text() or 0),
            "day_time": int(self.day_time.text() or 0),
            "weather": self.weather.currentData(),
            "border_size": self.border_size.value(),
            "border_center": [self.border_x.value(), self.border_z.value()],
            "spawn": [self.spawn_x.value(), self.spawn_y.value(), self.spawn_z.value()],
            "gamerules": {
                "keepInventory": "true" if self.rule_keep_inventory.isChecked() else "false",
                "doDaylightCycle": "true" if self.rule_daylight.isChecked() else "false",
                "doMobSpawning": "true" if self.rule_mob_spawning.isChecked() else "false",
                "doFireTick": "true" if self.rule_fire_tick.isChecked() else "false",
                "doWeatherCycle": "true" if self.rule_weather_cycle.isChecked() else "false",
                "doMobLoot": "true" if self.rule_mob_loot.isChecked() else "false",
                "doTileDrops": "true" if self.rule_tile_drops.isChecked() else "false",
                "mobGriefing": "true" if self.rule_mob_griefing.isChecked() else "false",
                "naturalRegeneration": "true" if self.rule_natural_regen.isChecked() else "false",
                "showCoordinates": "true" if self.rule_show_coordinates.isChecked() else "false",
                "announceAdvancements": "true" if self.rule_announce_advancements.isChecked() else "false",
                "randomTickSpeed": str(self.random_tick.value()),
            },
        }
        return {
            "world": self.state["world"],
            "player_uuid": self.state.get("player_uuid", "level"),
            "player": player,
            "level": level,
        }

    def _save(self) -> None:
        if not self.state or not self.service:
            QMessageBox.information(self, "创世神面板", "请先选择一个存档")
            return
        if not self.state.get("editable"):
            QMessageBox.warning(self, "创世神面板", f"该存档只读：{self.state.get('reason')}")
            return
        if self.safe_tp.isChecked():
            self._apply_safe_teleport()
        try:
            request = self._collect_request()
            preview = self.service.preview(request)
        except (ValueError, CreatorError) as exc:
            QMessageBox.warning(self, "创世神面板", str(exc))
            return
        if preview["warnings"]:
            lines = "\n".join(f"· {item['message']}" for item in preview["warnings"])
            answer = QMessageBox.warning(
                self,
                "超出原版上限",
                "您输入的值已超出原版上限，强制写入可能导致游戏崩溃或读档失败，是否继续？\n\n" + lines,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        answer = QMessageBox.question(
            self,
            "确认写入",
            "即将修改存档，并先生成完整备份。\n\n" + "\n".join(preview["changes"]) + "\n\n继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            result = self.service.apply(preview["token"])
        except (PreviewExpired, CreatorError, OSError, ValueError) as exc:
            QMessageBox.critical(self, "写入失败", str(exc))
            return
        self.status.setText(f"已写入，备份：{result['backup']}")
        QMessageBox.information(self, "写入成功", f"存档已保存。\n备份：{result['backup']}")
        self._load_world()

    def _apply_safe_teleport(self) -> None:
        from ..creator_region import read_region, region_files, surface_y

        if not self.state:
            return
        target_x = int(self.pos_x.value())
        target_z = int(self.pos_z.value())
        try:
            for path in region_files(self.state["world"]):
                archive = read_region(path)
                height = surface_y(archive, target_x, target_z)
                if height is not None:
                    self.pos_y.setValue(float(height + 1))
                    self.status.setText(f"安全传送：目标列最高方块 Y={height}")
                    return
        except OSError as exc:
            self.status.setText(f"高度查询失败：{exc}")
            return
        self.status.setText("目标 X/Z 没有已加载区块，未修改 Y 坐标")
        QMessageBox.information(
            self, "安全传送", "目标 X/Z 没有已加载的区块，无法确定落点。已保留原 Y 坐标。"
        )

    # ------------------------------------------------------------------
    def _pick_ops_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择服务端目录")
        if folder:
            self.ops_dir.setText(folder)

    def _load_ops(self) -> None:
        if not self.service:
            return
        folder = self.ops_dir.text().strip()
        if not folder:
            return
        try:
            entries = self.service.read_ops(folder)
        except CreatorError as exc:
            QMessageBox.warning(self, "创世神面板", str(exc))
            return
        self.ops_table.setRowCount(0)
        for entry in entries:
            row = self.ops_table.rowCount()
            self.ops_table.insertRow(row)
            self.ops_table.setItem(row, 0, QTableWidgetItem(str(entry.get("uuid", ""))))
            self.ops_table.setItem(row, 1, QTableWidgetItem(str(entry.get("name", ""))))
            self.ops_table.setItem(row, 2, QTableWidgetItem(str(entry.get("level", 0))))

    def _save_ops(self) -> None:
        if not self.service:
            return
        folder = self.ops_dir.text().strip()
        if not folder:
            QMessageBox.information(self, "创世神面板", "请先选择服务端目录")
            return
        entries = []
        for row in range(self.ops_table.rowCount()):
            try:
                entries.append(
                    {
                        "uuid": self.ops_table.item(row, 0).text(),
                        "name": self.ops_table.item(row, 1).text(),
                        "level": int(self.ops_table.item(row, 2).text()),
                    }
                )
            except (ValueError, AttributeError):
                continue
        try:
            result = self.service.write_ops(folder, entries)
        except (CreatorError, OSError) as exc:
            QMessageBox.critical(self, "写入失败", str(exc))
            return
        QMessageBox.information(self, "OP 已保存", f"已写入 {result['path']}")

    def _complete_advancements(self) -> None:
        if not self.service or not self.state:
            return
        selected = []
        for index in range(self.advance_list.count()):
            node = self.advance_list.item(index)
            if node.checkState() == Qt.Checked:
                selected.append(str(node.data(Qt.UserRole)))
        if not selected:
            QMessageBox.information(self, "成就", "请先勾选要完成的成就条目")
            return
        answer = QMessageBox.question(
            self,
            "成就",
            f"将把勾选的 {len(selected)} 个成就条目标记为完成。不会凭空创建未存在的成就。继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            result = self.service.complete_advancements(
                self.state["world"], self.state.get("player_uuid", "level"), selected
            )
        except (CreatorError, OSError) as exc:
            QMessageBox.critical(self, "操作失败", str(exc))
            return
        QMessageBox.information(self, "成就", f"已处理 {result['count']} 个成就条目")
        self._reload_advancements()

    def _check_advancements(self, value: bool) -> None:
        state = Qt.Checked if value else Qt.Unchecked
        for index in range(self.advance_list.count()):
            self.advance_list.item(index).setCheckState(state)

    def _convert_world(self) -> None:
        if not self.service:
            return
        source = self.convert_source.text().strip()
        if not source:
            QMessageBox.information(self, "旧格式转换", "请先选择要转换的旧存档目录或 level.dat")
            return
        target = str(self.convert_target.currentData() or "1.12.2")
        answer = QMessageBox.question(
            self,
            "旧格式转换",
            f"把 {source}\n转换为 {target} 结构？转换会生成新的世界目录，不会修改原文件。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.status.setText("正在转换存档…")
        _process_events()
        try:
            result = self.service.convert_world(
                source, target, source_era=str(self.convert_era.currentData() or "auto")
            )
        except (CreatorError, OSError, ValueError) as exc:
            self.status.setText("转换失败")
            QMessageBox.critical(self, "旧格式转换", str(exc))
            return
        self.status.setText(f"已转换到 {result.get('output', '')}")
        QMessageBox.information(
            self,
            "旧格式转换",
            f"输出：{result.get('output', '')}\n步骤：{len(result.get('steps') or [])} 步\n"
            f"警告：{'；'.join(result.get('warnings') or []) or '无'}",
        )
        self.refresh()

    def _preview_region(self) -> None:
        if not self.service or not self.state:
            return
        try:
            report = self.service.preview_region(
                {
                    "world": self.state["world"],
                    "old_id": self.old_block.text().strip(),
                    "new_id": self.new_block.text().strip(),
                }
            )
        except (CreatorError, OSError, ValueError) as exc:
            QMessageBox.warning(self, "创世神面板", str(exc))
            return
        self._region_token = report["token"]
        self.region_info.setText(
            f"预扫描：{report['files']} 个 region，{report['chunks']} 个区块，"
            f"预计替换 {report['replaced']} 个方块。确认后点“执行替换”。"
        )

    def _apply_region(self) -> None:
        token = getattr(self, "_region_token", "")
        if not token or not self.service:
            QMessageBox.information(self, "创世神面板", "请先预扫描")
            return
        answer = QMessageBox.question(
            self,
            "执行替换",
            "将备份整个世界后逐 region 重写，任一文件失败会整体回滚。继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            result = self.service.apply_region(token)
        except (PreviewExpired, CreatorError, OSError) as exc:
            QMessageBox.critical(self, "替换失败", str(exc))
            return
        self.region_info.setText(f"已替换 {result['replaced']} 个方块，备份：{result['backup']}")

    def _open_backup_dir(self) -> None:
        if not self.state:
            return
        import os

        path = Path(self.state["backup_root"])
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(str(path))  # noqa: S606 - 打开资源管理器


def _process_events() -> None:
    """处理一次挂起事件，避免长扫描时界面完全冻结。"""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is not None:
        app.processEvents()
