import tempfile
from pathlib import Path

import networkx as nx

from pbix_atlas.models import EdgeType, NodeType
from pbix_atlas.reports import render_source_tree_markdown, write_source_tree_report


def _graph_with_view():
    g = nx.DiGraph()
    g.add_node("src1", type=NodeType.SOURCE.value, label="https://odata.example.com/feed/")
    g.add_node("root", type=NodeType.QUERY.value, label="Root")
    g.add_node("leaf", type=NodeType.QUERY.value, label="Some_BRZ", view="Remote_Entity_Name")
    g.add_node("colA", type=NodeType.COLUMN.value, label="colA")
    g.add_edge("src1", "root", type=EdgeType.FEEDS.value)
    g.add_edge("root", "leaf", type=EdgeType.FEEDS.value)
    g.add_edge("leaf", "colA", type=EdgeType.FEEDS.value)
    return g


def test_markdown_includes_source_table_and_view():
    md = render_source_tree_markdown(_graph_with_view())
    assert "https://odata.example.com/feed/" in md
    assert "Remote_Entity_Name" in md
    assert "Some_BRZ" in md
    assert "colA" in md


def test_markdown_includes_ascii_tree_and_table():
    md = render_source_tree_markdown(_graph_with_view())
    assert "```" in md  # ASCII tree fenced block
    assert "| Table | Vue distante | Colonnes | Fiabilité | Détail |" in md


def test_write_source_tree_report_writes_file():
    g = _graph_with_view()
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "report.md"
        result = write_source_tree_report(g, path)
        assert result == path
        content = path.read_text(encoding="utf-8")
        assert "Some_BRZ" in content
