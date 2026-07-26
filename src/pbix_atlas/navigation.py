"""Graph navigation: depends only on networkx, nothing Power BI-specific.

Edges point from upstream to downstream, so the graph is inherently
reversible: upstream/downstream are just two traversals of the same graph.
"""

from __future__ import annotations

from pathlib import Path

import networkx as nx
import pandas as pd

from .models import EdgeType


def upstream(graph: nx.DiGraph, node: str, include_relationships: bool = False) -> set[str]:
    working_graph = graph if include_relationships else _without_relationships(graph)
    return nx.ancestors(working_graph, node) if node in working_graph else set()


def downstream(graph: nx.DiGraph, node: str, include_relationships: bool = False) -> set[str]:
    working_graph = graph if include_relationships else _without_relationships(graph)
    return nx.descendants(working_graph, node) if node in working_graph else set()


def _without_relationships(graph: nx.DiGraph) -> nx.DiGraph:
    edges_to_drop = [
        (u, v) for u, v, d in graph.edges(data=True) if d.get("type") == EdgeType.RELATES_TO.value
    ]
    if not edges_to_drop:
        return graph
    g2 = graph.copy()
    g2.remove_edges_from(edges_to_drop)
    return g2


def find_nodes(graph: nx.DiGraph, name_contains: str) -> list[str]:
    needle = name_contains.lower()
    return [n for n in graph.nodes if needle in n.lower()]


def build_tree(graph: nx.DiGraph, node: str, direction: str = "downstream", max_depth: int = 12) -> dict:
    """Nested {id, type, children} representation, e.g. for JSON/API responses."""
    working_graph = graph.reverse(copy=False) if direction == "upstream" else graph

    def _rec(current: str, depth: int, visited: set[str]) -> dict:
        result = {"id": current, "type": graph.nodes.get(current, {}).get("type", "?"), "children": []}
        if depth >= max_depth or current in visited:
            return result
        visited = visited | {current}
        children = sorted(working_graph.successors(current)) if current in working_graph else []
        result["children"] = [_rec(child, depth + 1, visited) for child in children]
        return result

    return _rec(node, 0, set())


def print_tree(graph: nx.DiGraph, node: str, direction: str = "downstream", max_depth: int = 12) -> None:
    tree = build_tree(graph, node, direction=direction, max_depth=max_depth)

    def _print(entry: dict, prefix: str, is_root: bool) -> None:
        if is_root:
            print(f"{entry['id']}  [{entry['type']}]")
        for i, child in enumerate(entry["children"]):
            is_last = i == len(entry["children"]) - 1
            branch = "└── " if is_last else "├── "
            print(f"{prefix}{branch}{child['id']}  [{child['type']}]")
            _print(child, prefix + ("    " if is_last else "│   "), is_root=False)

    _print(tree, "", is_root=True)


def export_graphml(graph: nx.DiGraph, path: str | Path) -> None:
    nx.write_graphml(graph, str(path))


def export_edges_csv(graph: nx.DiGraph, path: str | Path) -> None:
    rows = [
        {
            "source": u,
            "target": v,
            "edge_type": d.get("type"),
            "source_type": graph.nodes.get(u, {}).get("type"),
            "target_type": graph.nodes.get(v, {}).get("type"),
        }
        for u, v, d in graph.edges(data=True)
    ]
    pd.DataFrame(rows).to_csv(path, index=False)


def export_nodes_csv(graph: nx.DiGraph, path: str | Path) -> None:
    rows = [{"id": n, **d} for n, d in graph.nodes(data=True)]
    pd.DataFrame(rows).to_csv(path, index=False)


def graph_summary(graph: nx.DiGraph) -> dict[str, int]:
    counts: dict[str, int] = {}
    for _, d in graph.nodes(data=True):
        counts[d.get("type", "?")] = counts.get(d.get("type", "?"), 0) + 1
    counts["_edges_total"] = graph.number_of_edges()
    counts["_nodes_total"] = graph.number_of_nodes()
    return counts
