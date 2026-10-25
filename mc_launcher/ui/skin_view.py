"""皮肤 3D 预览：用等轴测投影把 64x64 皮肤贴图贴到人物方块模型上。"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
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

# 每个部件三个可视面的 UV：(u, v, w, h)
_UV_HEAD = {
    "front": (8, 8, 8, 8),
    "right": (0, 8, 8, 8),
    "top": (8, 0, 8, 8),
}
_UV_BODY = {
    "front": (20, 20, 8, 12),
    "right": (16, 20, 4, 12),
    "top": (20, 16, 8, 4),
}
_UV_ARM_R = {
    "front": (44, 20, 4, 12),
    "right": (40, 20, 4, 12),
    "top": (44, 16, 4, 4),
}
_UV_ARM_L = {
    "front": (36, 52, 4, 12),
    "right": (32, 52, 4, 12),
    "top": (36, 48, 4, 4),
}
_UV_LEG_R = {
    "front": (4, 20, 4, 12),
    "right": (0, 20, 4, 12),
    "top": (4, 16, 4, 4),
}
_UV_LEG_L = {
    "front": (20, 52, 4, 12),
    "right": (16, 52, 4, 12),
    "top": (20, 48, 4, 4),
}
# Alex（苗条模型）：手臂宽 3 像素，贴图 UV 与 Steve 不同
_ARM_L_SLIM = (-7.0, -4.0, 12.0, 24.0, -2.0, 2.0)
_ARM_R_SLIM = (4.0, 7.0, 12.0, 24.0, -2.0, 2.0)
_UV_ARM_R_SLIM = {
    "front": (44, 20, 3, 12),
    "right": (43, 20, 1, 12),
    "top": (44, 16, 3, 4),
}
_UV_ARM_L_SLIM = {
    "front": (36, 52, 3, 12),
    "right": (35, 52, 1, 12),
    "top": (36, 48, 3, 4),
}


class SkinPreview3D(QWidget):
    """轻量 3D 皮肤预览，无需 OpenGL：贴图按等轴测投影绘制到方块模型上。"""

    def __init__(self, width: int = 150, height: int = 200, parent=None):
        super().__init__(parent)
        self.setFixedSize(width, height)
        self._image: QImage | None = None
        self._model = "steve"

    # ------------------------------------------------------------------
    def set_skin(self, image: QImage | None) -> None:
        self._image = image if image is not None and not image.isNull() else None
        self.update()

    def clear_skin(self) -> None:
        self.set_skin(None)

    def set_model(self, model: str) -> None:
        """切换 Steve（经典手臂 4px）/ Alex（苗条手臂 3px）模型。"""
        self._model = "alex" if str(model).lower() in ("alex", "slim") else "steve"
        self.update()

    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), Qt.transparent)
        background = QPainterPath()
        background.addRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 16, 16)
        painter.setClipPath(background)
        painter.fillPath(background, QColor("#0f1813"))
        painter.setClipping(False)

        scale = min(
            (self.width() - 16) / (24 * _COS30),
            (self.height() - 16) / 44.0,
        )
        offset_x = self.width() / 2
        offset_y = (self.height() + 38 * scale) / 2

        def project(x: float, y: float, z: float) -> QPointF:
            return QPointF(
                (x - z) * _COS30 * scale + offset_x,
                (x + z) * 0.5 * scale - y * scale + offset_y,
            )

        image = self._image
        # 64x32 旧皮肤没有左臂/左腿的独立贴图，复用右侧贴图
        full = image is not None and image.height() >= 64
        slim = self._model == "alex"
        parts = [
            (_LEG_L, _UV_LEG_L if full else _UV_LEG_R),
            (_LEG_R, _UV_LEG_R),
            (_BODY, _UV_BODY),
            (
                _ARM_L_SLIM if slim else _ARM_L,
                (_UV_ARM_L_SLIM if slim else _UV_ARM_L) if full else _UV_ARM_R,
            ),
            (_ARM_R_SLIM if slim else _ARM_R, _UV_ARM_R_SLIM if slim else _UV_ARM_R),
            (_HEAD, _UV_HEAD),
        ]
        for box, uvs in parts:
            self._draw_box(painter, image, box, uvs, project, scale)

        painter.end()

    # ------------------------------------------------------------------
    def _draw_box(self, painter, image, box, uvs, project, scale: float) -> None:
        x0, x1, y0, y1, z0, z1 = box
        faces = [
            # (面名, 明暗遮罩透明度, 四个角点，按 左上/右上/右下/左下 的顺序给出)
            (
                "right",
                30,
                [project(x1, y1, z0), project(x1, y1, z1), project(x1, y0, z1), project(x1, y0, z0)],
            ),
            (
                "top",
                0,
                [project(x0, y1, z0), project(x1, y1, z0), project(x1, y1, z1), project(x0, y1, z1)],
            ),
            (
                "front",
                12,
                [project(x0, y1, z1), project(x1, y1, z1), project(x1, y0, z1), project(x0, y0, z1)],
            ),
        ]
        for name, shade, points in faces:
            uv = uvs.get(name)
            if uv is None:
                continue
            self._draw_face(painter, image, uv, points, shade)

    def _draw_face(self, painter, image: QImage | None, uv, points, shade: int = 0) -> None:
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
            # 裁剪区域用贴图坐标给出，随变换一起映射到屏幕上对应的面
            clip = QPainterPath()
            clip.addRect(QRectF(u0, v0, w, h))
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
        painter.setPen(QPen(QColor(0, 0, 0, 80), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawPolygon(polygon)
