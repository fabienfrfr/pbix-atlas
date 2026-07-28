from unittest.mock import MagicMock, PropertyMock, patch

import networkx as nx
import pandas as pd
import pytest

from pbix_atlas.graph_builder import LineageGraphBuilder
from pbix_atlas.models import DaxReference, EdgeType, NodeType


def _mock_model():
    model = MagicMock()
    model.queries.return_value = {
        "Q1": 'let Source = Csv.Document("http://example.com/data.csv") in Source',
    }
    model.schema_columns.return_value = pd.DataFrame(
        {"TableName": ["Q1"], "ColumnName": ["Col1"]}
    )
    model.calculated_columns.return_value = pd.DataFrame(
        {"TableName": [], "ColumnName": [], "Expression": []}
    )
    model.measures.return_value = pd.DataFrame(
        {"TableName": [], "Name": [], "Expression": []}
    )
    model.relationships.return_value = pd.DataFrame(
        {"FromTableName": [], "FromColumnName": [], "ToTableName": [], "ToColumnName": []}
    )
    return model


@pytest.fixture
def builder():
    return LineageGraphBuilder()


def _setup_build(requests):
    with patch("pbix_atlas.graph_builder.PBIXModel") as MockModel:
        instance = MockModel.return_value
        instance.queries.return_value = requests.get("queries")
        instance.schema_columns.return_value = requests.get("schema", pd.DataFrame({"TableName": [], "ColumnName": []}))
        instance.calculated_columns.return_value = requests.get("calc", pd.DataFrame({"TableName": [], "ColumnName": [], "Expression": []}))
        instance.measures.return_value = requests.get("measures", pd.DataFrame({"TableName": [], "Name": [], "Expression": []}))
        instance.relationships.return_value = requests.get("rels", pd.DataFrame({"FromTableName": [], "FromColumnName": [], "ToTableName": [], "ToColumnName": []}))
        yield builder
    return


def test_build_basic(builder):
    builder.layout_parser.load_raw_layout = MagicMock(side_effect=KeyError("No Report/Layout"))
    with patch("pbix_atlas.graph_builder.PBIXModel") as MockModel:
        instance = MockModel.return_value
        instance.queries.return_value = {"Q1": 'let Source = Csv.Document("http://example.com/data.csv") in Source'}
        instance.schema_columns.return_value = pd.DataFrame({"TableName": ["Q1"], "ColumnName": ["Col1"]})
        instance.calculated_columns.return_value = pd.DataFrame({"TableName": [], "ColumnName": [], "Expression": []})
        instance.measures.return_value = pd.DataFrame({"TableName": [], "Name": [], "Expression": []})
        instance.relationships.return_value = pd.DataFrame({"FromTableName": [], "FromColumnName": [], "ToTableName": [], "ToColumnName": []})

        g = builder.build("/fake/report.pbix")

    assert g.has_node("query::Q1")
    assert g.has_node("column::Q1::Col1")
    sources = [n for n, d in g.nodes(data=True) if d.get("type") == NodeType.SOURCE.value]
    assert len(sources) >= 1


def test_build_with_calculated_columns(builder):
    builder.layout_parser.load_raw_layout = MagicMock(side_effect=KeyError("No Report/Layout"))
    with patch("pbix_atlas.graph_builder.PBIXModel") as MockModel:
        instance = MockModel.return_value
        instance.queries.return_value = {"Q1": 'let S = Csv.Document("url") in S'}
        instance.schema_columns.return_value = pd.DataFrame({"TableName": ["Q1"], "ColumnName": ["Col1"]})
        instance.calculated_columns.return_value = pd.DataFrame(
            {"TableName": ["Q1"], "ColumnName": ["CalcCol"], "Expression": ["SUM(Q1[Col1])"]}
        )
        instance.measures.return_value = pd.DataFrame({"TableName": [], "Name": [], "Expression": []})
        instance.relationships.return_value = pd.DataFrame({"FromTableName": [], "FromColumnName": [], "ToTableName": [], "ToColumnName": []})

        g = builder.build("/fake/report.pbix")

    assert g.has_node("calculated_column::Q1::CalcCol")


def test_build_with_measures(builder):
    builder.layout_parser.load_raw_layout = MagicMock(side_effect=KeyError("No Report/Layout"))
    with patch("pbix_atlas.graph_builder.PBIXModel") as MockModel:
        instance = MockModel.return_value
        instance.queries.return_value = {"Q1": 'let S = Csv.Document("url") in S'}
        instance.schema_columns.return_value = pd.DataFrame({"TableName": ["Q1"], "ColumnName": ["Col1"]})
        instance.calculated_columns.return_value = pd.DataFrame({"TableName": [], "ColumnName": [], "Expression": []})
        instance.measures.return_value = pd.DataFrame(
            {"TableName": ["Q1"], "Name": ["Total"], "Expression": ["SUM(Q1[Col1])"]}
        )
        instance.relationships.return_value = pd.DataFrame({"FromTableName": [], "FromColumnName": [], "ToTableName": [], "ToColumnName": []})

        g = builder.build("/fake/report.pbix")

    assert g.has_node("measure::Q1::Total")


