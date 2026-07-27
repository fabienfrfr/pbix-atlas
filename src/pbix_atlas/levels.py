"""Depth-based views over the lineage graph (source -> table -> column -> ...)."""

from __future__ import annotations

import networkx as nx


def get_level(g: nx.DiGraph, depth: int, root_type: str = "source") -> list[dict]:
    """Nodes `depth` levels down from `root_type` nodes (1-indexed):
    depth=1 -> the root nodes themselves; depth=2 -> their direct children."""
    if depth < 1:
        raise ValueError("depth is 1-indexed: use 1 for the root nodes themselves")
    roots = [n for n, d in g.nodes(data=True) if d.get("type") == root_type]
    frontier = set(roots)
    for _ in range(depth - 1):
        frontier = {succ for n in frontier for succ in g.successors(n)}
    return [g.nodes[n] for n in frontier]


def list_sources(g: nx.DiGraph) -> list[dict]:
    """Just the physical sources - shorthand for `get_level(g, depth=1)`."""
    return get_level(g, depth=1)