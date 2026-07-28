from pathlib import Path
from unittest.mock import MagicMock, patch

import networkx as nx
import pandas as pd
import pytest

from pbix_atlas.codegen import (
    PythonPipelineGenerator,
    _safe_name,
    _indent,
    _compute_stats,
    generate_pipeline,
    generate_python_pipeline,
    generate_python_pipeline_with_stats,
)


def test_safe_name():
    assert _safe_name("hello world") == "hello_world"
    assert _safe_name("123abc") == "v_123abc"
    assert _safe_name("") == "v_"
    assert _safe_name("  hi  ") == "hi"
    assert _safe_name("foo.bar-baz") == "foo_bar_baz"


def test_indent():
    assert _indent("a\nb") == "    a\n    b"
    assert _indent("a\n\nb") == "    a\n\n    b"
    assert _indent("") == ""


def test_compute_stats():
    code = '''
measures[("T", "M1")] = model["T"]["A"].sum()
measures[("T", "M2")] = MeasureNotSupported("T", "M2", "COMPLEX(...)")
vm.Graph(id="g1", figure=...)
vm.Card(id="c1", text=...)
vm.Table(id="t1", figure=...)
# 2 visual(s) not mapped
'''
    graph = nx.DiGraph()
    graph.add_node("q1", type="query", label="Q1")
    stats = _compute_stats(code, graph)
    assert stats["queries"] == 1
    assert stats["measures_translated"] == 1
    assert stats["measures_unsupported"] == 1
    assert stats["visuals_mapped"] == 3
    assert stats["visuals_skipped"] == 2


def test_compute_stats_no_match():
    stats = _compute_stats("no relevant code", nx.DiGraph())
    assert stats["measures_unsupported"] == 0
    assert stats["visuals_mapped"] == 0
    assert stats["visuals_skipped"] == 0


@patch("pbix_atlas.codegen.LineageGraphBuilder")
@patch("pbix_atlas.codegen.ReportLayoutParser")
def test_pipeline_generator_init(mock_layout, mock_builder):
    mock_builder.return_value.build.return_value = nx.DiGraph()
    mock_layout.return_value.load_raw_layout.side_effect = KeyError("no layout")
    gen = PythonPipelineGenerator("/fake/report.pbix")
    assert gen.pbix_path.name == "report.pbix"


@patch("pbix_atlas.codegen.LineageGraphBuilder")
@patch("pbix_atlas.codegen.ReportLayoutParser")
def test_export_graphml(mock_layout, mock_builder, tmp_path):
    mock_builder.return_value.build.return_value = nx.DiGraph()
    mock_layout.return_value.load_raw_layout.side_effect = KeyError("no layout")
    gen = PythonPipelineGenerator("/fake/report.pbix")
    out = gen.export_graphml(tmp_path / "test.graphml")
    assert out.exists()


@patch("pbix_atlas.codegen.LineageGraphBuilder")
def test_export_json(mock_builder, tmp_path):
    mock_builder.return_value.build.return_value = nx.DiGraph()
    gen = PythonPipelineGenerator("/fake/report.pbix")
    out = gen.export_json(tmp_path / "test.json")
    assert out.exists()


@patch("pbix_atlas.codegen.LineageGraphBuilder")
@patch("pbix_atlas.codegen.ReportLayoutParser")
def test_query_nodes_in_order(mock_layout, mock_builder):
    g = nx.DiGraph()
    g.add_node("query::Q1", type="query", label="Q1")
    g.add_node("query::Q2", type="query", label="Q2")
    g.add_edge("query::Q1", "query::Q2", type="feeds")
    mock_builder.return_value.build.return_value = g
    mock_layout.return_value.load_raw_layout.side_effect = KeyError("no layout")

    gen = PythonPipelineGenerator("/fake/report.pbix")
    order = gen._query_nodes_in_order()
    assert order == ["query::Q1", "query::Q2"]


