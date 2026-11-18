from pbix_atlas.dax_translate import DaxTranslator


def test_translates_sum():
    result = DaxTranslator().translate("SUM(Sales[Amount])", default_table="Sales")
    assert result.supported
    assert result.python_expr == 'model["Sales"]["Amount"].sum()'


def test_translates_countrows():
    result = DaxTranslator().translate("COUNTROWS(Sales)", default_table="Sales")
    assert result.supported
    assert result.python_expr == 'len(model["Sales"])'


def test_translates_distinctcount():
    result = DaxTranslator().translate("DISTINCTCOUNT(Sales[CustomerId])", default_table="Sales")
    assert result.supported
    assert "nunique()" in result.python_expr


def test_translates_divide_with_alternate():
    result = DaxTranslator().translate("DIVIDE(SUM(Sales[Amount]), COUNTROWS(Sales), 0)", default_table="Sales")
    assert result.supported
    assert "if" in result.python_expr


def test_translates_average():
    result = DaxTranslator().translate("AVERAGE(Sales[Amount])", default_table="Sales")
    assert result.supported
    assert "mean()" in result.python_expr
    assert "Sales" in result.referenced_tables


def test_translates_min_max():
    for func, method in [("MIN", "min"), ("MAX", "max")]:
        result = DaxTranslator().translate(f"{func}(Sales[Amount])", default_table="Sales")
        assert result.supported
        assert f".{method}()" in result.python_expr


def test_translates_count_rows():
    result = DaxTranslator().translate("COUNT(Sales[CustomerId])", default_table="Sales")
    assert result.supported
    assert "count()" in result.python_expr


def test_translates_quoted_table():
    result = DaxTranslator().translate("SUM('My Table'[Amount])", default_table="Sales")
    assert result.supported
    assert "My Table" in result.python_expr


def test_translates_divide_no_alternate():
    result = DaxTranslator().translate(
        "DIVIDE(SUM(Sales[A]), COUNTROWS(Sales))",
        default_table="Sales",
    )
    assert result.supported
    assert "if" in result.python_expr


def test_translates_literal_integer():
    result = DaxTranslator().translate("42", default_table="Sales")
    assert result.supported
    assert result.python_expr == "42"


def test_translates_literal_negative():
    result = DaxTranslator().translate("-3.14", default_table="Sales")
    assert result.supported
    assert result.python_expr == "-3.14"


def test_translates_single_reference():
    result = DaxTranslator().translate("[Revenue]", default_table="Sales")
    assert result.supported
    assert "measures" in result.python_expr
    assert "Revenue" in result.python_expr


def test_unsupported_expression_is_flagged_not_guessed():
    result = DaxTranslator().translate('IF([Status] = 2, "TGS", "Rechange")', default_table="Sales")
    assert result.supported is False
    assert result.python_expr == ""
