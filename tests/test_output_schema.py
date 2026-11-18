import networkx as nx

from pbix_atlas.models import EdgeType, NodeType
from pbix_atlas.navigation import output_schema


def _vf(page, idx, label):
    return f"visual_field::report.pbix::{page}::{idx}::{label}"


def test_counts_by_source_type_per_page():
    g = nx.DiGraph()
    g.add_node("col1", type=NodeType.COLUMN.value, label="col1", table="T")
    g.add_node("m1", type=NodeType.MEASURE.value, label="m1", table="T")
    vf1, vf2 = _vf("PageA", 0, "col1"), _vf("PageA", 1, "m1")
    g.add_node(vf1, type=NodeType.VISUAL_FIELD.value, label="col1", page="PageA")
    g.add_node(vf2, type=NodeType.VISUAL_FIELD.value, label="m1", page="PageA")
    g.add_edge("col1", vf1, type=EdgeType.DISPLAYED_IN.value)
    g.add_edge("m1", vf2, type=EdgeType.DISPLAYED_IN.value)

    schema = output_schema(g)
    assert schema["PageA"]["visual_count"] == 2
    assert schema["PageA"]["by_source_type"] == {"column": 1, "measure": 1}
    assert schema["PageA"]["unresolved"] == []


def test_unresolved_fields_are_listed():
    g = nx.DiGraph()
    unresolved_id = "unresolved::T::Missing"
    g.add_node(unresolved_id, type=NodeType.UNRESOLVED.value, label="Missing")
    vf1 = _vf("PageB", 0, "Missing")
    g.add_node(vf1, type=NodeType.VISUAL_FIELD.value, label="Missing", page="PageB")
    g.add_edge(unresolved_id, vf1, type=EdgeType.DISPLAYED_IN.value)

    schema = output_schema(g)
    assert schema["PageB"]["by_source_type"] == {"unresolved": 1}
    assert schema["PageB"]["unresolved"] == ["Missing"]
