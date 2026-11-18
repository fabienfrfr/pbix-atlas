import pytest

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
    MParseError,
    RecordExpr,
    TryExpr,
    UnaryOp,
    ast_from_dict,
    ast_to_dict,
    parse_m_expression,
)


def test_literal_values():
    assert parse_m_expression("42") == Lit(42)
    assert parse_m_expression("3.14") == Lit(3.14)
    assert parse_m_expression('"hello"') == Lit("hello")
    assert parse_m_expression("true") == Lit(True)
    assert parse_m_expression("false") == Lit(False)
    assert parse_m_expression("null") == Lit(None)


def test_identifiers():
    assert parse_m_expression("x") == Ident("x")
    assert parse_m_expression("Table.AddColumn") == Ident("Table.AddColumn")
    assert parse_m_expression("Foo.Bar.Baz") == Ident("Foo.Bar.Baz")


def test_binary_operators():
    assert parse_m_expression("1 + 2") == BinOp(op="+", left=Lit(1), right=Lit(2))
    assert parse_m_expression("3 - 4") == BinOp(op="-", left=Lit(3), right=Lit(4))
    assert parse_m_expression("5 * 6") == BinOp(op="*", left=Lit(5), right=Lit(6))
    assert parse_m_expression("8 / 2") == BinOp(op="/", left=Lit(8), right=Lit(2))
    assert parse_m_expression("1 = 1") == BinOp(op="=", left=Lit(1), right=Lit(1))
    assert parse_m_expression("1 <> 2") == BinOp(op="<>", left=Lit(1), right=Lit(2))
    assert parse_m_expression("1 < 2") == BinOp(op="<", left=Lit(1), right=Lit(2))
    assert parse_m_expression("2 > 1") == BinOp(op=">", left=Lit(2), right=Lit(1))
    assert parse_m_expression("1 <= 2") == BinOp(op="<=", left=Lit(1), right=Lit(2))
    assert parse_m_expression("2 >= 1") == BinOp(op=">=", left=Lit(2), right=Lit(1))
    assert parse_m_expression("x and y") == BinOp(op="and", left=Ident("x"), right=Ident("y"))
    assert parse_m_expression("x or y") == BinOp(op="or", left=Ident("x"), right=Ident("y"))
    assert parse_m_expression('"a" & "b"') == BinOp(op="&", left=Lit("a"), right=Lit("b"))
    assert parse_m_expression("a ?? b") == BinOp(op="??", left=Ident("a"), right=Ident("b"))


def test_precedence():
    node = parse_m_expression("1 + 2 * 3")
    assert node == BinOp(op="+", left=Lit(1), right=BinOp(op="*", left=Lit(2), right=Lit(3)))
    node = parse_m_expression("1 * 2 + 3")
    assert node == BinOp(op="+", left=BinOp(op="*", left=Lit(1), right=Lit(2)), right=Lit(3))
    node = parse_m_expression("a and b or c")
    assert node == BinOp(op="or", left=BinOp(op="and", left=Ident("a"), right=Ident("b")), right=Ident("c"))


def test_unary_operators():
    assert parse_m_expression("not x") == UnaryOp(op="not", expr=Ident("x"))
    assert parse_m_expression("-1") == UnaryOp(op="-", expr=Lit(1))
    assert parse_m_expression("+x") == UnaryOp(op="+", expr=Ident("x"))
    assert parse_m_expression("not not x") == UnaryOp(op="not", expr=UnaryOp(op="not", expr=Ident("x")))


def test_if_expression():
    node = parse_m_expression("if true then 1 else 2")
    assert node == If(cond=Lit(True), then_=Lit(1), else_=Lit(2))


def test_lambda_each():
    node = parse_m_expression("each _ + 1")
    assert isinstance(node, Lambda)
    assert node.params == ["_"]
    assert node.body == BinOp(op="+", left=Ident("_"), right=Lit(1))


def test_lambda_params():
    node = parse_m_expression("(x, y) => x + y")
    assert isinstance(node, Lambda)
    assert node.params == ["x", "y"]
    assert node.body == BinOp(op="+", left=Ident("x"), right=Ident("y"))


def test_lambda_single_param():
    node = parse_m_expression("(x) => x")
    assert isinstance(node, Lambda)
    assert node.params == ["x"]
    assert node.body == Ident("x")


