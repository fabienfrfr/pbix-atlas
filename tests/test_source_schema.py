import networkx as nx

from pbix_atlas.models import EdgeType, NodeType
from pbix_atlas.navigation import source_schema


def test_stops_at_first_query_with_columns():
    """A source feeding a query that already has columns should not keep
    walking further downstream (that's the separate BRZ->SLV->GLD pipeline,
    not "what this source directly provides")."""
    g = nx.DiGraph()
    g.add_node("src1", type=NodeType.SOURCE.value, label="my_source")
    g.add_node("q1", type=NodeType.QUERY.value, label="q1")
    g.add_node("q2", type=NodeType.QUERY.value, label="q2")
    g.add_node("col1", type=NodeType.COLUMN.value, label="col1")
    g.add_node("col2", type=NodeType.COLUMN.value, label="col2")
    g.add_edge("src1", "q1", type=EdgeType.FEEDS.value)
    g.add_edge("q1", "q2", type=EdgeType.FEEDS.value)
    g.add_edge("q1", "col1", type=EdgeType.FEEDS.value)
    g.add_edge("q2", "col2", type=EdgeType.FEEDS.value)

    schema = source_schema(g)
    assert schema["my_source"] == {
        "q1": {"view": None, "columns": ["col1"], "names_reliable": True, "renamed_columns": {}}
    }


def test_follows_column_less_pass_through_queries():
    """A source feeding a column-less "root"/parameter query should keep
    walking until it reaches the real staging table(s)."""
    g = nx.DiGraph()
    g.add_node("src1", type=NodeType.SOURCE.value, label="my_source")
    g.add_node("root", type=NodeType.QUERY.value, label="Root")
    g.add_node("staging", type=NodeType.QUERY.value, label="Staging")
    g.add_node("colA", type=NodeType.COLUMN.value, label="colA")
    g.add_edge("src1", "root", type=EdgeType.FEEDS.value)
    g.add_edge("root", "staging", type=EdgeType.FEEDS.value)
    g.add_edge("staging", "colA", type=EdgeType.FEEDS.value)

    schema = source_schema(g)
    assert schema["my_source"] == {
        "Root": {"view": None, "columns": [], "names_reliable": True, "renamed_columns": {}},
        "Staging": {"view": None, "columns": ["colA"], "names_reliable": True, "renamed_columns": {}},
    }


def test_does_not_follow_past_a_query_with_a_resolved_view():
    """A query with a resolved `view` is a genuine leaf staging table by
    construction (an OData entity access was found), even if its column
    extraction happened to fail (0 columns) - traversal must not walk past
    it into its own downstream pipeline."""
    g = nx.DiGraph()
    g.add_node("src1", type=NodeType.SOURCE.value, label="my_source")
    g.add_node("root", type=NodeType.QUERY.value, label="Root")
    g.add_node("leaf", type=NodeType.QUERY.value, label="Leaf_BRZ", view="RemoteEntityName")
    g.add_node("downstream", type=NodeType.QUERY.value, label="Downstream_SLV")
    g.add_node("colX", type=NodeType.COLUMN.value, label="colX")
    g.add_edge("src1", "root", type=EdgeType.FEEDS.value)
    g.add_edge("root", "leaf", type=EdgeType.FEEDS.value)
    g.add_edge("leaf", "downstream", type=EdgeType.FEEDS.value)
    g.add_edge("downstream", "colX", type=EdgeType.FEEDS.value)

    schema = source_schema(g)
    assert schema["my_source"] == {
        "Root": {"view": None, "columns": [], "names_reliable": True, "renamed_columns": {}},
        "Leaf_BRZ": {"view": "RemoteEntityName", "columns": [], "names_reliable": True, "renamed_columns": {}},
    }
    assert "Downstream_SLV" not in schema["my_source"]


def test_multiple_sources_are_independent():
    g = nx.DiGraph()
    g.add_node("src1", type=NodeType.SOURCE.value, label="source_1")
    g.add_node("src2", type=NodeType.SOURCE.value, label="source_2")
    g.add_node("q1", type=NodeType.QUERY.value, label="q1")
    g.add_node("q2", type=NodeType.QUERY.value, label="q2")
    g.add_edge("src1", "q1", type=EdgeType.FEEDS.value)
    g.add_edge("src2", "q2", type=EdgeType.FEEDS.value)

    schema = source_schema(g)
    assert set(schema.keys()) == {"source_1", "source_2"}
    assert schema["source_1"] == {"q1": {"view": None, "columns": [], "names_reliable": True, "renamed_columns": {}}}
    assert schema["source_2"] == {"q2": {"view": None, "columns": [], "names_reliable": True, "renamed_columns": {}}}


def test_names_are_post_rename_marks_table_unreliable():
    """A column captured after an unresolved (table-driven) rename must be
    flagged as unreliable: it is NOT the source's original column name."""
    g = nx.DiGraph()
    g.add_node("src1", type=NodeType.SOURCE.value, label="my_source")
    g.add_node("q1", type=NodeType.QUERY.value, label="q1")
    g.add_node(
        "col1",
        type=NodeType.COLUMN.value,
        label="Nice Name",
        inferred=True,
        dynamic_rename=True,
        names_are_post_rename=True,
    )
    g.add_edge("src1", "q1", type=EdgeType.FEEDS.value)
    g.add_edge("q1", "col1", type=EdgeType.FEEDS.value)

    schema = source_schema(g)
    assert schema["my_source"]["q1"]["names_reliable"] is False


def test_dynamic_rename_before_columns_known_stays_reliable():
    """dynamic_rename=True alone (unresolved rename happened, but *after*
    the columns were captured, e.g. DA_BRZ) does not make names unreliable -
    only names_are_post_rename=True does."""
    g = nx.DiGraph()
    g.add_node("src1", type=NodeType.SOURCE.value, label="my_source")
    g.add_node("q1", type=NodeType.QUERY.value, label="q1")
    g.add_node(
        "col1",
        type=NodeType.COLUMN.value,
        label="raw_code",
        inferred=True,
        dynamic_rename=True,
        names_are_post_rename=False,
    )
    g.add_edge("src1", "q1", type=EdgeType.FEEDS.value)
    g.add_edge("q1", "col1", type=EdgeType.FEEDS.value)

    schema = source_schema(g)
    assert schema["my_source"]["q1"]["names_reliable"] is True
