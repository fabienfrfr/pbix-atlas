"""Application-level service: caches lineage graphs and exposes them through
plain Python calls. Framework-agnostic on purpose, so it can be tested or
reused without spinning up FastAPI.
"""

from __future__ import annotations

from pathlib import Path

import networkx as nx

from ..graph_builder import LineageGraphBuilder
from ..navigation import (
    build_tree,
    downstream,
    export_edges_csv,
    export_graphml,
    export_nodes_csv,
    find_nodes,
    graph_summary,
    upstream,
)


class LineageGraphCache:
    """Builds each .pbix graph once and keeps it in memory, keyed by
    resolved path."""

    def __init__(self, builder: LineageGraphBuilder | None = None):
        self._builder = builder or LineageGraphBuilder()
        self._graphs: dict[str, nx.DiGraph] = {}

    def get_or_build(self, pbix_path: str) -> nx.DiGraph:
        key = str(Path(pbix_path).resolve())
        if key not in self._graphs:
            self._graphs[key] = self._builder.build(pbix_path)
        return self._graphs[key]

    def loaded_paths(self) -> list[str]:
        return list(self._graphs.keys())

    def summary(self, pbix_path: str) -> dict:
        graph = self.get_or_build(pbix_path)
        counts = graph_summary(graph)
        edge_count = counts.pop("_edges_total")
        counts.pop("_nodes_total", None)
        return {"node_counts": counts, "edge_count": edge_count}

    def search(self, pbix_path: str, query: str) -> list[str]:
        return find_nodes(self.get_or_build(pbix_path), query)

    def upstream(self, pbix_path: str, node_id: str, include_relationships: bool = False) -> list[str]:
        return sorted(upstream(self.get_or_build(pbix_path), node_id, include_relationships))

    def downstream(self, pbix_path: str, node_id: str, include_relationships: bool = False) -> list[str]:
        return sorted(downstream(self.get_or_build(pbix_path), node_id, include_relationships))

    def tree(self, pbix_path: str, node_id: str, direction: str = "downstream", max_depth: int = 12) -> dict:
        return build_tree(self.get_or_build(pbix_path), node_id, direction=direction, max_depth=max_depth)

    def export(self, pbix_path: str, output_dir: str) -> dict[str, str]:
        graph = self.get_or_build(pbix_path)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        stem = Path(pbix_path).stem

        graphml_path = out / f"{stem}.graphml"
        nodes_csv_path = out / f"{stem}_nodes.csv"
        edges_csv_path = out / f"{stem}_edges.csv"

        export_graphml(graph, graphml_path)
        export_nodes_csv(graph, nodes_csv_path)
        export_edges_csv(graph, edges_csv_path)

        return {
            "graphml_path": str(graphml_path),
            "nodes_csv_path": str(nodes_csv_path),
            "edges_csv_path": str(edges_csv_path),
        }
