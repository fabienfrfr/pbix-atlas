import networkx as nx
import pytest

from pbix_atlas.levels import get_level


def _make_graph():
    g = nx.DiGraph()
    g.add_node("src1", type="source", name="SRC1")
    g.add_node("src2", type="source", name="SRC2")
    g.add_node("t1", type="query", name="T1")
    g.add_node("t2", type="query", name="T2")
    g.add_node("c1", type="column", name="C1")
    g.add_edge("src1", "t1")
    g.add_edge("src1", "t2")
    g.add_edge("t2", "c1")
    return g


def test_get_level_depth_1():
    g = _make_graph()
    result = get_level(g, depth=1)
    assert len(result) == 2
    names = {r["name"] for r in result}
    assert names == {"SRC1", "SRC2"}


def test_get_level_depth_2():
    g = _make_graph()
    result = get_level(g, depth=2)
    assert len(result) == 2
    names = {r["name"] for r in result}
    assert names == {"T1", "T2"}


def test_get_level_invalid_depth():
    g = _make_graph()
    with pytest.raises(ValueError):
        get_level(g, depth=0)
