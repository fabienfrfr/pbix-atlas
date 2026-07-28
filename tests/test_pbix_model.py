"""Unit tests for the PBIXModel adapter (src/pbix_atlas/pbix_model.py).

`PBIXRay` itself does real binary parsing of a .pbix zip archive, so it is
mocked here: these tests only check that PBIXModel wires its methods to the
right `pbixray` attributes and shapes the result the way the rest of the
package expects (dict merging for queries, passthrough DataFrames for the
rest).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from pbix_atlas.pbix_model import PBIXModel


@pytest.fixture
def mock_ray():
    """A MagicMock standing in for a pbixray.PBIXRay instance, pre-loaded
    with small but representative DataFrames for every attribute PBIXModel
    reads from."""
    ray = MagicMock()
    ray.power_query = pd.DataFrame(
        [
            {"TableName": "Sales", "Expression": "Source = Csv.Document(...)"},
            {"TableName": "Products", "Expression": "Source = Excel.Workbook(...)"},
        ]
    )
    ray.m_parameters = pd.DataFrame(
        [
            {"ParameterName": "ServerName", "Expression": '"myserver.database.windows.net"'},
        ]
    )
    ray.schema = pd.DataFrame(
        [
            {"TableName": "Sales", "ColumnName": "Amount", "PandasDataType": "float64"},
            {"TableName": "Sales", "ColumnName": "Date", "PandasDataType": "datetime64[ns]"},
        ]
    )
    ray.dax_columns = pd.DataFrame([{"TableName": "Sales", "ColumnName": "Margin", "Expression": "[Amount] - [Cost]"}])
    ray.dax_measures = pd.DataFrame([{"TableName": "Sales", "Name": "Total Sales", "Expression": "SUM(Sales[Amount])"}])
    ray.relationships = pd.DataFrame(
        [{"FromTableName": "Sales", "FromColumnName": "ProductID", "ToTableName": "Products", "ToColumnName": "ID"}]
    )
    return ray


@pytest.fixture
def model(mock_ray):
    with patch("pbix_atlas.pbix_model.PBIXRay", return_value=mock_ray):
        yield PBIXModel("/fake/report.pbix")


def test_init_stores_path_and_builds_ray(mock_ray):
    with patch("pbix_atlas.pbix_model.PBIXRay", return_value=mock_ray) as MockRay:
        m = PBIXModel("/fake/report.pbix")
    assert str(m.path) == "/fake/report.pbix"
    MockRay.assert_called_once_with("/fake/report.pbix")


def test_init_accepts_path_object(mock_ray, tmp_path):
    pbix_file = tmp_path / "report.pbix"
    with patch("pbix_atlas.pbix_model.PBIXRay", return_value=mock_ray):
        m = PBIXModel(pbix_file)
    assert m.path == pbix_file


def test_queries_merges_power_query_and_m_parameters(model):
    queries = model.queries()
    assert queries["Sales"] == "Source = Csv.Document(...)"
    assert queries["Products"] == "Source = Excel.Workbook(...)"
    assert queries["ServerName"] == '"myserver.database.windows.net"'
    assert len(queries) == 3


def test_queries_returns_plain_dict(model):
    assert isinstance(model.queries(), dict)


def test_schema_columns_selects_expected_fields(model):
    cols = model.schema_columns()
    assert list(cols.columns) == ["TableName", "ColumnName"]
    assert len(cols) == 2
    assert set(cols["ColumnName"]) == {"Amount", "Date"}


def test_calculated_columns_passthrough(model, mock_ray):
    result = model.calculated_columns()
    assert result is mock_ray.dax_columns
    assert result.iloc[0]["ColumnName"] == "Margin"


def test_measures_passthrough(model, mock_ray):
    result = model.measures()
    assert result is mock_ray.dax_measures
    assert result.iloc[0]["Name"] == "Total Sales"


def test_relationships_passthrough(model, mock_ray):
    result = model.relationships()
    assert result is mock_ray.relationships
    assert result.iloc[0]["FromTableName"] == "Sales"


def test_queries_empty_tables(mock_ray):
    mock_ray.power_query = pd.DataFrame(columns=["TableName", "Expression"])
    mock_ray.m_parameters = pd.DataFrame(columns=["ParameterName", "Expression"])
    with patch("pbix_atlas.pbix_model.PBIXRay", return_value=mock_ray):
        m = PBIXModel("/fake/empty.pbix")
    assert m.queries() == {}


def test_queries_only_m_parameters(mock_ray):
    mock_ray.power_query = pd.DataFrame(columns=["TableName", "Expression"])
    with patch("pbix_atlas.pbix_model.PBIXRay", return_value=mock_ray):
        m = PBIXModel("/fake/params_only.pbix")
    queries = m.queries()
    assert queries == {"ServerName": '"myserver.database.windows.net"'}
