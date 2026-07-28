from pbix_atlas.schema_infer import infer_schema_from_steps


def _lit(v):
    return {"_": "Lit", "value": v}


def _ident(name):
    return {"_": "Ident", "name": name}


def _list(items):
    return {"_": "ListExpr", "items": items}


def _invoke(func, args):
    return {"_": "Invoke", "func": _ident(func), "args": args}


def test_transform_column_types_gives_base_schema():
    steps = [
        ("Source", _invoke("Csv.Document", [_lit("url")])),
        (
            "Type modifié",
            _invoke(
                "Table.TransformColumnTypes",
                [_ident("Source"), _list([_list([_lit("colA"), {"_": "TypeLit", "raw": "text"}])])],
            ),
        ),
    ]
    result = infer_schema_from_steps(steps)
    assert result.columns == ["colA"]
    assert result.dynamic_rename is False


def test_literal_rename_is_applied():
    steps = [
        ("Source", _invoke("Csv.Document", [_lit("url")])),
        (
            "Type modifié",
            _invoke(
                "Table.TransformColumnTypes",
                [_ident("Source"), _list([_list([_lit("raw_name"), {"_": "TypeLit", "raw": "text"}])])],
            ),
        ),
        (
            "Renamed",
            _invoke("Table.RenameColumns", [_ident("Type modifié"), _list([_list([_lit("raw_name"), _lit("Nice Name")])])]),
        ),
    ]
    result = infer_schema_from_steps(steps)
    assert result.columns == ["Nice Name"]
    assert result.dynamic_rename is False


def test_dynamic_rename_is_flagged_and_columns_kept_as_is():
    steps = [
        ("Source", _invoke("Csv.Document", [_lit("url")])),
        (
            "Type modifié",
            _invoke(
                "Table.TransformColumnTypes",
                [_ident("Source"), _list([_list([_lit("raw_name"), {"_": "TypeLit", "raw": "text"}])])],
            ),
        ),
        # RenamePairs is a computed value (not a literal ListExpr): can't resolve statically
        ("Renamed", _invoke("Table.RenameColumns", [_ident("Type modifié"), _ident("RenamePairs")])),
    ]
    result = infer_schema_from_steps(steps)
    assert result.columns == ["raw_name"]
    assert result.dynamic_rename is True


def test_auxiliary_bindings_are_ignored():
    """A side let-binding (e.g. a small lookup table built from an unrelated
    identifier) must not pollute the main chain's schema, even if it uses
    tracked functions like Table.SelectColumns."""
    steps = [
        ("Source", _invoke("Csv.Document", [_lit("url")])),
        (
            "Type modifié",
            _invoke(
                "Table.TransformColumnTypes",
                [_ident("Source"), _list([_list([_lit("colA"), {"_": "TypeLit", "raw": "text"}])])],
            ),
        ),
        # Auxiliary: operates on an unrelated table, not on "Type modifié"
        ("LookupTable", _ident("SomeOtherQuery")),
        ("LookupCols", _invoke("Table.SelectColumns", [_ident("LookupTable"), _list([_lit("unrelated_col")])])),
        ("Final", _invoke("Table.ReplaceErrorValues", [_ident("Type modifié"), _list([])])),
    ]
    result = infer_schema_from_steps(steps)
    assert result.columns == ["colA"]


def test_extract_view_name_finds_odata_entity_access():
    from pbix_atlas.schema_infer import extract_view_name

    steps = [
        _invoke("OData.Feed", [_lit("https://example.com/odata/")]),
        {
            "_": "FieldAccess",
            "field": "Data",
            "target": {
                "_": "ItemAccess",
                "target": _ident("Source"),
                "index": {
                    "_": "RecordExpr",
                    "fields": [["Name", _lit("Remote_Entity_Name")], ["Signature", _lit("table")]],
                },
            },
        },
    ]
    assert extract_view_name(steps) == "Remote_Entity_Name"


def test_extract_view_name_returns_none_when_absent():
    from pbix_atlas.schema_infer import extract_view_name

    steps = [_invoke("Csv.Document", [_lit("https://example.com/export.php?id=1")])]
    assert extract_view_name(steps) is None


def test_empty_steps_returns_empty_schema():
    result = infer_schema_from_steps([])
    assert result.columns == []
    assert result.dynamic_rename is False
