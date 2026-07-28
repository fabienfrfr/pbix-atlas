"""Graph navigation: depends only on networkx, nothing Power BI-specific.

Edges point from upstream to downstream, so the graph is inherently
reversible: upstream/downstream are just two traversals of the same graph.
"""

from __future__ import annotations

import json
from contextlib import suppress
from pathlib import Path

import networkx as nx
import pandas as pd

from .models import EdgeType


def upstream(graph: nx.DiGraph, node: str, include_relationships: bool = False) -> set[str]:
    """Upstream. Takes `graph`, `node`, `include_relationships`."""
    working_graph = graph if include_relationships else _without_relationships(graph)
    return nx.ancestors(working_graph, node) if node in working_graph else set()


def downstream(graph: nx.DiGraph, node: str, include_relationships: bool = False) -> set[str]:
    """Downstream. Takes `graph`, `node`, `include_relationships`."""
    working_graph = graph if include_relationships else _without_relationships(graph)
    return nx.descendants(working_graph, node) if node in working_graph else set()


def _without_relationships(graph: nx.DiGraph) -> nx.DiGraph:
    edges_to_drop = [(u, v) for u, v, d in graph.edges(data=True) if d.get("type") == EdgeType.RELATES_TO.value]
    if not edges_to_drop:
        return graph
    g2 = graph.copy()
    g2.remove_edges_from(edges_to_drop)
    return g2


def find_nodes(graph: nx.DiGraph, name_contains: str) -> list[str]:
    """Find nodes. Takes `graph`, `name_contains`."""
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
    """Print tree. Takes `graph`, `node`, `direction`, `max_depth`."""
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


def _graphml_safe_value(value):
    """GraphML attributes must be str/int/float/bool/long: no None, no dict/list."""
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def export_graphml(graph: nx.DiGraph, path: str | Path) -> None:
    """Export graphml. Takes `graph`, `path`."""
    safe_graph = nx.DiGraph()
    for n, data in graph.nodes(data=True):
        safe_graph.add_node(n, **{k: _graphml_safe_value(v) for k, v in data.items()})
    for u, v, data in graph.edges(data=True):
        safe_graph.add_edge(u, v, **{k: _graphml_safe_value(val) for k, val in data.items()})
    nx.write_graphml(safe_graph, str(path))


def export_edges_csv(graph: nx.DiGraph, path: str | Path) -> None:
    """Export edges csv. Takes `graph`, `path`."""
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
    """Export nodes csv. Takes `graph`, `path`."""
    rows = [{"id": n, **d} for n, d in graph.nodes(data=True)]
    pd.DataFrame(rows).to_csv(path, index=False)


def export_json(graph: nx.DiGraph, path: str | Path) -> Path:
    """Node-link JSON export of the graph. More readable than GraphML:
    `operation`/`body` are nested JSON objects here (GraphML flattens them
    to strings out of necessity).

    Moved here from `codegen.py`: it's a plain graph export like
    `export_graphml`/`export_nodes_csv`/`export_edges_csv` above, with no
    dependency on the Python-pipeline code generator. Building a
    `PythonPipelineGenerator` (which re-reads and re-parses the whole .pbix)
    just to call this was unnecessary coupling - this now works on any
    already-built graph, exactly like its siblings."""
    data = nx.node_link_data(graph, edges="edges")
    for node in data["nodes"]:
        for key in ("operation", "body"):
            if isinstance(node.get(key), str):
                with suppress(json.JSONDecodeError):
                    node[key] = json.loads(node[key])
    path = Path(path)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def source_schema(graph: nx.DiGraph) -> dict[str, dict[str, dict]]:
    """Nested {source_label: {table_label: {"view": str|None, "columns":
    [...], "names_reliable": bool}}}, covering every physical source down
    to its columns - exactly the "which attributes come from which
    source" view, as a reusable structure instead of a one-off script.

    `view` is the remote entity/table name a query actually reads, when
    that's different from (and more informative than) the local query
    name - e.g. an OData query picking one entity out of a navigation
    table via `Source{[Name="RemoteEntity", Signature="table"]}[Data]`.
    None when the query name already *is* the real table (e.g. HTTP/CSV
    endpoints, one URL per table).

    `names_reliable` is False when a column list was statically inferred
    (see `schema_infer.py`) from *after* a table-driven rename step that
    couldn't be resolved - meaning those specific names are NOT the
    source's original column names, just whatever that dynamic rename
    produced, which cannot be known without executing the query against
    the live source. Columns straight from the loaded semantic model, or
    inferred before any such rename, are marked reliable.

    A source sometimes feeds a "pass-through" query with no columns of its
    own (a URL parameter, or a thin wrapper like `OData.Feed(...)`) before
    reaching the real staging tables - so this follows `query --feeds-->
    query` edges *only* through such column-less queries, and stops as
    soon as a query actually has columns, rather than walking the entire
    downstream BRZ->SLV->GLD pipeline (which is a separate question from
    "what does this source directly provide")."""

    def _columns_of(qid: str) -> dict:
        columns = []
        reliable = True
        renamed: dict[str, str] = {}
        for c in graph.successors(qid):
            cdata = graph.nodes[c]
            if cdata.get("type") not in ("column", "calculated_column"):
                continue
            columns.append(cdata["label"])
            if cdata.get("names_are_post_rename"):
                reliable = False
            source_col = cdata.get("source_column")
            if source_col and source_col != cdata["label"]:
                renamed[cdata["label"]] = source_col
        return {
            "view": graph.nodes[qid].get("view"),
            "columns": sorted(columns),
            "names_reliable": reliable,
            "renamed_columns": renamed,  # {current_name: original_source_name}, only when
            # a *literal* (statically resolvable) rename was applied - see schema_infer.py
        }

    result: dict[str, dict[str, dict]] = {}
    for node, data in graph.nodes(data=True):
        if data.get("type") != "source":
            continue

        tables: dict[str, dict] = {}
        seen: set[str] = set()
        frontier = [n for n in graph.successors(node) if graph.nodes[n].get("type") == "query"]
        while frontier:
            qid = frontier.pop()
            if qid in seen:
                continue
            seen.add(qid)
            info = _columns_of(qid)
            tables[graph.nodes[qid]["label"]] = info
            # keep following the chain only through genuine pass-throughs
            # (no columns AND no resolved view/entity name); a query with a
            # `view` is a real leaf staging table by construction, even if
            # its column extraction happened to fail - don't walk past it
            # into its own downstream pipeline (that's BRZ->SLV->GLD, a
            # separate question from "what this source directly provides").
            if not info["columns"] and info["view"] is None:
                frontier.extend(
                    n for n in graph.successors(qid) if graph.nodes[n].get("type") == "query" and n not in seen
                )
        result[data["label"]] = tables
    return result


