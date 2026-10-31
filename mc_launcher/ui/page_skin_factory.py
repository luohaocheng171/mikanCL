"""皮肤工厂：64×64 皮肤像素编辑器（含第二层遮罩）+ 实时 3D 预览 + 多皮肤库。

支持画笔 / 橡皮 / 填充 / 取色 / 加亮 / 加深 / 直线 / 矩形 / 椭圆 / 喷枪，
镜像对称 / 撤销重做 / 缩放 / 网格，以及最多 8 层的多层绘画（导出时自动合并），
按部位高亮 UV，Steve / Alex 模型实时预览；皮肤可保存到本地皮肤库（data/skins），
也可从皮肤库载入或一键应用到当前账号。皮肤文件仅写本地，不上传。
"""

from __future__ import annotations

import random
import re
import time
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QIcon,
    QImage,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME
from ..config import DATA_DIR
from ..i18n import t
from .skin_view import SkinPreview3D
from .widgets import Card, card_title_row, page_header

# 部位 → (底层 UV, 第二层 UV)；都是 (x, y, w, h)
PARTS = {
    "head": ((8, 8, 8, 8), (40, 8, 8, 8)),
    "body": ((20, 20, 8, 12), (20, 36, 8, 12)),
    "right_arm": ((44, 20, 4, 12), (44, 36, 4, 12)),
    "left_arm": ((36, 52, 4, 12), (52, 52, 4, 12)),
    "right_leg": ((4, 20, 4, 12), (4, 36, 4, 12)),
    "left_leg": ((20, 52, 4, 12), (4, 52, 4, 12)),
}
PART_LABELS = {
    "head": "头部",
    "body": "身体",
    "right_arm": "右臂",
    "left_arm": "左臂",
    "right_leg": "右腿",
    "left_leg": "左腿",
}

# 常用预设色板
PRESET_COLORS = [
    "#000000", "#ffffff", "#7f7f7f", "#c0c0c0",
    "#8b4513", "#d2b48c", "#4caf50", "#2e7d32",
    "#2196f3", "#1565c0", "#e53935", "#fdd835",
]

MAX_UNDO = 40


def skins_dir() -> Path:
    folder = DATA_DIR / "skins"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


MAX_LAYERS = 8
# 形状类工具：按下-拖动预览、松开提交
SHAPE_TOOLS = ("line", "rect", "ellipse")


