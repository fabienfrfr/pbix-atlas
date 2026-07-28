import networkx as nx

from pbix_atlas.graph_builder import LineageGraphBuilder
from pbix_atlas.models import DaxReference, EdgeType, NodeType, node_id


def test_add_unresolved_dax_ref_creates_visible_node_and_edge():
    """A DAX reference that can't be resolved to any known column/measure
    must leave a trace in the graph instead of silently vanishing."""
    g = nx.DiGraph()
    mid = node_id(NodeType.MEASURE, "Mesure", "Some Measure")
    g.add_node(mid, type=NodeType.MEASURE.value, label="Some Measure", table="Mesure")

    builder = LineageGraphBuilder()
    ref = DaxReference(table="Axe_X", name="Value")
    builder._add_unresolved_dax_ref(g, ref, default_table="Mesure", dependent_id=mid)

    unresolved_id = node_id(NodeType.UNRESOLVED, "Axe_X", "Value")
    assert g.nodes[unresolved_id]["type"] == NodeType.UNRESOLVED.value
    assert g.has_edge(unresolved_id, mid)
    assert g.edges[unresolved_id, mid]["type"] == EdgeType.DERIVES_FROM.value


def test_add_unresolved_dax_ref_uses_default_table_for_unqualified_refs():
    g = nx.DiGraph()
    cid = node_id(NodeType.CALCULATED_COLUMN, "DA_GLD", "Some Calc Col")
    g.add_node(cid, type=NodeType.CALCULATED_COLUMN.value, label="Some Calc Col", table="DA_GLD")

    builder = LineageGraphBuilder()
    ref = DaxReference(table=None, name="Missing")
    builder._add_unresolved_dax_ref(g, ref, default_table="DA_GLD", dependent_id=cid)

    unresolved_id = node_id(NodeType.UNRESOLVED, "DA_GLD", "Missing")
    assert unresolved_id in g.nodes
    assert g.has_edge(unresolved_id, cid)


def test_unresolved_id_scheme_matches_visual_field_side():
    """The measure/calc-column fallback and the visual_field fallback must
    converge on the same node id for the same missing (table, field), so a
    field that's both DAX-referenced and shown on a report page produces
    one unresolved node, not two."""
    from pbix_atlas.models import VisualFieldUsage

    g = nx.DiGraph()
    vid = node_id(NodeType.VISUAL_FIELD, "report.pbix", "Page1", "0", "Value")
    g.add_node(vid, type=NodeType.VISUAL_FIELD.value, label="Value")

    usage = VisualFieldUsage(
        page="Page1", visual_index=0, visual_type="card", field_kind="Column", table="Axe_X", field="Value"
    )
    unresolved_id_from_visual = node_id(NodeType.UNRESOLVED, usage.table or "?", usage.field)

    mid = node_id(NodeType.MEASURE, "Mesure", "Some Measure")
    g.add_node(mid, type=NodeType.MEASURE.value, label="Some Measure", table="Mesure")
    builder = LineageGraphBuilder()
    ref = DaxReference(table="Axe_X", name="Value")
    builder._add_unresolved_dax_ref(g, ref, default_table="Mesure", dependent_id=mid)
    unresolved_id_from_measure = node_id(NodeType.UNRESOLVED, "Axe_X", "Value")

    assert unresolved_id_from_visual == unresolved_id_from_measure
