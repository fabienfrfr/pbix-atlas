from contextlib import asynccontextmanager
from pathlib import Path
import tempfile
import zipfile
import json
from unittest.mock import patch

import networkx as nx
import pytest
from fastapi.testclient import TestClient

from pbix_atlas.api.app import app
from pbix_atlas.api.service import LineageGraphCache


def _make_graph():
    g = nx.DiGraph()
    g.add_node("src1", type="source", label="http://example.com")
    g.add_node("q1", type="query", label="Query1")
    g.add_node("col1", type="column", label="Col1")
    g.add_edge("src1", "q1", type="feeds")
    g.add_edge("q1", "col1", type="feeds")
    return g


def _make_pbix(path: Path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("Report/Layout", json.dumps({"sections": []}).encode("utf-16-le"))


@pytest.fixture
def graph():
    return _make_graph()


@pytest.fixture
def cache(graph):
    cache = LineageGraphCache()
    return cache


def _test_lifespan(cache):
    @asynccontextmanager
    async def lifespan(app):
        app.state.cache = cache
        yield

    return lifespan


@pytest.fixture
def client(graph, tmp_path):
    pbix = tmp_path / "report.pbix"
    _make_pbix(pbix)
    cache = LineageGraphCache()
    cache._graphs[str(pbix.resolve())] = graph
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _test_lifespan(cache)
    with TestClient(app) as c:
        yield c, str(pbix)
    app.router.lifespan_context = original_lifespan


@pytest.fixture
def error_client(tmp_path):
    pbix = tmp_path / "report.pbix"
    _make_pbix(pbix)
    cache = LineageGraphCache()
    g = _make_graph()
    cache._graphs[str(pbix.resolve())] = g
    # Override to raise on summary
    original_summary = cache.summary
    cache.summary = lambda pbix_path: (_ for _ in ()).throw(ValueError("test error"))
    cache.search = lambda pbix_path, query: (_ for _ in ()).throw(ValueError("test error"))
    cache.upstream = lambda pbix_path, nid, **kw: (_ for _ in ()).throw(ValueError("test error"))
    cache.downstream = lambda pbix_path, nid, **kw: (_ for _ in ()).throw(ValueError("test error"))
    cache.tree = lambda pbix_path, nid, **kw: (_ for _ in ()).throw(ValueError("test error"))
    cache.export = lambda pbix_path, out_dir: (_ for _ in ()).throw(ValueError("test error"))
    cache.source_schema = lambda pbix_path, title="Source Lineage Report": (_ for _ in ()).throw(
        ValueError("test error")
    )
    cache.codegen = lambda pbix_path, out="": (_ for _ in ()).throw(ValueError("test error"))
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _test_lifespan(cache)
    with TestClient(app) as c:
        yield c, str(pbix)
    app.router.lifespan_context = original_lifespan


def test_build_graph(client):
    c, pbix_path = client
    resp = c.post("/graphs", json={"pbix_path": pbix_path})
    assert resp.status_code == 200
    data = resp.json()
    assert "pbix_path" in data
    assert "node_counts" in data
    assert "edge_count" in data


def test_build_graph_error(error_client):
    c, pbix_path = error_client
    resp = c.post("/graphs", json={"pbix_path": pbix_path})
    assert resp.status_code == 400


def test_list_loaded_graphs(client):
    c, pbix_path = client
    resp = c.get("/graphs")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_invalidate_graph(client):
    c, pbix_path = client
    c.post("/graphs", json={"pbix_path": pbix_path})
    assert c.get("/graphs").json() != []

    resp = c.post("/graphs/invalidate", json={"pbix_path": pbix_path})
    assert resp.status_code == 200
    assert resp.json()["evicted"] is True

    assert c.get("/graphs").json() == []


def test_invalidate_graph_unknown_path(client):
    c, pbix_path = client
    resp = c.post("/graphs/invalidate", json={"pbix_path": "/never/built.pbix"})
    assert resp.status_code == 200
    assert resp.json()["evicted"] is False


def test_invalidate_all_graphs(client):
    c, pbix_path = client
    c.post("/graphs", json={"pbix_path": pbix_path})
    resp = c.post("/graphs/invalidate-all")
    assert resp.status_code == 200
    assert resp.json()["evicted_count"] >= 1
    assert c.get("/graphs").json() == []


def test_build_graph_accepts_force_rebuild_flag(client):
    """force_rebuild triggers a real re-parse (unlike the other client tests,
    which pre-seed a fake graph into the cache) - the actual rebuild
    behavior is unit-tested at the service layer; here we only check the
    request schema round-trips the flag without erroring on validation."""
    c, pbix_path = client
    resp = c.post("/graphs", json={"pbix_path": pbix_path, "force_rebuild": False})
    assert resp.status_code == 200


def test_search_nodes(client):
    c, pbix_path = client
    resp = c.post("/search", json={"pbix_path": pbix_path, "query": "src"})
    assert resp.status_code == 200
    data = resp.json()
    assert "src1" in data["nodes"]


def test_search_nodes_error(error_client):
    c, pbix_path = error_client
    resp = c.post("/search", json={"pbix_path": pbix_path, "query": "x"})
    assert resp.status_code == 400


def test_get_upstream(client):
    c, pbix_path = client
    resp = c.post(
        "/upstream",
        json={"pbix_path": pbix_path, "node_id": "col1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "src1" in data["nodes"]


def test_get_upstream_error(error_client):
    c, pbix_path = error_client
    resp = c.post(
        "/upstream",
        json={"pbix_path": pbix_path, "node_id": "col1"},
    )
    assert resp.status_code == 400


def test_get_downstream(client):
    c, pbix_path = client
    resp = c.post(
        "/downstream",
        json={"pbix_path": pbix_path, "node_id": "src1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "col1" in data["nodes"]


def test_get_downstream_error(error_client):
    c, pbix_path = error_client
    resp = c.post(
        "/downstream",
        json={"pbix_path": pbix_path, "node_id": "src1"},
    )
    assert resp.status_code == 400


def test_get_lineage_tree(client):
    c, pbix_path = client
    resp = c.post(
        "/tree",
        json={
            "pbix_path": pbix_path,
            "node_id": "src1",
            "direction": "downstream",
            "max_depth": 5,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "src1"
    assert "children" in data


def test_get_lineage_tree_error(error_client):
    c, pbix_path = error_client
    resp = c.post(
        "/tree",
        json={
            "pbix_path": pbix_path,
            "node_id": "src1",
            "direction": "upstream",
        },
    )
    assert resp.status_code == 400


def test_export_graph(client, tmp_path):
    c, pbix_path = client
    resp = c.post(
        "/export",
        json={"pbix_path": pbix_path, "output_dir": str(tmp_path)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "graphml_path" in data


def test_export_graph_error(error_client):
    c, pbix_path = error_client
    resp = c.post(
        "/export",
        json={"pbix_path": pbix_path, "output_dir": "/tmp"},
    )
    assert resp.status_code == 400


def test_get_source_schema(client):
    c, pbix_path = client
    resp = c.post("/source-schema", json={"pbix_path": pbix_path})
    assert resp.status_code == 200
    data = resp.json()
    assert "markdown" in data
    assert "schema_data" in data
    assert "Source Lineage Report" in data["markdown"]


def test_get_source_schema_custom_title(client):
    c, pbix_path = client
    resp = c.post("/source-schema", json={"pbix_path": pbix_path, "title": "My Title"})
    assert resp.status_code == 200
    assert "My Title" in resp.json()["markdown"]


def test_get_source_schema_error(error_client):
    c, pbix_path = error_client
    resp = c.post("/source-schema", json={"pbix_path": pbix_path})
    assert resp.status_code == 400


def test_codegen(client, tmp_path):
    c, pbix_path = client
    with patch("pbix_atlas.api.service.generate_python_pipeline_with_stats") as mock_codegen:
        mock_codegen.return_value = (str(tmp_path / "out.py"), {"tables": 1})
        resp = c.post(
            "/codegen",
            json={"pbix_path": pbix_path, "output_path": str(tmp_path / "out.py")},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "output_path" in data
    assert "stats" in data


def test_codegen_default_path(client):
    c, pbix_path = client
    with patch("pbix_atlas.api.service.generate_python_pipeline_with_stats") as mock_codegen:

        def _mock_codegen(p, out):
            return (str(out), {"tables": 1})

        mock_codegen.side_effect = _mock_codegen
        resp = c.post(
            "/codegen",
            json={"pbix_path": pbix_path},
        )
    assert resp.status_code == 200
