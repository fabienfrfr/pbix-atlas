from pbix_atlas.m_parser import (
    BinOp,
    FieldAccess,
    Ident,
    If,
    Invoke,
    ItemAccess,
    Lambda,
    LetExpr,
    ListExpr,
    Lit,
    TryExpr,
    TypeLit,
    UnaryOp,
    RecordExpr,
)
from pbix_atlas.m_transpile import MTranspiler


def _t(node, model_ref="model"):
    return MTranspiler().expr(node, scope=set(), model_ref=model_ref)


def test_lit():
    assert _t(Lit(42)) == "42"
    assert _t(Lit(3.14)) == "3.14"
    assert _t(Lit("hello")) == "'hello'"
    assert _t(Lit(True)) == "True"
    assert _t(Lit(None)) == "None"


def test_ident():
    assert _t(Ident("x")) == "model['x']"
    assert _t(Ident("_safe_var")) == "model['_safe_var']"


def test_ident_underscore():
    assert _t(Ident("_")) == "row"


def test_ident_in_scope():
    t = MTranspiler()
    assert t.expr(Ident("x"), scope={"x"}) == "x"


def test_ident_globals():
    assert _t(Ident("Order.Ascending")) == "'asc'"
    assert _t(Ident("Int64.Type")) == "'Int64'"
    assert _t(Ident("Replacer.ReplaceValue")) == "m_ops.default_replacer"


def test_field_access():
    result = _t(FieldAccess(Ident("rec"), "Field"))
    assert result == "m_ops.field(model['rec'], 'Field')"


def test_field_access_implicit_underscore():
    result = _t(FieldAccess(Ident("_"), "Field"))
    assert result == "m_ops.field(row, 'Field')"


def test_item_access():
    result = _t(ItemAccess(Ident("lst"), Lit(0)))
    assert result == "m_ops.item_access(model['lst'], 0)"


def test_invoke_simple():
    from pbix_atlas.m_transpile import SIMPLE_CALLS
    func_name = list(SIMPLE_CALLS.keys())[0]
    result = _t(Invoke(Ident(func_name), [Ident("x")]))
    assert "m_ops." in result


def test_invoke_scope_func():
    result = _t(Invoke(Ident("my_fn"), [Lit(1)]), model_ref="model")
    assert "model['my_fn'](1)" in result


def test_invoke_list_count():
    result = _t(Invoke(Ident("List.Count"), [ListExpr([Lit(1), Lit(2)])]))
    assert "len(" in result


def test_invoke_list_is_empty():
    result = _t(Invoke(Ident("List.IsEmpty"), [ListExpr([])]))
    assert "== 0" in result


def test_invoke_hash_table():
    result = _t(Invoke(Ident("#table"), [ListExpr([Lit("A")]), ListExpr([Lit(1)])]))
    assert "m_ops.hash_table(" in result


def test_invoke_hash_date():
    result = _t(Invoke(Ident("#date"), [Lit(2024), Lit(1), Lit(15)]))
    assert "m_ops.hash_date(2024, 1, 15)" == result


def test_invoke_hash_datetime():
    result = _t(Invoke(Ident("#datetime"), [Lit(2024), Lit(1), Lit(15), Lit(12), Lit(0), Lit(0)]))
    assert "m_ops.hash_datetime(" in result


def test_invoke_hash_duration():
    result = _t(Invoke(Ident("#duration"), [Lit(1), Lit(2), Lit(3), Lit(4)]))
    assert "m_ops.hash_duration(" in result


def test_invoke_m_error():
    result = _t(Invoke(Ident("__m_error__"), [Lit("bad")]))
    assert "m_ops.raise_m_error('bad')" == result


def test_invoke_unknown_ident():
    result = _t(Invoke(Ident("FormatDate"), [Lit("x")]))
    assert "model['FormatDate']('x')" in result


def test_lambda():
    result = _t(Lambda(params=["x", "y"], body=BinOp("+", Ident("x"), Ident("y"))))
    assert "lambda x, y:" in result


def test_lambda_underscore_param():
    result = _t(Lambda(params=["_"], body=Ident("_")))
    assert "lambda row:" in result


def test_if():
    result = _t(If(cond=Lit(True), then_=Lit(1), else_=Lit(2)))
    assert "(1 if True else 2)" == result


def test_binop_arithmetic():
    assert _t(BinOp("+", Lit(1), Lit(2))) == "(1 + 2)"
    assert _t(BinOp("-", Lit(3), Lit(1))) == "(3 - 1)"


def test_binop_string_concat():
    result = _t(BinOp("&", Lit("a"), Lit("b")))
    assert "m_ops.text_from(" in result


def test_binop_coalesce():
    result = _t(BinOp("??", Ident("a"), Lit(0)))
    assert "is not None" in result


def test_binop_comparison():
    assert _t(BinOp("=", Lit(1), Lit(1))) == "(1 == 1)"
    assert _t(BinOp("<>", Lit(1), Lit(2))) == "(1 != 2)"