def test_let_block():
    node = parse_m_expression("let X = 1, Y = 2 in Y")
    assert isinstance(node, LetExpr)
    assert len(node.steps) == 2
    assert node.steps[0] == ("X", Lit(1))
    assert node.steps[1] == ("Y", Lit(2))
    assert node.body == Ident("Y")


def test_function_invocation():
    node = parse_m_expression("Func(1, 2)")
    assert node == Invoke(func=Ident("Func"), args=[Lit(1), Lit(2)])


def test_function_invocation_no_args():
    node = parse_m_expression("Func()")
    assert node == Invoke(func=Ident("Func"), args=[])


def test_function_invocation_single_arg():
    node = parse_m_expression("Func(x)")
    assert node == Invoke(func=Ident("Func"), args=[Ident("x")])


def test_field_access_bracket():
    node = parse_m_expression("[Field]")
    assert node == FieldAccess(target=Ident("_"), field="Field")


def test_field_access_postfix():
    node = parse_m_expression("rec[Field]")
    assert node == FieldAccess(target=Ident("rec"), field="Field")


def test_field_access_question_mark():
    node = parse_m_expression("[Field]?")
    assert node == FieldAccess(target=Ident("_"), field="Field")


def test_field_access_quoted():
    node = parse_m_expression('[#"Quoted Field"]')
    assert node == FieldAccess(target=Ident("_"), field="Quoted Field")


def test_item_access():
    node = parse_m_expression("lst{0}")
    assert node == ItemAccess(target=Ident("lst"), index=Lit(0))


def test_item_access_expr_index():
    node = parse_m_expression("lst{i}")
    assert node == ItemAccess(target=Ident("lst"), index=Ident("i"))


def test_list_literal():
    node = parse_m_expression("{1, 2, 3}")
    assert node == ListExpr(items=[Lit(1), Lit(2), Lit(3)])


def test_list_literal_empty():
    node = parse_m_expression("{}")
    assert node == ListExpr(items=[])


def test_record_literal():
    node = parse_m_expression("[a = 1, b = 2]")
    assert node == RecordExpr(fields=[("a", Lit(1)), ("b", Lit(2))])


def test_try_expression_with_otherwise():
    node = parse_m_expression("try x otherwise 0")
    assert node == TryExpr(expr=Ident("x"), otherwise=Lit(0))


def test_try_expression_without_otherwise():
    node = parse_m_expression("try x")
    assert node == TryExpr(expr=Ident("x"), otherwise=None)


def test_ast_roundtrip():
    node = parse_m_expression("let x = 1 in x + 2")
    d = ast_to_dict(node)
    node2 = ast_from_dict(d)
    d2 = ast_to_dict(node2)
    assert d == d2


def test_ast_roundtrip_complex():
    node = parse_m_expression("if x > 0 then x * y else [a = 1]{0}")
    d = ast_to_dict(node)
    node2 = ast_from_dict(d)
    d2 = ast_to_dict(node2)
    assert d == d2


def test_nested_expressions():
    node = parse_m_expression("let f = (x) => if x > 0 then x * 2 else 0 in f(5)")
    assert isinstance(node, LetExpr)
    assert len(node.steps) == 1
    name, lam = node.steps[0]
    assert name == "f"
    assert isinstance(lam, Lambda)
    assert isinstance(lam.body, If)
    assert isinstance(node.body, Invoke)
    assert node.body.args == [Lit(5)]


def test_nested_postfix():
    node = parse_m_expression("tbl{0}[col]")
    assert node == FieldAccess(
        target=ItemAccess(target=Ident("tbl"), index=Lit(0)),
        field="col",
    )


def test_parse_error_invalid_token():
    with pytest.raises(MParseError):
        parse_m_expression("1 @")


def test_parse_error_unexpected_token():
    with pytest.raises(MParseError):
        parse_m_expression("if then else")


def test_parse_error_trailing_tokens():
    with pytest.raises(MParseError):
        parse_m_expression("1 2")


def test_invoke_chained():
    node = parse_m_expression("a(b)(c)")
    assert node == Invoke(
        func=Invoke(func=Ident("a"), args=[Ident("b")]),
        args=[Ident("c")],
    )


def test_let_with_invocation():
    node = parse_m_expression("let a = Func(1) in a")
    assert isinstance(node, LetExpr)
    name, val = node.steps[0]
    assert name == "a"
    assert val == Invoke(func=Ident("Func"), args=[Lit(1)])