@patch("pbix_atlas.codegen.LineageGraphBuilder")
@patch("pbix_atlas.codegen.ReportLayoutParser")
def test_query_nodes_in_order_cycle(mock_layout, mock_builder):
    g = nx.DiGraph()
    g.add_node("query::Q1", type="query", label="Q1")
    g.add_node("query::Q2", type="query", label="Q2")
    mock_builder.return_value.build.return_value = g
    mock_layout.return_value.load_raw_layout.side_effect = KeyError("no layout")

    gen = PythonPipelineGenerator("/fake/report.pbix")
    order = gen._query_nodes_in_order()
    assert len(order) == 2


@patch("pbix_atlas.codegen.LineageGraphBuilder")
def test_measures_code(mock_builder):
    g = nx.DiGraph()
    g.add_node("measure::T::Total", type="measure", label="Total", table="T", dax_expression="SUM(T[A])")
    mock_builder.return_value.build.return_value = g

    gen = PythonPipelineGenerator("/fake/report.pbix")
    code = gen._measures_code()
    assert "compute_measures" in code
    assert "def compute_measures" in code


@patch("pbix_atlas.codegen.LineageGraphBuilder")
@patch("pbix_atlas.codegen.ReportLayoutParser")
def test_dashboard_code_no_visuals(mock_layout, mock_builder):
    mock_builder.return_value.build.return_value = nx.DiGraph()
    mock_layout.return_value.load_raw_layout.side_effect = KeyError("no layout")

    gen = PythonPipelineGenerator("/fake/report.pbix")
    code = gen._dashboard_code()
    assert "dashboard = vm.Dashboard(pages=[])" in code


@patch("pbix_atlas.codegen.LineageGraphBuilder")
@patch("pbix_atlas.codegen.ReportLayoutParser")
def test_visual_component_bar(mock_layout, mock_builder):
    from pbix_atlas.layout_roles import VisualSpec

    mock_layout.return_value.load_raw_layout.side_effect = KeyError("no layout")
    gen = PythonPipelineGenerator("/fake/report.pbix")
    spec = VisualSpec(
        page="Page1",
        visual_index=0,
        visual_type="columnChart",
        generic_type="bar",
        roles={
            "Category": [("T", "Cat", "Column")],
            "Values": [("T", "Val", "Column")],
        },
    )
    result = gen._visual_component(spec, {"count": 0})
    assert result is not None
    assert "vm.Graph" in result


@patch("pbix_atlas.codegen.LineageGraphBuilder")
@patch("pbix_atlas.codegen.ReportLayoutParser")
def test_visual_component_multi_table(mock_layout, mock_builder):
    from pbix_atlas.layout_roles import VisualSpec

    mock_layout.return_value.load_raw_layout.side_effect = KeyError("no layout")
    gen = PythonPipelineGenerator("/fake/report.pbix")
    spec = VisualSpec(
        page="Page1",
        visual_index=0,
        visual_type="columnChart",
        generic_type="bar",
        roles={
            "Category": [("T1", "Cat", "Column")],
            "Values": [("T2", "Val", "Column")],
        },
    )
    result = gen._visual_component(spec, {"count": 0})
    assert result is None


@patch("pbix_atlas.codegen.LineageGraphBuilder")
@patch("pbix_atlas.codegen.ReportLayoutParser")
def test_visual_component_missing_category(mock_layout, mock_builder):
    from pbix_atlas.layout_roles import VisualSpec

    mock_layout.return_value.load_raw_layout.side_effect = KeyError("no layout")
    gen = PythonPipelineGenerator("/fake/report.pbix")
    spec = VisualSpec(
        page="Page1",
        visual_index=0,
        visual_type="columnChart",
        generic_type="bar",
        roles={},
    )
    result = gen._visual_component(spec, {"count": 0})
    assert result is None


