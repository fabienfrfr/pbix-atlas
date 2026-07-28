from pbix_atlas.api.schemas import (
    BuildGraphRequest,
    GraphSummaryResponse,
    SearchRequest,
    NodeListResponse,
    NodeQuery,
    TreeQuery,
    TreeNode,
    ExportRequest,
    ExportResponse,
    CodegenRequest,
    CodegenResponse,
)


def test_build_graph_request():
    r = BuildGraphRequest(pbix_path="/path/to/file.pbix")
    assert r.pbix_path == "/path/to/file.pbix"


def test_graph_summary_response():
    r = GraphSummaryResponse(pbix_path="/f.pbix", node_counts={"query": 5}, edge_count=10)
    assert r.edge_count == 10
    assert r.node_counts["query"] == 5


def test_search_request():
    r = SearchRequest(pbix_path="/f.pbix", query="sales")
    assert r.query == "sales"


def test_node_list_response():
    r = NodeListResponse(nodes=["a", "b"])
    assert r.nodes == ["a", "b"]


def test_node_query_defaults():
    r = NodeQuery(pbix_path="/f.pbix", node_id="n1")
    assert r.include_relationships is False


def test_node_query_with_relationships():
    r = NodeQuery(pbix_path="/f.pbix", node_id="n1", include_relationships=True)
    assert r.include_relationships is True


def test_tree_query_defaults():
    r = TreeQuery(pbix_path="/f.pbix", node_id="n1")
    assert r.direction == "downstream"
    assert r.max_depth == 12


def test_tree_query_custom():
    r = TreeQuery(pbix_path="/f.pbix", node_id="n1", direction="upstream", max_depth=5)
    assert r.direction == "upstream"
    assert r.max_depth == 5


def test_tree_node():
    child = TreeNode(id="c1", type="column")
    parent = TreeNode(id="p1", type="query", children=[child])
    assert parent.id == "p1"
    assert parent.children[0].id == "c1"
    assert parent.model_dump()["children"][0]["id"] == "c1"


def test_tree_node_to_dict_recursive():
    root = TreeNode(
        id="root",
        type="source",
        children=[
            TreeNode(id="child", type="query", children=[TreeNode(id="grandchild", type="column")]),
        ],
    )
    d = root.model_dump()
    assert d["id"] == "root"
    assert d["children"][0]["children"][0]["id"] == "grandchild"


def test_export_request_defaults():
    r = ExportRequest(pbix_path="/f.pbix")
    assert r.output_dir == "."


def test_export_response():
    r = ExportResponse(
        graphml_path="/out/g.graphml",
        nodes_csv_path="/out/g_nodes.csv",
        edges_csv_path="/out/g_edges.csv",
    )
    assert "graphml" in r.graphml_path


def test_codegen_request_defaults():
    r = CodegenRequest(pbix_path="/f.pbix")
    assert r.output_path == ""


def test_codegen_response():
    r = CodegenResponse(
        output_path="/out/pipeline.py",
        stats={"queries": 5, "measures_translated": 3},
    )
    assert r.stats["measures_translated"] == 3
