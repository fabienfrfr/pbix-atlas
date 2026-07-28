"""Transpiles a parsed M AST into readable Python source calling `m_ops`."""

from __future__ import annotations

import re

from .m_parser import (
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
    MNode,
    RecordExpr,
    TryExpr,
    TypeLit,
    UnaryOp,
)

GLOBALS: dict[str, str] = {
    "Order.Ascending": "'asc'",
    "Order.Descending": "'desc'",
    "JoinKind.Inner": "'inner'",
    "JoinKind.LeftOuter": "'left'",
    "JoinKind.RightOuter": "'right'",
    "JoinKind.FullOuter": "'outer'",
    "Int64.Type": "'Int64'",
    "Byte.Type": "'Int64'",
    "Currency.Type": "'float'",
    "Number.Type": "'float'",
    "Double.Type": "'float'",
    "Percentage.Type": "'float'",
    "Text.Type": "'string'",
    "Date.Type": "'date'",
    "DateTime.Type": "'datetime'",
    "DateTimeZone.Type": "'datetime'",
    "Time.Type": "'time'",
    "Logical.Type": "'bool'",
    "Any.Type": "None",
    "Binary.Type": "None",
    "None.Type": "None",
    "Replacer.ReplaceValue": "m_ops.default_replacer",
    "Replacer.ReplaceText": "m_ops.default_text_replacer",
    "Compression.Deflate": "'deflate'",
    "TextEncoding.Utf8": "'utf-8'",
    "ExtraValues.Ignore": "'ignore'",
    "ExtraValues.Error": "'error'",
    "MissingField.UseNull": "'use_null'",
    "MissingField.Ignore": "'ignore'",
    "Occurrence.All": "'all'",
    "Occurrence.First": "'first'",
    "Occurrence.Last": "'last'",
}

# Direct passthrough: M function -> (m_ops function, arg transform names unchanged)
SIMPLE_CALLS: dict[str, str] = {
    "Table.SelectRows": "table_select_rows",
    "Table.AddColumn": "table_add_column",
    "Table.SelectColumns": "table_select_columns",
    "Table.RemoveColumns": "table_remove_columns",
    "Table.ReorderColumns": "table_reorder_columns",
    "Table.Distinct": "table_distinct",
    "Table.ColumnNames": "table_column_names",
    "Table.NestedJoin": "table_nested_join",
    "Table.Join": "table_nested_join",
    "Table.ExpandTableColumn": "table_expand_table_column",
    "Table.ExpandRecordColumn": "table_expand_record_column",
    "Table.CombineColumns": "table_combine_columns",
    "Table.FromRecords": "table_from_records",
    "Table.FromRows": "table_from_rows",
    "Table.FromList": "table_from_list",
    "Table.Combine": "table_combine",
    "Table.SplitColumn": "table_split_column",
    "Table.ToRows": "table_to_rows",
    "Table.ReplaceValue": "table_replace_value",
    "Table.RenameColumns": "table_rename_columns",
    "Table.Sort": "table_sort",
    "Table.TransformColumnTypes": "table_transform_column_types",
    "Table.TransformColumns": "table_transform_columns",
    "Table.PromoteHeaders": "table_promote_headers",
    "Table.Group": "table_group",
    "Table.ReplaceErrorValues": "table_replace_error_values",
    "Table.Pivot": "table_pivot",
    "List.Select": "list_select",
    "List.Transform": "list_transform",
    "List.AnyTrue": "list_any_true",
    "List.RemoveNulls": "list_remove_nulls",
    "List.Dates": "list_dates",
    "List.Distinct": "list_distinct",
    "List.Accumulate": "list_accumulate",
    "List.Contains": "list_contains",
    "List.First": "list_first",
    "List.Max": "list_max",
    "List.Sum": "list_sum",
    "Text.Combine": "text_combine",
    "Text.Contains": "text_contains",
    "Text.StartsWith": "text_starts_with",
    "Text.EndsWith": "text_ends_with",
    "Text.Lower": "text_lower",
    "Text.Upper": "text_upper",
    "Text.Proper": "text_proper",
    "Text.Trim": "text_trim",
    "Text.TrimStart": "text_trim_start",
    "Text.TrimEnd": "text_trim_end",
    "Text.From": "text_from",
    "Text.Length": "text_length",
    "Text.Replace": "text_replace",
    "Text.Split": "text_split",
    "Text.Middle": "text_middle",
    "Text.Start": "text_start",
    "Text.End": "text_end",
    "Text.AfterDelimiter": "text_after_delimiter",
    "Text.BeforeDelimiter": "text_before_delimiter",
    "Combiner.CombineTextByDelimiter": "combiner_combine_text_by_delimiter",
    "Splitter.SplitTextByEachDelimiter": "splitter_split_by_each_delimiter",
    "Splitter.SplitByNothing": "splitter_split_by_nothing",
    "Number.From": "number_from",
    "Number.Round": "number_round",
    "Number.Abs": "number_abs",
    "Number.IntegerDivide": "number_integer_divide",
    "Date.From": "date_from",
    "Date.Year": "date_year",
    "Date.Month": "date_month",
    "Date.Day": "date_day",
    "Date.DayOfWeek": "date_day_of_week",
    "Date.WeekOfYear": "date_week_of_year",
    "Date.StartOfWeek": "date_start_of_week",
    "Date.EndOfWeek": "date_end_of_week",
    "Date.ToText": "date_to_text",
    "DateTime.LocalNow": "datetime_local_now",
    "Duration.Days": "duration_days",
    "Record.FieldOrDefault": "record_field_or_default",
    "Record.Field": "record_field",
    "Value.Is": "value_is",
    "Binary.FromText": "binary_from_text",
    "Binary.Decompress": "binary_decompress",
    "Json.Document": "json_document",
    "Web.Contents": "web_contents",
    "File.Contents": "file_contents",
    "Folder.Files": "folder_files",
    "Excel.Workbook": "excel_workbook",
    "Csv.Document": "csv_document",
    "Sql.Database": "sql_database_handle",
    "OData.Feed": "odata_feed_handle",
}