def test_unary_op():
    assert _t(UnaryOp("not", Lit(True))) == "(not True)"
    assert _t(UnaryOp("-", Lit(5))) == "(-5)"
    assert _t(UnaryOp("+", Lit(3))) == "(+3)"


def test_list_expr():
    result = _t(ListExpr([Lit(1), Lit(2), Lit(3)]))
    assert result == "[1, 2, 3]"


def test_record_expr():
    result = _t(RecordExpr(fields=[("a", Lit(1)), ("b", Lit(2))]))
    assert "'a': 1" in result
    assert "'b': 2" in result
    assert "{" in result


def test_let_expr():
    from pbix_atlas.m_transpile import MTranspiler
    ast = LetExpr(steps=[("X", Lit(1))], body=Ident("X"))
    lines, final = MTranspiler().transpile_query(ast)
    assert len(lines) == 1
    assert "X =" in lines[0]
    assert final == "X"


def test_let_expr_inline():
    ast = LetExpr(steps=[("X", Lit(1))], body=Ident("X"))
    result = _t(ast)
    assert "next(" in result
    assert "for " in result


def test_try_expr():
    result = _t(TryExpr(expr=Ident("x"), otherwise=Lit(0)))
    assert "m_ops.try_or(" in result


def test_try_expr_no_otherwise():
    result = _t(TryExpr(expr=Ident("x"), otherwise=None))
    assert "m_ops.try_or(" in result
    assert "lambda: None" in result


def test_type_lit():
    result = _t(TypeLit(raw="table"))
    assert result == "'table'"


def test_type_lit_known():
    result = _t(TypeLit(raw="Int64.Type"))
    assert result == "'Int64'"


def test_transpile_query_returns_lines_and_final():
    ast = LetExpr(
        steps=[("Source", Lit(1))],
        body=BinOp("+", Ident("Source"), Lit(2)),
    )
    lines, final = MTranspiler().transpile_query(ast)
    assert len(lines) == 1
    assert "Source =" in lines[0]
    assert "(Source + 2)" == final


def test_transpile_query_non_let():
    ast = Lit(42)
    lines, final = MTranspiler().transpile_query(ast)
    assert lines == []
    assert final == "42"


def test_transpile_module_function():
    from pbix_atlas.m_transpile import transpile_query
    ast = LetExpr(steps=[("X", Lit(1))], body=Ident("X"))
    lines, final = transpile_query(ast)
    assert len(lines) == 1


def test_invoke_func_is_expr():
    result = _t(Invoke(FieldAccess(Ident("x"), "method"), [Lit(1)]))
    assert "model" in result


def test_field_access_scope():
    t = MTranspiler()
    node = FieldAccess(target=Ident("myvar"), field="col")
    assert "m_ops.field(myvar, 'col')" == t.expr(node, scope={"myvar"})


def test_invoke_scope_var():
    t = MTranspiler()
    node = Invoke(func=Ident("myfn"), args=[Lit(1)])
    result = t.expr(node, scope={"myfn"})
    assert "myfn(1)" == result


def test_binop_mul():
    assert _t(BinOp("*", Lit(2), Lit(3))) == "(2 * 3)"


def test_binop_div():
    assert _t(BinOp("/", Lit(6), Lit(2))) == "(6 / 2)"


def test_binop_and():
    assert _t(BinOp("and", Lit(True), Lit(False))) == "(True and False)"


def test_binop_or():
    assert _t(BinOp("or", Lit(True), Lit(False))) == "(True or False)"


def test_binop_lt():
    assert _t(BinOp("<", Lit(1), Lit(2))) == "(1 < 2)"


def test_binop_le():
    assert _t(BinOp("<=", Lit(1), Lit(2))) == "(1 <= 2)"


def test_binop_gt():
    assert _t(BinOp(">", Lit(2), Lit(1))) == "(2 > 1)"


def test_binop_ge():
    assert _t(BinOp(">=", Lit(2), Lit(1))) == "(2 >= 1)"


def test_invoke_simple_call():
    from pbix_atlas.m_transpile import SIMPLE_CALLS
    for m_name, py_name in list(SIMPLE_CALLS.items())[:5]:
        result = _t(Invoke(Ident(m_name), [Ident("x")]))
        assert f"m_ops.{py_name}(" in result


def test_invoke_no_ident_func():
    result = _t(Invoke(Lit(42), [Lit(1)]))
    assert "42(1)" == result


def test_string_with_quotes():
    result = _t(Lit("he'llo"))
    assert "he" in result and "llo" in result
    assert result[0] in ("'", '"')
    assert result[-1] == result[0]


def test_globals_remaining():
    assert _t(Ident("Binary.Type")) == "None"
    assert _t(Ident("Compression.Deflate")) == "'deflate'"


def test_expr_raises_on_unknown():
    import pytest

    with pytest.raises(ValueError, match="Unsupported"):
        _t("not a node")