def render_source_tree_lines(graph: nx.DiGraph) -> list[str]:
    """Renders `source_schema` as ASCII tree lines: source -> [view ->]
    table (column count) -> column names. Shared by `print_source_schema`
    and `reports.render_source_tree_markdown` so both stay in sync -
    there's exactly one place that knows how to draw this tree.

    Tables are grouped under their `view` (the real remote entity/table
    name, e.g. for an OData source) when one is known; otherwise they
    hang directly off the source, as before."""
    lines: list[str] = []
    for source, tables in source_schema(graph).items():
        lines.append(source)

        grouped: dict[str | None, dict[str, dict]] = {}
        for table, info in tables.items():
            grouped.setdefault(info.get("view"), {})[table] = info
        groups = list(grouped.items())

        for gi, (view, group_tables) in enumerate(groups):
            is_last_group = gi == len(groups) - 1
            indent = "    " if is_last_group else "│   "
            if view is not None:
                branch = "└──" if is_last_group else "├──"
                lines.append(f"{branch} {view}")
                table_prefix = indent
            else:
                table_prefix = ""

            table_names = list(group_tables)
            for i, table in enumerate(table_names):
                is_last_table = i == len(table_names) - 1
                branch = "└──" if is_last_table else "├──"
                info = group_tables[table]
                cols = info["columns"]
                flag = "" if info["names_reliable"] else "  [names may be renamed, unresolved]"
                lines.append(f"{table_prefix}{branch} {table} ({len(cols)} cols){flag}")
                if not cols:
                    continue
                pad = table_prefix + ("     " if is_last_table else "│   ")
                renamed = info.get("renamed_columns", {})
                col_strs = [f"{c} (was: {renamed[c]})" if c in renamed else c for c in cols]
                lines.append(f"{pad}  {', '.join(col_strs)}")
    return lines


def print_source_schema(graph: nx.DiGraph) -> None:
    """Prints `render_source_tree_lines` to stdout."""
    print("\n".join(render_source_tree_lines(graph)))


def output_schema(graph: nx.DiGraph) -> dict[str, dict]:
    """{page_label: {"visual_count": int, "by_source_type": {type: count},
    "unresolved": [field_label, ...]}}, the symmetric counterpart of
    `source_schema` for the *output* side: report pages -> what actually
    feeds the fields shown on them (column / calculated_column / measure /
    unresolved).

    `unresolved` lists fields shown on the page that couldn't be traced
    back to any column or measure - see `_add_unresolved_dax_ref` /
    `_add_visual_fields` in `graph_builder.py`. A non-empty list here is a
    real gap in the model or the lineage extraction, not a display quirk."""
    result: dict[str, dict] = {}
    for node, data in graph.nodes(data=True):
        if data.get("type") != "visual_field":
            continue
        page = data["page"]
        entry = result.setdefault(page, {"visual_count": 0, "by_source_type": {}, "unresolved": []})
        entry["visual_count"] += 1

        sources = [p for p in graph.predecessors(node) if graph.nodes[p].get("type") != "visual_field"]
        if not sources:
            continue
        source_type = graph.nodes[sources[0]].get("type", "?")
        entry["by_source_type"][source_type] = entry["by_source_type"].get(source_type, 0) + 1
        if source_type == "unresolved":
            entry["unresolved"].append(data["label"])
    return result


def print_output_schema(graph: nx.DiGraph) -> None:
    """Prints `output_schema` as a condensed ASCII tree: page -> field
    count by source type, with any unresolved fields called out."""
    for page, info in output_schema(graph).items():
        by_type = ", ".join(f"{n} {t}" for t, n in info["by_source_type"].items())
        print(f"{page} ({info['visual_count']} champs) : {by_type}")
        for field in info["unresolved"]:
            print(f"  ⚠ non résolu : {field}")


def graph_summary(graph: nx.DiGraph) -> dict[str, int]:
    """Graph summary. Takes `graph`."""
    counts: dict[str, int] = {}
    for _, d in graph.nodes(data=True):
        counts[d.get("type", "?")] = counts.get(d.get("type", "?"), 0) + 1
    counts["_edges_total"] = graph.number_of_edges()
    counts["_nodes_total"] = graph.number_of_nodes()
    return counts
