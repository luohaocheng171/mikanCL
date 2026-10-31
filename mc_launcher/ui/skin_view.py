"""皮肤 3D 预览与 3D 绘画。

用等轴测投影把 64×64 皮肤贴图贴到方块模型上（无需 OpenGL），支持：
- 底层 + 第二层（overlay：帽子 / 外套 / 袖子 / 裤腿）透明叠加渲染；
- Steve（4px 手臂）/ Alex（3px 手臂）两种模型；
- 鼠标拖动 360° 旋转（水平 yaw + 上下 pitch）、滚轮缩放、右键平移；
- 画笔 / 鼠标双模式切换：画笔模式左键作画、右键擦除；鼠标模式拖动旋转；
- 屏幕点 → 贴图 UV 的拾取，从而在 3D 模型上直接作画。
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QTransform,
)
from PySide6.QtWidgets import QWidget

_COS30 = 0.8660254

# 部件尺寸（单位：皮肤像素，x 左右、y 上下、z 前后），原点在双脚中心
_HEAD = (-4.0, 4.0, 24.0, 32.0, -4.0, 4.0)
_BODY = (-4.0, 4.0, 12.0, 24.0, -2.0, 2.0)
_ARM_L = (-8.0, -4.0, 12.0, 24.0, -2.0, 2.0)
_ARM_R = (4.0, 8.0, 12.0, 24.0, -2.0, 2.0)
_LEG_L = (-4.0, 0.0, 0.0, 12.0, -2.0, 2.0)
_LEG_R = (0.0, 4.0, 0.0, 12.0, -2.0, 2.0)
_ARM_L_SLIM = (-7.0, -4.0, 12.0, 24.0, -2.0, 2.0)
_ARM_R_SLIM = (4.0, 7.0, 12.0, 24.0, -2.0, 2.0)

# 面法线（"right" 为 x1 面，"left" 为 x0 面，"front" 为 z1 面）
_FACE_NORMALS = {
    "front": (0.0, 0.0, 1.0),
    "back": (0.0, 0.0, -1.0),
    "right": (1.0, 0.0, 0.0),
    "left": (-1.0, 0.0, 0.0),
    "top": (0.0, 1.0, 0.0),
    "bottom": (0.0, -1.0, 0.0),
}
_SHADE = {"front": 12, "right": 30, "top": 0, "left": 26, "back": 18, "bottom": 42}

# 每个部件 6 个面的 UV：(u, v, w, h)；64×64 皮肤的第二层在标准布局内偏移
_UV_HEAD = {
    "front": (8, 8, 8, 8),
    "right": (0, 8, 8, 8),
    "left": (16, 8, 8, 8),
    "back": (24, 8, 8, 8),
    "top": (8, 0, 8, 8),
    "bottom": (16, 0, 8, 8),
}
_UV_HEAD_OVER = {
    "front": (40, 8, 8, 8),
    "right": (32, 8, 8, 8),
    "left": (48, 8, 8, 8),
    "back": (56, 8, 8, 8),
    "top": (40, 0, 8, 8),
    "bottom": (48, 0, 8, 8),
}
_UV_BODY = {
    "front": (20, 20, 8, 12),
    "right": (16, 20, 4, 12),
    "left": (28, 20, 4, 12),
    "back": (32, 20, 8, 12),
    "top": (20, 16, 8, 4),
    "bottom": (28, 16, 8, 4),
}
_UV_BODY_OVER = {
    "front": (20, 36, 8, 12),
    "right": (16, 36, 4, 12),
    "left": (28, 36, 4, 12),
    "back": (32, 36, 8, 12),
    "top": (20, 32, 8, 4),
    "bottom": (28, 32, 8, 4),
}
_UV_ARM_R = {
    "front": (44, 20, 4, 12),
    "right": (40, 20, 4, 12),
    "left": (48, 20, 4, 12),
    "back": (52, 20, 4, 12),
    "top": (44, 16, 4, 4),
    "bottom": (48, 16, 4, 4),
}
_UV_ARM_R_OVER = {
    "front": (44, 36, 4, 12),
    "right": (40, 36, 4, 12),
    "left": (48, 36, 4, 12),
    "back": (52, 36, 4, 12),
    "top": (44, 32, 4, 4),
    "bottom": (48, 32, 4, 4),
}
_UV_ARM_L = {
    "front": (36, 52, 4, 12),
    "right": (32, 52, 4, 12),
    "left": (40, 52, 4, 12),
    "back": (44, 52, 4, 12),
    "top": (36, 48, 4, 4),
    "bottom": (40, 48, 4, 4),
}
_UV_ARM_L_OVER = {
    "front": (52, 52, 4, 12),
    "right": (48, 52, 4, 12),
    "left": (56, 52, 4, 12),
    "back": (60, 52, 4, 12),
    "top": (52, 48, 4, 4),
    "bottom": (56, 48, 4, 4),
}
_UV_LEG_R = {
    "front": (4, 20, 4, 12),
    "right": (0, 20, 4, 12),
    "left": (8, 20, 4, 12),
    "back": (12, 20, 4, 12),
    "top": (4, 16, 4, 4),
    "bottom": (8, 16, 4, 4),
}
_UV_LEG_R_OVER = {
    "front": (4, 36, 4, 12),
    "right": (0, 36, 4, 12),
    "left": (8, 36, 4, 12),
    "back": (12, 36, 4, 12),
    "top": (4, 32, 4, 4),
    "bottom": (8, 32, 4, 4),
}
_UV_LEG_L = {
    "front": (20, 52, 4, 12),
    "right": (16, 52, 4, 12),
    "left": (24, 52, 4, 12),
    "back": (28, 52, 4, 12),
    "top": (20, 48, 4, 4),
    "bottom": (24, 48, 4, 4),
}
_UV_LEG_L_OVER = {
    "front": (4, 52, 4, 12),
    "right": (0, 52, 4, 12),
    "left": (8, 52, 4, 12),
    "back": (12, 52, 4, 12),
    "top": (4, 48, 4, 4),
    "bottom": (8, 48, 4, 4),
}
# Alex（苗条模型）：手臂宽 3 像素
_UV_ARM_R_SLIM = {
    "front": (44, 20, 3, 12),
    "right": (40, 20, 4, 12),
    "left": (47, 20, 4, 12),
    "back": (51, 20, 3, 12),
    "top": (44, 16, 3, 4),
    "bottom": (47, 16, 3, 4),
}
_UV_ARM_R_SLIM_OVER = {
    "front": (44, 36, 3, 12),
    "right": (40, 36, 4, 12),
    "left": (47, 36, 4, 12),
    "back": (51, 36, 3, 12),
    "top": (44, 32, 3, 4),
    "bottom": (47, 32, 3, 4),
}
_UV_ARM_L_SLIM = {
    "front": (36, 52, 3, 12),
    "right": (32, 52, 4, 12),
    "left": (39, 52, 4, 12),
    "back": (43, 52, 3, 12),
    "top": (36, 48, 3, 4),
    "bottom": (39, 48, 3, 4),
}
_UV_ARM_L_SLIM_OVER = {
    "front": (52, 52, 3, 12),
    "right": (48, 52, 4, 12),
    "left": (55, 52, 4, 12),
    "back": (59, 52, 3, 12),
    "top": (52, 48, 3, 4),
    "bottom": (55, 48, 3, 4),
}
# 披风贴图：主区域为 (0,0)-(10,16)，右侧厚度面取主区域最右一列
_UV_CAPE_MAIN = (0, 0, 10, 16)
_UV_CAPE_SIDE = (9, 0, 1, 16)


def _face_points(name, x0, x1, y0, y1, z0, z1, project) -> list[QPointF]:
    """按 [左上, 右上, 右下, 左下] 的顺序返回某个面的四个投影点。"""
    if name == "front":
        corners = ((x0, y1, z1), (x1, y1, z1), (x1, y0, z1), (x0, y0, z1))
    elif name == "back":
        corners = ((x1, y1, z0), (x0, y1, z0), (x0, y0, z0), (x1, y0, z0))
    elif name == "right":
        corners = ((x1, y1, z0), (x1, y1, z1), (x1, y0, z1), (x1, y0, z0))
    elif name == "left":
        corners = ((x0, y1, z1), (x0, y1, z0), (x0, y0, z0), (x0, y0, z1))
    elif name == "top":
        corners = ((x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1))
    else:  # bottom
        corners = ((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1))
    return [project(*corner) for corner in corners]


class SkinPreview3D(QWidget):
    """轻量 3D 皮肤预览 / 绘画板：按等轴测投影贴图，无需 OpenGL。"""

    stroke_started = Signal()
    stroke_pixel = Signal(int, int, bool)  # u, v, 是否擦除
    stroke_ended = Signal()
    hover_changed = Signal(str, int, int)  # 部位 key, u, v（无命中时为空串 / -1）
    yaw_changed = Signal(int)
    pitch_changed = Signal(int)
    zoom_changed = Signal(float)

    def __init__(self, width: int = 150, height: int = 200, parent=None):
        super().__init__(parent)
        self.setFixedSize(width, height)
        self._image: QImage | None = None
        self._cape: QImage | None = None
        self._model = "steve"
        self._layer = "base"
        self._part_filter: str | None = None
        self._paintable = False
        self._mode = "brush"  # brush=作画, mouse=只旋转查看
        self._yaw = 0.0
        self._pitch = 0.0
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._hits: list[tuple] = []
        self._last_pos: QPointF | None = None
        self._painting = False
        self._erase = False
        self._rotating = False
        self._panning = False
        self._last_x = 0.0
        self._last_y = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._auto_step)

    # ------------------------------------------------------------------
    def set_skin(self, image: QImage | None, cape: QImage | None = None) -> None:
        """设置皮肤；可选同时设置披风（不传则不绘制披风）。"""
        self._image = image if image is not None and not image.isNull() else None
        self._cape = cape if cape is not None and not cape.isNull() else None
        self.update()

    def set_cape(self, image: QImage | None) -> None:
        """皮肤异步加载完成后单独设置披风；传 None 或无效图片即清除。"""
        self._cape = image if image is not None and not image.isNull() else None
        self.update()

    def clear_cape(self) -> None:
        self.set_cape(None)

    def clear_skin(self) -> None:
        self.set_skin(None)

    def set_model(self, model: str) -> None:
        """切换 Steve（经典手臂 4px）/ Alex（苗条手臂 3px）模型。"""
        self._model = "alex" if str(model).lower() in ("alex", "slim") else "steve"
        self.update()

    def set_layer(self, layer: str) -> None:
        """3D 作画的目标图层：base（底层）或 overlay（第二层）。"""
        self._layer = "overlay" if str(layer).lower() == "overlay" else "base"
        self.update()

    def set_part_filter(self, part: str | None) -> None:
        """限制 3D 作画只能落在指定部位；传 None 表示整身都可画。"""
        self._part_filter = part or None

    def set_paintable(self, on: bool) -> None:
        self._paintable = bool(on)
        self.setMouseTracking(self._paintable)
        self.setCursor(Qt.CrossCursor if self._paintable else Qt.ArrowCursor)

    def set_yaw(self, degrees: float) -> None:
        value = float(degrees) % 360.0
        if abs(value - self._yaw) < 1e-6:
            return
        self._yaw = value
        self.update()
        self.yaw_changed.emit(int(round(value)) % 360)

    def set_pitch(self, degrees: float) -> None:
        """上下视角（绕 X 轴），限制在 ±89° 避免翻转。"""
        value = max(-89.0, min(89.0, float(degrees)))
        if abs(value - self._pitch) < 1e-6:
            return
        self._pitch = value
        self.update()
        self.pitch_changed.emit(int(round(value)))

    def set_zoom(self, factor: float) -> None:
        factor = max(0.2, min(8.0, float(factor)))
        if abs(factor - self._zoom) < 1e-6:
            return
        self._zoom = factor
        self.update()
        self.zoom_changed.emit(factor)

    def zoom_by(self, delta: float) -> None:
        self.set_zoom(self._zoom * (1.0 + delta))

    def pan_by(self, dx: float, dy: float) -> None:
        self._pan_x += dx
        self._pan_y += dy
        self.update()

    def set_mode(self, mode: str) -> None:
        """交互模式：brush（按当前工具作画）/ mouse（仅旋转查看）。"""
        self._mode = "mouse" if str(mode).lower() == "mouse" else "brush"
        self.setCursor(
            Qt.OpenHandCursor if self._mode == "mouse"
            else (Qt.CrossCursor if self._paintable else Qt.ArrowCursor)
        )

    def set_auto_rotate(self, on: bool) -> None:
        if on:
            self._timer.start()
        else:
            self._timer.stop()

    def rotate_by(self, delta_degrees: float) -> None:
        """在当前视角基础上旋转指定角度（供界面按钮调用，不依赖鼠标）。"""
        self.set_yaw(self._yaw + float(delta_degrees))

    def reset_view(self) -> None:
        """恢复默认视角（方向、俯仰、缩放、平移全部复位）。"""
        self._pitch = 0.0
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self.set_yaw(0.0)
        self.pitch_changed.emit(0)
        self.zoom_changed.emit(1.0)
        self.update()

    def _auto_step(self) -> None:
        self.set_yaw(self._yaw + 3.0)

    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        painter = QPainter(self)
        try:
            self._paint(painter)
        finally:
            # 绘制中途出现任何异常也必须结束 painter，否则 Qt 会反复报
            # "QBackingStore::endPaint() called with active painter"
            painter.end()

    def _paint(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), Qt.transparent)
        background = QPainterPath()
        background.addRoundedRect(
            QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0), 16, 16
        )
        painter.setClipPath(background)
        painter.fillPath(background, QColor("#0f1813"))

        scale = min(
            (self.width() - 16) / (24 * _COS30),
            (self.height() - 16) / 44.0,
        ) * self._zoom
        offset_x = self.width() / 2 + self._pan_x
        offset_y = (self.height() + 38 * scale) / 2 + self._pan_y
        yaw = math.radians(self._yaw)
        pitch = math.radians(self._pitch)
        cos_a = math.cos(yaw)
        sin_a = math.sin(yaw)
        cos_p = math.cos(pitch)
        sin_p = math.sin(pitch)

        def rotated(x: float, y: float, z: float) -> tuple[float, float, float]:
            # 先绕 X 轴俯仰（看头顶 / 脚底），再绕 Y 轴水平旋转
            y2 = y * cos_p - z * sin_p
            z2 = y * sin_p + z * cos_p
            x3 = x * cos_a - z2 * sin_a
            z3 = x * sin_a + z2 * cos_a
            return (x3, y2, z3)

        def project(x: float, y: float, z: float) -> QPointF:
            rx, ry, rz = rotated(x, y, z)
            return QPointF(
                (rx - rz) * _COS30 * scale + offset_x,
                (rx + rz) * 0.5 * scale - ry * scale + offset_y,
            )

        def depth(x: float, y: float, z: float) -> float:
            rx, ry, rz = rotated(x, y, z)
            return rx + ry + rz

        items: list[dict] = []
        image = self._image
        if image is not None:
            full = image.height() >= 64
            slim = self._model == "alex"
            if slim:
                arm_l_box, arm_l_uv, arm_l_over = (
                    _ARM_L_SLIM,
                    _UV_ARM_L_SLIM,
                    _UV_ARM_L_SLIM_OVER,
                )
                arm_r_box, arm_r_uv, arm_r_over = (
                    _ARM_R_SLIM,
                    _UV_ARM_R_SLIM,
                    _UV_ARM_R_SLIM_OVER,
                )
            else:
                arm_l_box, arm_l_uv, arm_l_over = (_ARM_L, _UV_ARM_L, _UV_ARM_L_OVER)
                arm_r_box, arm_r_uv, arm_r_over = (_ARM_R, _UV_ARM_R, _UV_ARM_R_OVER)
            # 64×32 旧皮肤没有左臂/左腿的独立贴图，复用右侧贴图
            definitions = [
                ("left_leg", _LEG_L, _UV_LEG_L if full else _UV_LEG_R, _UV_LEG_L_OVER),
                ("right_leg", _LEG_R, _UV_LEG_R, _UV_LEG_R_OVER),
                ("body", _BODY, _UV_BODY, _UV_BODY_OVER),
                ("left_arm", arm_l_box, arm_l_uv if full else arm_r_uv, arm_l_over),
                ("right_arm", arm_r_box, arm_r_uv, arm_r_over),
                ("head", _HEAD, _UV_HEAD, _UV_HEAD_OVER),
            ]
            for part, box, uvs, over in definitions:
                cx = (box[0] + box[1]) / 2.0
                cy = (box[2] + box[3]) / 2.0
                cz = (box[4] + box[5]) / 2.0
                items.append(
                    {
                        "kind": "box",
                        "part": part,
                        "layer": "base",
                        "box": box,
                        "uvs": uvs,
                        "inflate": 0.0,
                        "key": (depth(cx, cy, cz), 0),
                    }
                )
                if part == "head":
                    show_over = image.width() >= 64 and image.height() >= 16
                else:
                    show_over = full
                if show_over:
                    items.append(
                        {
                            "kind": "box",
                            "part": part,
                            "layer": "overlay",
                            "box": box,
                            "uvs": over,
                            "inflate": 0.6,
                            "key": (depth(cx, cy, cz), 1),
                        }
                    )
        cape = self._cape
        if cape is not None and not cape.isNull():
            items.append({"kind": "cape", "key": (depth(0.0, 16.0, -3.0), 0)})

        hits: list[tuple] = []
        for item in sorted(items, key=lambda it: it["key"]):
            if item["kind"] == "cape":
                self._draw_cape(painter, cape, project)
                continue
            box = item["box"]
            inflate = item["inflate"]
            x0, x1, y0, y1, z0, z1 = (
                box[0] - inflate,
                box[1] + inflate,
                box[2] - inflate,
                box[3] + inflate,
                box[4] - inflate,
                box[5] + inflate,
            )
            overlay = item["layer"] == "overlay"
            for name in _FACE_NORMALS:
                uv = item["uvs"].get(name)
                if uv is None:
                    continue
                u0, v0, w, h = uv
                if u0 + w > image.width() or v0 + h > image.height():
                    continue  # 64×32 旧皮肤没有该层的贴图区域
                nx, ny, nz = rotated(*_FACE_NORMALS[name])
                if nx + ny + nz <= 0.0:
                    continue  # 背面剔除
                points = _face_points(name, x0, x1, y0, y1, z0, z1, project)
                if abs((points[1].x() - points[0].x()) * (points[3].y() - points[0].y())
                       - (points[1].y() - points[0].y()) * (points[3].x() - points[0].x())) < 0.5:
                    continue  # 面几乎与视线平行
                self._draw_face(
                    painter, image, uv, points, 0 if overlay else _SHADE[name], not overlay
                )
                hits.append(
                    (item["part"], item["layer"], u0, v0, w, h, points[0], points[1], points[3])
                )

        self._hits = hits
        if self._paintable and self._last_pos is not None:
            resolved = self._hit(self._last_pos)
            if resolved is not None:
                self._draw_texel(painter, resolved)

    # ------------------------------------------------------------------
    def _draw_cape(self, painter, cape: QImage, project) -> None:
        """在身体后方绘制一块薄披风板（主面 + 右侧厚度面），略微向外倾斜。"""
        x0, x1 = -5.0, 5.0  # 比身体（-4~4）左右各宽 1 像素，边缘露出
        top_y, bottom_y = 24.5, 8.5  # 从肩部垂下 16 像素
        near_top, far_top = -2.2, -3.2
        near_bottom, far_bottom = -3.7, -4.7
        main = [
            project(x0, top_y, near_top),
            project(x1, top_y, near_top),
            project(x1, bottom_y, near_bottom),
            project(x0, bottom_y, near_bottom),
        ]
        side = [
            project(x1, top_y, far_top),
            project(x1, top_y, near_top),
            project(x1, bottom_y, near_bottom),
            project(x1, bottom_y, far_bottom),
        ]
        self._draw_face(painter, cape, _UV_CAPE_SIDE, side, 45, False)
        self._draw_face(painter, cape, _UV_CAPE_MAIN, main, 20, False)

    def _draw_face(
        self, painter, image: QImage | None, uv, points, shade: int = 0, outline: bool = True
    ) -> None:
        u0, v0, w, h = uv
        p0, p1, _p2, p3 = points
        polygon = QPolygonF(points)
        painter.save()
        if image is not None and w > 0 and h > 0:
            ux = (p1.x() - p0.x()) / w
            uy = (p1.y() - p0.y()) / w
            vx = (p3.x() - p0.x()) / h
            vy = (p3.y() - p0.y()) / h
            transform = QTransform(
                ux,
                uy,
                vx,
                vy,
                p0.x() - (u0 * ux + v0 * vx),
                p0.y() - (u0 * uy + v0 * vy),
            )
            painter.setTransform(transform, True)
            # 裁剪区域用贴图坐标给出，随变换一起映射到屏幕上对应的面；
            # 与贴图实际尺寸求交，避免 UV 越界时取到图外像素
            clip_rect = QRectF(u0, v0, w, h).intersected(
                QRectF(0.0, 0.0, float(image.width()), float(image.height()))
            )
            clip = QPainterPath()
            clip.addRect(clip_rect)
            painter.setClipPath(clip)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
            painter.drawImage(0, 0, image)
        else:
            painter.setBrush(QColor("#3c5a48"))
            painter.drawPolygon(polygon)
        painter.restore()
        if shade > 0:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, shade))
            painter.drawPolygon(polygon)
        if outline:
            painter.setPen(QPen(QColor(0, 0, 0, 80), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawPolygon(polygon)

    def _draw_texel(self, painter, resolved) -> None:
        """高亮鼠标命中的那个贴图像素，帮助精确作画。"""
        part, _layer, u, v, rec = resolved
        u0, v0, w, h, p0, p1, p3 = rec[2:]
        a0 = (u - u0) / w
        a1 = (u + 1 - u0) / w
        b0 = (v - v0) / h
        b1 = (v + 1 - v0) / h

        def point(a: float, b: float) -> QPointF:
            return QPointF(
                p0.x() + a * (p1.x() - p0.x()) + b * (p3.x() - p0.x()),
                p0.y() + a * (p1.y() - p0.y()) + b * (p3.y() - p0.y()),
            )

        quad = QPolygonF([point(a0, b0), point(a1, b0), point(a1, b1), point(a0, b1)])
        painter.setPen(QPen(QColor(255, 255, 255, 230), 1))
        painter.setBrush(QColor(255, 255, 255, 70))
        painter.drawPolygon(quad)

    # ------------------------------------------------------------------
    def _hit(self, pos: QPointF) -> tuple | None:
        """屏幕点 → 当前图层内最上层可见面的贴图像素：(part, layer, u, v, rec)。"""
        for rec in reversed(self._hits):
            part, layer = rec[0], rec[1]
            if layer != self._layer:
                continue
            if self._part_filter is not None and part != self._part_filter:
                continue
            u0, v0, w, h, p0, p1, p3 = rec[2], rec[3], rec[4], rec[5], rec[6], rec[7], rec[8]
            ex = p1.x() - p0.x()
            ey = p1.y() - p0.y()
            fx = p3.x() - p0.x()
            fy = p3.y() - p0.y()
            det = ex * fy - ey * fx
            if abs(det) < 1e-6:
                continue
            qx = pos.x() - p0.x()
            qy = pos.y() - p0.y()
            a = (qx * fy - qy * fx) / det
            b = (ex * qy - ey * qx) / det
            if -0.001 <= a < 1.001 and -0.001 <= b < 1.001:
                u = int(u0 + min(max(a, 0.0), 0.9999) * w)
                v = int(v0 + min(max(b, 0.0), 0.9999) * h)
                if 0 <= u < 64 and 0 <= v < 64:
                    return part, layer, u, v, rec
        return None

    # ------------------------------------------------------------------
    def _start_rotate(self, pos: QPointF) -> None:
        self._rotating = True
        self._last_x = pos.x()
        self._last_y = pos.y()
        self.setCursor(Qt.ClosedHandCursor)

    def _start_pan(self, pos: QPointF) -> None:
        self._panning = True
        self._last_x = pos.x()
        self._last_y = pos.y()
        self.setCursor(Qt.SizeAllCursor)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        pos = event.position()
        self._last_pos = pos
        modifiers = event.modifiers()
        # 中键或 Shift：始终进入旋转
        if event.button() == Qt.MiddleButton or modifiers & Qt.ShiftModifier:
            self._start_rotate(pos)
            return
        # 非可绘制预览（账号页实际皮肤）或「鼠标」模式：左键旋转、右键平移
        if not self._paintable or self._mode == "mouse":
            if event.button() == Qt.LeftButton:
                self._start_rotate(pos)
            elif event.button() == Qt.RightButton:
                self._start_pan(pos)
            return
        # 画笔模式：左键作画、右键擦除
        if event.button() not in (Qt.LeftButton, Qt.RightButton):
            return
        hit = self._hit(pos)
        if hit is None:
            return
        self._painting = True
        self._erase = event.button() == Qt.RightButton
        self.stroke_started.emit()
        self.stroke_pixel.emit(hit[2], hit[3], self._erase)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        pos = event.position()
        self._last_pos = pos
        if self._rotating:
            dx = pos.x() - self._last_x
            dy = pos.y() - self._last_y
            self._last_x = pos.x()
            self._last_y = pos.y()
            self.set_yaw(self._yaw + dx * 0.6)
            self.set_pitch(self._pitch - dy * 0.5)
            return
        if self._panning:
            self.pan_by(pos.x() - self._last_x, pos.y() - self._last_y)
            self._last_x = pos.x()
            self._last_y = pos.y()
            return
        if self._paintable:
            hit = self._hit(pos)
            self.hover_changed.emit(
                hit[0] if hit is not None else "",
                hit[2] if hit is not None else -1,
                hit[3] if hit is not None else -1,
            )
            if self._painting and hit is not None:
                self.stroke_pixel.emit(hit[2], hit[3], self._erase)
                return
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._rotating:
            self._rotating = False
            if self._mode == "mouse" or not self._paintable:
                self.setCursor(Qt.OpenHandCursor)
            else:
                self.setCursor(Qt.CrossCursor)
            return
        if self._panning:
            self._panning = False
            if self._mode == "mouse" or not self._paintable:
                self.setCursor(Qt.OpenHandCursor)
            else:
                self.setCursor(Qt.CrossCursor)
            return
        if not self._painting:
            return
        if event.button() in (Qt.LeftButton, Qt.RightButton):
            self._painting = False
            self._erase = False
            self.stroke_ended.emit()

    def wheelEvent(self, event) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        if delta == 0:
            return
        self.zoom_by(0.1 if delta > 0 else -0.1)
        event.accept()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._last_pos = None
        if self._paintable:
            self.hover_changed.emit("", -1, -1)
        self.update()


__all__ = ["SkinPreview3D"]
