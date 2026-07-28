from pathlib import Path
from unittest.mock import MagicMock, patch

import networkx as nx
import pytest

from pbix_atlas.api.service import LineageGraphCache


def _make_graph():
    g = nx.DiGraph()
    g.add_node("src1", type="source", label="http://example.com")
    g.add_node("q1", type="query", label="Query1")
    g.add_node("col1", type="column", label="Col1")
    g.add_edge("src1", "q1", type="feeds")
    g.add_edge("q1", "col1", type="feeds")
    return g


@pytest.fixture
def cache():
    builder = MagicMock()
    builder.build.return_value = _make_graph()
    return LineageGraphCache(builder=builder)


def test_get_or_build(cache):
    g = cache.get_or_build("/fake/path.pbix")
    assert g.has_node("src1")
    assert g.has_node("q1")


def test_get_or_build_caches(cache):
    g1 = cache.get_or_build("/fake/path.pbix")
    g2 = cache.get_or_build("/fake/path.pbix")
    assert g1 is g2


def test_loaded_paths(cache):
    assert cache.loaded_paths() == []
    cache.get_or_build("/fake/path.pbix")
    assert len(cache.loaded_paths()) == 1


def test_summary(cache):
    s = cache.summary("/fake/path.pbix")
    assert "node_counts" in s
    assert "edge_count" in s
    assert s["edge_count"] == 2


def test_search(cache):
    results = cache.search("/fake/path.pbix", "src")
    assert "src1" in results


def test_upstream(cache):
    nodes = cache.upstream("/fake/path.pbix", "col1")
    assert "src1" in nodes
    assert "q1" in nodes


def test_downstream(cache):
    nodes = cache.downstream("/fake/path.pbix", "src1")
    assert "col1" in nodes


def test_tree(cache):
    tree = cache.tree("/fake/path.pbix", "src1", direction="downstream", max_depth=5)
    assert tree["id"] == "src1"


def test_export(cache, tmp_path):
    result = cache.export("/fake/path.pbix", str(tmp_path))
    assert "graphml_path" in result
    assert "nodes_csv_path" in result
    assert "edges_csv_path" in result
    assert "json_path" in result
    assert Path(result["graphml_path"]).exists()
    assert Path(result["nodes_csv_path"]).exists()


def test_codegen_default_output(cache, tmp_path):
    pbix_path = str(tmp_path / "report.pbix")
    Path(pbix_path).touch()
    with patch("pbix_atlas.api.service.generate_python_pipeline_with_stats") as mock_gen:
        mock_gen.return_value = (Path("/tmp/out.py"), {"queries": 1})
        result = cache.codegen(pbix_path)
        assert "output_path" in result
        assert "stats" in result


def test_codegen_with_output(cache, tmp_path):
    output = str(tmp_path / "out.py")
    with patch("pbix_atlas.api.service.generate_python_pipeline_with_stats") as mock_gen:
        mock_gen.return_value = (Path(output), {"queries": 1})
        result = cache.codegen("/fake/pbix", output)
        assert "output_path" in result


def test_summary_removes_internal_counts(cache):
    s = cache.summary("/fake/path.pbix")
    assert "_nodes_total" not in s["node_counts"]
    assert "_edges_total" not in s


def test_upstream_with_relationships(cache):
    nodes = cache.upstream("/fake/path.pbix", "col1", include_relationships=True)
    assert isinstance(nodes, list)


def test_downstream_with_relationships(cache):
    nodes = cache.downstream("/fake/path.pbix", "src1", include_relationships=True)
    assert isinstance(nodes, list)