def test_build_with_relationships(builder):
    builder.layout_parser.load_raw_layout = MagicMock(side_effect=KeyError("No Report/Layout"))
    with patch("pbix_atlas.graph_builder.PBIXModel") as MockModel:
        instance = MockModel.return_value
        instance.queries.return_value = {}
        instance.schema_columns.return_value = pd.DataFrame(
            {"TableName": ["T1", "T2"], "ColumnName": ["Key", "Key"]}
        )
        instance.calculated_columns.return_value = pd.DataFrame({"TableName": [], "ColumnName": [], "Expression": []})
        instance.measures.return_value = pd.DataFrame({"TableName": [], "Name": [], "Expression": []})
        instance.relationships.return_value = pd.DataFrame(
            {"FromTableName": ["T1"], "FromColumnName": ["Key"], "ToTableName": ["T2"], "ToColumnName": ["Key"]}
        )

        g = builder.build("/fake/report.pbix")

    assert g.has_node("column::T1::Key")
    assert g.has_node("column::T2::Key")


def test_build_no_layout(builder):
    builder.layout_parser.load_raw_layout = MagicMock(side_effect=KeyError("No Report/Layout"))
    with patch("pbix_atlas.graph_builder.PBIXModel") as MockModel:
        instance = MockModel.return_value
        instance.queries.return_value = {}
        instance.schema_columns.return_value = pd.DataFrame({"TableName": [], "ColumnName": []})
        instance.calculated_columns.return_value = pd.DataFrame({"TableName": [], "ColumnName": [], "Expression": []})
        instance.measures.return_value = pd.DataFrame({"TableName": [], "Name": [], "Expression": []})
        instance.relationships.return_value = pd.DataFrame({"FromTableName": [], "FromColumnName": [], "ToTableName": [], "ToColumnName": []})

        g = builder.build("/fake/report.pbix")
    assert g is not None


def test_resolve_dax_reference(builder):
    column_lookup = {("T", "Col1"): "col_id"}
    measure_lookup = {("T", "M1"): "m_id"}

    ref = DaxReference(table="T", name="Col1")
    assert builder._resolve_dax_reference(ref, "T", column_lookup, measure_lookup) == "col_id"

    ref2 = DaxReference(table="T", name="M1")
    assert builder._resolve_dax_reference(ref2, "T", column_lookup, measure_lookup) == "m_id"

    ref3 = DaxReference(table=None, name="M1")
    assert builder._resolve_dax_reference(ref3, "T", column_lookup, measure_lookup) == "m_id"

    ref4 = DaxReference(table=None, name="Unknown")
    assert builder._resolve_dax_reference(ref4, "T", column_lookup, measure_lookup) is None


def test_add_unresolved_dax_ref(builder):
    g = nx.DiGraph()
    builder._add_unresolved_dax_ref(
        g, DaxReference(table="T", name="Missing"), default_table="T", dependent_id="mid"
    )
    assert g.has_node("unresolved::T::Missing")
    assert len(list(g.edges())) == 1


def test_query_dependencies(builder):
    g = nx.DiGraph()
    g.add_node("query::Q1", type=NodeType.QUERY.value, label="Q1")
    g.add_node("query::Q2", type=NodeType.QUERY.value, label="Q2")

    with patch.object(builder.m_resolver, "resolve", return_value={"Q1": [], "Q2": ["Q1"]}):
        builder._add_query_dependencies(g, {"Q1": "...", "Q2": "..."})

    assert g.has_edge("query::Q1", "query::Q2")


def test_add_inferred_columns(builder):
    g = nx.DiGraph()
    g.add_node("query::Staging", type=NodeType.QUERY.value, label="Staging")
    g.add_node(
        "query::Staging::step1", type="step", label="step1",
        operation='{"_":"Invoke","func":{"_":"Ident","name":"Csv.Document"},"args":[{"_":"Lit","value":"url"}]}',
        order=0,
    )
    g.add_edge("query::Staging", "query::Staging::step1", type="contains")

    column_lookup = {}
    builder._add_inferred_columns(g, column_lookup)


def test_add_visual_fields(builder):
    g = nx.DiGraph()
    g.add_node("column::T::Col1", type=NodeType.COLUMN.value, label="Col1")

    layout = {
        "sections": [
            {
                "displayName": "Page1",
                "visualContainers": [
                    {
                        "config": '{"singleVisual":{"visualType":"columnChart","prototypeQuery":{"From":[{"Name":"a","Entity":"T"}],"Select":[{"Name":"C1","Column":{"Expression":{"SourceRef":{"Source":"a"}},"Property":"Col1"}}]}}}',
                    }
                ],
            }
        ]
    }
    builder._add_visual_fields(
        g, layout, "report.pbix",
        {("T", "Col1"): "column::T::Col1"},
        {},
    )
    assert any(
        d.get("type") == NodeType.VISUAL_FIELD.value
        for _, d in g.nodes(data=True)
    )


def test_add_visual_fields_unresolved(builder):
    g = nx.DiGraph()

    layout = {
        "sections": [
            {
                "displayName": "Page1",
                "visualContainers": [
                    {
                        "config": '{"singleVisual":{"visualType":"columnChart","prototypeQuery":{"From":[{"Name":"a","Entity":"T"}],"Select":[{"Name":"C1","Column":{"Expression":{"SourceRef":{"Source":"a"}},"Property":"Missing"}}]}}}',
                    }
                ],
            }
        ]
    }
    builder._add_visual_fields(g, layout, "report.pbix", {}, {})
    assert g.has_node("unresolved::T::Missing")
