"""Mod 前置关系图模型：把 mods/ 元数据转成节点与依赖边，并检测缺失前置/循环依赖。

纯逻辑，不依赖 Qt，便于单独测试；界面由 ui/page_modgraph.py 负责绘制。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# 这些依赖由游戏本体或加载器提供，不算「缺失的 Mod」，画图时直接忽略
PLATFORM_DEPENDENCIES = {
    "minecraft",
    "forge",
    "neoforge",
    "fabric",
    "fabricloader",
    "quilt_loader",
    "quiltloader",
    "java",
    "liteloader",
    "javafml",
    "lowcodefml",
    "mixinextras",
}


@dataclass
class ModNode:
    """图中的一个 Mod；missing=True 表示某个 Mod 的前置没有装进 mods/。"""

    modid: str
    name: str
    version: str = ""
    loader: str = ""
    path: str = ""
    missing: bool = False


@dataclass
class ModEdge:
    """source 依赖 target（箭头由被依赖方指回使用者，绘制时自行决定方向）。"""

    source: str
    target: str
    version_range: str = ""
    ok: bool = True


@dataclass
class ModGraph:
    nodes: list[ModNode] = field(default_factory=list)
    edges: list[ModEdge] = field(default_factory=list)
    # 每组是一个环上的 modid 列表（长度 1 表示自依赖）
    cycles: list[list[str]] = field(default_factory=list)

    @property
    def missing_nodes(self) -> list[ModNode]:
        return [node for node in self.nodes if node.missing]

    @property
    def cycle_edges(self) -> set[tuple[str, str]]:
        """环上的边集合，供绘制时高亮。"""
        marked: set[tuple[str, str]] = set()
        for group in self.cycles:
            members = set(group)
            for edge in self.edges:
                if edge.source in members and edge.target in members:
                    marked.add((edge.source, edge.target))
        return marked


def build_mod_graph(metadata: dict[Path, dict]) -> ModGraph:
    """由 scan_mod_metadata 的结果构建关系图。"""
    nodes: dict[str, ModNode] = {}
    edges: list[ModEdge] = []
    for path, meta in metadata.items():
        modid = str(meta.get("modid") or Path(path).stem).strip()
        if not modid or modid in nodes:
            # 重复 modid 只保留第一个，冲突问题交给依赖检查页展示
            continue
        nodes[modid] = ModNode(
            modid=modid,
            name=str(meta.get("name") or modid),
            version=str(meta.get("version") or ""),
            loader=str(meta.get("loader") or ""),
            path=str(path),
        )
        depends = meta.get("depends") or []
        for dep in depends:
            if not isinstance(dep, dict):
                continue
            target = str(dep.get("modid") or "").strip()
            if not target or target.lower() in PLATFORM_DEPENDENCIES:
                continue
            if target.lower() == modid.lower():
                continue  # 自依赖没有意义，忽略
            edges.append(
                ModEdge(
                    source=modid,
                    target=target,
                    version_range=str(dep.get("version_range") or ""),
                )
            )
    # 缺失的前置补成虚线节点，让「谁缺了什么」在图上直接可见
    for edge in edges:
        if edge.target not in nodes:
            nodes[edge.target] = ModNode(modid=edge.target, name=edge.target, missing=True)
    for edge in edges:
        edge.ok = not nodes[edge.target].missing
    graph = ModGraph(nodes=list(nodes.values()), edges=edges)
    graph.cycles = _find_cycles(nodes, edges)
    return graph


def _find_cycles(nodes: dict[str, ModNode], edges: list[ModEdge]) -> list[list[str]]:
    """Tarjan 强连通分量；只返回真正的环（含自依赖）。"""
    adjacency: dict[str, set[str]] = {
        modid: set() for modid, node in nodes.items() if not node.missing
    }
    for edge in edges:
        if edge.source in adjacency and edge.target in adjacency:
            adjacency[edge.source].add(edge.target)

    index = 0
    indices: dict[str, int] = {}
    lows: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    groups: list[list[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = lows[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for nxt in adjacency[node]:
            if nxt not in indices:
                visit(nxt)
                lows[node] = min(lows[node], lows[nxt])
            elif nxt in on_stack:
                lows[node] = min(lows[node], indices[nxt])
        if lows[node] == indices[node]:
            group: list[str] = []
            while True:
                item = stack.pop()
                on_stack.discard(item)
                group.append(item)
                if item == node:
                    break
            if len(group) > 1 or node in adjacency[node]:
                groups.append(group)

    for node in adjacency:
        if node not in indices:
            visit(node)
    return groups
