import json

from pbix_atlas.layout_roles import (
    VisualSpec,
    PageFilters,
    _resolve_item,
    _parse_filter_blob,
    extract_visual_specs,
    VISUAL_TYPE_MAP,
)


def test_extract_visual_specs_empty():
    assert extract_visual_specs({}) == []
    assert extract_visual_specs({"sections": []}) == []


def test_extract_visual_specs_basic():
    layout = {
        "sections": [
            {
                "displayName": "Page1",
                "visualContainers": [
                    {
                        "config": json.dumps(
                            {
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
                                    "projections": {
                                        "Category": [{"queryRef": "SumAmount"}],
                                    },
                                }
                            }
                        ),
                    }
                ],
            }
        ]
    }
    specs = extract_visual_specs(layout)
    assert len(specs) == 1
    s = specs[0]
    assert s.page == "Page1"
    assert s.visual_type == "columnChart"
    assert s.generic_type == "bar"
    assert "Category" in s.roles
    assert s.roles["Category"] == [("Sales", "Amount", "Measure")]


def test_generic_type_none_for_unknown():
    layout = {
        "sections": [
            {
                "displayName": "Page1",
                "visualContainers": [
                    {
                        "config": json.dumps(
                            {
                                "singleVisual": {
                                    "visualType": "someCustomVisual",
                                    "prototypeQuery": {"From": [], "Select": []},
                                    "projections": {},
                                }
                            }
                        ),
                    }
                ],
            }
        ]
    }
    specs = extract_visual_specs(layout)
    assert specs[0].generic_type is None


def test_skips_invalid_config():
    layout = {
        "sections": [
            {
                "displayName": "Page1",
                "visualContainers": [{"config": "not valid"}],
            }
        ]
    }
    assert extract_visual_specs(layout) == []


def test_skips_no_single_visual():
    layout = {
        "sections": [
            {
                "displayName": "Page1",
                "visualContainers": [{"config": json.dumps({"notSingle": True})}],
            }
        ]
    }
    specs = extract_visual_specs(layout)
    assert specs == []


def test_extract_visual_specs_with_filters():
    layout = {
        "sections": [
            {
                "displayName": "Page1",
                "filters": [
                    json.dumps(
                        {
                            "expression": {
                                "Column": {
                                    "Expression": {"SourceRef": {"Entity": "T"}},
                                    "Property": "colA",
                                }
                            },
                            "type": "basic",
                            "howCreated": "manual",
                        }
                    ),
                ],
                "visualContainers": [
                    {
                        "config": json.dumps(
                            {
                                "singleVisual": {
                                    "visualType": "tableEx",
                                    "prototypeQuery": {
                                        "From": [{"Name": "a", "Entity": "T"}],
                                        "Select": [
                                            {
                                                "Name": "C1",
                                                "Column": {
                                                    "Expression": {"SourceRef": {"Source": "a"}},
                                                    "Property": "colA",
                                                },
                                            }
                                        ],
                                    },
                                    "projections": {},
                                }
                            }
                        ),
                        "filters": [
                            json.dumps(
                                {
                                    "expression": {
                                        "Column": {
                                            "Expression": {"SourceRef": {"Entity": "T"}},
                                            "Property": "colB",
                                        }
                                    },
                                    "type": "basic",
                                    "howCreated": "manual",
                                }
                            ),
                        ],
                    }
                ],
            }
        ]
    }
    specs = extract_visual_specs(layout)
    assert len(specs) == 1
    assert len(specs[0].filters) == 2


def test_parse_filter_blob():
    result = _parse_filter_blob(
        json.dumps(
            {
                "expression": {
                    "Column": {
                        "Expression": {"SourceRef": {"Entity": "T"}},
                        "Property": "colA",
                    }
                },
                "type": "basic",
            }
        )
    )
    assert result["table"] == "T"
    assert result["field"] == "colA"
    assert result["filter_type"] == "basic"

    # Already a dict
    result2 = _parse_filter_blob(
        {"expression": {"Column": {"Expression": {"SourceRef": {"Entity": "T2"}}, "Property": "X"}}, "type": "basic"}
    )
    assert result2 is not None
    assert result2["field"] == "X"

    # Invalid
    assert _parse_filter_blob("not json") is None
    assert _parse_filter_blob("42") is None
    result3 = _parse_filter_blob({})
    assert result3 is None or "table" in result3


