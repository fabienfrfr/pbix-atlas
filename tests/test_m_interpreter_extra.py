import pandas as pd
import pytest

from pbix_atlas.m_interpreter import Env, MInterpreter, MTable, MRuntimeError
from pbix_atlas.m_parser import parse_m_expression


def run(expr: str, env_vars: dict | None = None):
    interp = MInterpreter()
    env = Env()
    for k, v in (env_vars or {}).items():
        env.set(k, v)
    ast = parse_m_expression(expr)
    return interp.eval(ast, env)


def test_null_literal():
    assert run("null") is None


def test_boolean_literals():
    assert run("true") is True
    assert run("false") is False


def test_arithmetic_operators():
    assert run("10 - 3") == 7
    assert run("10 * 3") == 30
    assert run("10 / 3") == 10 / 3


def test_coalesce():
    assert run("null ?? 5") == 5
    assert run("3 ?? 5") == 3


def test_and_or():
    assert run("true and false") is False
    assert run("true and true") is True
    assert run("false or true") is True
    assert run("false or false") is False


def test_comparison_operators():
    assert run("1 = 1") is True
    assert run("1 = 2") is False
    assert run("1 <> 2") is True
    assert run("1 < 2") is True
    assert run("1 > 2") is False
    assert run("1 <= 1") is True
    assert run("2 >= 1") is True


def test_unary_not():
    assert run("not true") is False
    assert run("not false") is True


def test_unary_negate():
    assert run("-5") == -5


def test_string_concat():
    assert run('"hello" & " " & "world"') == "hello world"


def test_list_literal():
    result = run("{1, 2, 3}")
    assert result == [1, 2, 3]


def test_list_empty():
    assert run("{}") == []


def test_record_literal():
    result = run('[a = 1, b = "hello"]')
    assert result == {"a": 1, "b": "hello"}


def test_field_access_on_record():
    result = run("[a = 1, b = 2][a]")
    assert result == 1


def test_item_access_on_list():
    result = run("{10, 20, 30}{1}")
    assert result == 20


def test_if_else():
    assert run("if false then 1 else 2") == 2
    assert run('if "a" = "a" then true else false') is True


def test_lambda_single_arg():
    interp = MInterpreter()
    env = Env()
    fn = interp.eval(parse_m_expression("(x) => x * 2"), env)
    assert fn.call([5]) == 10


def test_lambda_two_args():
    interp = MInterpreter()
    env = Env()
    fn = interp.eval(parse_m_expression("(a, b) => a + b"), env)
    assert fn.call([3, 4]) == 7


def test_each_lambda():
    interp = MInterpreter()
    env = Env()
    fn = interp.eval(parse_m_expression("each _ * 10"), env)
    assert fn.call([7]) == 70


def test_let_block():
    result = run("let A = 1 + 2, B = A * 3 in B")
    assert result == 9


def test_let_block_two_steps():
    result = run("""
        let
            X = 10,
            Y = X + 5,
            Z = Y * 2
        in Z
    """)
    assert result == 30


def test_list_transform():
    result = run("List.Transform({1, 2, 3}, each _ * 10)")
    assert result == [10, 20, 30]


def test_list_select():
    result = run("List.Select({1, 2, 3, 4}, each _ > 2)")
    assert result == [3, 4]


def test_list_sum():
    result = run("List.Sum({1, 2, 3})")
    assert result == 6


def test_list_count():
    result = run("List.Count({1, 2, 3})")
    assert result == 3


def test_list_is_empty():
    assert run("List.IsEmpty({})") is True
    assert run("List.IsEmpty({1})") is False


def test_list_first():
    assert run("List.First({1, 2})") == 1
    assert run("List.First({})") is None


def test_text_upper():
    assert run('Text.Upper("hello")') == "HELLO"


def test_text_lower():
    assert run('Text.Lower("HELLO")') == "hello"


def test_text_length():
    assert run('Text.Length("hello")') == 5


def test_text_contains():
    assert run('Text.Contains("hello world", "world")') is True


def test_text_combine():
    assert run('Text.Combine({"a", "b", "c"}, ", ")') == "a, b, c"


def test_number_from():
    assert run('Number.From("42")') == 42.0


def test_number_round():
    assert run("Number.Round(3.14159, 2)") == 3.14


def test_date_year():
    result = run('#date(2024, 6, 15)')
    assert result.year == 2024


def test_table_from_records():
    result = run("Table.FromRecords({[a = 1, b = 2], [a = 3, b = 4]})")
    assert isinstance(result, MTable)
    assert list(result.df["a"]) == [1, 3]


