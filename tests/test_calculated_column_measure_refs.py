import networkx as nx
import pandas as pd

from pbix_atlas.graph_builder import LineageGraphBuilder
from pbix_atlas.models import EdgeType, NodeType, node_id


class _StubModel:
    """Minimal stand-in for PBIXModel exposing just what the two methods
    under test need."""

    def __init__(self, calculated_columns_df: pd.DataFrame, measures_df: pd.DataFrame):
        self._cc = calculated_columns_df
        self._m = measures_df

    def calculated_columns(self) -> pd.DataFrame:
        return self._cc

    def measures(self) -> pd.DataFrame:
        return self._m


def test_calculated_column_can_reference_a_measure():
    """A calculated column's DAX can legitimately call a measure (e.g. via
    CALCULATE(...)). Resolving calculated columns before measures exist in
    the lookup - or without passing measure_lookup at all - would silently
    (or, post unresolved-fallback, needlessly) fail this every time."""
    cc_df = pd.DataFrame(
        [{"TableName": "T", "ColumnName": "Status", "Expression": "IF(T[X] > CALCULATE([Avg Measure]), \"OK\", \"KO\")"}]
    )
    measures_df = pd.DataFrame([{"TableName": "T", "Name": "Avg Measure", "Expression": "AVERAGE(T[X])"}])
    model = _StubModel(cc_df, measures_df)

    builder = LineageGraphBuilder()
    g = nx.DiGraph()
    column_lookup: dict[tuple[str, str], str] = {("T", "X"): node_id(NodeType.COLUMN, "T", "X")}
    g.add_node(column_lookup[("T", "X")], type=NodeType.COLUMN.value, label="X", table="T")

    cc_returned_df = builder._add_calculated_columns(g, model, column_lookup)
    measure_lookup = builder._add_measures(g, model, column_lookup)
    builder._resolve_calculated_column_refs(g, cc_returned_df, column_lookup, measure_lookup)

    cid = node_id(NodeType.CALCULATED_COLUMN, "T", "Status")
    mid = node_id(NodeType.MEASURE, "T", "Avg Measure")
    assert g.has_edge(mid, cid)
    assert g.edges[mid, cid]["type"] == EdgeType.DERIVES_FROM.value
    # and no unresolved node should have been created for this reference
    assert not any(d.get("type") == NodeType.UNRESOLVED.value for _, d in g.nodes(data=True))