@patch("pbix_atlas.codegen.LineageGraphBuilder")
@patch("pbix_atlas.codegen.ReportLayoutParser")
def test_visual_component_table(mock_layout, mock_builder):
    from pbix_atlas.layout_roles import VisualSpec

    mock_layout.return_value.load_raw_layout.side_effect = KeyError("no layout")
    gen = PythonPipelineGenerator("/fake/report.pbix")
    spec = VisualSpec(
        page="Page1",
        visual_index=0,
        visual_type="tableEx",
        generic_type="table",
        roles={"Values": [("T", "Val", "Column")]},
    )
    result = gen._visual_component(spec, {"count": 0})
    assert result is not None
    assert "vm.Table" in result


@patch("pbix_atlas.codegen.LineageGraphBuilder")
@patch("pbix_atlas.codegen.ReportLayoutParser")
def test_visual_component_kpi(mock_layout, mock_builder):
    from pbix_atlas.layout_roles import VisualSpec

    mock_layout.return_value.load_raw_layout.side_effect = KeyError("no layout")
    gen = PythonPipelineGenerator("/fake/report.pbix")
    spec = VisualSpec(
        page="Page1",
        visual_index=0,
        visual_type="card",
        generic_type="kpi",
        roles={"Values": [("T", "Total", "Measure")]},
    )
    result = gen._visual_component(spec, {"count": 0})
    assert result is not None
    assert "vm.Card" in result


@patch("pbix_atlas.codegen.LineageGraphBuilder")
@patch("pbix_atlas.codegen.ReportLayoutParser")
def test_visual_component_kpi_no_measure(mock_layout, mock_builder):
    from pbix_atlas.layout_roles import VisualSpec

    mock_layout.return_value.load_raw_layout.side_effect = KeyError("no layout")
    gen = PythonPipelineGenerator("/fake/report.pbix")
    spec = VisualSpec(
        page="Page1",
        visual_index=0,
        visual_type="card",
        generic_type="kpi",
        roles={"Values": [("T", "Val", "Column")]},
    )
    result = gen._visual_component(spec, {"count": 0})
    assert result is None


@patch("pbix_atlas.codegen.LineageGraphBuilder")
@patch("pbix_atlas.codegen.ReportLayoutParser")
def test_visual_component_unknown_type(mock_layout, mock_builder):
    from pbix_atlas.layout_roles import VisualSpec

    mock_layout.return_value.load_raw_layout.side_effect = KeyError("no layout")
    gen = PythonPipelineGenerator("/fake/report.pbix")
    spec = VisualSpec(
        page="Page1",
        visual_index=0,
        visual_type="unknown",
        generic_type="unknown",
    )
    result = gen._visual_component(spec, {"count": 0})
    assert result is None


@patch("pbix_atlas.codegen.LineageGraphBuilder")
@patch("pbix_atlas.codegen.ReportLayoutParser")
def test_visual_component_multi_table_skipped(mock_layout, mock_builder):
    from pbix_atlas.layout_roles import VisualSpec

    mock_layout.return_value.load_raw_layout.side_effect = KeyError("no layout")
    gen = PythonPipelineGenerator("/fake/report.pbix")
    spec = VisualSpec(
        page="Page1",
        visual_index=0,
        visual_type="columnChart",
        generic_type="bar",
        roles={
            "Category": [("T1", "Cat", "Column")],
            "Y": [("T2", "Val", "Column")],
        },
    )
    skipped = {"count": 0}
    result = gen._visual_component(spec, skipped)
    assert result is None
    assert skipped["count"] == 1


@patch("pbix_atlas.codegen.LineageGraphBuilder")
@patch("pbix_atlas.codegen.ReportLayoutParser")
def test_generate_pipeline(mock_layout, mock_builder, tmp_path):
    mock_builder.return_value.build.return_value = nx.DiGraph()
    mock_layout.return_value.load_raw_layout.side_effect = KeyError("no layout")

    pbix = tmp_path / "report.pbix"
    pbix.touch()
    graphml = tmp_path / "out.graphml"
    py = tmp_path / "out.py"
    g, p = generate_pipeline(str(pbix), str(graphml), str(py))
    assert Path(g).exists()
    assert Path(p).exists()


