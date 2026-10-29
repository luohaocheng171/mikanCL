"""界面主题：配色、样式表与手绘图标。"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)

BG = "#0c1310"
CARD = "#121d16"
TEXT = "#e8f1ea"
MUTED = "#8aa192"
ACCENT = "#65d46e"

STYLESHEET = """
* { outline: none; }
QWidget { color: #e8f1ea; font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif; font-size: 13px; }
QMainWindow, QWidget#Root { background-color: #0c1310; }
QFrame#Sidebar { background-color: #0a100c; border-right: 1px solid #1b2920; }
QLabel#LogoTitle { font-size: 19px; font-weight: 700; color: #eef7f0; letter-spacing: 1px; }
QLabel#LogoSub { font-size: 10px; color: #6d8876; letter-spacing: 2px; }
QFrame#TitleBar { background-color: #0a100c; border-bottom: 1px solid #1b2920; }
QLabel#TitleBarText { font-size: 12px; color: #8fa898; letter-spacing: 1px; }
QPushButton#WinButton { background: transparent; border: none; border-radius: 7px; color: #9fb6a7; font-size: 14px; }
QPushButton#WinButton:hover { background-color: #182620; color: #e6f2ea; }
QPushButton#WinClose { background: transparent; border: none; border-radius: 7px; color: #9fb6a7; font-size: 13px; }
QPushButton#WinClose:hover { background-color: #c23b3b; color: #ffffff; }
QPushButton#NavButton { text-align: left; padding: 10px 14px; border-radius: 9px; color: #9fb6a7; background: transparent; border: none; font-size: 13px; }
QPushButton#NavButton:hover { background-color: #142018; color: #dfeee3; }
QPushButton#NavButton:checked { background-color: #1a2f22; color: #86e88f; font-weight: 600; }
QFrame#Card { background-color: #121d16; border: 1px solid #1f2f25; border-radius: 14px; }
QLabel#CardTitle { font-size: 15px; font-weight: 600; color: #eaf4ec; }
QLabel#TaskStage { color: #9fe0ab; font-size: 13px; font-weight: 600; }
QLabel#StatValue { color: #f1f8f3; font-size: 19px; font-weight: 700; }
QLabel#Muted { color: #8aa192; font-size: 12px; }
QLabel#Tiny { color: #6e8778; font-size: 11px; }
QLabel#PageTitle { font-size: 24px; font-weight: 700; color: #f1f8f3; }
QLabel#PageSub { color: #8ba393; font-size: 12px; }
QLabel#Badge { border-radius: 8px; padding: 2px 8px; font-size: 11px; font-weight: 600; }
QLabel#Badge[kind="green"] { background-color: #1e3d27; color: #8fe89b; }
QLabel#Badge[kind="gray"] { background-color: #202c25; color: #97ab9e; }
QLabel#Badge[kind="blue"] { background-color: #1c2f3f; color: #7fc2ea; }
QLabel#Badge[kind="orange"] { background-color: #3d3220; color: #e8c37a; }
QLineEdit, QSpinBox, QComboBox { background-color: #0e1712; border: 1px solid #24362b; border-radius: 8px; padding: 7px 10px; color: #e8f1ea; selection-background-color: #2a5d38; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: #4b9a5c; }
QLineEdit:disabled, QSpinBox:disabled { color: #6d8575; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background-color: #111c15; border: 1px solid #2a3d30; selection-background-color: #244a31; outline: none; padding: 4px; }
QPushButton { background-color: #18271e; border: 1px solid #273a2f; border-radius: 8px; padding: 7px 12px; color: #dfece3; }
QPushButton:hover { background-color: #203327; border-color: #385144; }
QPushButton:pressed { background-color: #15241c; }
QPushButton:disabled { color: #607567; background-color: #131f18; border-color: #1e2c23; }
QPushButton#Primary { background-color: #65d46e; border: none; color: #08200e; font-weight: 700; font-size: 15px; padding: 13px 20px; border-radius: 11px; }
QPushButton#Primary:hover { background-color: #79e282; }
QPushButton#Primary:pressed { background-color: #55c25e; }
QPushButton#Primary:disabled { background-color: #24372a; color: #5f7867; }
QPushButton#Ghost { background-color: transparent; border: none; color: #8fa99a; padding: 5px 8px; }
QPushButton#Ghost:hover { color: #d9ecdf; background-color: #1a2a20; }
QPushButton#Danger { background-color: #3a1d20; border: 1px solid #5c2b31; color: #e8909a; }
QPushButton#Danger:hover { background-color: #4a2329; }
QPushButton#Chip { background-color: #15221a; border: 1px solid #24382b; border-radius: 14px; padding: 5px 12px; color: #a9c3b1; font-size: 12px; }
QPushButton#Chip:hover { border-color: #4c8c5b; color: #d4f0da; }
QPushButton#Mini { background-color: #16241c; border: 1px solid #25382b; border-radius: 6px; padding: 2px 8px; color: #b6cfbd; font-size: 11px; }
QPushButton#Mini:hover { border-color: #4c8c5b; color: #e2f5e7; }
QPushButton#Mini:disabled { color: #5c7263; border-color: #1c2a21; }
QFrame#VersionRow { background-color: #0f1813; border: 1px solid #1d2c23; border-radius: 11px; }
QFrame#VersionRow:hover { background-color: #15241b; border-color: #2c4736; }
QFrame#VersionRow[selected="true"] { background-color: #173024; border-color: #4f9a5f; }
QProgressBar { background-color: #101c15; border: none; border-radius: 4px; min-height: 8px; max-height: 8px; }
QProgressBar::chunk { background-color: #65d46e; border-radius: 4px; }
QSlider::groove:horizontal { height: 4px; background: #203027; border-radius: 2px; }
QSlider::handle:horizontal { width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; background: #65d46e; }
QSlider::sub-page:horizontal { background: #3f8d4d; border-radius: 2px; }
QCheckBox { color: #b7cbbd; spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; border: 1px solid #33493b; background: #0e1712; }
QCheckBox::indicator:checked { background-color: #65d46e; border-color: #65d46e; }
QTextEdit#Console, QPlainTextEdit#Console { background-color: #080e0a; border: 1px solid #1c2a21; border-radius: 10px; color: #a9c4b2; font-family: Consolas, "Cascadia Mono", monospace; font-size: 12px; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
QScrollBar::handle:vertical { background: #2b4033; border-radius: 4px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #3c5a47; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 8px; }
QScrollBar::handle:horizontal { background: #2b4033; border-radius: 4px; min-width: 24px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QTabWidget::pane { border: none; background: transparent; }
QTabBar::tab { background: #111b15; color: #8fa79a; padding: 7px 14px; border-top-left-radius: 8px; border-top-right-radius: 8px; margin-right: 3px; max-width: 220px; }
QTabBar::tab:selected { background: #1d3025; color: #dff0e5; }
QTabBar::tab:hover { background: #18261d; }
QTableWidget { background-color: #0f1813; border: 1px solid #1f2f25; border-radius: 10px; gridline-color: #1b2a21; selection-background-color: #1c3626; selection-color: #e9f5ec; }
QHeaderView::section { background-color: #13211a; color: #8fa99a; border: none; padding: 7px 8px; font-weight: 600; }
QTableWidget::item { padding: 4px 6px; }
QFrame#ProjectCard { background-color: #101a14; border: 1px solid #1f2f25; border-radius: 12px; }
QFrame#ProjectCard:hover { background-color: #15241b; border-color: #3f7b4e; }
QLabel#Cover { border-radius: 9px; background-color: #0d1712; }
QLabel#GroupHeader { color: #b9d2c0; font-size: 14px; font-weight: 700; padding: 6px 2px; }
QLabel#DetailTitle { font-size: 22px; font-weight: 700; color: #f1f8f3; }
QFrame#LoaderCard { background-color: #0f1813; border: 1px solid #1f2f25; border-radius: 11px; }
QFrame#LoaderCard:hover { background-color: #16261c; border-color: #356447; }
QFrame#LoaderCard[selected="true"] { background-color: #173024; border-color: #4f9a5f; }
QFrame#LoaderCard[unsupported="true"] { background-color: #11160f; border-color: #23291f; }
QListWidget { background-color: #0f1813; border: 1px solid #1f2f25; border-radius: 10px; padding: 6px; outline: none; }
QListWidget::item { padding: 8px 10px; border-radius: 8px; color: #b7cbbd; }
QListWidget::item:hover { background-color: #16241b; }
QListWidget::item:selected { background-color: #1d3527; color: #dff0e5; }
QListWidget#SettingsNav { background-color: #0e1712; border: 1px solid #1e2c23; padding: 10px 6px; }
QListWidget#SettingsNav::item { padding: 10px 14px; margin: 2px 0; font-size: 13px; }
QListWidget#VersionList::item { padding: 7px 10px; color: #9fb6a7; }
QLabel#Stat { color: #8aa192; font-size: 11px; }
QMenu { background-color: #121d16; border: 1px solid #273a2f; padding: 4px; }
QMenu::item { padding: 6px 22px; border-radius: 6px; }
QMenu::item:selected { background-color: #1f3528; }
QToolTip { background-color: #121d16; color: #e8f1ea; border: 1px solid #2c4235; padding: 6px; }
QSplitter::handle { background: transparent; }
QStatusBar { background-color: #0a100c; color: #7f9788; border-top: 1px solid #1a2820; font-size: 11px; }
QStatusBar::item { border: none; }
QFrame#TaskCenter { background-color: #0e1712; border: 1px solid #1b2920; border-radius: 10px; }
QPushButton#TaskToggle { text-align: left; background: transparent; border: none; color: #a9c3b1; font-size: 12px; font-weight: 600; padding: 4px 6px; }
QPushButton#TaskToggle:hover { color: #dff0e5; background: transparent; }
QFrame#TaskRow { background-color: #101a14; border: 1px solid #1d2c23; border-radius: 8px; }
QLabel#TaskTitle { color: #cfdcd2; font-size: 11px; font-weight: 600; }
QLabel#TaskStatus { color: #7f9788; font-size: 10px; }
QPushButton#TaskCancel { background: transparent; border: 1px solid #2a3d30; border-radius: 5px; color: #8fa99a; font-size: 10px; padding: 1px 4px; }
QPushButton#TaskCancel:hover { background-color: #3a1d20; border-color: #5c2b31; color: #e8909a; }
"""


def make_block_icon(size: int = 64) -> QIcon:
    """绘制像素风草方块作为图标。"""
    scale = max(1, size // 16)
    pixmap = QPixmap(16 * scale, 16 * scale)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, False)
    palette = {
        "g": "#6fdc71",
        "G": "#4fae55",
        "d": "#8b5a37",
        "D": "#6b4227",
        "s": "#a87347",
        "k": "#4b2c19",
    }
    rows = [
        "gggggggggggggggg",
        "gGgggGgggggGggGg",
        "gGGgggGGggGGgggg",
        "GGGGGGGGGGGGGGGG",
        "dddddddddddddddd",
        "dsddddddsddddddd",
        "ddddkddddddddddd",
        "ddddddddsddddkdd",
        "dsdddddddddddddd",
        "ddddddsddddddddd",
        "ddddddddddkddddd",
        "ddddsddddddddddd",
        "dddddddddddddsdd",
        "ddkdddddsddddddd",
        "dddddddddddddddd",
        "DDDDDDDDDDDDDDDD",
    ]
    for y, row in enumerate(rows):
        for x, char in enumerate(row):
            painter.fillRect(x * scale, y * scale, scale, scale, QColor(palette[char]))
    painter.end()
    return QIcon(pixmap)


def make_avatar(name: str, size: int = 56) -> QPixmap:
    """生成 8x8 像素风玩家头像（按昵称决定末影人/史蒂夫配色）。"""
    seed = sum(ord(c) for c in name) if name else 0
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), 12, 12)
    painter.setClipPath(path)
    cell = size / 8

    if seed % 3 == 0:
        rows = [
            "KKKKKKKK", "KKKKKKKK", "KKKKKKKK", "KKKKKKKK",
            "KKKKKKKK", "KKKKKKKK", "KKKKKKKK", "KKKKKKKK",
        ]
        palette = {"K": "#1d1b22"}
        eye = "#a06df0"
        mouth = "#a06df0"
    else:
        rows = [
            "HHHHHHHH", "HHHHHHHH", "HSSSSSSH", "SESSSSES",
            "SSSSSSSS", "SSSMMSSS", "SSSSSSSS", "SSSSSSSS",
        ]
        palette = {"H": "#33251c", "S": "#c9976d", "E": "#28324f", "M": "#8b4537"}
        eye = "#28324f"
        mouth = "#8b4537"

    for y, row in enumerate(rows):
        for x, char in enumerate(row):
            painter.fillRect(QRectF(x * cell, y * cell, cell + 0.4, cell + 0.4), QColor(palette[char]))
    if seed % 3 == 0:
        painter.fillRect(QRectF(cell * 2, cell * 3, cell, cell), QColor(eye))
        painter.fillRect(QRectF(cell * 5, cell * 3, cell, cell), QColor(eye))
        painter.fillRect(QRectF(cell * 3.3, cell * 5.4, cell * 1.5, cell * 0.5), QColor(mouth))
    painter.end()
    return pixmap


def make_nav_icon(kind: str, size: int = 20, color: str = "#9fb6a7") -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor(color), 1.7)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    s = size
    if kind == "home":
        painter.drawPolyline(
            QPolygonF([QPointF(s * 0.18, s * 0.48), QPointF(s * 0.5, s * 0.18), QPointF(s * 0.82, s * 0.48)])
        )
        painter.drawLine(QPointF(s * 0.26, s * 0.44), QPointF(s * 0.26, s * 0.82))
        painter.drawLine(QPointF(s * 0.74, s * 0.44), QPointF(s * 0.74, s * 0.82))
        painter.drawLine(QPointF(s * 0.26, s * 0.82), QPointF(s * 0.74, s * 0.82))
        painter.drawRect(QRectF(s * 0.42, s * 0.58, s * 0.16, s * 0.24))
    elif kind == "download":
        painter.drawLine(QPointF(s * 0.5, s * 0.18), QPointF(s * 0.5, s * 0.62))
        painter.drawPolyline(
            QPolygonF([QPointF(s * 0.32, s * 0.46), QPointF(s * 0.5, s * 0.64), QPointF(s * 0.68, s * 0.46)])
        )
        painter.drawLine(QPointF(s * 0.2, s * 0.78), QPointF(s * 0.8, s * 0.78))
        painter.drawLine(QPointF(s * 0.2, s * 0.86), QPointF(s * 0.8, s * 0.86))
    elif kind == "downloads":
        painter.drawRect(QRectF(s * 0.18, s * 0.2, s * 0.64, s * 0.6))
        painter.drawLine(QPointF(s * 0.18, s * 0.4), QPointF(s * 0.82, s * 0.4))
        painter.drawLine(QPointF(s * 0.36, s * 0.48), QPointF(s * 0.36, s * 0.72))
        painter.drawLine(QPointF(s * 0.5, s * 0.48), QPointF(s * 0.5, s * 0.66))
        painter.drawLine(QPointF(s * 0.64, s * 0.48), QPointF(s * 0.64, s * 0.72))
    elif kind == "modpack":
        painter.drawRect(QRectF(s * 0.18, s * 0.24, s * 0.64, s * 0.56))
        painter.drawLine(QPointF(s * 0.18, s * 0.4), QPointF(s * 0.82, s * 0.4))
        painter.drawLine(QPointF(s * 0.5, s * 0.4), QPointF(s * 0.5, s * 0.56))
        painter.drawEllipse(QRectF(s * 0.42, s * 0.44, s * 0.16, s * 0.16))
    elif kind == "browser":
        painter.drawEllipse(QRectF(s * 0.16, s * 0.16, s * 0.68, s * 0.68))
        painter.drawEllipse(QRectF(s * 0.34, s * 0.16, s * 0.32, s * 0.68))
        painter.drawLine(QPointF(s * 0.16, s * 0.5), QPointF(s * 0.84, s * 0.5))
    elif kind == "content":
        painter.drawRect(QRectF(s * 0.18, s * 0.18, s * 0.28, s * 0.28))
        painter.drawRect(QRectF(s * 0.54, s * 0.18, s * 0.28, s * 0.28))
        painter.drawRect(QRectF(s * 0.18, s * 0.54, s * 0.28, s * 0.28))
        painter.drawLine(QPointF(s * 0.56, s * 0.68), QPointF(s * 0.84, s * 0.68))
        painter.drawLine(QPointF(s * 0.7, s * 0.54), QPointF(s * 0.7, s * 0.82))
    elif kind == "loader":
        painter.drawLine(QPointF(s * 0.28, s * 0.18), QPointF(s * 0.62, s * 0.52))
        painter.drawEllipse(QRectF(s * 0.55, s * 0.52, s * 0.3, s * 0.3))
        painter.drawLine(QPointF(s * 0.2, s * 0.8), QPointF(s * 0.4, s * 0.6))
    elif kind == "account":
        painter.drawEllipse(QRectF(s * 0.34, s * 0.16, s * 0.32, s * 0.32))
        painter.drawArc(QRectF(s * 0.18, s * 0.5, s * 0.64, s * 0.46), 0, 180 * 16)
    elif kind == "control":
        for y in (0.3, 0.5, 0.7):
            painter.drawLine(QPointF(s * 0.16, s * y), QPointF(s * 0.84, s * y))
            painter.drawEllipse(QRectF(s * 0.3 if y < 0.45 else s * 0.58, s * y - s * 0.07, s * 0.14, s * 0.14))
    else:  # settings
        painter.drawEllipse(QRectF(s * 0.29, s * 0.29, s * 0.42, s * 0.42))
        for angle in range(0, 360, 45):
            painter.save()
            painter.translate(s / 2, s / 2)
            painter.rotate(angle)
            painter.drawLine(QPointF(0, s * 0.26), QPointF(0, s * 0.4))
            painter.restore()
    painter.end()
    return QIcon(pixmap)


def make_dot(color: str = ACCENT, size: int = 8) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))
    painter.drawEllipse(0, 0, size, size)
    painter.end()
    return pixmap