class SkinCanvas(QWidget):
    """可绘制的 64×64 皮肤画布。

    多层系统：self._layers[0] 为底层（皮肤贴图本体），其上为自定义层，
    显示时自上而下合成（composite），导出 PNG / 应用账号时自动合并。
    撤销重做以整份图层快照为单位，所有 QPainter 操作均有 try/finally 保护。
    """

    changed = Signal()
    history_changed = Signal(bool, bool)
    cursor_info = Signal(int, int, QColor)
    color_picked = Signal(QColor)
    layers_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._layers: list[dict] = [self._new_layer(self.tr("底层"), custom=False)]
        self._active = 0
        self._cell = 5
        self.setFixedSize(64 * self._cell, 64 * self._cell)
        self._color = QColor(0, 0, 0)
        self._tool = "brush"
        self._brush_size = 1
        self._mirror = False
        self._grid = True
        self._highlight_part: str | None = None
        self._stroke_active = False
        self._erasing = False
        self._undo: list[dict] = []
        self._redo: list[dict] = []
        self._cache: QImage | None = None
        self._shape_anchor: tuple[int, int] | None = None
        self._shape_current: tuple[int, int] | None = None
        self._rng = random.Random()

    # ---- 图层管理 -----------------------------------------------------
    @staticmethod
    def _blank_image() -> QImage:
        img = QImage(64, 64, QImage.Format_ARGB32)
        img.fill(QColor(0, 0, 0, 0))
        return img

    def _new_layer(self, name: str, custom: bool = True) -> dict:
        return {"name": name, "image": self._blank_image(), "visible": True, "custom": custom}

    def layer_count(self) -> int:
        return len(self._layers)

    def layer_name(self, index: int) -> str:
        if 0 <= index < len(self._layers):
            return str(self._layers[index]["name"])
        return ""

    def layer_visible(self, index: int) -> bool:
        return 0 <= index < len(self._layers) and bool(self._layers[index]["visible"])

    def active_layer(self) -> int:
        return self._active

    def _target(self) -> QImage:
        return self._layers[self._active]["image"]

    def add_layer(self, name: str | None = None) -> int:
        self._cancel_stroke()
        if len(self._layers) >= MAX_LAYERS:
            return -1
        self._push_undo()
        if not name:
            name = self.tr("图层 {0}").format(len(self._layers))
        self._layers.append(self._new_layer(name))
        self._active = len(self._layers) - 1
        self.layers_changed.emit()
        self._invalidate()
        return self._active

    def remove_layer(self, index: int) -> bool:
        self._cancel_stroke()
        if index <= 0 or index >= len(self._layers):  # 底层不可删除
            return False
        self._push_undo()
        self._layers.pop(index)
        if self._active >= index:
            self._active = max(0, self._active - 1)
        self.layers_changed.emit()
        self._invalidate()
        return True

    def move_layer(self, index: int, delta: int) -> bool:
        """delta=+1 上移（更靠近顶层），-1 下移；底层始终在最底。"""
        self._cancel_stroke()
        new_index = index + delta
        if index <= 0 or not (1 <= new_index < len(self._layers)):
            return False
        self._push_undo()
        layers = self._layers
        layers[index], layers[new_index] = layers[new_index], layers[index]
        if self._active == index:
            self._active = new_index
        elif self._active == new_index:
            self._active = index
        self.layers_changed.emit()
        self._invalidate()
        return True

    def set_layer_visible(self, index: int, visible: bool) -> None:
        if not (0 <= index < len(self._layers)):
            return
        if bool(self._layers[index]["visible"]) == bool(visible):
            return
        self._push_undo()
        self._layers[index]["visible"] = bool(visible)
        self._invalidate()

    def set_active_layer(self, index: int) -> None:
        # 注意：不发 layers_changed，避免与图层列表 UI 互相触发
        if 0 <= index < len(self._layers) and index != self._active:
            self._cancel_stroke()
            self._active = index

    # ---- 合成 ---------------------------------------------------------
    def composite(self) -> QImage:
        """把所有可见层自上而下合成为一张皮肤贴图（带缓存）。"""
        if self._cache is None:
            out = self._blank_image()
            painter = QPainter(out)
            try:
                for layer in self._layers:
                    if layer["visible"]:
                        painter.drawImage(0, 0, layer["image"])
            finally:
                painter.end()
            self._cache = out
        return self._cache

    @property
    def image(self) -> QImage:
        """合成后的皮肤贴图（导出 / 预览 / 取色统一走这里）。"""
        return self.composite()

    def _invalidate(self) -> None:
        self._cache = None
        self.update()
        self.changed.emit()

    # ------------------------------------------------------------------
    def set_image(self, image: QImage | None, push_history: bool = True) -> None:
        """载入整张皮肤：重置为单个底层（多层工程不随 PNG 持久化）。"""
        self._cancel_stroke()
        if push_history:
            self._push_undo()
        base = self._blank_image()
        if image is not None and not image.isNull():
            base = image.convertToFormat(QImage.Format_ARGB32).scaled(
                64, 64, Qt.IgnoreAspectRatio, Qt.FastTransformation
            )
        self._layers = [{"name": self.tr("底层"), "image": base, "visible": True, "custom": False}]
        self._active = 0
        self.layers_changed.emit()
        self._invalidate()

    def set_color(self, color: QColor) -> None:
        self._color = QColor(color)

    def set_tool(self, tool: str) -> None:
        self._cancel_stroke()
        self._tool = tool

    def set_brush_size(self, size: int) -> None:
        self._brush_size = max(1, int(size))

    def set_mirror(self, on: bool) -> None:
        self._mirror = bool(on)

    def set_grid(self, on: bool) -> None:
        self._grid = bool(on)
        self.update()

    def set_highlight(self, part: str | None) -> None:
        self._highlight_part = part or None
        self.update()

    def set_zoom(self, cell: int) -> None:
        cell = max(3, min(10, int(cell)))
        if cell == self._cell:
            return
        self._cell = cell
        self.setFixedSize(64 * cell, 64 * cell)
        self.update()

    def clear(self) -> None:
        """清空当前活动层。"""
        self._cancel_stroke()
        self._push_undo()
        self._target().fill(QColor(0, 0, 0, 0))
        self._invalidate()

    def _cancel_stroke(self) -> None:
        """中止进行中的笔画 / 形状预览（切换工具、图层、撤销前必须调用）。"""
        self._stroke_active = False
        self._erasing = False
        if self._shape_anchor is not None:
            self._shape_anchor = None
            self._shape_current = None
            self.update()

    # ---- 3D 作画接口 ---------------------------------------------------
    def begin_stroke(self) -> None:
        """3D 预览按下时调用：一次笔画只压入一份撤销快照（幂等）。"""
        if self._stroke_active or self._tool == "picker":
            return
        self._stroke_active = True
        self._push_undo()

    def end_stroke(self) -> None:
        self._stroke_active = False
        self._erasing = False

    def paint_pixel(self, x: int, y: int, erase: bool = False) -> None:
        """在指定贴图像素上应用当前工具（供 3D 预览调用）。"""
        if not (0 <= x < 64 and 0 <= y < 64):
            return
        if self._tool == "picker" and not erase:
            self._pick_pixel(x, y)
            return
        if self._tool in SHAPE_TOOLS and not erase:
            # 形状工具在 3D 上退化为单像素画笔，避免无意义的“空中拖框”
            self._apply_brush_pixel(x, y, False)
            return
        self._apply_pixel(x, y, erase or self._tool == "eraser")

    # ---- 历史记录（整份图层快照） --------------------------------------
    def _snapshot(self) -> dict:
        return {
            "layers": [
                (layer["name"], layer["image"].copy(), layer["visible"], layer["custom"])
                for layer in self._layers
            ],
            "active": self._active,
        }

    def _restore(self, snap: dict) -> None:
        self._layers = [
            {"name": name, "image": img.copy(), "visible": vis, "custom": custom}
            for name, img, vis, custom in snap["layers"]
        ]
        self._active = min(int(snap["active"]), len(self._layers) - 1)
        self.layers_changed.emit()
        self._invalidate()

    def _push_undo(self) -> None:
        self._undo.append(self._snapshot())
        if len(self._undo) > MAX_UNDO:
            self._undo.pop(0)
        self._redo.clear()
        self.history_changed.emit(True, False)

    def undo(self) -> None:
        self._cancel_stroke()
        if not self._undo:
            return
        self._redo.append(self._snapshot())
        self._restore(self._undo.pop())
        self.history_changed.emit(bool(self._undo), True)

    def redo(self) -> None:
        self._cancel_stroke()
        if not self._redo:
            return
        self._undo.append(self._snapshot())
        self._restore(self._redo.pop())
        self.history_changed.emit(True, bool(self._redo))

    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        try:
            cell = self._cell
            for y in range(64):
                for x in range(64):
                    painter.fillRect(
                        x * cell,
                        y * cell,
                        cell,
                        cell,
                        QColor("#2b2b2b" if (x + y) % 2 == 0 else "#333333"),
                    )
            painter.drawImage(self.rect(), self.composite())
            # 形状工具拖动预览（直接画在控件上，不触碰图层数据）
            if self._shape_anchor is not None and self._shape_current is not None:
                painter.setPen(QPen(QColor(self._color), max(1, self._brush_size)))
                x0, y0 = self._shape_anchor
                x1, y1 = self._shape_current

                def _c(v: int) -> int:
                    return v * cell + cell // 2

                if self._tool == "line":
                    painter.drawLine(_c(x0), _c(y0), _c(x1), _c(y1))
                elif self._tool == "rect":
                    painter.drawRect(
                        min(x0, x1) * cell,
                        min(y0, y1) * cell,
                        (abs(x1 - x0) + 1) * cell,
                        (abs(y1 - y0) + 1) * cell,
                    )
                elif self._tool == "ellipse":
                    painter.drawEllipse(
                        min(x0, x1) * cell,
                        min(y0, y1) * cell,
                        (abs(x1 - x0) + 1) * cell,
                        (abs(y1 - y0) + 1) * cell,
                    )
            if self._grid:
                painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
                for i in range(1, 64):
                    painter.drawLine(i * cell, 0, i * cell, 64 * cell)
                    painter.drawLine(0, i * cell, 64 * cell, i * cell)
            if self._highlight_part and self._highlight_part in PARTS:
                painter.setPen(QPen(QColor(0, 220, 120, 220), 2))
                painter.setBrush(QColor(0, 220, 120, 40))
                for rect in PARTS[self._highlight_part]:
                    x, y, w, h = rect
                    painter.drawRect(x * cell, y * cell, w * cell, h * cell)
        finally:
            painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        button = event.button()
        if button not in (Qt.LeftButton, Qt.RightButton):
            return
        pos = event.position().toPoint()
        pixel = self._pixel_at(pos)
        if button == Qt.LeftButton and self._tool == "picker":
            self._pick(pos)
            return
        self._stroke_active = True
        self._erasing = button == Qt.RightButton
        self._push_undo()
        if self._tool in SHAPE_TOOLS and not self._erasing:
            if pixel is not None:
                self._shape_anchor = pixel
                self._shape_current = pixel
                self.update()
            return
        if pixel is not None:
            self._apply_tool(pos)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        pos = event.position().toPoint()
        pixel = self._pixel_at(pos)
        if pixel is not None:
            self.cursor_info.emit(pixel[0], pixel[1], self.composite().pixelColor(*pixel))
        if not self._stroke_active:
            return
        if self._shape_anchor is not None:
            if pixel is not None and pixel != self._shape_current:
                self._shape_current = pixel
                self.update()
            return
        self._apply_tool(pos)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() not in (Qt.LeftButton, Qt.RightButton):
            return
        if self._shape_anchor is not None:
            end = self._pixel_at(event.position().toPoint()) or self._shape_current
            self._stamp_shape(self._shape_anchor, end)
            self._shape_anchor = None
            self._shape_current = None
        self._stroke_active = False
        self._erasing = False

    # ------------------------------------------------------------------
    def _pixel_at(self, pos: QPoint) -> tuple[int, int] | None:
        px = pos.x() // self._cell
        py = pos.y() // self._cell
        if 0 <= px < 64 and 0 <= py < 64:
            return px, py
        return None

    def _pick(self, pos: QPoint) -> None:
        pixel = self._pixel_at(pos)
        if pixel is None:
            return
        self._pick_pixel(*pixel)

    def _pick_pixel(self, px: int, py: int) -> None:
        if not (0 <= px < 64 and 0 <= py < 64):
            return
        color = QColor(self.composite().pixelColor(px, py))
        self._color = color
        self.color_picked.emit(color)

    def _apply_tool(self, pos: QPoint) -> None:
        p = self._pixel_at(pos)
        if p is None:
            return
        self._apply_pixel(p[0], p[1], self._erasing or self._tool == "eraser")

    def _apply_pixel(self, px: int, py: int, erase: bool) -> None:
        if not (0 <= px < 64 and 0 <= py < 64):
            return
        if self._tool == "fill" and not erase:
            self._fill(px, py, QColor(self._color))
            self._invalidate()
            return
        if self._tool == "spray" and not erase:
            self._spray(px, py)
            self._invalidate()
            return
        self._apply_brush_pixel(px, py, erase)

    def _apply_brush_pixel(self, px: int, py: int, erase: bool) -> None:
        color = QColor(0, 0, 0, 0) if erase else QColor(self._color)
        target = self._target()
        painter = QPainter(target)
        try:
            if erase:
                # 透明色以 SourceOver 绘制不会改变目标像素，必须用 Clear 才会真正擦除
                painter.setCompositionMode(QPainter.CompositionMode_Clear)
                color = QColor(0, 0, 0)
            half = max(0, self._brush_size - 1) // 2
            for dy in range(-half, half + 1):
                for dx in range(-half, half + 1):
                    x, y = px + dx, py + dy
                    if not (0 <= x < 64 and 0 <= y < 64):
                        continue
                    if self._tool in ("lighten", "darken") and not erase:
                        self._shade(x, y, self._tool == "lighten", painter, target)
                    else:
                        painter.setPen(QPen(color, 1))
                        painter.drawPoint(x, y)
                        if self._mirror:
                            self._mirror_pixel(x, y, color, painter)
        finally:
            painter.end()
        self._invalidate()

    def _spray(self, px: int, py: int) -> None:
        """喷枪：在半径内随机撒点，密度随笔刷增大。"""
        target = self._target()
        radius = 2 + self._brush_size * 2
        count = 6 + self._brush_size * 5
        painter = QPainter(target)
        try:
            painter.setPen(QPen(QColor(self._color), 1))
            placed = 0
            attempts = 0
            while placed < count and attempts < count * 4:
                attempts += 1
                dx = self._rng.randint(-radius, radius)
                dy = self._rng.randint(-radius, radius)
                if dx * dx + dy * dy > radius * radius:
                    continue
                x, y = px + dx, py + dy
                if 0 <= x < 64 and 0 <= y < 64:
                    painter.drawPoint(x, y)
                    placed += 1
        finally:
            painter.end()

    def _stamp_shape(self, start: tuple[int, int] | None, end: tuple[int, int] | None) -> None:
        """把预览中的直线 / 矩形 / 椭圆提交到当前层。"""
        if start is None or end is None:
            return
        target = self._target()
        painter = QPainter(target)
        try:
            painter.setPen(QPen(QColor(self._color), max(1, self._brush_size)))
            x0, y0 = start
            x1, y1 = end
            if self._tool == "line":
                painter.drawLine(x0, y0, x1, y1)
            elif self._tool == "rect":
                painter.drawRect(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))
            elif self._tool == "ellipse":
                painter.drawEllipse(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))
        finally:
            painter.end()
        self._invalidate()

    def _shade(self, x: int, y: int, lighten: bool, painter: QPainter, target: QImage) -> None:
        current = QColor(target.pixelColor(x, y))
        base = current if current.alpha() > 0 else QColor(self._color)
        if lighten:
            base = base.lighter(130)
        else:
            base = base.darker(130)
        base.setAlpha(base.alpha() if current.alpha() > 0 else 255)
        painter.setPen(QPen(base, 1))
        painter.drawPoint(x, y)
        if self._mirror:
            self._mirror_pixel(x, y, base, painter)

    def _mirror_pixel(self, x: int, y: int, color, painter) -> None:
        """在当前高亮部位内做水平镜像（左↔右对称，底层与第二层分别处理）。"""
        if self._highlight_part not in PARTS:
            # 未选部位时以整张皮肤中线镜像
            mx = 63 - x
            if 0 <= mx < 64:
                painter.setPen(QPen(color, 1))
                painter.drawPoint(mx, y)
            return
        # 底层与第二层的 UV 区域可能不连续，按像素实际所在的那个矩形镜像
        for base_x, base_y, w, h in PARTS[self._highlight_part]:
            if base_x <= x < base_x + w and base_y <= y < base_y + h:
                mx = base_x + (base_x + w - 1 - x)
                if 0 <= mx < 64:
                    painter.setPen(QPen(color, 1))
                    painter.drawPoint(mx, y)
                return

    def _fill(self, x: int, y: int, color: QColor) -> None:
        target_img = self._target()
        target = QColor(target_img.pixelColor(x, y))
        if target == color:
            return
        stack = [(x, y)]
        seen = set()
        painter = QPainter(target_img)
        try:
            painter.setPen(QPen(color, 1))
            while stack:
                cx, cy = stack.pop()
                if (cx, cy) in seen or not (0 <= cx < 64 and 0 <= cy < 64):
                    continue
                if QColor(target_img.pixelColor(cx, cy)) != target:
                    continue
                seen.add((cx, cy))
                painter.drawPoint(cx, cy)
                stack.extend([(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)])
        finally:
            painter.end()


