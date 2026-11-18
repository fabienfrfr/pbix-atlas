import pandas as pd

from pbix_atlas.m_interpreter import Env, MInterpreter, MTable
from pbix_atlas.m_parser import parse_m_expression


def run(expr: str, env_vars: dict | None = None):
    interp = MInterpreter()
    env = Env()
    for k, v in (env_vars or {}).items():
        env.set(k, v)
    ast = parse_m_expression(expr)
    return interp.eval(ast, env)


def test_arithmetic_and_comparisons():
    assert run("1 + 2 * 3") == 7
    assert run('"a" & "b"') == "ab"
    assert run("5 <= 5") is True
    assert run("5 < 3") is False
    assert run("null ?? 2") == 2
    assert run("3 ?? 2") == 3


def test_if_and_lambda():
    assert run("if 1 = 1 then 10 else 20") == 10
    interp = MInterpreter()
    env = Env()
    fn = interp.eval(parse_m_expression("(a, b) => a + b"), env)
    assert fn.call([2, 3]) == 5


def test_let_block_step_references():
    src = """
    let
        Source = 10,
        Doubled = Source * 2,
        Result = Doubled + Source
    in
        Result
    """
    assert run(src) == 30


def test_table_selectrows_and_addcolumn():
    table = MTable(pd.DataFrame({"A": [1, 2, 3], "B": ["x", "y", "z"]}))
    interp = MInterpreter()
    env = Env()
    env.set("Source", table)

    filtered = interp.eval(parse_m_expression("Table.SelectRows(Source, each [A] > 1)"), env)
    assert list(filtered.df["A"]) == [2, 3]

    added = interp.eval(parse_m_expression('Table.AddColumn(Source, "C", each [A] * 10)'), env)
    assert list(added.df["C"]) == [10, 20, 30]


def test_table_rename_select_sort_distinct():
    table = MTable(pd.DataFrame({"A": [3, 1, 2], "B": [1, 1, 2]}))
    interp = MInterpreter()
    env = Env()
    env.set("Source", table)

    renamed = interp.eval(
        parse_m_expression('Table.RenameColumns(Source, {{"A", "Z"}})'),
        env,
    )
    assert list(renamed.df.columns) == ["Z", "B"]

    sorted_t = interp.eval(parse_m_expression('Table.Sort(Source, {{"A", Order.Ascending}})'), env)
    assert list(sorted_t.df["A"]) == [1, 2, 3]


def test_nested_join_and_expand():
    left = MTable(pd.DataFrame({"Key": [1, 2, 3]}))
    right = MTable(pd.DataFrame({"Key": [1, 2], "Value": ["one", "two"]}))
    interp = MInterpreter()
    env = Env()
    env.set("L", left)
    env.set("R", right)

    joined = interp.eval(
        parse_m_expression('Table.NestedJoin(L, {"Key"}, R, {"Key"}, "Joined", JoinKind.LeftOuter)'),
        env,
    )
    env.set("Joined", joined)
    expanded = interp.eval(
        parse_m_expression('Table.ExpandTableColumn(Joined, "Joined", {"Value"}, {"Value"})'),
        env,
    )
    result = dict(zip(expanded.df["Key"], expanded.df["Value"], strict=False))
    assert result[1] == "one"
    assert result[2] == "two"
    assert pd.isna(result[3])


def test_group_by_with_aggregation():
    table = MTable(pd.DataFrame({"Cat": ["a", "a", "b"], "Val": [1, 2, 3]}))
    interp = MInterpreter()
    env = Env()
    env.set("Source", table)
    grouped = interp.eval(
        parse_m_expression(
            'Table.Group(Source, {"Cat"}, {{"Total", each List.Sum([Val])}})',
        ),
        env,
    )
    assert set(grouped.df.columns) >= {"Cat", "Total"}
    totals = dict(zip(grouped.df["Cat"], grouped.df["Total"], strict=False))
    assert totals["a"] == 3
    assert totals["b"] == 3


def test_replace_value_with_custom_function():
    table = MTable(pd.DataFrame({"A": [1, None, 3]}))
    interp = MInterpreter()
    env = Env()
    env.set("Source", table)
    replaced = interp.eval(
        parse_m_expression(
            "Table.ReplaceValue(Source, each [A] = null, null, "
            '(current, isMatch, newVal) => if isMatch then -1 else current, {"A"})',
        ),
        env,
    )
    values = list(replaced.df["A"])
    assert values == [1, -1, 3]


def test_text_functions():
    assert run('Text.Upper("abc")') == "ABC"
    assert run('Text.Contains("hello world", "wor")') is True
    assert run('Text.Combine({"a", "b", "c"}, "-")') == "a-b-c"