def test_parse_filter_blob_measure():
    result = _parse_filter_blob(
        json.dumps(
            {
                "expression": {
                    "Measure": {
                        "Expression": {"SourceRef": {"Entity": "T"}},
                        "Property": "Total",
                    }
                },
                "type": "basic",
            }
        )
    )
    assert result["field"] == "Total"


def test_parse_filter_blob_hierarchy_level():
    result = _parse_filter_blob(
        json.dumps(
            {
                "expression": {
                    "HierarchyLevel": {
                        "Expression": {"SourceRef": {"Entity": "Cal"}},
                        "Property": "Date",
                    }
                },
                "type": "advanced",
            }
        )
    )
    assert result["field"] == "Date"


def test_visual_type_map_covers_all():
    expected = {"bar", "bar_h", "line", "area", "pie", "scatter", "table", "kpi", "filter", "gauge", "treemap"}
    assert set(VISUAL_TYPE_MAP.values()) >= expected


def test_resolve_item_unresolved():
    kind, table, field = _resolve_item({"Name": "X"}, {})
    assert kind == "Unresolved"
    assert table is None
    assert field == "X"


def test_resolve_item_aggregation():
    item = {
        "Aggregation": {
            "Expression": {
                "Column": {
                    "Expression": {"SourceRef": {"Source": "a"}},
                    "Property": "Val",
                }
            }
        }
    }
    kind, table, field = _resolve_item(item, {"a": "T"})
    assert kind == "Column"
    assert field == "Val"


def test_resolve_item_percentile():
    item = {
        "Percentile": {
            "Expression": {"SourceRef": {"Source": "a"}},
            "Property": "P",
        }
    }
    kind, table, field = _resolve_item(item, {"a": "T"})
    assert kind == "Percentile"


def test_visual_spec_dataclass():
    vs = VisualSpec(page="P1", visual_index=0, visual_type="columnChart", generic_type="bar")
    assert vs.page == "P1"
    assert vs.visual_index == 0
    assert vs.roles == {}
    assert vs.filters == []


def test_page_filters_dataclass():
    pf = PageFilters(page="P1")
    assert pf.page == "P1"
    assert pf.filters == []


def test_multiple_visuals_in_section():
    layout = {
        "sections": [
            {
                "displayName": "P1",
                "visualContainers": [
                    {
                        "config": json.dumps(
                            {
                                "singleVisual": {
                                    "visualType": "columnChart",
                                    "prototypeQuery": {
                                        "From": [{"Name": "a", "Entity": "T"}],
                                        "Select": [
                                            {
                                                "Name": "M1",
                                                "Measure": {
                                                    "Expression": {"SourceRef": {"Source": "a"}},
                                                    "Property": "M1",
                                                },
                                            }
                                        ],
                                    },
                                    "projections": {"Category": [{"queryRef": "M1"}]},
                                }
                            }
                        ),
                    },
                    {
                        "config": json.dumps(
                            {
                                "singleVisual": {
                                    "visualType": "card",
                                    "prototypeQuery": {
                                        "From": [{"Name": "a", "Entity": "T"}],
                                        "Select": [
                                            {
                                                "Name": "V1",
                                                "Column": {
                                                    "Expression": {"SourceRef": {"Source": "a"}},
                                                    "Property": "Val",
                                                },
                                            }
                                        ],
                                    },
                                    "projections": {"Values": [{"queryRef": "V1"}]},
                                }
                            }
                        ),
                    },
                ],
            }
        ]
    }
    specs = extract_visual_specs(layout)
    assert len(specs) == 2
    assert specs[0].generic_type == "bar"
    assert specs[1].generic_type == "kpi"