class SkinFactoryPage(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._recent: list[QColor] = []
        self._build()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 20, 26, 20)
        outer.setSpacing(16)
        header, _ = page_header(
            self.tr("皮肤工厂"),
            self.tr("像素级绘制 64×64 皮肤（含第二层遮罩），撤销重做 / 缩放 / 多皮肤库，成品可应用到账号"),
        )
        outer.addWidget(header)

        body = QHBoxLayout()
        body.setSpacing(16)

        # ---------------- 左：画布与工具 ----------------
        canvas_card = Card()
        canvas_card.body.addWidget(
            card_title_row(self.tr("像素画布"), self.tr("左键绘制 · 右键擦除 · Ctrl+Z 撤销"))
        )
        self.canvas = SkinCanvas()
        self.canvas.changed.connect(self._on_canvas_changed)
        self.canvas.history_changed.connect(self._on_history_changed)
        self.canvas.cursor_info.connect(self._on_cursor_info)
        self.canvas.color_picked.connect(self._on_color_picked)
        canvas_card.body.addWidget(self.canvas, alignment=Qt.AlignHCenter)

        tool_row = QHBoxLayout()
        tool_row.setSpacing(6)
        self._tool_buttons = QButtonGroup(self)
        self._tool_buttons.setExclusive(True)
        tool_defs = (
            ("brush", self.tr("画笔")),
            ("eraser", self.tr("橡皮")),
            ("fill", self.tr("填充")),
            ("picker", self.tr("取色")),
            ("lighten", self.tr("加亮")),
            ("darken", self.tr("加深")),
            ("line", self.tr("直线")),
            ("rect", self.tr("矩形")),
            ("ellipse", self.tr("椭圆")),
            ("spray", self.tr("喷枪")),
        )
        for index, (tool, label) in enumerate(tool_defs):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(tool == "brush")
            btn.setObjectName("GhostCompact")
            btn.setFixedHeight(28)
            btn.clicked.connect(lambda _checked=False, value=tool: self.canvas.set_tool(value))
            self._tool_buttons.addButton(btn, index)
            tool_row.addWidget(btn)
        tool_row.addStretch(1)
        canvas_card.body.addLayout(tool_row)

        opt_row = QHBoxLayout()
        opt_row.setSpacing(8)
        opt_row.addWidget(QLabel(self.tr("笔刷")))
        size_spin = QSpinBox()
        size_spin.setRange(1, 8)
        size_spin.valueChanged.connect(self.canvas.set_brush_size)
        opt_row.addWidget(size_spin)

        self.mirror_check = QCheckBox(self.tr("镜像对称"))
        self.mirror_check.toggled.connect(self.canvas.set_mirror)
        opt_row.addWidget(self.mirror_check)

        self.grid_check = QCheckBox(self.tr("网格"))
        self.grid_check.setChecked(True)
        self.grid_check.toggled.connect(self.canvas.set_grid)
        opt_row.addWidget(self.grid_check)

        opt_row.addWidget(QLabel(self.tr("缩放")))
        zoom_combo = QComboBox()
        for cell in (4, 5, 6, 8):
            zoom_combo.addItem(f"{cell}×", cell)
        zoom_combo.setCurrentIndex(1)
        zoom_combo.currentIndexChanged.connect(
            lambda i: self.canvas.set_zoom(zoom_combo.itemData(i))
        )
        opt_row.addWidget(zoom_combo)

        undo_btn = QPushButton(self.tr("撤销"))
        undo_btn.setObjectName("GhostCompact")
        undo_btn.setEnabled(False)
        undo_btn.clicked.connect(self.canvas.undo)
        self._undo_btn = undo_btn
        opt_row.addWidget(undo_btn)
        redo_btn = QPushButton(self.tr("重做"))
        redo_btn.setObjectName("GhostCompact")
        redo_btn.setEnabled(False)
        redo_btn.clicked.connect(self.canvas.redo)
        self._redo_btn = redo_btn
        opt_row.addWidget(redo_btn)
        opt_row.addStretch(1)
        canvas_card.body.addLayout(opt_row)

        color_row = QHBoxLayout()
        color_row.setSpacing(6)
        color_row.addWidget(QLabel(self.tr("颜色")))
        self.color_btn = QPushButton("")
        self.color_btn.setFixedSize(28, 28)
        self.color_btn.setToolTip(self.tr("选择颜色"))
        self.color_btn.clicked.connect(self._pick_color)
        color_row.addWidget(self.color_btn)
        for hex_color in PRESET_COLORS:
            swatch = QPushButton("")
            swatch.setFixedSize(20, 20)
            swatch.setStyleSheet(
                f"QPushButton {{ background: {hex_color}; border: 1px solid #555; border-radius: 3px; }}"
            )
            swatch.setToolTip(hex_color)
            swatch.clicked.connect(
                lambda _checked=False, value=hex_color: self._select_color(QColor(value))
            )
            color_row.addWidget(swatch)
        self.recent_row = QHBoxLayout()
        self.recent_row.setSpacing(4)
        color_row.addSpacing(10)
        color_row.addWidget(QLabel(self.tr("最近")))
        color_row.addLayout(self.recent_row)
        color_row.addStretch(1)
        canvas_card.body.addLayout(color_row)

        part_row = QHBoxLayout()
        part_row.setSpacing(8)
        part_row.addWidget(QLabel(self.tr("部位")))
        self.part_combo = QComboBox()
        self.part_combo.addItem(self.tr("整体（不限部位）"), None)
        for key, label in PART_LABELS.items():
            self.part_combo.addItem(self.tr(label), key)
        self.part_combo.currentIndexChanged.connect(self._on_part_changed)
        part_row.addWidget(self.part_combo)

        self.status_label = QLabel(self.tr("坐标 -  颜色 -"))
        self.status_label.setObjectName("Tiny")
        part_row.addWidget(self.status_label, 1)
        canvas_card.body.addLayout(part_row)

        # ---------------- 多层编辑 ----------------
        layer_box = QHBoxLayout()
        layer_box.setSpacing(8)
        self.layers_list = QListWidget()
        self.layers_list.setFixedHeight(110)
        self.layers_list.itemChanged.connect(self._on_layer_item_changed)
        self.layers_list.currentRowChanged.connect(self._on_layer_row_changed)
        layer_box.addWidget(self.layers_list, 1)
        layer_btns = QVBoxLayout()
        layer_btns.setSpacing(4)
        add_layer_btn = QPushButton(self.tr("新建图层"))
        add_layer_btn.setObjectName("GhostCompact")
        add_layer_btn.clicked.connect(self._add_layer)
        layer_btns.addWidget(add_layer_btn)
        del_layer_btn = QPushButton(self.tr("删除图层"))
        del_layer_btn.setObjectName("GhostCompact")
        del_layer_btn.clicked.connect(self._remove_layer)
        layer_btns.addWidget(del_layer_btn)
        up_layer_btn = QPushButton(self.tr("上移"))
        up_layer_btn.setObjectName("GhostCompact")
        up_layer_btn.clicked.connect(lambda: self._move_layer(1))
        layer_btns.addWidget(up_layer_btn)
        down_layer_btn = QPushButton(self.tr("下移"))
        down_layer_btn.setObjectName("GhostCompact")
        down_layer_btn.clicked.connect(lambda: self._move_layer(-1))
        layer_btns.addWidget(down_layer_btn)
        layer_btns.addStretch(1)
        layer_box.addLayout(layer_btns)
        canvas_card.body.addLayout(layer_box)
        layer_tip = QLabel(
            self.tr("多层编辑：勾选控制图层可见性，点击选中为活动层；"
                    "自定义图层仅用于创作，导出 PNG / 保存皮肤库 / 应用账号时自动合并。")
        )
        layer_tip.setObjectName("Tiny")
        layer_tip.setWordWrap(True)
        canvas_card.body.addWidget(layer_tip)
        self.canvas.layers_changed.connect(self._reload_layers)
        self._reload_layers()

        file_row = QHBoxLayout()
        file_row.setSpacing(8)
        import_btn = QPushButton(self.tr("导入 PNG…"))
        import_btn.clicked.connect(self._import_png)
        file_row.addWidget(import_btn)
        save_btn = QPushButton(self.tr("导出 PNG…"))
        save_btn.clicked.connect(self._save_png)
        file_row.addWidget(save_btn)
        clear_btn = QPushButton(self.tr("清空画布"))
        clear_btn.clicked.connect(self._clear_canvas)
        file_row.addWidget(clear_btn)
        apply_btn = QPushButton(self.tr("应用到当前账号"))
        apply_btn.setObjectName("Primary")
        apply_btn.clicked.connect(lambda: self._apply_image(self.canvas.image))
        file_row.addWidget(apply_btn)
        file_row.addStretch(1)
        canvas_card.body.addLayout(file_row)

        body.addWidget(canvas_card, 3)

        # ---------------- 右：预览 + 皮肤库 ----------------
        right = QVBoxLayout()
        right.setSpacing(14)

        preview_card = Card()
        preview_card.body.addWidget(
            card_title_row(self.tr("3D 预览"), self.tr("选中部位后直接在 3D 模型上作画"))
        )
        self.preview = SkinPreview3D(210, 300)
        self.preview.set_paintable(True)
        self.preview.stroke_started.connect(self.canvas.begin_stroke)
        self.preview.stroke_pixel.connect(self._on_preview_stroke)
        self.preview.stroke_ended.connect(self.canvas.end_stroke)
        self.preview.hover_changed.connect(self._on_preview_hover)
        self.preview.yaw_changed.connect(self._on_preview_yaw)
        preview_card.body.addWidget(self.preview, alignment=Qt.AlignHCenter)

        layer_row = QHBoxLayout()
        layer_row.setSpacing(6)
        layer_row.addWidget(QLabel(self.tr("3D 图层")))
        self.layer_combo = QComboBox()
        self.layer_combo.addItem(self.tr("底层"), "base")
        self.layer_combo.addItem(self.tr("第二层"), "overlay")
        self.layer_combo.currentIndexChanged.connect(
            lambda i: self.preview.set_layer(self.layer_combo.itemData(i))
        )
        layer_row.addWidget(self.layer_combo)
        layer_row.addStretch(1)
        preview_card.body.addLayout(layer_row)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(6)
        mode_row.addWidget(QLabel(self.tr("操作模式")))
        self.mode_brush = QPushButton(self.tr("画笔"))
        self.mode_brush.setCheckable(True)
        self.mode_brush.setChecked(True)
        self.mode_brush.setFixedHeight(28)
        self.mode_mouse = QPushButton(self.tr("鼠标"))
        self.mode_mouse.setCheckable(True)
        self.mode_mouse.setFixedHeight(28)
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        self._mode_group.addButton(self.mode_brush)
        self._mode_group.addButton(self.mode_mouse)
        self.mode_brush.clicked.connect(lambda: self.preview.set_mode("brush"))
        self.mode_mouse.clicked.connect(lambda: self.preview.set_mode("mouse"))
        mode_row.addWidget(self.mode_brush)
        mode_row.addWidget(self.mode_mouse)
        mode_row.addStretch(1)
        preview_card.body.addLayout(mode_row)

        view_row = QHBoxLayout()
        view_row.setSpacing(6)
        view_row.addWidget(QLabel(self.tr("视角")))
        self.yaw_slider = QSlider(Qt.Horizontal)
        self.yaw_slider.setRange(0, 359)
        self.yaw_slider.setFixedWidth(96)
        self.yaw_slider.valueChanged.connect(self.preview.set_yaw)
        view_row.addWidget(self.yaw_slider)
        left_btn = QPushButton(self.tr("左转"))
        left_btn.setObjectName("GhostCompact")
        left_btn.setFixedHeight(28)
        left_btn.clicked.connect(lambda: self.preview.rotate_by(-15))
        view_row.addWidget(left_btn)
        right_btn = QPushButton(self.tr("右转"))
        right_btn.setObjectName("GhostCompact")
        right_btn.setFixedHeight(28)
        right_btn.clicked.connect(lambda: self.preview.rotate_by(15))
        view_row.addWidget(right_btn)
        reset_view_btn = QPushButton(self.tr("复位视角"))
        reset_view_btn.setObjectName("GhostCompact")
        reset_view_btn.setFixedHeight(28)
        reset_view_btn.clicked.connect(self.preview.reset_view)
        view_row.addWidget(reset_view_btn)
        self.auto_rotate = QCheckBox(self.tr("自动旋转"))
        self.auto_rotate.toggled.connect(self.preview.set_auto_rotate)
        view_row.addWidget(self.auto_rotate)
        view_row.addStretch(1)
        preview_card.body.addLayout(view_row)

        zoom_row = QHBoxLayout()
        zoom_row.setSpacing(6)
        zoom_row.addWidget(QLabel(self.tr("缩放")))
        zoom_out_btn = QPushButton("－")
        zoom_out_btn.setObjectName("GhostCompact")
        zoom_out_btn.setFixedSize(28, 28)
        zoom_out_btn.setToolTip(self.tr("缩小"))
        zoom_out_btn.clicked.connect(lambda: self.preview.zoom_by(-0.15))
        zoom_row.addWidget(zoom_out_btn)
        zoom_in_btn = QPushButton("＋")
        zoom_in_btn.setObjectName("GhostCompact")
        zoom_in_btn.setFixedSize(28, 28)
        zoom_in_btn.setToolTip(self.tr("放大"))
        zoom_in_btn.clicked.connect(lambda: self.preview.zoom_by(0.15))
        zoom_row.addWidget(zoom_in_btn)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setObjectName("Tiny")
        self.zoom_label.setMinimumWidth(42)
        self.zoom_label.setAlignment(Qt.AlignCenter)
        self.preview.zoom_changed.connect(
            lambda f: self.zoom_label.setText(f"{int(round(f * 100))}%")
        )
        zoom_row.addWidget(self.zoom_label)
        zoom_row.addStretch(1)
        preview_card.body.addLayout(zoom_row)

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel(self.tr("模型")))
        model_combo = QComboBox()
        model_combo.addItem(self.tr("经典（Steve）"), "steve")
        model_combo.addItem(self.tr("纤细（Alex）"), "alex")
        model_combo.currentIndexChanged.connect(
            lambda i: self.preview.set_model(model_combo.itemData(i))
        )
        model_row.addWidget(model_combo)
        model_row.addStretch(1)
        preview_card.body.addLayout(model_row)

        hint = QLabel(
            self.tr(
                "「画笔」模式：左键作画、右键擦除；「鼠标」模式：拖动旋转 360°、右键平移、"
                "滚轮缩放；Shift + 拖动或中键可随时旋转。切换图层可编辑帽子 / 外套 / 袖 / 裤腿。"
            )
        )
        hint.setObjectName("Tiny")
        hint.setWordWrap(True)
        preview_card.body.addWidget(hint)
        right.addWidget(preview_card)

        library_card = Card()
        library_card.body.addWidget(
            card_title_row(self.tr("皮肤库"), self.tr("多皮肤保存、载入与删除"))
        )
        self.skin_list = QListWidget()
        self.skin_list.setFixedHeight(150)
        self.skin_list.itemDoubleClicked.connect(lambda _i: self._load_selected_skin())
        library_card.body.addWidget(self.skin_list)

        save_row = QHBoxLayout()
        save_row.setSpacing(6)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(self.tr("新皮肤名称"))
        save_row.addWidget(self.name_edit, 1)
        save_to_lib = QPushButton(self.tr("保存到皮肤库"))
        save_to_lib.setObjectName("PrimaryCompact")
        save_to_lib.clicked.connect(self._save_to_library)
        save_row.addWidget(save_to_lib)
        library_card.body.addLayout(save_row)

        lib_row = QHBoxLayout()
        lib_row.setSpacing(6)
        load_btn = QPushButton(self.tr("载入"))
        load_btn.clicked.connect(self._load_selected_skin)
        lib_row.addWidget(load_btn)
        apply_lib_btn = QPushButton(self.tr("应用"))
        apply_lib_btn.clicked.connect(self._apply_selected_skin)
        lib_row.addWidget(apply_lib_btn)
        delete_btn = QPushButton(self.tr("删除"))
        delete_btn.setObjectName("GhostCompact")
        delete_btn.clicked.connect(self._delete_selected_skin)
        lib_row.addWidget(delete_btn)
        refresh_btn = QPushButton(self.tr("刷新"))
        refresh_btn.setObjectName("GhostCompact")
        refresh_btn.clicked.connect(self._reload_library)
        lib_row.addWidget(refresh_btn)
        lib_row.addStretch(1)
        library_card.body.addLayout(lib_row)

        tip = QLabel(
            self.tr(
                "皮肤库保存在 data/skins，双击列表项可直接载入；"
                "载入/切换皮肤不会向服务器上传任何文件。"
            )
        )
        tip.setObjectName("Tiny")
        tip.setWordWrap(True)
        library_card.body.addWidget(tip)
        right.addWidget(library_card)
        right.addStretch(1)

        body.addLayout(right, 2)
        outer.addLayout(body, 1)

        self._select_color(QColor("#3f76d1"))
        self._on_canvas_changed()
        self._reload_library()

        # 快捷键：Ctrl+Z 撤销、Ctrl+Y / Ctrl+Shift+Z 重做
        QShortcut(QKeySequence.StandardKey.Undo, self, activated=self.canvas.undo)
        QShortcut(QKeySequence.StandardKey.Redo, self, activated=self.canvas.redo)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, activated=self.canvas.redo)

    # ------------------------------------------------------------------
    def _on_canvas_changed(self) -> None:
        self.preview.set_skin(QImage(self.canvas.image))

    def _on_history_changed(self, can_undo: bool, can_redo: bool) -> None:
        self._undo_btn.setEnabled(can_undo)
        self._redo_btn.setEnabled(can_redo)

    def _on_cursor_info(self, x: int, y: int, color: QColor) -> None:
        alpha = color.alpha()
        if alpha == 0:
            text = f"({x}, {y})  {self.tr('透明')}"
        else:
            text = f"({x}, {y})  {color.name().upper()}  α{alpha}"
        self.status_label.setText(text)

    def _on_preview_stroke(self, u: int, v: int, erase: bool) -> None:
        self.canvas.paint_pixel(u, v, erase)

    def _on_preview_hover(self, part: str, u: int, v: int) -> None:
        if not part or not (0 <= u < 64 and 0 <= v < 64):
            self.status_label.setText(self.tr("坐标 -  颜色 -"))
            return
        label = part
        for i in range(self.part_combo.count()):
            if self.part_combo.itemData(i) == part:
                label = self.part_combo.itemText(i)
                break
        color = QColor(self.canvas.image.pixelColor(u, v))
        if color.alpha() == 0:
            text = f"{label}  ({u}, {v})  {self.tr('透明')}"
        else:
            text = f"{label}  ({u}, {v})  {color.name().upper()}  α{color.alpha()}"
        self.status_label.setText(text)

    def _on_preview_yaw(self, degrees: int) -> None:
        self.yaw_slider.blockSignals(True)
        self.yaw_slider.setValue(degrees)
        self.yaw_slider.blockSignals(False)

    def _on_color_picked(self, color: QColor) -> None:
        self._select_color(color)

    def _select_color(self, color: QColor) -> None:
        self.canvas.set_color(color)
        self.color_btn.setStyleSheet(
            f"QPushButton {{ background: {color.name()}; border: 1px solid #666; border-radius: 6px; }}"
        )
        if color.isValid() and color.alpha() > 0:
            self._push_recent(QColor(color))

    def _push_recent(self, color: QColor) -> None:
        if any(c.name() == color.name() for c in self._recent):
            return
        self._recent.insert(0, QColor(color))
        del self._recent[6:]
        while self.recent_row.count():
            item = self.recent_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for color in self._recent:
            swatch = QPushButton("")
            swatch.setFixedSize(20, 20)
            swatch.setStyleSheet(
                f"QPushButton {{ background: {color.name()}; border: 1px solid #555; border-radius: 3px; }}"
            )
            swatch.setToolTip(color.name())
            swatch.clicked.connect(
                lambda _checked=False, value=color: self._select_color(QColor(value))
            )
            self.recent_row.addWidget(swatch)

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(self.canvas._color, self, self.tr("选择颜色"))
        if color.isValid():
            self._select_color(color)

    def _on_part_changed(self, index: int) -> None:
        part = self.part_combo.itemData(index)
        self.canvas.set_highlight(part)
        self.preview.set_part_filter(part)

    def _clear_canvas(self) -> None:
        self.canvas.clear()

    # ---- 多层编辑 -----------------------------------------------------
    def _reload_layers(self) -> None:
        """根据画布图层状态重建列表：顶行 = 最上层，勾选 = 可见，选中 = 活动层。"""
        self.layers_list.blockSignals(True)
        self.layers_list.clear()
        count = self.canvas.layer_count()
        for row, index in enumerate(range(count - 1, -1, -1)):
            item = QListWidgetItem(self.canvas.layer_name(index))
            item.setData(Qt.UserRole, index)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if self.canvas.layer_visible(index) else Qt.Unchecked)
            self.layers_list.addItem(item)
            if index == self.canvas.active_layer():
                self.layers_list.setCurrentRow(row)
        self.layers_list.blockSignals(False)

    def _current_layer_index(self) -> int | None:
        item = self.layers_list.currentItem()
        if item is None:
            return None
        data = item.data(Qt.UserRole)
        return int(data) if data is not None else None

    def _on_layer_item_changed(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.UserRole)
        if data is None:
            return
        self.canvas.set_layer_visible(int(data), item.checkState() == Qt.Checked)

    def _on_layer_row_changed(self, row: int) -> None:
        item = self.layers_list.item(row)
        if item is None:
            return
        data = item.data(Qt.UserRole)
        if data is not None:
            self.canvas.set_active_layer(int(data))

    def _add_layer(self) -> None:
        name, ok = QInputDialog.getText(
            self,
            self.tr("新建图层"),
            self.tr("图层名称"),
            text=self.tr("图层 {0}").format(self.canvas.layer_count()),
        )
        if not ok:
            return
        if self.canvas.add_layer(name.strip() or None) < 0:
            QMessageBox.information(
                self, APP_NAME, self.tr("最多支持 {0} 个图层。").format(MAX_LAYERS)
            )

    def _remove_layer(self) -> None:
        index = self._current_layer_index()
        if index is None:
            return
        if index == 0:
            QMessageBox.information(self, APP_NAME, self.tr("底层不可删除。"))
            return
        answer = QMessageBox.question(
            self,
            APP_NAME,
            self.tr("确定删除图层「{0}」？该层内容将丢失。").format(self.canvas.layer_name(index)),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.canvas.remove_layer(index)

    def _move_layer(self, delta: int) -> None:
        index = self._current_layer_index()
        if index is None:
            return
        self.canvas.move_layer(index, delta)

    def _import_png(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("导入皮肤 PNG"), str(Path.home()), "PNG 图片 (*.png)"
        )
        if not path:
            return
        image = QImage(path)
        if image.isNull():
            QMessageBox.warning(self, APP_NAME, self.tr("无法读取该图片。"))
            return
        self.canvas.set_image(image)

    def _save_png(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("保存皮肤 PNG"), str(Path.home() / "skin.png"), "PNG 图片 (*.png)"
        )
        if not path:
            return
        if not self.canvas.image.save(path, "PNG"):
            QMessageBox.warning(self, APP_NAME, self.tr("保存失败。"))

    # ---- 皮肤库 -------------------------------------------------------
    def _reload_library(self) -> None:
        self.skin_list.clear()
        folder = skins_dir()
        files = sorted(folder.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in files:
            item = QListWidgetItem(path.stem)
            item.setData(Qt.UserRole, str(path))
            thumb = QPixmap(str(path))
            if not thumb.isNull():
                item.setIcon(QIcon(thumb))
                item.setToolTip(self.tr("双击载入 {0}").format(path.name))
            self.skin_list.addItem(item)
        if not files:
            item = QListWidgetItem(self.tr("皮肤库为空，编辑后点「保存到皮肤库」"))
            item.setFlags(Qt.NoItemFlags)
            self.skin_list.addItem(item)

    def _selected_path(self) -> Path | None:
        item = self.skin_list.currentItem()
        if item is None:
            return None
        data = item.data(Qt.UserRole)
        if not data:
            return None
        path = Path(str(data))
        return path if path.exists() else None

    def _save_to_library(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            name = time.strftime("skin-%Y%m%d-%H%M%S")
        safe = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]", "_", name).strip("_")
        if not safe:
            safe = time.strftime("skin-%Y%m%d-%H%M%S")
        target = skins_dir() / f"{safe}.png"
        if target.exists():
            answer = QMessageBox.question(
                self,
                APP_NAME,
                self.tr("皮肤「{0}」已存在，是否覆盖？").format(safe),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        if not self.canvas.image.save(str(target), "PNG"):
            QMessageBox.warning(self, APP_NAME, self.tr("保存皮肤文件失败。"))
            return
        self.name_edit.clear()
        self._reload_library()
        self.ctx.bus.toast.emit(self.tr("皮肤已保存到皮肤库：{0}").format(safe))

    def _load_selected_skin(self) -> None:
        path = self._selected_path()
        if path is None:
            QMessageBox.information(self, APP_NAME, self.tr("请先在皮肤库中选择一个皮肤。"))
            return
        image = QImage(str(path))
        if image.isNull():
            QMessageBox.warning(self, APP_NAME, self.tr("无法读取该皮肤文件。"))
            return
        self.canvas.set_image(image)
        self.name_edit.setText(path.stem)
        self.ctx.bus.toast.emit(self.tr("已载入皮肤：{0}").format(path.stem))

    def _apply_selected_skin(self) -> None:
        path = self._selected_path()
        if path is None:
            QMessageBox.information(self, APP_NAME, self.tr("请先在皮肤库中选择一个皮肤。"))
            return
        image = QImage(str(path))
        if image.isNull():
            QMessageBox.warning(self, APP_NAME, self.tr("无法读取该皮肤文件。"))
            return
        self._apply_image(image)

    def _delete_selected_skin(self) -> None:
        path = self._selected_path()
        if path is None:
            QMessageBox.information(self, APP_NAME, self.tr("请先在皮肤库中选择一个皮肤。"))
            return
        answer = QMessageBox.question(
            self,
            APP_NAME,
            self.tr("确定删除皮肤「{0}」？").format(path.stem),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            path.unlink()
        except OSError:
            QMessageBox.warning(self, APP_NAME, self.tr("删除失败。"))
            return
        self._reload_library()
        self.ctx.bus.toast.emit(self.tr("已删除皮肤：{0}").format(path.stem))

    def _apply_image(self, image: QImage) -> None:
        account = self.ctx.current_account()
        if account is None:
            QMessageBox.information(self, APP_NAME, self.tr("请先选择一个账号。"))
            return
        target = skins_dir() / f"{account.name}.png"
        if not image.save(str(target), "PNG"):
            QMessageBox.warning(self, APP_NAME, self.tr("保存皮肤文件失败。"))
            return
        account.skin_path = str(target)
        self.ctx.accounts.update(account)
        self.ctx.bus.accounts_changed.emit()
        self._reload_library()
        self.ctx.bus.toast.emit(t("AccountsPage", "皮肤已应用到账号 {0}", account.name))

    def shutdown(self) -> None:
        pass


__all__ = ["SkinFactoryPage"]
