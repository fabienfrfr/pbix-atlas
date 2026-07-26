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
    assert 'nunique()' in result.python_expr


def test_translates_divide_with_alternate():
    result = DaxTranslator().translate(
        "DIVIDE(SUM(Sales[Amount]), COUNTROWS(Sales), 0)", default_table="Sales"
    )
    assert result.supported
    assert "if" in result.python_expr


def test_unsupported_expression_is_flagged_not_guessed():
    result = DaxTranslator().translate(
        'IF([Status] = 2, "TGS", "Rechange")', default_table="Sales"
    )
    assert result.supported is False
    assert result.python_expr == ""
