"""Application-level service: caches lineage graphs and exposes them through
plain Python calls. Framework-agnostic on purpose, so it can be tested or
reused without spinning up FastAPI.
"""

from __future__ import annotations

from pathlib import Path

import networkx as nx

from ..codegen import generate_python_pipeline_with_stats
from ..graph_builder import LineageGraphBuilder
from ..navigation import (
    build_tree,
    downstream,
    export_edges_csv,
    export_graphml,
    export_json,
    export_nodes_csv,
    find_nodes,
    graph_summary,
    source_schema,
    upstream,
)
from ..reports import render_source_tree_markdown


class LineageGraphCache:
    """Builds each .pbix graph once and keeps it in memory, keyed by
    resolved path. A cached graph is automatically rebuilt if the file's
    mtime on disk has changed since it was cached; `invalidate`/
    `invalidate_all` force a rebuild on the next call regardless of mtime."""

    def __init__(self, builder: LineageGraphBuilder | None = None):
        """Initialize."""
        self._builder = builder or LineageGraphBuilder()
        self._graphs: dict[str, nx.DiGraph] = {}
        self._mtimes: dict[str, float] = {}

    def get_or_build(self, pbix_path: str, force_rebuild: bool = False) -> nx.DiGraph:
        """Return the cached graph for `pbix_path`, building it if it's not
        cached yet, if the file has changed on disk since it was cached
        (mtime comparison), or if `force_rebuild` is set. If the path can't
        be stat'd (e.g. it doesn't exist yet, or is a virtual test path),
        the mtime check is skipped and plain existence-in-cache is used -
        the real error surfaces from `self._builder.build` instead, with a
        clearer message."""
        key = str(Path(pbix_path).resolve())
        try:
            current_mtime: float | None = Path(pbix_path).stat().st_mtime
        except OSError:
            current_mtime = None
        stale = current_mtime is not None and key in self._mtimes and self._mtimes[key] != current_mtime
        if force_rebuild or key not in self._graphs or stale:
            self._graphs[key] = self._builder.build(pbix_path)
            if current_mtime is not None:
                self._mtimes[key] = current_mtime
        return self._graphs[key]

    def invalidate(self, pbix_path: str) -> bool:
        """Drop the cached graph for `pbix_path`, if any. Returns whether
        something was actually evicted. The next call for this path rebuilds
        from disk regardless of mtime."""
        key = str(Path(pbix_path).resolve())
        found = key in self._graphs
        self._graphs.pop(key, None)
        self._mtimes.pop(key, None)
        return found

    def invalidate_all(self) -> int:
        """Drop every cached graph. Returns how many were evicted."""
        count = len(self._graphs)
        self._graphs.clear()
        self._mtimes.clear()
        return count

    def loaded_paths(self) -> list[str]:
        """Loaded paths."""
        return list(self._graphs.keys())

    def summary(self, pbix_path: str, force_rebuild: bool = False) -> dict:
        """Summary. Takes `pbix_path`."""
        graph = self.get_or_build(pbix_path, force_rebuild=force_rebuild)
        counts = graph_summary(graph)
        edge_count = counts.pop("_edges_total")
        counts.pop("_nodes_total", None)
        return {"node_counts": counts, "edge_count": edge_count}

    def search(self, pbix_path: str, query: str) -> list[str]:
        """Search. Takes `pbix_path`, `query`."""
        return find_nodes(self.get_or_build(pbix_path), query)

    def upstream(self, pbix_path: str, node_id: str, include_relationships: bool = False) -> list[str]:
        """Upstream. Takes `pbix_path`, `node_id`, `include_relationships`."""
        return sorted(upstream(self.get_or_build(pbix_path), node_id, include_relationships))

    def downstream(self, pbix_path: str, node_id: str, include_relationships: bool = False) -> list[str]:
        """Downstream. Takes `pbix_path`, `node_id`, `include_relationships`."""
        return sorted(downstream(self.get_or_build(pbix_path), node_id, include_relationships))

    def tree(self, pbix_path: str, node_id: str, direction: str = "downstream", max_depth: int = 12) -> dict:
        """Tree. Takes `pbix_path`, `node_id`, `direction`, `max_depth`."""
        return build_tree(self.get_or_build(pbix_path), node_id, direction=direction, max_depth=max_depth)

    def export(self, pbix_path: str, output_dir: str) -> dict[str, str]:
        """Export. Takes `pbix_path`, `output_dir`."""
        graph = self.get_or_build(pbix_path)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        stem = Path(pbix_path).stem

        graphml_path = out / f"{stem}.graphml"
        nodes_csv_path = out / f"{stem}_nodes.csv"
        edges_csv_path = out / f"{stem}_edges.csv"
        json_path = out / f"{stem}.json"

        export_graphml(graph, graphml_path)
        export_nodes_csv(graph, nodes_csv_path)
        export_edges_csv(graph, edges_csv_path)
        export_json(graph, json_path)

        return {
            "graphml_path": str(graphml_path),
            "nodes_csv_path": str(nodes_csv_path),
            "edges_csv_path": str(edges_csv_path),
            "json_path": str(json_path),
        }

    def source_schema(self, pbix_path: str, title: str = "Source Lineage Report") -> dict:
        """Source-side lineage report: every physical source down to its
        tables/columns, as both Markdown (for humans) and structured JSON
        (for programmatic use). Mirrors what the notebook's
        `print_source_schema`/`write_source_tree_report` produce."""
        graph = self.get_or_build(pbix_path)
        return {
            "markdown": render_source_tree_markdown(graph, title=title),
            "schema_data": source_schema(graph),
        }

    def codegen(self, pbix_path: str, output_path: str = "") -> dict:
        """Generate the standalone Python pipeline for a .pbix. Does not use
        the cached graph (codegen re-reads the .pbix directly), kept as its
        own method purely so the API surface stays symmetrical with the
        lineage-graph endpoints above."""
        out = Path(output_path) if output_path else Path(pbix_path).with_name(f"{Path(pbix_path).stem}_pipeline.py")
        out.parent.mkdir(parents=True, exist_ok=True)
        written_path, stats = generate_python_pipeline_with_stats(pbix_path, out)
        return {"output_path": str(written_path), "stats": stats}