@patch("pbix_atlas.codegen.LineageGraphBuilder")
@patch("pbix_atlas.codegen.ReportLayoutParser")
def test_generate_python_pipeline(mock_layout, mock_builder, tmp_path):
    mock_builder.return_value.build.return_value = nx.DiGraph()

    pbix = tmp_path / "report.pbix"
    pbix.touch()
    py = tmp_path / "out.py"
    result = generate_python_pipeline(str(pbix), str(py))
    assert result == py


@patch("pbix_atlas.codegen.LineageGraphBuilder")
@patch("pbix_atlas.codegen.ReportLayoutParser")
def test_generate_python_pipeline_with_stats(mock_layout, mock_builder, tmp_path):
    mock_builder.return_value.build.return_value = nx.DiGraph()

    pbix = tmp_path / "report.pbix"
    pbix.touch()
    py = tmp_path / "out.py"
    path, stats = generate_python_pipeline_with_stats(str(pbix), str(py))
    assert "queries" in stats


@patch("pbix_atlas.codegen.LineageGraphBuilder")
@patch("pbix_atlas.codegen.ReportLayoutParser")
def test_generate_full_template(mock_layout, mock_builder):
    g = nx.DiGraph()
    g.add_node("query::Q1", type="query", label="Q1")
    mock_builder.return_value.build.return_value = g
    mock_layout.return_value.load_raw_layout.side_effect = KeyError("no layout")

    gen = PythonPipelineGenerator("/fake/report.pbix")
    code = gen.generate()
    assert "pbix-atlas" in code
    assert "m_ops" in code


@patch("pbix_atlas.codegen.LineageGraphBuilder")
@patch("pbix_atlas.codegen.ReportLayoutParser")
def test_query_functions_code_body_none(mock_layout, mock_builder):
    g = nx.DiGraph()
    g.add_node("query::Q1", type="query", label="Q1")
    mock_builder.return_value.build.return_value = g
    mock_layout.return_value.load_raw_layout.side_effect = KeyError("no layout")

    gen = PythonPipelineGenerator("/fake/report.pbix")
    order = gen._query_nodes_in_order()
    blocks, calls = gen._query_functions_code(order)
    assert "could not be parsed" in blocks


@patch("pbix_atlas.codegen.LineageGraphBuilder")
@patch("pbix_atlas.codegen.ReportLayoutParser")
def test_pie_chart(mock_layout, mock_builder):
    from pbix_atlas.layout_roles import VisualSpec

    mock_layout.return_value.load_raw_layout.side_effect = KeyError("no layout")
    gen = PythonPipelineGenerator("/fake/report.pbix")
    spec = VisualSpec(
        page="Page1",
        visual_index=0,
        visual_type="pieChart",
        generic_type="pie",
        roles={
            "Category": [("T", "Cat", "Column")],
            "Values": [("T", "Val", "Column")],
        },
    )
    result = gen._visual_component(spec, {"count": 0})
    assert result is not None
    assert "px.pie" in result


@patch("pbix_atlas.codegen.LineageGraphBuilder")
@patch("pbix_atlas.codegen.ReportLayoutParser")
def test_bar_h_chart(mock_layout, mock_builder):
    from pbix_atlas.layout_roles import VisualSpec

    mock_layout.return_value.load_raw_layout.side_effect = KeyError("no layout")
    gen = PythonPipelineGenerator("/fake/report.pbix")
    spec = VisualSpec(
        page="Page1",
        visual_index=0,
        visual_type="barChart",
        generic_type="bar_h",
        roles={
            "Category": [("T", "Cat", "Column")],
            "Values": [("T", "Val", "Column")],
        },
    )
    result = gen._visual_component(spec, {"count": 0})
    assert result is not None
    assert 'orientation="h"' in result