_BINOP_PY = {
    "=": "==",
    "<>": "!=",
    "and": "and",
    "or": "or",
    "<": "<",
    ">": ">",
    "<=": "<=",
    ">=": ">=",
    "+": "+",
    "-": "-",
    "*": "*",
    "/": "/",
}


def _safe_name(name: str) -> str:
    out = re.sub(r"\W+", "_", name.strip())
    if not out or out[0].isdigit():
        out = f"v_{out}"
    return out


class MTranspiler:
    """Transpiles one M AST into readable Python source. `scope` tracks
    names bound by enclosing let-steps/lambda params so references resolve
    to the right generated variable instead of a table lookup."""

    def transpile_query(self, ast: MNode, model_ref: str = "model") -> tuple[list[str], str]:
        """Returns (list of python statement lines, name of the final result variable)."""
        if not isinstance(ast, LetExpr):
            return [], self.expr(ast, scope=set())

        lines: list[str] = []
        scope: set[str] = set()
        for name, expr in ast.steps:
            var = _safe_name(name)
            lines.append(f"{var} = {self.expr(expr, scope, model_ref)}  # step: {name!r}")
            scope.add(name)
        final = self.expr(ast.body, scope, model_ref)
        return lines, final

    def expr(self, node: MNode, scope: set[str], model_ref: str = "model") -> str:  # noqa: PLR0911
        if isinstance(node, Lit):
            return repr(node.value)
        if isinstance(node, Ident):
            if node.name == "_":
                return "row"
            if node.name in scope:
                return _safe_name(node.name)
            if node.name in GLOBALS:
                return GLOBALS[node.name]
            return f"{model_ref}[{node.name!r}]"
        if isinstance(node, FieldAccess):
            target = self.expr(node.target, scope, model_ref)
            return f"m_ops.field({target}, {node.field!r})"
        if isinstance(node, ItemAccess):
            target = self.expr(node.target, scope, model_ref)
            index = self.expr(node.index, scope, model_ref)
            return f"m_ops.item_access({target}, {index})"
        if isinstance(node, Invoke):
            return self._invoke(node, scope, model_ref)
        if isinstance(node, Lambda):
            params = ["row" if p == "_" else _safe_name(p) for p in node.params]
            inner_scope = scope | set(node.params) | {"_"}
            body = self.expr(node.body, inner_scope, model_ref)
            return f"lambda {', '.join(params)}: {body}"
        if isinstance(node, If):
            cond = self.expr(node.cond, scope, model_ref)
            then_ = self.expr(node.then_, scope, model_ref)
            else_ = self.expr(node.else_, scope, model_ref)
            return f"({then_} if {cond} else {else_})"
        if isinstance(node, BinOp):
            left = self.expr(node.left, scope, model_ref)
            right = self.expr(node.right, scope, model_ref)
            if node.op == "&":
                return f"(m_ops.text_from({left}) + m_ops.text_from({right}))"
            if node.op == "??":
                return f"({left} if {left} is not None else {right})"
            return f"({left} {_BINOP_PY[node.op]} {right})"
        if isinstance(node, UnaryOp):
            inner = self.expr(node.expr, scope, model_ref)
            return f"(not {inner})" if node.op == "not" else f"({node.op}{inner})"
        if isinstance(node, ListExpr):
            return "[" + ", ".join(self.expr(e, scope, model_ref) for e in node.items) + "]"
        if isinstance(node, RecordExpr):
            fields = ", ".join(f"{name!r}: {self.expr(v, scope, model_ref)}" for name, v in node.fields)
            return "{" + fields + "}"
        if isinstance(node, LetExpr):
            inner_scope = set(scope)
            clauses = []
            for name, step_expr in node.steps:
                clauses.append(f"{_safe_name(name)} in [{self.expr(step_expr, inner_scope, model_ref)}]")
                inner_scope.add(name)
            body = self.expr(node.body, inner_scope, model_ref)
            return f"next({body} for {' for '.join(clauses)})"
        if isinstance(node, TryExpr):
            expr_code = self.expr(node.expr, scope, model_ref)
            other = self.expr(node.otherwise, scope, model_ref) if node.otherwise else "None"
            return f"m_ops.try_or(lambda: {expr_code}, lambda: {other})"
        if isinstance(node, TypeLit):
            return GLOBALS.get(node.raw, repr(node.raw))
        raise ValueError(f"Unsupported AST node: {type(node).__name__}")

    def _invoke(self, node: Invoke, scope: set[str], model_ref: str) -> str:  # noqa: PLR0911
        args = [self.expr(a, scope, model_ref) for a in node.args]
        if isinstance(node.func, Ident):
            name = node.func.name
            if name in scope:
                fn = _safe_name(name)
                return f"{fn}({', '.join(args)})"
            if name == "List.Count":
                return f"len({args[0]})"
            if name == "List.IsEmpty":
                return f"(len({args[0]}) == 0)"
            if name in SIMPLE_CALLS:
                return f"m_ops.{SIMPLE_CALLS[name]}({', '.join(args)})"
            if name == "#table":
                return f"m_ops.hash_table({args[0]}, {args[1]})"
            if name == "#date":
                return f"m_ops.hash_date({', '.join(args)})"
            if name == "#datetime":
                return f"m_ops.hash_datetime({', '.join(args)})"
            if name == "#duration":
                return f"m_ops.hash_duration({', '.join(args)})"
            if name == "__m_error__":
                return f"m_ops.raise_m_error({args[0]})"
            # Not local, not stdlib: likely another top-level query that is
            # itself a function (e.g. a small reusable "Format_Date" helper
            # query) - call it via the model dict, same as a bare reference.
            return f"{model_ref}[{name!r}]({', '.join(args)})"
        fn = self.expr(node.func, scope, model_ref)
        return f"{fn}({', '.join(args)})"


def transpile_query(ast: MNode, model_ref: str = "model") -> tuple[list[str], str]:
    return MTranspiler().transpile_query(ast, model_ref)
