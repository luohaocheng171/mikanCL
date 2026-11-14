"""Mod 关系网：用 QGraphicsView 自绘前置依赖图，缺失前置与循环依赖高亮。

不使用 WebView2/QtWebEngine，纯 QPainter 绘制，老机器也能流畅缩放平移。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QThread, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..content import scan_mod_metadata
from ..context import AppContext
from ..modgraph import ModGraph, ModNode, build_mod_graph
from ..version import scan_installed_versions
from .widgets import Card, page_header, related_features_row

NODE_W = 196.0
NODE_H = 56.0
COL_GAP = 110.0
ROW_GAP = 16.0
MARGIN = 32.0

_COLOR_TEXT = QColor("#e6f4ea")
_COLOR_SUB = QColor("#93b1a1")
_COLOR_BORDER = QColor("#33493b")
_COLOR_FILL = QColor("#14261c")
_COLOR_MISSING_FILL = QColor("#2a1614")
_COLOR_MISSING_BORDER = QColor("#a8463c")
_COLOR_MISSING_TEXT = QColor("#ffb4a8")
_COLOR_CYCLE = QColor("#e0a44a")
_COLOR_EDGE = QColor(159, 182, 167, 90)
_COLOR_EDGE_MISSING = QColor("#d0574a")


class ModGraphWorker(QThread):
    """后台读取 mods/ 里的 jar 元数据并构图，避免卡住界面。"""

    done = Signal(object)
    failed = Signal(str)

    def __init__(self, mods_dir: Path, parent=None):
        super().__init__(parent)
        self.mods_dir = Path(mods_dir)

    def run(self) -> None:
        try:
            self.done.emit(build_mod_graph(scan_mod_metadata(self.mods_dir)))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class ModNodeItem(QGraphicsItem):
    def __init__(self, node: ModNode, in_cycle: bool):
        super().__init__()
        self.node = node
        self.in_cycle = in_cycle
        self._rect = QRectF(0, 0, NODE_W, NODE_H)
        self.setAcceptHoverEvents(True)
        self.setToolTip(self._tooltip())

    def _tooltip(self) -> str:
        node = self.node
        if node.missing:
            return f"缺少前置：{node.modid}\n这个 Mod 没有安装到 mods/ 目录"
        lines = [f"{node.name}（{node.modid}）"]
        if node.version:
            lines.append(f"版本：{node.version}")
        if node.loader:
            lines.append(f"加载器：{node.loader}")
        if node.path:
            lines.append(f"文件：{node.path}")
        return "\n".join(lines)

    def boundingRect(self) -> QRectF:  # noqa: N802
        return self._rect.adjusted(-1.0, -1.0, 1.0, 1.0)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        if self.node.missing:
            fill, border, text, subtext = (
                _COLOR_MISSING_FILL,
                _COLOR_MISSING_BORDER,
                _COLOR_MISSING_TEXT,
                QColor("#e08a80"),
            )
        else:
            fill, border, text, subtext = _COLOR_FILL, _COLOR_BORDER, _COLOR_TEXT, _COLOR_SUB
        if self.in_cycle:
            border = _COLOR_CYCLE
        painter.setBrush(QBrush(fill))
        painter.setPen(QPen(border, 1.4))
        painter.drawRoundedRect(self._rect, 10, 10)

        title_font = QFont(painter.font())
        title_font.setBold(True)
        title_font.setPointSizeF(9.5)
        painter.setFont(title_font)
        painter.setPen(QPen(text))
        metrics = QFontMetricsF(title_font)
        title = metrics.elidedText(self.node.name, Qt.ElideRight, NODE_W - 20)
        painter.drawText(QRectF(10, 7, NODE_W - 20, 20), Qt.AlignLeft | Qt.AlignVCenter, title)

        sub_font = QFont(painter.font())
        sub_font.setBold(False)
        sub_font.setPointSizeF(8.0)
        painter.setFont(sub_font)
        painter.setPen(QPen(subtext))
        if self.node.missing:
            subtitle = "缺少前置 · 未安装"
        else:
            bits = []
            if self.node.version:
                bits.append(f"v{self.node.version}")
            if self.node.loader and self.node.loader != "unknown":
                bits.append(self.node.loader)
            subtitle = " · ".join(bits) or self.node.modid
        subtitle = QFontMetricsF(sub_font).elidedText(subtitle, Qt.ElideRight, NODE_W - 20)
        painter.drawText(QRectF(10, 28, NODE_W - 20, 18), Qt.AlignLeft | Qt.AlignVCenter, subtitle)


class ModGraphScene(QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._graph = ModGraph()

    def set_graph(self, graph: ModGraph) -> None:
        self.clear()
        self._graph = graph
        if not graph.nodes:
            hint = QGraphicsTextItem("mods/ 目录里没有可解析的 Mod（也可能是该版本还没装 Mod）")
            hint.setDefaultTextColor(QColor("#93b1a1"))
            font = QFont()
            font.setPointSizeF(11)
            hint.setFont(font)
            hint.setPos(MARGIN, MARGIN)
            self.addItem(hint)
            self.setSceneRect(QRectF(0, 0, 560, 90))
            return

        levels = self._compute_levels(graph)
        columns: dict[int, list[ModNode]] = {}
        for node in graph.nodes:
            columns.setdefault(levels.get(node.modid, 0), []).append(node)
        positions: dict[str, QPointF] = {}
        max_row = 0
        for level, nodes in columns.items():
            nodes.sort(key=lambda item: (item.missing, item.name.lower()))
            max_row = max(max_row, len(nodes))
            for row, node in enumerate(nodes):
                positions[node.modid] = QPointF(
                    MARGIN + level * (NODE_W + COL_GAP),
                    MARGIN + row * (NODE_H + ROW_GAP),
                )

        cycle_members = {modid for group in graph.cycles for modid in group}
        for node in graph.nodes:
            item = ModNodeItem(node, node.modid in cycle_members)
            item.setPos(positions[node.modid])
            self.addItem(item)

        cycle_edges = graph.cycle_edges
        for edge in graph.edges:
            start_node = positions.get(edge.source)
            end_node = positions.get(edge.target)
            if start_node is None or end_node is None:
                continue
            start = QPointF(start_node.x(), start_node.y() + NODE_H / 2)
            end = QPointF(end_node.x() + NODE_W, end_node.y() + NODE_H / 2)
            is_cycle = (edge.source, edge.target) in cycle_edges
            # 环上的两条反向边端点相同，必须一上一下弯开，否则会完全重叠
            bow = (-46.0 if end.x() >= start.x() else 46.0) if is_cycle else 0.0
            path_item = QGraphicsPathItem(self._edge_path(start, end, bow))
            if not edge.ok:
                pen = QPen(_COLOR_EDGE_MISSING, 1.8, Qt.DashLine)
            elif is_cycle:
                pen = QPen(_COLOR_CYCLE, 2.0)
            else:
                pen = QPen(_COLOR_EDGE, 1.3)
            path_item.setPen(pen)
            path_item.setZValue(-1)
            path_item.setToolTip(
                f"{edge.source} → {edge.target}"
                + (f"\n版本要求：{edge.version_range}" if edge.version_range else "")
                + ("\n（该前置未安装）" if not edge.ok else "")
            )
            self.addItem(path_item)

        levels_count = max(columns) + 1 if columns else 1
        width = MARGIN * 2 + levels_count * NODE_W + (levels_count - 1) * COL_GAP
        height = MARGIN * 2 + max(max_row, 1) * NODE_H + (max(max_row, 1) - 1) * ROW_GAP
        self.setSceneRect(QRectF(0, 0, max(width, 400), max(height, 200)))

    @staticmethod
    def _edge_path(start: QPointF, end: QPointF, bow: float = 0.0) -> QPainterPath:
        offset = max(40.0, abs(end.x() - start.x()) * 0.42)
        path = QPainterPath(start)
        if end.x() >= start.x():
            path.cubicTo(
                start.x() + offset,
                start.y() + bow,
                end.x() - offset,
                end.y() + bow,
                end.x(),
                end.y(),
            )
        else:
            path.cubicTo(
                start.x() - offset,
                start.y() + bow,
                end.x() + offset,
                end.y() + bow,
                end.x(),
                end.y(),
            )
        return path

    @staticmethod
    def _compute_levels(graph: ModGraph) -> dict[str, int]:
        """按依赖深度分层：被依赖的放左边，依赖别人的放右边。

        环上就地断开（返回 0），避免无限递归；缺失节点放在其使用者的左侧一层。
        """
        adjacency: dict[str, list[str]] = {
            node.modid: [] for node in graph.nodes if not node.missing
        }
        for edge in graph.edges:
            if edge.source in adjacency and edge.target in adjacency:
                adjacency[edge.source].append(edge.target)

        cache: dict[str, int] = {}
        visiting: set[str] = set()

        def level(modid: str) -> int:
            if modid in cache:
                return cache[modid]
            if modid in visiting:
                return 0
            visiting.add(modid)
            value = 0
            for dep in adjacency.get(modid, ()):
                value = max(value, level(dep) + 1)
            visiting.discard(modid)
            cache[modid] = value
            return value

        for modid in adjacency:
            level(modid)
        for node in graph.nodes:
            if not node.missing:
                continue
            dependents = [
                cache.get(edge.source, 0) for edge in graph.edges if edge.target == node.modid
            ]
            cache[node.modid] = max(0, min(dependents) - 1) if dependents else 0
        return cache


class ModGraphView(QGraphicsView):
    def __init__(self, scene: ModGraphScene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self.setFrameShape(QFrame.NoFrame)
        # 自绘深色画布：不依赖全局样式表，避免露出白色底影响观感
        self.setBackgroundBrush(QBrush(QColor("#0d1712")))
        self._zoom = 1.0

    def wheelEvent(self, event) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        if not delta:
            return super().wheelEvent(event)
        factor = 1.15 if delta > 0 else 1 / 1.15
        target = min(2.5, max(0.25, self._zoom * factor))
        if target == self._zoom:
            return
        self.scale(target / self._zoom, target / self._zoom)
        self._zoom = target
        event.accept()

    def fit_graph(self) -> None:
        rect = self.scene().sceneRect()
        if rect.isEmpty():
            return
        self.resetTransform()
        self.fitInView(rect.adjusted(-12, -12, 12, 12), Qt.KeepAspectRatio)
        scale = self.transform().m11()
        if scale > 1.2:
            # 小图不要放得太大，1.2 倍以内看着最舒服
            self.resetTransform()
            self.scale(1.2, 1.2)
            scale = 1.2
        self._zoom = max(0.25, min(2.5, scale))


class ModGraphPage(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self._worker: ModGraphWorker | None = None
        self._loaded = False
        self._build()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 20, 26, 20)
        outer.setSpacing(12)
        header, _ = page_header(
            self.tr("Mod 关系网"),
            self.tr("把 mods/ 的前置依赖画成一张网：红色=缺少前置，橙色=循环依赖"),
        )
        outer.addWidget(header)

        bar_card = Card(margins=14, spacing=8)
        bar = QHBoxLayout()
        bar.setSpacing(8)
        bar.addWidget(QLabel(self.tr("游戏版本")))
        self._version_combo = QComboBox()
        self._version_combo.setMinimumWidth(220)
        self._version_combo.currentIndexChanged.connect(lambda _index: self._scan())
        bar.addWidget(self._version_combo)
        self._refresh_btn = QPushButton(self.tr("重新扫描"))
        self._refresh_btn.clicked.connect(self._scan)
        bar.addWidget(self._refresh_btn)
        self._fit_btn = QPushButton(self.tr("适配视图"))
        self._fit_btn.setObjectName("Ghost")
        self._fit_btn.clicked.connect(lambda: self._view.fit_graph())
        bar.addWidget(self._fit_btn)
        bar.addStretch(1)
        bar_card.body.addLayout(bar)

        self._status = QLabel("")
        self._status.setObjectName("Tiny")
        self._status.setWordWrap(True)
        bar_card.body.addWidget(self._status)

        legend = QLabel(
            self.tr(
                "图例：红色节点 = 缺少前置（没装进 mods/）；橙色边框/连线 = 循环依赖；"
                "滚轮缩放，按住空白处拖动平移"
            )
        )
        legend.setObjectName("Tiny")
        legend.setWordWrap(True)
        bar_card.body.addWidget(legend)
        outer.addWidget(bar_card)

        self._scene = ModGraphScene(self)
        self._view = ModGraphView(self._scene, self)
        outer.addWidget(self._view, 1)
        outer.setStretchFactor(self._view, 1)

        self._scripts = QLabel(
            self.tr("提示：只解析 jar 内 fabric.mod.json / mods.toml / mcmod.info 的前置信息；解析失败的文件按文件名显示。")
        )
        self._scripts.setObjectName("Tiny")
        self._scripts.setWordWrap(True)
        outer.addWidget(self._scripts)
        outer.addWidget(related_features_row(self.ctx, "modgraph"))

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """页面切换时调用：刷新版本下拉，首次进入才真正扫描 jar。"""
        self._rebuild_versions()
        if not self._loaded:
            self._scan()

    def _rebuild_versions(self) -> None:
        previous = self._version_combo.currentData()
        versions = scan_installed_versions(self.ctx.config.game_path)
        self._version_combo.blockSignals(True)
        self._version_combo.clear()
        for version in versions:
            text = version.id + (f"（{version.loader}）" if version.loader else "")
            self._version_combo.addItem(text, version.id)
        if previous:
            index = self._version_combo.findData(previous)
            if index >= 0:
                self._version_combo.setCurrentIndex(index)
        self._version_combo.blockSignals(False)
        has_version = self._version_combo.count() > 0
        self._version_combo.setEnabled(has_version)
        self._refresh_btn.setEnabled(has_version)
        if not has_version:
            self._status.setText(self.tr("未检测到已安装的版本，请先在「下载安装」中安装游戏。"))

    def _scan(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        version_id = self._version_combo.currentData()
        if not version_id:
            self._scene.set_graph(ModGraph())
            return
        try:
            mods_dir = self.ctx.config.resolve_game_dirs(str(version_id)).targets("mods")[0]
        except Exception as exc:  # noqa: BLE001
            self._status.setText(str(exc))
            return
        self._status.setText(self.tr("正在扫描 {0} …").format(mods_dir))
        worker = ModGraphWorker(mods_dir, self)
        worker.done.connect(self._on_graph_ready)
        worker.failed.connect(self._on_graph_failed)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        worker.start()

    def _on_graph_ready(self, graph: object) -> None:
        if not isinstance(graph, ModGraph):
            return
        self._loaded = True
        self._scene.set_graph(graph)
        self._view.fit_graph()
        parts = [
            self.tr("{0} 个 Mod").format(len(graph.nodes)),
            self.tr("{0} 条依赖").format(len(graph.edges)),
        ]
        missing = len(graph.missing_nodes)
        cycles = len(graph.cycles)
        if missing:
            parts.append(self.tr("{0} 个缺少前置").format(missing))
        if cycles:
            parts.append(self.tr("{0} 组循环依赖").format(cycles))
        self._status.setText(" · ".join(parts))
        self._status.setStyleSheet(
            "color: #ff9b8f;" if missing or cycles else "color: #9fb6a7;"
        )

    def _on_graph_failed(self, message: str) -> None:
        self._status.setText(self.tr("扫描失败：{0}").format(message))

    def _on_worker_finished(self) -> None:
        self._worker = None
