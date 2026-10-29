"""NBT 查看 / 编辑器：读写 level.dat、playerdata 等 .dat 存档。"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..context import AppContext
from ..nbt import (
    NBTError,
    TAG_BYTE,
    TAG_BYTE_ARRAY,
    TAG_COMPOUND,
    TAG_DOUBLE,
    TAG_FLOAT,
    TAG_INT,
    TAG_INT_ARRAY,
    TAG_LIST,
    TAG_LONG,
    TAG_LONG_ARRAY,
    TAG_NAMES,
    TAG_SHORT,
    TAG_STRING,
    load_nbt_typed_file,
    save_nbt_typed_file,
)

# 可编辑的叶子类型
_EDITABLE_TAGS = {TAG_BYTE, TAG_SHORT, TAG_INT, TAG_LONG, TAG_FLOAT, TAG_DOUBLE, TAG_STRING}
# 右键可新增的类型（顺序即菜单顺序）
_ADD_TAGS = (
    (TAG_BYTE, "Byte"),
    (TAG_SHORT, "Short"),
    (TAG_INT, "Int"),
    (TAG_LONG, "Long"),
    (TAG_FLOAT, "Float"),
    (TAG_DOUBLE, "Double"),
    (TAG_STRING, "String"),
    (TAG_COMPOUND, "Compound"),
)


def _format_value(tag: int, value: Any) -> str:
    if tag == TAG_COMPOUND:
        return f"{len(value)} 个子标签"
    if tag == TAG_LIST:
        element_tag, items = value
        suffix = TAG_NAMES.get(element_tag, "TAG_End") if element_tag else "空"
        return f"{len(items)} 项 · {suffix}"
    if tag == TAG_BYTE_ARRAY:
        return f"<{len(value)} 字节>"
    if tag in (TAG_INT_ARRAY, TAG_LONG_ARRAY):
        preview = ", ".join(str(v) for v in list(value)[:6])
        more = "…" if len(value) > 6 else ""
        return f"[{preview}{more}]"
    if tag == TAG_STRING:
        text = str(value)
        return text if len(text) <= 80 else text[:80] + "…"
    return str(value)


def _parse_value(tag: int, text: str) -> Any:
    if tag == TAG_STRING:
        return text
    if tag == TAG_FLOAT:
        return float(text)
    if tag == TAG_DOUBLE:
        return float(text)
    return int(text)


def _count_tags(node: tuple[int, Any]) -> int:
    tag, value = node
    if tag == TAG_COMPOUND:
        return 1 + sum(_count_tags(child) for child in value.values())
    if tag == TAG_LIST:
        _element_tag, items = value
        return 1 + sum(_count_tags(child) for child in items)
    return 1


class NbtEditorDialog(QDialog):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self._root_name = ""
        self._root: tuple[int, Any] | None = None
        self._file_path = ""
        self._dirty = False
        self._updating = False
        self._confirmed = False
        self.setWindowTitle(self.tr("NBT 编辑器"))
        self.setMinimumSize(900, 600)
        self.resize(900, 600)
        self._build()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(self.tr("选择 .dat 存档文件（level.dat / playerdata/*.dat）"))
        self.path_edit.setReadOnly(True)
        top.addWidget(self.path_edit, 1)

        open_button = QPushButton(self.tr("打开…"))
        open_button.clicked.connect(self._open_file)
        top.addWidget(open_button)
        save_button = QPushButton(self.tr("保存"))
        save_button.setObjectName("Primary")
        save_button.clicked.connect(self.save)
        top.addWidget(save_button)
        save_as_button = QPushButton(self.tr("另存为…"))
        save_as_button.clicked.connect(self._save_as)
        top.addWidget(save_as_button)
        outer.addLayout(top)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels([self.tr("名称"), self.tr("类型"), self.tr("值")])
        self.tree.setColumnWidth(0, 300)
        self.tree.setColumnWidth(1, 130)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.setAlternatingRowColors(True)
        outer.addWidget(self.tree, 1)

        self.status_label = QLabel(self.tr("尚未打开文件"))
        self.status_label.setObjectName("Tiny")
        outer.addWidget(self.status_label)

    # ------------------------------------------------------------------
    # 打开 / 保存
    # ------------------------------------------------------------------
    def _open_file(self) -> None:
        answer = QMessageBox.question(
            self,
            self.tr("打开 NBT 存档"),
            self.tr(
                "编辑 NBT 可能导致存档损坏，建议先备份。\n"
                "首次保存时会自动在同目录生成 .bak 备份。继续？"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("选择 NBT 文件"),
            self._default_dir(),
            self.tr("NBT 存档 (*.dat *.nbt);;所有文件 (*.*)"),
        )
        if path:
            self._load_path(path)

    def _default_dir(self) -> str:
        try:
            base = self.ctx.config.game_path
        except Exception:  # noqa: BLE001 - 配置异常时退回用户目录
            return str(Path.home())
        if base.exists():
            return str(base)
        return str(Path.home())

    def _load_path(self, path: str) -> None:
        try:
            root_name, root = load_nbt_typed_file(Path(path))
        except (NBTError, OSError, ValueError) as exc:
            QMessageBox.critical(
                self, self.tr("无法读取 NBT"), f"{path}\n\n{exc}"
            )
            return
        if root[0] != TAG_COMPOUND:
            QMessageBox.critical(self, self.tr("无法读取 NBT"), self.tr("根标签不是 TAG_Compound。"))
            return
        self._root_name = root_name
        self._root = root
        self._file_path = path
        self._dirty = False
        self._confirmed = False
        self._updating = True
        try:
            self.path_edit.setText(path)
            self._populate()
        finally:
            self._updating = False
        self._update_status()

    def open_path(self, path: str) -> None:
        """供外部入口直接打开指定文件（不弹确认框）。"""
        self._load_path(path)

    def _populate(self) -> None:
        self.tree.clear()
        if self._root is None:
            return
        item = QTreeWidgetItem(self.tree)
        item.setText(0, Path(self._file_path).name or "root")
        item.setText(1, TAG_NAMES[TAG_COMPOUND])
        item.setText(2, _format_value(TAG_COMPOUND, self._root[1]))
        item.setData(0, Qt.UserRole, ("root", None, None))
        self._fill_children(item, self._root)

    def _fill_children(self, parent_item: QTreeWidgetItem, node: tuple[int, Any]) -> None:
        tag, value = node
        if tag == TAG_COMPOUND:
            for name, child in value.items():
                child_item = QTreeWidgetItem(parent_item)
                child_item.setText(0, str(name))
                child_item.setText(1, TAG_NAMES.get(child[0], str(child[0])))
                child_item.setText(2, _format_value(child[0], child[1]))
                child_item.setData(0, Qt.UserRole, ("dict", value, name))
                self._apply_flags(child_item, child[0])
                self._fill_children(child_item, child)
        elif tag == TAG_LIST:
            _element_tag, items = value
            for index, child in enumerate(items):
                child_item = QTreeWidgetItem(parent_item)
                child_item.setText(0, f"[{index}]")
                child_item.setText(1, TAG_NAMES.get(child[0], str(child[0])))
                child_item.setText(2, _format_value(child[0], child[1]))
                child_item.setData(0, Qt.UserRole, ("list", items, index))
                self._apply_flags(child_item, child[0])
                self._fill_children(child_item, child)

    def _apply_flags(self, item: QTreeWidgetItem, tag: int) -> None:
        flags = item.flags() | Qt.ItemIsSelectable | Qt.ItemIsEnabled
        if tag in _EDITABLE_TAGS:
            flags |= Qt.ItemIsEditable
        item.setFlags(flags)

    # ------------------------------------------------------------------
    # 编辑
    # ------------------------------------------------------------------
    def _node_at(self, container_kind: str, container, key):
        """返回 (parent_node, node)：key 在 container 中对应的节点及父节点。"""
        if container_kind == "dict":
            parent_node = self._find_compound_holding(container)
            return parent_node, parent_node[1][key] if parent_node else None
        if container_kind == "list":
            parent_node = self._find_list_holding(container)
            return parent_node, container[key] if parent_node else None
        return None, None

    def _find_compound_holding(self, target: dict):
        if self._root is None:
            return None

        def walk(node):
            tag, value = node
            if tag == TAG_COMPOUND:
                if value is target:
                    return node
                for child in value.values():
                    found = walk(child)
                    if found is not None:
                        return found
            elif tag == TAG_LIST:
                for child in value[1]:
                    found = walk(child)
                    if found is not None:
                        return found
            return None

        return walk(self._root)

    def _find_list_holding(self, target: list):
        if self._root is None:
            return None

        def walk(node):
            tag, value = node
            if tag == TAG_COMPOUND:
                for child in value.values():
                    found = walk(child)
                    if found is not None:
                        return found
            elif tag == TAG_LIST:
                if value[1] is target:
                    return node
                for child in value[1]:
                    found = walk(child)
                    if found is not None:
                        return found
            return None

        return walk(self._root)

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._updating or column != 2:
            return
        data = item.data(0, Qt.UserRole)
        if not data or data[0] == "root":
            return
        container_kind, container, key = data
        _parent, node = self._node_at(container_kind, container, key)
        if node is None:
            return
        tag = node[0]
        if tag not in _EDITABLE_TAGS:
            return
        text = item.text(2)
        try:
            new_value = _parse_value(tag, text)
        except (TypeError, ValueError):
            self._updating = True
            try:
                item.setText(2, _format_value(tag, node[1]))
            finally:
                self._updating = False
            QMessageBox.warning(
                self, self.tr("值不合法"), self.tr("{0} 无法解析为 {1}。").format(text, TAG_NAMES[tag])
            )
            return
        new_node = (tag, new_value)
        if container_kind == "dict":
            container[key] = new_node
        else:
            container[key] = new_node
        self._dirty = True
        self._updating = True
        try:
            item.setText(2, _format_value(tag, new_value))
        finally:
            self._updating = False
        self._update_status()

    # ------------------------------------------------------------------
    # 右键菜单：添加 / 删除
    # ------------------------------------------------------------------
    def _show_context_menu(self, position) -> None:
        item = self.tree.itemAt(position)
        menu = QMenu(self)
        if item is not None:
            data = item.data(0, Qt.UserRole)
            node = self._current_node(item)
            can_add = node is not None and node[0] == TAG_COMPOUND
            add_menu = menu.addMenu(self.tr("添加子标签"))
            add_menu.setEnabled(can_add)
            for tag, label in _ADD_TAGS:
                action = add_menu.addAction(label)
                action.triggered.connect(
                    lambda _checked=False, t=tag, i=item: self._add_child(i, t)
                )
            delete_action = menu.addAction(self.tr("删除标签"))
            delete_action.setEnabled(data is not None and data[0] != "root")
            delete_action.triggered.connect(lambda: self._delete_item(item))
        else:
            menu.addAction(self.tr("没有可操作项")).setEnabled(False)
        menu.exec(self.tree.viewport().mapToGlobal(position))

    def _current_node(self, item: QTreeWidgetItem):
        data = item.data(0, Qt.UserRole)
        if not data:
            return None
        if data[0] == "root":
            return self._root
        return self._node_at(data[0], data[1], data[2])[1]

    def _add_child(self, item: QTreeWidgetItem, tag: int) -> None:
        node = self._current_node(item)
        if node is None or node[0] != TAG_COMPOUND:
            return
        name, ok = QInputDialog.getText(self, self.tr("添加子标签"), self.tr("标签名称："))
        name = (name or "").strip()
        if not ok or not name:
            return
        if name in node[1]:
            QMessageBox.warning(self, self.tr("名称重复"), self.tr("同级已存在同名标签。"))
            return
        if tag == TAG_COMPOUND:
            value: Any = {}
        elif tag == TAG_STRING:
            text, ok = QInputDialog.getText(
                self, self.tr("添加子标签"), self.tr("{0} 的值：").format(name)
            )
            if not ok:
                return
            value = text
        else:
            text, ok = QInputDialog.getText(
                self, self.tr("添加子标签"), self.tr("{0} 的值（数字）：").format(name)
            )
            if not ok:
                return
            try:
                value = _parse_value(tag, text)
            except (TypeError, ValueError):
                QMessageBox.warning(self, self.tr("值不合法"), self.tr("请输入合法的数字。"))
                return
        node[1][name] = (tag, value)
        self._dirty = True
        self._rebuild()

    def _delete_item(self, item: QTreeWidgetItem) -> None:
        data = item.data(0, Qt.UserRole)
        if not data or data[0] == "root":
            return
        container_kind, container, key = data
        answer = QMessageBox.question(
            self,
            self.tr("删除标签"),
            self.tr("确定删除「{0}」及其所有子标签？").format(item.text(0)),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            if container_kind == "dict":
                container.pop(key, None)
            else:
                if 0 <= key < len(container):
                    container.pop(key)
        except (KeyError, IndexError):
            return
        self._dirty = True
        self._rebuild()

    def _rebuild(self) -> None:
        self._updating = True
        try:
            self._populate()
        finally:
            self._updating = False
        self._update_status()

    # ------------------------------------------------------------------
    # 保存
    # ------------------------------------------------------------------
    def save(self) -> bool:
        if self._root is None or not self._file_path:
            QMessageBox.information(self, self.tr("NBT 编辑器"), self.tr("请先打开一个 .dat 文件。"))
            return False
        return self._write_to(self._file_path)

    def _save_as(self) -> None:
        if self._root is None:
            QMessageBox.information(self, self.tr("NBT 编辑器"), self.tr("请先打开一个 .dat 文件。"))
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("另存为"),
            self._file_path or str(Path.home()),
            self.tr("NBT 存档 (*.dat *.nbt);;所有文件 (*.*)"),
        )
        if path:
            self._write_to(path)

    def _write_to(self, path: str) -> bool:
        if not self._confirmed:
            answer = QMessageBox.question(
                self,
                self.tr("保存 NBT"),
                self.tr(
                    "修改 NBT 可能导致存档无法读取。\n"
                    "将在同目录自动生成 .bak 备份，确认保存？"
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return False
            self._confirmed = True
        if self._root is None:
            return False
        target = Path(path)
        backup = target.with_name(target.name + ".bak")
        if target.exists() and not backup.exists():
            try:
                shutil.copy2(target, backup)
            except OSError as exc:
                QMessageBox.warning(
                    self, self.tr("备份失败"), self.tr("无法生成备份：{0}").format(exc)
                )
        try:
            save_nbt_typed_file(target, self._root_name, self._root)
        except (NBTError, OSError, ValueError) as exc:
            QMessageBox.critical(self, self.tr("保存失败"), str(exc))
            return False
        self._file_path = str(target)
        self.path_edit.setText(self._file_path)
        self._dirty = False
        self._update_status()
        QMessageBox.information(
            self, self.tr("已保存"), self.tr("已保存：{0}\n备份：{1}").format(target, backup)
        )
        return True

    # ------------------------------------------------------------------
    def _update_status(self) -> None:
        if self._root is None:
            self.status_label.setText(self.tr("尚未打开文件"))
            return
        total = _count_tags(self._root)
        state = self.tr("有未保存的修改") if self._dirty else self.tr("无修改")
        self.status_label.setText(
            self.tr("已加载 {0} 个标签 · {1}").format(total, state)
        )

    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802
        if self._dirty:
            answer = QMessageBox.question(
                self,
                self.tr("未保存的修改"),
                self.tr("当前有未保存的修改，确定关闭吗？"),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
        super().closeEvent(event)
