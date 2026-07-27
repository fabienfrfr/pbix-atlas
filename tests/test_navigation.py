import os
import tempfile

import networkx as nx

from pbix_atlas.models import EdgeType, NodeType
from pbix_atlas.navigation import (
    build_tree,
    downstream,
    export_edges_csv,
    export_nodes_csv,
    find_nodes,
    graph_summary,
    upstream,
)


def _make_graph():
    g = nx.DiGraph()
    g.add_node("src1", type=NodeType.SOURCE.value)
    g.add_node("q1", type=NodeType.QUERY.value)
    g.add_node("q2", type=NodeType.QUERY.value)
    g.add_node("col1", type=NodeType.COLUMN.value)
    g.add_node("col2", type=NodeType.COLUMN.value)
    g.add_edge("src1", "q1", type=EdgeType.FEEDS.value)
    g.add_edge("q1", "q2", type=EdgeType.FEEDS.value)
    g.add_edge("q1", "col1", type=EdgeType.FEEDS.value)
    g.add_edge("q2", "col2", type=EdgeType.FEEDS.value)
    return g


def test_upstream():
    g = _make_graph()
    assert upstream(g, "col2") == {"q1", "q2", "src1"}
    assert upstream(g, "src1") == set()


def test_downstream():
    g = _make_graph()
    assert downstream(g, "src1") == {"q1", "q2", "col1", "col2"}
    assert downstream(g, "col2") == set()


def test_upstream_excludes_relationships():
    g = _make_graph()
    g.add_node("q3", type=NodeType.QUERY.value)
    g.add_edge("q1", "q3", type=EdgeType.RELATES_TO.value)
    assert "q1" in upstream(g, "q3", include_relationships=True)
    assert upstream(g, "q3", include_relationships=False) == set()
    assert "q3" in downstream(g, "q1", include_relationships=True)
    assert "q3" not in downstream(g, "q1")


def test_find_nodes():
    g = _make_graph()
    g.add_node("My_Table", type=NodeType.QUERY.value)
    g.add_node("MY_COLUMN", type=NodeType.COLUMN.value)
    assert "My_Table" in find_nodes(g, "my_tab")
    assert "MY_COLUMN" in find_nodes(g, "column")


def test_build_tree():
    g = _make_graph()
    tree = build_tree(g, "src1", direction="downstream")
    assert tree["id"] == "src1"
    assert tree["type"] == NodeType.SOURCE.value
    child_ids = {c["id"] for c in tree["children"]}
    assert child_ids == {"q1"}
    q1_children = {c["id"] for c in tree["children"][0]["children"]}
    assert q1_children == {"q2", "col1"}


def test_graph_summary():
    g = _make_graph()
    s = graph_summary(g)
    assert s[NodeType.SOURCE.value] == 1
    assert s[NodeType.QUERY.value] == 2
    assert s[NodeType.COLUMN.value] == 2
    assert s["_nodes_total"] == 5
    assert s["_edges_total"] == 4


def test_export_csv_roundtrip():
    g = _make_graph()
    with tempfile.TemporaryDirectory() as tmpdir:
        nodes_path = os.path.join(tmpdir, "nodes.csv")
        edges_path = os.path.join(tmpdir, "edges.csv")
        export_nodes_csv(g, nodes_path)
        export_edges_csv(g, edges_path)
        with open(nodes_path) as f:
            lines = f.readlines()
        assert len(lines) == 6  # header + 5 nodes
        assert "id" in lines[0]
        with open(edges_path) as f:
            lines = f.readlines()
        assert len(lines) == 5  # header + 4 edges
        assert "source" in lines[0]
        assert "target" in lines[0]
