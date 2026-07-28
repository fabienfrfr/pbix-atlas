import json
import zipfile
import io
import tempfile
from pathlib import Path

import pytest

from pbix_atlas.layout import ReportLayoutParser
from pbix_atlas.models import VisualFieldUsage


def _make_pbix(layout_dict: dict) -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix=".pbix", delete=False)
    path = Path(tmp.name)
    with zipfile.ZipFile(path, "w") as z:
        text = json.dumps(layout_dict)
        z.writestr("Report/Layout", text.encode("utf-16-le"))
    return path


def test_load_raw_layout():
    layout = {"sections": []}
    pbix = _make_pbix(layout)
    result = ReportLayoutParser().load_raw_layout(pbix)
    assert result == layout
    pbix.unlink()


def test_iter_visual_fields_empty():
    layout = {"sections": []}
    result = list(ReportLayoutParser().iter_visual_fields(layout))
    assert result == []


def test_iter_visual_fields_no_sections():
    result = list(ReportLayoutParser().iter_visual_fields({}))
    assert result == []


def test_iter_visual_fields_section_no_vc():
    layout = {"sections": [{"displayName": "Page1"}]}
    result = list(ReportLayoutParser().iter_visual_fields(layout))
    assert result == []


def test_iter_visual_fields_with_valid_visual():
    vc_config = json.dumps({
        "singleVisual": {
            "visualType": "columnChart",
            "prototypeQuery": {
                "From": [{"Name": "a", "Entity": "Sales"}],
                "Select": [
                    {
                        "Name": "SumAmount",
                        "Measure": {
                            "Expression": {"SourceRef": {"Source": "a"}},
                            "Property": "Amount",
                        },
                    }
                ],
            },
        }
    })
    layout = {
        "sections": [
            {
                "displayName": "Page1",
                "visualContainers": [{"config": vc_config}],
            }
        ]
    }
    fields = list(ReportLayoutParser().iter_visual_fields(layout))
    assert len(fields) == 1
    f = fields[0]
    assert f.page == "Page1"
    assert f.visual_index == 0
    assert f.visual_type == "columnChart"
    assert f.field_kind == "Measure"
    assert f.table == "Sales"
    assert f.field == "Amount"


def test_iter_visual_fields_column_field():
    vc_config = json.dumps({
        "singleVisual": {
            "visualType": "tableEx",
            "prototypeQuery": {
                "From": [{"Name": "a", "Entity": "Products"}],
                "Select": [
                    {
                        "Name": "ProdName",
                        "Column": {
                            "Expression": {"SourceRef": {"Source": "a"}},
                            "Property": "ProductName",
                        },
                    }
                ],
            },
        }
    })
    layout = {
        "sections": [
            {
                "displayName": "Page2",
                "visualContainers": [{"config": vc_config}],
            }
        ]
    }
    fields = list(ReportLayoutParser().iter_visual_fields(layout))
    assert len(fields) == 1
    assert fields[0].field_kind == "Column"
    assert fields[0].field == "ProductName"


def test_skips_visual_groups():
    layout = {
        "sections": [
            {
                "displayName": "Page1",
                "visualContainers": [{"config": json.dumps({})}],
            }
        ]
    }
    fields = list(ReportLayoutParser().iter_visual_fields(layout))
    assert len(fields) == 0


def test_skips_invalid_json_config():
    layout = {
        "sections": [
            {
                "displayName": "Page1",
                "visualContainers": [{"config": "not valid json"}],
            }
        ]
    }
    fields = list(ReportLayoutParser().iter_visual_fields(layout))
    assert len(fields) == 0


def test_resolve_select_item_aggregation():
    item = {
        "Aggregation": {
            "Expression": {
                "Column": {
                    "Expression": {"SourceRef": {"Source": "a"}},
                    "Property": "Amount",
                }
            }
        }
    }
    kind, table, field = ReportLayoutParser()._resolve_select_item(
        item, {"a": "Sales"}
    )
    assert kind == "Column"
    assert table == "Sales"
    assert field == "Amount"


def test_resolve_select_item_hierarchy_level():
    item = {
        "HierarchyLevel": {
            "Expression": {"SourceRef": {"Source": "a"}},
            "Property": "DateField",
        }
    }
    kind, table, field = ReportLayoutParser()._resolve_select_item(
        item, {"a": "Calendar"}
    )
    assert kind == "HierarchyLevel"
    assert table == "Calendar"
    assert field == "DateField"


def test_resolve_select_item_unresolved():
    item = {"Name": "SomeField"}
    kind, table, field = ReportLayoutParser()._resolve_select_item(item, {})
    assert kind == "Unresolved"
    assert table is None
    assert field == "SomeField"


def test_resolve_select_item_percentile():
    item = {
        "Percentile": {
            "Expression": {"SourceRef": {"Source": "a"}},
            "Property": "PctField",
        }
    }
    kind, table, field = ReportLayoutParser()._resolve_select_item(
        item, {"a": "T"}
    )
    assert kind == "Percentile"
    assert table == "T"
    assert field == "PctField"


def test_load_raw_layout_handles_bom():
    tmp = tempfile.NamedTemporaryFile(suffix=".pbix", delete=False)
    path = Path(tmp.name)
    with zipfile.ZipFile(path, "w") as z:
        text = "\ufeff" + json.dumps({"key": "value"})
        z.writestr("Report/Layout", text.encode("utf-16-le"))
    result = ReportLayoutParser().load_raw_layout(path)
    assert result == {"key": "value"}
    path.unlink()


def test_load_raw_layout_key_error():
    with tempfile.NamedTemporaryFile(suffix=".pbix", delete=False) as f:
        path = Path(f.name)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("Other/Section", b"data")
    with pytest.raises(KeyError):
        ReportLayoutParser().load_raw_layout(path)
    path.unlink()


def test_page_name_fallback():
    layout = {
        "sections": [{"name": "Section1", "visualContainers": []}]
    }
    fields = list(ReportLayoutParser().iter_visual_fields(layout))
    assert fields == []


def test_multiple_pages_and_visuals():
    layout = {
        "sections": [
            {
                "displayName": "P1",
                "visualContainers": [
                    {
                        "config": json.dumps({
                            "singleVisual": {
                                "visualType": "card",
                                "prototypeQuery": {
                                    "From": [{"Name": "a", "Entity": "T"}],
                                    "Select": [
                                        {
                                            "Name": "M1",
                                            "Measure": {"Expression": {"SourceRef": {"Source": "a"}}, "Property": "M1"},
                                        }
                                    ],
                                },
                            }
                        }),
                    }
                ],
            },
            {
                "displayName": "P2",
                "visualContainers": [
                    {
                        "config": json.dumps({
                            "singleVisual": {
                                "visualType": "card",
                                "prototypeQuery": {
                                    "From": [{"Name": "a", "Entity": "T"}],
                                    "Select": [
                                        {
                                            "Name": "M2",
                                            "Measure": {"Expression": {"SourceRef": {"Source": "a"}}, "Property": "M2"},
                                        }
                                    ],
                                },
                            }
                        }),
                    }
                ],
            },
        ]
    }
    fields = list(ReportLayoutParser().iter_visual_fields(layout))
    assert len(fields) == 2
    assert fields[0].page == "P1"
    assert fields[0].field == "M1"
    assert fields[1].page == "P2"
    assert fields[1].field == "M2"
