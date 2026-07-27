"""Builds the universal lineage graph of a .pbix file.

LineageGraphBuilder orchestrates source detection, the pbixray adapter, and
the DAX/M/Layout parsers to produce a networkx.DiGraph from physical source
down to visual field. It depends only on abstractions, so any piece can be
swapped without touching the rest (dependency inversion).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import networkx as nx

from .dax import DaxReferenceParser
from .layout import ReportLayoutParser
from .models import DaxReference, EdgeType, NodeType, node_id
from .mquery import MQueryDependencyResolver
from .pbix_model import PBIXModel
from .sources import SourceDetectorRegistry, normalize_source_identifier


class LineageGraphBuilder:
    def __init__(
        self,
        source_registry: Optional[SourceDetectorRegistry] = None,
        dax_parser: Optional[DaxReferenceParser] = None,
        m_resolver: Optional[MQueryDependencyResolver] = None,
        layout_parser: Optional[ReportLayoutParser] = None,
    ):
        self.source_registry = source_registry or SourceDetectorRegistry()
        self.dax_parser = dax_parser or DaxReferenceParser()
        self.m_resolver = m_resolver or MQueryDependencyResolver()
        self.layout_parser = layout_parser or ReportLayoutParser()

    def build(self, pbix_path: str | Path) -> nx.DiGraph:
        pbix_path = Path(pbix_path)
        model = PBIXModel(pbix_path)
        g = nx.DiGraph()

        queries = model.queries()
        self._add_sources_and_queries(g, queries)
        self._add_query_dependencies(g, queries)

        column_lookup = self._add_columns(g, model)
        self._add_calculated_columns(g, model, column_lookup)
        measure_lookup = self._add_measures(g, model, column_lookup)
        self._add_relationships(g, model, column_lookup)

        try:
            layout = self.layout_parser.load_raw_layout(pbix_path)
            self._add_visual_fields(g, layout, pbix_path.name, column_lookup, measure_lookup)
        except KeyError:
            pass  # some .pbix files (dataset only, no report) have no Report/Layout

        return g

    def _add_sources_and_queries(self, g: nx.DiGraph, queries: dict[str, str]) -> None:
        from .m_parser import LetExpr, ast_to_dict, parse_m_expression

        for name, expr in queries.items():
            qid = node_id(NodeType.QUERY, name)
            g.add_node(qid, type=NodeType.QUERY.value, label=name)

            for ref in self.source_registry.detect(expr):
                sid = node_id(NodeType.SOURCE, ref.system, normalize_source_identifier(ref))
                g.add_node(sid, type=NodeType.SOURCE.value, label=ref.identifier, system=ref.system)
                g.add_edge(sid, qid, type=EdgeType.FEEDS.value)

            # Each step node carries its operation as a structured tree
            # (function + arguments, JSON-safe) - not generated code. The
            # code generator reads this and produces Python from it.
            try:
                ast = parse_m_expression(expr)
            except Exception:  # noqa: BLE001 - keep the query node even if parsing fails
                g.nodes[qid]["body"] = None
                continue

            is_let = isinstance(ast, LetExpr)
            g.nodes[qid]["body"] = json.dumps(ast_to_dict(ast.body if is_let else ast))
            prev_id = None
            for order, (step_name, step_expr) in enumerate(ast.steps if is_let else []):
                func = step_expr.func.name if hasattr(step_expr, "func") and hasattr(step_expr.func, "name") else ""
                step_id = f"{qid}::{step_name}"
                g.add_node(
                    step_id, type="step", label=step_name, function=func,
                    operation=json.dumps(ast_to_dict(step_expr)), order=order,
                )
                g.add_edge(qid, step_id, type="contains")
                if prev_id:
                    g.add_edge(prev_id, step_id, type=EdgeType.FEEDS.value)
                prev_id = step_id

    def _add_query_dependencies(self, g: nx.DiGraph, queries: dict[str, str]) -> None:
        deps_graph = self.m_resolver.resolve(queries)
        for name, deps in deps_graph.items():
            qid = node_id(NodeType.QUERY, name)
            for dep in deps:
                g.add_edge(node_id(NodeType.QUERY, dep), qid, type=EdgeType.FEEDS.value)

    def _add_columns(self, g: nx.DiGraph, model: PBIXModel) -> dict[tuple[str, str], str]:
        lookup: dict[tuple[str, str], str] = {}
        for _, row in model.schema_columns().iterrows():
            table, col = str(row["TableName"]), str(row["ColumnName"])
            cid = node_id(NodeType.COLUMN, table, col)
            g.add_node(cid, type=NodeType.COLUMN.value, label=col, table=table)

            qid = node_id(NodeType.QUERY, table)
            if g.has_node(qid):
                g.add_edge(qid, cid, type=EdgeType.FEEDS.value)

            lookup[(table, col)] = cid
        return lookup

    def _add_calculated_columns(
        self, g: nx.DiGraph, model: PBIXModel, column_lookup: dict[tuple[str, str], str]
    ) -> None:
        for _, row in model.calculated_columns().iterrows():
            table, col, expr = str(row["TableName"]), str(row["ColumnName"]), str(row["Expression"])
            cid = node_id(NodeType.CALCULATED_COLUMN, table, col)
            g.add_node(cid, type=NodeType.CALCULATED_COLUMN.value, label=col, table=table)
            column_lookup[(table, col)] = cid  # a calculated column takes precedence over a same-named physical one

            for ref in self.dax_parser.parse(expr):
                dep_id = self._resolve_dax_reference(ref, default_table=table, column_lookup=column_lookup)
                if dep_id and dep_id != cid:
                    g.add_edge(dep_id, cid, type=EdgeType.DERIVES_FROM.value)

    def _add_measures(
        self, g: nx.DiGraph, model: PBIXModel, column_lookup: dict[tuple[str, str], str]
    ) -> dict[tuple[str, str], str]:
        measure_lookup: dict[tuple[str, str], str] = {}
        measures_df = model.measures()

        for _, row in measures_df.iterrows():
            table, name, expr = str(row["TableName"]), str(row["Name"]), str(row["Expression"])
            mid = node_id(NodeType.MEASURE, table, name)
            g.add_node(mid, type=NodeType.MEASURE.value, label=name, table=table, dax_expression=expr)
            measure_lookup[(table, name)] = mid

        for _, row in measures_df.iterrows():
            table, name, expr = str(row["TableName"]), str(row["Name"]), str(row["Expression"])
            mid = node_id(NodeType.MEASURE, table, name)
            for ref in self.dax_parser.parse(expr):
                dep_id = self._resolve_dax_reference(
                    ref, default_table=table, column_lookup=column_lookup, measure_lookup=measure_lookup
                )
                if dep_id and dep_id != mid:
                    g.add_edge(dep_id, mid, type=EdgeType.DERIVES_FROM.value)

        return measure_lookup

    def _resolve_dax_reference(
        self,
        ref: DaxReference,
        default_table: str,
        column_lookup: dict[tuple[str, str], str],
        measure_lookup: Optional[dict[tuple[str, str], str]] = None,
    ) -> Optional[str]:
        measure_lookup = measure_lookup or {}

        if ref.table:
            if (ref.table, ref.name) in column_lookup:
                return column_lookup[(ref.table, ref.name)]
            if (ref.table, ref.name) in measure_lookup:
                return measure_lookup[(ref.table, ref.name)]
        else:
            # unqualified [Field]: DAX convention -> measure, same table first, then global
            if (default_table, ref.name) in measure_lookup:
                return measure_lookup[(default_table, ref.name)]
            for (_tbl, nm), mnode_id in measure_lookup.items():
                if nm == ref.name:
                    return mnode_id
            if (default_table, ref.name) in column_lookup:
                return column_lookup[(default_table, ref.name)]

        return None

    def _add_relationships(
        self, g: nx.DiGraph, model: PBIXModel, column_lookup: dict[tuple[str, str], str]
    ) -> None:
        for _, row in model.relationships().iterrows():
            from_id = column_lookup.get((str(row["FromTableName"]), str(row["FromColumnName"])))
            to_id = column_lookup.get((str(row["ToTableName"]), str(row["ToColumnName"])))
            if from_id and to_id:
                g.add_edge(from_id, to_id, type=EdgeType.RELATES_TO.value)
                g.add_edge(to_id, from_id, type=EdgeType.RELATES_TO.value)

    def _add_visual_fields(
        self,
        g: nx.DiGraph,
        layout: dict,
        pbix_name: str,
        column_lookup: dict[tuple[str, str], str],
        measure_lookup: dict[tuple[str, str], str],
    ) -> None:
        from .layout_roles import extract_visual_specs

        role_lookup: dict[tuple[str, int, str, str], str] = {}
        for spec in extract_visual_specs(layout):
            for role, fields in spec.roles.items():
                for table, field_name, _kind in fields:
                    role_lookup[(spec.page, spec.visual_index, table or "", field_name)] = role

        for usage in self.layout_parser.iter_visual_fields(layout):
            vid = node_id(NodeType.VISUAL_FIELD, pbix_name, usage.page, str(usage.visual_index), usage.field)
            role = role_lookup.get((usage.page, usage.visual_index, usage.table or "", usage.field), "")
            g.add_node(
                vid,
                type=NodeType.VISUAL_FIELD.value,
                label=usage.field,
                page=usage.page,
                visual_index=usage.visual_index,
                visual_type=usage.visual_type,
                role=role,
            )

            source_id = None
            if usage.table:
                if usage.field_kind == "Measure":
                    source_id = measure_lookup.get((usage.table, usage.field))
                else:
                    source_id = column_lookup.get((usage.table, usage.field))
                    if source_id is None:
                        source_id = measure_lookup.get((usage.table, usage.field))

            if source_id:
                g.add_edge(source_id, vid, type=EdgeType.DISPLAYED_IN.value)
            else:
                # kept visible rather than silently dropped: a field the report
                # shows but that couldn't be matched back to the model
                unresolved_id = node_id(NodeType.UNRESOLVED, pbix_name, usage.table or "?", usage.field)
                g.add_node(unresolved_id, type=NodeType.UNRESOLVED.value, label=usage.field)
                g.add_edge(unresolved_id, vid, type=EdgeType.DISPLAYED_IN.value)