def test_table_from_rows():
    result = run('Table.FromRows({{1, "x"}, {2, "y"}}, {"A", "B"})')
    assert isinstance(result, MTable)
    assert list(result.df["A"]) == [1, 2]


def test_table_column_names():
    table = MTable(pd.DataFrame({"A": [1], "B": [2]}))
    interp = MInterpreter()
    env = Env()
    env.set("T", table)
    result = interp.eval(parse_m_expression("Table.ColumnNames(T)"), env)
    assert result == ["A", "B"]


def test_table_to_rows():
    table = MTable(pd.DataFrame({"A": [1, 2], "B": [3, 4]}))
    interp = MInterpreter()
    env = Env()
    env.set("T", table)
    result = interp.eval(parse_m_expression("Table.ToRows(T)"), env)
    assert result == [[1, 3], [2, 4]]


def test_table_distinct():
    table = MTable(pd.DataFrame({"A": [1, 1, 2], "B": [1, 1, 2]}))
    interp = MInterpreter()
    env = Env()
    env.set("T", table)
    result = interp.eval(parse_m_expression("Table.Distinct(T)"), env)
    assert len(result.df) == 2


def test_table_select_columns():
    table = MTable(pd.DataFrame({"A": [1], "B": [2], "C": [3]}))
    interp = MInterpreter()
    env = Env()
    env.set("T", table)
    result = interp.eval(parse_m_expression('Table.SelectColumns(T, {"A", "C"})'), env)
    assert list(result.df.columns) == ["A", "C"]


def test_table_remove_columns():
    table = MTable(pd.DataFrame({"A": [1], "B": [2], "C": [3]}))
    interp = MInterpreter()
    env = Env()
    env.set("T", table)
    result = interp.eval(parse_m_expression('Table.RemoveColumns(T, {"A", "C"})'), env)
    assert list(result.df.columns) == ["B"]


def test_try_expression():
    result = run('try Text.Upper("hello") otherwise "fallback"')
    assert result == "HELLO" or (isinstance(result, dict) and result.get("Value") == "HELLO")


def test_try_expression_catch():
    result = run('try error "fail" otherwise -1')
    assert result == -1


def test_each_in_table_select_rows():
    table = MTable(pd.DataFrame({"A": [1, 2, 3]}))
    interp = MInterpreter()
    env = Env()
    env.set("Source", table)
    result = interp.eval(
        parse_m_expression("Table.SelectRows(Source, each [A] > 1)"),
        env,
    )
    assert list(result.df["A"]) == [2, 3]


def test_error_raises_m_runtime_error():
    with pytest.raises(MRuntimeError):
        run('error "something went wrong"')





def test_record_field():
    result = run('Record.Field([a = 1, b = 2], "a")')
    assert result == 1


def test_value_is():
    assert run('Value.Is(42, Int64.Type)') is True


def test_table_transform_column_types():
    table = MTable(pd.DataFrame({"A": ["1", "2"]}))
    interp = MInterpreter()
    env = Env()
    env.set("Source", table)
    result = interp.eval(
        parse_m_expression('Table.TransformColumnTypes(Source, {{"A", Int64.Type}})'),
        env,
    )
    assert result.df["A"].dtype.name == "Int64"


def test_table_promote_headers():
    df = pd.DataFrame({0: ["H1", "a"], 1: ["H2", "b"]})
    table = MTable(df)
    interp = MInterpreter()
    env = Env()
    env.set("Source", table)
    result = interp.eval(
        parse_m_expression("Table.PromoteHeaders(Source)"),
        env,
    )
    assert list(result.df.columns) == ["H1", "H2"]


def test_table_pivot():
    table = MTable(pd.DataFrame({"Cat": ["x", "x"], "K": ["A", "B"], "V": [1, 2]}))
    interp = MInterpreter()
    env = Env()
    env.set("Source", table)
    result = interp.eval(
        parse_m_expression('Table.Pivot(Source, {"K"}, "K", "V")'),
        env,
    )
    assert "A" in result.df.columns or "B" in result.df.columns


def test_table_reorder_columns():
    table = MTable(pd.DataFrame({"B": [1], "A": [2], "C": [3]}))
    interp = MInterpreter()
    env = Env()
    env.set("Source", table)
    result = interp.eval(
        parse_m_expression('Table.ReorderColumns(Source, {"A", "B"})'),
        env,
    )
    assert list(result.df.columns[:2]) == ["A", "B"]
