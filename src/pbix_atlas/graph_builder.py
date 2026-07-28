"""Builds the universal lineage graph of a .pbix file.

LineageGraphBuilder orchestrates source detection, the pbixray adapter, and
the DAX/M/Layout parsers to produce a networkx.DiGraph from physical source
down to visual field. It depends only on abstractions, so any piece can be
swapped without touching the rest (dependency inversion).
"""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import pandas as pd

from .dax import DaxReferenceParser
from .layout import ReportLayoutParser
from .models import DaxReference, EdgeType, NodeType, node_id
from .mquery import MQueryDependencyResolver
from .pbix_model import PBIXModel
from .schema_infer import extract_view_name, infer_schema_from_steps
from .sources import SourceDetectorRegistry, normalize_source_identifier


class LineageGraphBuilder:
    """LineageGraphBuilder (see attributes/methods below)."""

    def __init__(
        self,
        source_registry: SourceDetectorRegistry | None = None,
        dax_parser: DaxReferenceParser | None = None,
        m_resolver: MQueryDependencyResolver | None = None,
        layout_parser: ReportLayoutParser | None = None,
    ):
        """Initialize."""
        self.source_registry = source_registry or SourceDetectorRegistry()
        self.dax_parser = dax_parser or DaxReferenceParser()
        self.m_resolver = m_resolver or MQueryDependencyResolver()
        self.layout_parser = layout_parser or ReportLayoutParser()

    def build(self, pbix_path: str | Path) -> nx.DiGraph:
        """Build. Takes `pbix_path`."""
        pbix_path = Path(pbix_path)
        model = PBIXModel(pbix_path)
        g = nx.DiGraph()

        queries = model.queries()
        self._add_sources_and_queries(g, queries)
        self._add_query_dependencies(g, queries)

        column_lookup = self._add_columns(g, model)
        self._add_inferred_columns(g, column_lookup)
        cc_df = self._add_calculated_columns(g, model, column_lookup)
        measure_lookup = self._add_measures(g, model, column_lookup)
        self._resolve_calculated_column_refs(g, cc_df, column_lookup, measure_lookup)
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
            except Exception:
                g.nodes[qid]["body"] = None
                continue

            is_let = isinstance(ast, LetExpr)
            g.nodes[qid]["body"] = json.dumps(ast_to_dict(ast.body if is_let else ast))
            prev_id = None
            step_ops: list[dict] = []
            for order, (step_name, step_expr) in enumerate(ast.steps if is_let else []):
                func = step_expr.func.name if hasattr(step_expr, "func") and hasattr(step_expr.func, "name") else ""
                step_id = f"{qid}::{step_name}"
                op_dict = ast_to_dict(step_expr)
                step_ops.append(op_dict)
                g.add_node(
                    step_id,
                    type="step",
                    label=step_name,
                    function=func,
                    operation=json.dumps(op_dict),
                    order=order,
                )
                g.add_edge(qid, step_id, type="contains")
                if prev_id:
                    g.add_edge(prev_id, step_id, type=EdgeType.FEEDS.value)
                prev_id = step_id

            view_name = extract_view_name(step_ops)
            if view_name:
                g.nodes[qid]["view"] = view_name

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

    def _add_inferred_columns(self, g: nx.DiGraph, column_lookup: dict[tuple[str, str], str]) -> None:
        """For query tables absent from the semantic model (staging/bronze
        queries, never loaded), statically infer column names from their M
        steps instead of leaving them column-less. Best-effort: only adds
        names actually found in the M code (see `schema_infer`), and tags
        each inferred column with `inferred=True`, `dynamic_rename=True`
        when a rename step could not be resolved statically anywhere in
        the chain, and `names_are_post_rename=True` when the specific
        names captured here were read *after* such an unresolved rename -
        meaning they are NOT the source's original column names, just
        whatever that rename happened to produce (unknowable statically).
        `dynamic_rename=True` with `names_are_post_rename=False` (e.g.
        DA_BRZ) means the names ARE the pre-rename/raw source names."""
        import json as _json

        tables_with_columns = {table for table, _ in column_lookup}

        for qid, data in list(g.nodes(data=True)):
            if data.get("type") != NodeType.QUERY.value:
                continue
            table = data["label"]
            if table in tables_with_columns:
                continue  # already has a real schema from the loaded model

            steps = sorted(
                (g.nodes[s] for s in g.successors(qid) if g.nodes[s].get("type") == "step"),
                key=lambda d: d["order"],
            )
            if not steps:
                continue

            ordered_steps = [(s["label"], _json.loads(s["operation"])) for s in steps]
            inferred = infer_schema_from_steps(ordered_steps)
            if not inferred.columns:
                continue

            for col, source_col in zip(
                inferred.columns, inferred.source_columns or [None] * len(inferred.columns), strict=False
            ):
                cid = node_id(NodeType.COLUMN, table, col)
                g.add_node(
                    cid,
                    type=NodeType.COLUMN.value,
                    label=col,
                    table=table,
                    inferred=True,
                    dynamic_rename=inferred.dynamic_rename,
                    names_are_post_rename=inferred.names_are_post_rename,
                    source_column=source_col,
                )
                g.add_edge(qid, cid, type=EdgeType.FEEDS.value)
                column_lookup[(table, col)] = cid

    def _add_calculated_columns(
        self, g: nx.DiGraph, model: PBIXModel, column_lookup: dict[tuple[str, str], str]
    ) -> pd.DataFrame:
        """Registers calculated-column nodes only (no DAX resolution yet).
        Resolution happens later, in `_resolve_calculated_column_refs`, once
        measures are also registered - a calculated column's DAX can
        reference a measure (e.g. `CALCULATE([SomeMeasure], ...)`), so
        resolving it before the measure lookup even exists would silently
        (or, since the `unresolved` fallback was added, visibly but
        needlessly) fail every such reference."""
        cc_df = model.calculated_columns()
        for _, row in cc_df.iterrows():
            table, col = str(row["TableName"]), str(row["ColumnName"])
            cid = node_id(NodeType.CALCULATED_COLUMN, table, col)
            g.add_node(cid, type=NodeType.CALCULATED_COLUMN.value, label=col, table=table)
            column_lookup[(table, col)] = cid  # a calculated column takes precedence over a same-named physical one
        return cc_df

    def _resolve_calculated_column_refs(
        self,
        g: nx.DiGraph,
        cc_df: pd.DataFrame,
        column_lookup: dict[tuple[str, str], str],
        measure_lookup: dict[tuple[str, str], str],
    ) -> None:
        for _, row in cc_df.iterrows():
            table, col, expr = str(row["TableName"]), str(row["ColumnName"]), str(row["Expression"])
            cid = node_id(NodeType.CALCULATED_COLUMN, table, col)
            for ref in self.dax_parser.parse(expr):
                dep_id = self._resolve_dax_reference(
                    ref, default_table=table, column_lookup=column_lookup, measure_lookup=measure_lookup
                )
                if dep_id and dep_id != cid:
                    g.add_edge(dep_id, cid, type=EdgeType.DERIVES_FROM.value)
                elif dep_id is None:
                    self._add_unresolved_dax_ref(g, ref, default_table=table, dependent_id=cid)

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
                elif dep_id is None:
                    self._add_unresolved_dax_ref(g, ref, default_table=table, dependent_id=mid)

        return measure_lookup

    def _add_unresolved_dax_ref(self, g: nx.DiGraph, ref: DaxReference, default_table: str, dependent_id: str) -> None:
        """Mirrors the visual_field fallback: a DAX reference ([Field] or
        Table[Field]) that can't be matched to any known column/measure is
        kept as a visible `unresolved` node rather than being silently
        dropped - e.g. a what-if parameter table like `Axe_X[Value]` that
        isn't loaded as a real column anywhere. Without this, such
        dependencies simply vanished from the graph with no trace."""
        table = ref.table or default_table
        unresolved_id = node_id(NodeType.UNRESOLVED, table, ref.name)
        g.add_node(unresolved_id, type=NodeType.UNRESOLVED.value, label=ref.name, table=table)
        g.add_edge(unresolved_id, dependent_id, type=EdgeType.DERIVES_FROM.value)

    def _resolve_dax_reference(
        self,
        ref: DaxReference,
        default_table: str,
        column_lookup: dict[tuple[str, str], str],
        measure_lookup: dict[tuple[str, str], str] | None = None,
    ) -> str | None:
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

    def _add_relationships(self, g: nx.DiGraph, model: PBIXModel, column_lookup: dict[tuple[str, str], str]) -> None:
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
                # shows but that couldn't be matched back to the model. Same id
                # scheme as `_add_unresolved_dax_ref` (table + field, no pbix
                # name) so both mechanisms converge on one node per missing
                # entity instead of creating duplicates for the same gap.
                unresolved_id = node_id(NodeType.UNRESOLVED, usage.table or "?", usage.field)
                g.add_node(unresolved_id, type=NodeType.UNRESOLVED.value, label=usage.field, table=usage.table)
                g.add_edge(unresolved_id, vid, type=EdgeType.DISPLAYED_IN.value)
