"""M interpreter."""

from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

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


class MRuntimeError(Exception):
    """Raised for genuinely unimplemented M functions/operators - never a
    silent no-op, so gaps surface loudly instead of producing wrong data."""


# --------------------------------------------------------------------- values
@dataclass
class MTable:
    """M's `table` value: a thin pandas.DataFrame wrapper so the interpreter
    can distinguish tables from plain records/lists at runtime."""

    df: pd.DataFrame

    def __repr__(self) -> str:
        """Return a debug-friendly string representation."""
        return f"MTable({len(self.df)} rows, cols={list(self.df.columns)})"


@dataclass
class MFunction:
    """A closure: an M `each`/`(x,y)=>` lambda plus the environment it
    captured, so nested lambdas see their enclosing step bindings."""

    params: list[str]
    body: MNode
    closure: Env
    interpreter: MInterpreter = field(repr=False)

    def call(self, args: list[Any]) -> Any:
        """Call. Takes `args`."""
        child = self.closure.child()
        for name, val in zip(self.params, args, strict=False):
            child.set(name, val)
        return self.interpreter.eval(self.body, child)


class Env:
    """Env (see attributes/methods below)."""

    def __init__(self, parent: Env | None = None):
        """Initialize."""
        self.vars: dict[str, Any] = {}
        self.parent = parent

    def get(self, name: str) -> Any:
        """Get. Takes `name`."""
        env: Env | None = self
        while env is not None:
            if name in env.vars:
                return env.vars[name]
            env = env.parent
        raise MRuntimeError(f"Unbound identifier: {name}")

    def has(self, name: str) -> bool:
        """Has. Takes `name`."""
        env: Env | None = self
        while env is not None:
            if name in env.vars:
                return True
            env = env.parent
        return False

    def set(self, name: str, value: Any) -> None:
        """Set. Takes `name`, `value`."""
        self.vars[name] = value

    def child(self) -> Env:
        """Child."""
        return Env(parent=self)


@dataclass
class SqlDatabaseHandle:
    """SqlDatabaseHandle (see attributes/methods below)."""

    server: str
    database: str


@dataclass
class ODataFeedHandle:
    """ODataFeedHandle (see attributes/methods below)."""

    url: str


def _to_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, MTable):
        return value.df.to_dict("records")
    raise MRuntimeError(f"Expected an M list, got {type(value).__name__}")


def _as_row(row: Any):
    """Normalizes a pandas row (Series) and a plain dict to the same `_[field]`
    access interface used inside row-context lambdas."""
    return row


# --------------------------------------------------------------- interpreter
class MInterpreter:
    """MInterpreter (see attributes/methods below)."""

    def __init__(self, stdlib: dict[str, Callable] | None = None, globals_: dict[str, Any] | None = None):
        """Initialize."""
        self.stdlib = {**_default_stdlib(), **(stdlib or {})}
        self.globals = {**_default_globals(), **(globals_ or {})}

    def eval(self, node: MNode, env: Env) -> Any:  # noqa: PLR0911
        """Eval. Takes `node`, `env`."""
        if isinstance(node, Lit):
            return node.value
        if isinstance(node, Ident):
            if env.has(node.name):
                return env.get(node.name)
            if node.name in self.globals:
                return self.globals[node.name]
            raise MRuntimeError(f"Unbound identifier: {node.name}")
        if isinstance(node, FieldAccess):
            target = self.eval(node.target, env)
            return self._get_field(target, node.field)
        if isinstance(node, ItemAccess):
            target = self.eval(node.target, env)
            index = self.eval(node.index, env)
            return self._get_item(target, index)
        if isinstance(node, Invoke):
            return self._eval_invoke(node, env)
        if isinstance(node, Lambda):
            return MFunction(params=node.params, body=node.body, closure=env, interpreter=self)
        if isinstance(node, If):
            return self.eval(node.then_, env) if self.eval(node.cond, env) else self.eval(node.else_, env)
        if isinstance(node, BinOp):
            return self._eval_binop(node, env)
        if isinstance(node, UnaryOp):
            val = self.eval(node.expr, env)
            if node.op == "-":
                return -val
            if node.op == "+":
                return val
            if node.op == "not":
                return not val
            raise MRuntimeError(f"Unsupported unary operator: {node.op}")
        if isinstance(node, ListExpr):
            return [self.eval(e, env) for e in node.items]
        if isinstance(node, RecordExpr):
            return {name: self.eval(v, env) for name, v in node.fields}
        if isinstance(node, LetExpr):
            child = env.child()
            for name, expr in node.steps:
                child.set(name, self.eval(expr, child))
            return self.eval(node.body, child)
        if isinstance(node, TryExpr):
            try:
                value = self.eval(node.expr, env)
                return {"HasError": False, "Value": value}
            except MRuntimeError:
                if node.otherwise is not None:
                    return self.eval(node.otherwise, env)
                return {"HasError": True, "Value": None}
        if isinstance(node, TypeLit):
            return self.globals.get(node.raw, node.raw)
        raise MRuntimeError(f"Unsupported AST node: {type(node).__name__}")

    # -- helpers
    def _get_field(self, target: Any, field_name: str) -> Any:
        if isinstance(target, MTable):
            return target.df[field_name].tolist()
        if isinstance(target, dict):
            if field_name not in target:
                raise MRuntimeError(f"Field not found: {field_name}")
            return target[field_name]
        if isinstance(target, pd.Series):
            return target[field_name]
        if target is None:
            return None
        raise MRuntimeError(f"Cannot access field {field_name!r} on {type(target).__name__}")

    def _get_item(self, target: Any, index: Any) -> Any:
        if isinstance(target, SqlDatabaseHandle):
            import sqlalchemy

            schema = index.get("Schema") if isinstance(index, dict) else None
            name = index.get("Item") or index.get("Name") if isinstance(index, dict) else None
            table_ref = f"[{schema}].[{name}]" if schema else f"[{name}]"
            engine = sqlalchemy.create_engine(
                f"mssql+pyodbc://{target.server}/{target.database}?driver=ODBC+Driver+17+for+SQL+Server",
            )
            return MTable(pd.read_sql(f"SELECT * FROM {table_ref}", engine))
        if isinstance(target, ODataFeedHandle):
            import requests

            name = index.get("Name") if isinstance(index, dict) else None
            resp = requests.get(f"{target.url.rstrip('/')}/{name}", timeout=60)
            resp.raise_for_status()
            payload = resp.json()
            return {"Name": name, "Data": MTable(pd.json_normalize(payload.get("value", payload)))}
        if isinstance(target, list):
            if isinstance(index, dict):
                for item in target:
                    if isinstance(item, dict) and all(item.get(k) == v for k, v in index.items()):
                        return item
                raise MRuntimeError(f"No item matching {index!r}")
            return target[int(index)]
        if isinstance(target, MTable):
            if isinstance(index, dict):
                mask = pd.Series(True, index=target.df.index)
                for k, v in index.items():
                    mask &= target.df[k] == v
                matches = target.df[mask]
                if len(matches) == 0:
                    raise MRuntimeError(f"No row matching {index!r}")
                return matches.iloc[0]
            return target.df.iloc[int(index)]
        raise MRuntimeError(f"Cannot index {type(target).__name__} with {index!r}")

    def _eval_binop(self, node: BinOp, env: Env) -> Any:  # noqa: PLR0911
        if node.op == "and":
            return self.eval(node.left, env) and self.eval(node.right, env)
        if node.op == "or":
            return self.eval(node.left, env) or self.eval(node.right, env)
        if node.op == "??":
            left = self.eval(node.left, env)
            return self.eval(node.right, env) if _is_m_null(left) else left
        left = self.eval(node.left, env)
        right = self.eval(node.right, env)
        op = node.op
        if op == "&":
            return _m_str(left) + _m_str(right)
        if op == "+":
            return left + right
        if op == "-":
            return left - right
        if op == "*":
            return left * right
        if op == "/":
            return left / right
        if op == "=":
            return _m_equals(left, right)
        if op == "<>":
            return not _m_equals(left, right)
        if op == "<":
            return (not _is_m_null(left)) and (not _is_m_null(right)) and left < right
        if op == ">":
            return (not _is_m_null(left)) and (not _is_m_null(right)) and left > right
        if op == "<=":
            return (not _is_m_null(left)) and (not _is_m_null(right)) and left <= right
        if op == ">=":
            return (not _is_m_null(left)) and (not _is_m_null(right)) and left >= right
        raise MRuntimeError(f"Unsupported operator: {op}")

    def _eval_invoke(self, node: Invoke, env: Env) -> Any:
        args = [self.eval(a, env) for a in node.args]
        if isinstance(node.func, Ident):
            name = node.func.name
            if env.has(name):
                fn = env.get(name)
                return self._call(fn, args)
            if name in self.stdlib:
                return self.stdlib[name](self, *args)
            raise MRuntimeError(f"Unsupported M function: {name}")
        fn = self.eval(node.func, env)
        return self._call(fn, args)

    def _call(self, fn: Any, args: list[Any]) -> Any:
        if isinstance(fn, MFunction):
            return fn.call(args)
        if callable(fn):
            return fn(*args)
        raise MRuntimeError(f"Value is not callable: {fn!r}")


def _is_m_null(x: Any) -> bool:
    if x is None:
        return True
    try:
        result = pd.isna(x)
        return bool(result) if not hasattr(result, "__len__") else False
    except (TypeError, ValueError):
        return False


def _m_equals(a: Any, b: Any) -> bool:
    a_null, b_null = _is_m_null(a), _is_m_null(b)
    if a_null or b_null:
        return a_null and b_null
    return a == b


def _m_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


# ------------------------------------------------------------------ globals
def _default_globals() -> dict[str, Any]:
    return {
        # sort order markers
        "Order.Ascending": "asc",
        "Order.Descending": "desc",
        # join kinds
        "JoinKind.Inner": "inner",
        "JoinKind.LeftOuter": "left",
        "JoinKind.RightOuter": "right",
        "JoinKind.FullOuter": "outer",
        "JoinKind.LeftAnti": "left_anti",
        "JoinKind.RightAnti": "right_anti",
        # column type markers used by Table.TransformColumnTypes
        "Int64.Type": "Int64",
        "Byte.Type": "Int64",
        "Currency.Type": "float",
        "Number.Type": "float",
        "Double.Type": "float",
        "Percentage.Type": "float",
        "Text.Type": "string",
        "Date.Type": "date",
        "DateTime.Type": "datetime",
        "DateTimeZone.Type": "datetime",
        "Time.Type": "time",
        "Logical.Type": "bool",
        "Any.Type": None,
        "Binary.Type": None,
        "None.Type": None,
        # misc
        "Compression.Deflate": "deflate",
        "BinaryEncoding.Base64": "base64",
        "QuoteStyle.Csv": "csv",
        "QuoteStyle.None": "none",
        "TextEncoding.Utf8": "utf-8",
        "ExtraValues.Ignore": "ignore",
        "ExtraValues.Error": "error",
        "MissingField.UseNull": "use_null",
        "MissingField.Ignore": "ignore",
        "RoundingMode.Down": "down",
        "RoundingMode.Up": "up",
        "Occurrence.All": "all",
        "Occurrence.First": "first",
        "Occurrence.Last": "last",
        "Precision.Double": "double",
    }


# ------------------------------------------------------------------- stdlib
def _col_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return list(value)
    raise MRuntimeError(f"Expected a column name or list of names, got {value!r}")


def _fn_table_selectrows(interp: MInterpreter, table: MTable, predicate: MFunction) -> MTable:
    df = table.df
    if len(df) == 0:
        return MTable(df)
    mask = df.apply(lambda row: bool(predicate.call([row])), axis=1)
    return MTable(df[mask].reset_index(drop=True))


def _fn_table_addcolumn(interp: MInterpreter, table: MTable, name: str, fn: MFunction, *_type) -> MTable:
    df = table.df.copy()
    df[name] = df.apply(lambda row: fn.call([row]), axis=1) if len(df) else pd.Series(dtype=object)
    return MTable(df)


def _fn_table_selectcolumns(interp, table: MTable, cols, *_opt) -> MTable:
    return MTable(table.df[_col_list(cols)])


def _fn_table_removecolumns(interp, table: MTable, cols, *_opt) -> MTable:
    return MTable(table.df.drop(columns=_col_list(cols), errors="ignore"))


def _fn_table_renamecolumns(interp, table: MTable, pairs: list, *_opt) -> MTable:
    mapping = {p[0]: p[1] for p in pairs}
    return MTable(table.df.rename(columns=mapping))


def _fn_table_sort(interp, table: MTable, pairs: list) -> MTable:
    by = [p[0] for p in pairs]
    ascending = [p[1] != "desc" for p in pairs]
    return MTable(table.df.sort_values(by=by, ascending=ascending).reset_index(drop=True))


def _fn_table_distinct(interp, table: MTable, cols=None) -> MTable:
    subset = _col_list(cols) if cols else None
    return MTable(table.df.drop_duplicates(subset=subset).reset_index(drop=True))


def _fn_table_columnnames(interp, table: MTable) -> list:
    return list(table.df.columns)


_DTYPE_CONVERTERS = {
    "Int64": lambda s: pd.to_numeric(s, errors="coerce").astype("Int64"),
    "float": lambda s: pd.to_numeric(s, errors="coerce"),
    "string": lambda s: s.astype("string"),
    "bool": lambda s: s.astype("boolean"),
    "date": lambda s: pd.to_datetime(s, errors="coerce"),
    "datetime": lambda s: pd.to_datetime(s, errors="coerce"),
    "time": lambda s: pd.to_datetime(s, errors="coerce"),
}


def _fn_table_transformcolumntypes(interp, table: MTable, pairs: list, *_culture) -> MTable:
    df = table.df.copy()
    for pair in pairs:
        col, dtype = pair[0], pair[1]
        if dtype is None or col not in df.columns:
            continue
        converter = _DTYPE_CONVERTERS.get(dtype)
        if converter:
            df[col] = converter(df[col])
    return MTable(df)


def _fn_table_transformcolumns(interp, table: MTable, specs: list, *_opt) -> MTable:
    df = table.df.copy()
    for spec in specs:
        col, fn = spec[0], spec[1]
        if col in df.columns:
            df[col] = df[col].apply(lambda v, _fn=fn: _fn.call([v]) if isinstance(_fn, MFunction) else _fn(v))
    return MTable(df)


def _fn_table_replacevalue(  # noqa: PLR0913, PLR0917
    interp,
    table: MTable,
    old_val,
    new_val,
    replacer,
    cols,
) -> MTable:
    df = table.df.copy()
    for c in _col_list(cols):
        if c not in df.columns:
            continue
        if isinstance(old_val, MFunction):

            def _apply(row, _c=c):
                is_match = bool(old_val.call([row]))
                if isinstance(replacer, MFunction):
                    return replacer.call([row[_c], is_match, new_val])
                return new_val if is_match else row[_c]

            df[c] = df.apply(_apply, axis=1)
        else:

            def _apply_scalar(v, _c=c):
                if isinstance(replacer, MFunction):
                    return replacer.call([v, old_val, new_val])
                return new_val if v == old_val else v

            df[c] = df[c].apply(_apply_scalar)
    return MTable(df)


def _fn_table_nestedjoin(  # noqa: PLR0913, PLR0917
    interp,
    t1: MTable,
    keys1,
    t2: MTable,
    keys2,
    new_col: str,
    join_kind="left",
) -> MTable:
    keys1, keys2 = _col_list(keys1), _col_list(keys2)
    df1, df2 = t1.df, t2.df

    def find_matches(row):
        """Find matches. Takes `row`."""
        mask = pd.Series(True, index=df2.index)
        for k1, k2 in zip(keys1, keys2, strict=False):
            mask &= df2[k2] == row[k1]
        return MTable(df2[mask].reset_index(drop=True))

    out = df1.copy()
    out[new_col] = out.apply(find_matches, axis=1) if len(out) else pd.Series(dtype=object)
    return MTable(out)


def _fn_table_expandtablecolumn(interp, table: MTable, col_name: str, expand_cols, new_names=None) -> MTable:
    expand_cols = _col_list(expand_cols)
    new_names = _col_list(new_names) if new_names else expand_cols
    df = table.df
    rows: list[dict] = []
    for _, row in df.iterrows():
        nested = row[col_name]
        base = {k: v for k, v in row.items() if k != col_name}
        nested_df = nested.df if isinstance(nested, MTable) else pd.DataFrame()
        if len(nested_df) == 0:
            merged = dict(base)
            merged.update(dict.fromkeys(new_names))
            rows.append(merged)
        else:
            for _, nrow in nested_df.iterrows():
                merged = dict(base)
                for ec, nn in zip(expand_cols, new_names, strict=False):
                    merged[nn] = nrow.get(ec)
                rows.append(merged)
    return MTable(pd.DataFrame(rows))


def _fn_table_expandrecordcolumn(interp, table: MTable, col_name: str, fields, new_names=None) -> MTable:
    fields = _col_list(fields)
    new_names = _col_list(new_names) if new_names else fields
    df = table.df.copy()
    for f_, nn in zip(fields, new_names, strict=False):
        df[nn] = df[col_name].apply(lambda rec, _f=f_: rec.get(_f) if isinstance(rec, dict) else None)
    return MTable(df.drop(columns=[col_name]))


def _fn_table_group(interp, table: MTable, keys, agg_specs: list) -> MTable:
    keys = _col_list(keys)
    df = table.df
    if len(df) == 0:
        cols = [*keys, *[spec[0] for spec in agg_specs]]
        return MTable(pd.DataFrame(columns=cols))
    rows = []
    for key_vals, sub in df.groupby(keys, dropna=False):
        key_vals = key_vals if isinstance(key_vals, tuple) else (key_vals,)
        row = dict(zip(keys, key_vals, strict=False))
        sub_table = MTable(sub.reset_index(drop=True))
        for spec in agg_specs:
            new_name, agg_fn = spec[0], spec[1]
            row[new_name] = agg_fn.call([sub_table]) if isinstance(agg_fn, MFunction) else agg_fn
        rows.append(row)
    return MTable(pd.DataFrame(rows))


def _fn_table_combinecolumns(interp, table: MTable, cols, combiner, new_col: str) -> MTable:
    cols = _col_list(cols)
    df = table.df.copy()
    df[new_col] = df[cols].apply(lambda vals: interp._call(combiner, [list(vals)]), axis=1)
    return MTable(df.drop(columns=cols))


def _fn_table_promoteheaders(interp, table: MTable, *_opt) -> MTable:
    df = table.df
    if len(df) == 0:
        return MTable(df)
    new_df = df.iloc[1:].reset_index(drop=True)
    new_df.columns = [str(v) for v in df.iloc[0]]
    return MTable(new_df)


def _fn_table_pivot(interp, table: MTable, pivot_col: str, value_col: str, agg_fn=None, *_opt) -> MTable:
    df = table.df
    group_cols = [c for c in df.columns if c not in (pivot_col, value_col)]
    aggfunc = "first"
    pivoted = df.pivot_table(index=group_cols or None, columns=pivot_col, values=value_col, aggfunc=aggfunc)
    return MTable(pivoted.reset_index())


def _fn_table_fromrecords(interp, records: list, *_opt) -> MTable:
    return MTable(pd.DataFrame(records))


def _fn_table_fromlist(interp, items: list, splitter=None, *_opt) -> MTable:
    return MTable(pd.DataFrame({"Column1": items}))


def _fn_table_fromrows(interp, rows: list, columns=None, *_opt) -> MTable:
    return MTable(pd.DataFrame(rows, columns=_col_list(columns) if columns else None))


def _fn_table_combine(interp, tables: list) -> MTable:
    frames = [t.df for t in tables]
    return MTable(pd.concat(frames, ignore_index=True) if frames else pd.DataFrame())


# -- List.*
def _fn_list_select(interp, items: list, predicate: MFunction) -> list:
    return [x for x in items if predicate.call([x])]


def _fn_list_transform(interp, items: list, fn: MFunction) -> list:
    return [fn.call([x]) for x in items]


def _fn_list_anytrue(interp, items: list) -> bool:
    return any(bool(x) for x in items)


def _fn_list_removenulls(interp, items: list) -> list:
    return [x for x in items if x is not None]


def _fn_list_dates(interp, start, count: int, step=1) -> list:
    ts = pd.Timestamp(start)
    step_td = step if isinstance(step, pd.Timedelta) else pd.Timedelta(days=step)
    return [ts + step_td * i for i in range(int(count))]


def _fn_list_distinct(interp, items: list, *_opt) -> list:
    seen, out = [], []
    for x in items:
        if x not in seen:
            seen.append(x)
            out.append(x)
    return out


def _fn_list_count(interp, items: list) -> int:
    return len(items)


def _fn_list_sum(interp, items: list) -> Any:
    return sum(x for x in items if x is not None)


# -- Text.*
def _fn_text_combine(interp, items: list, delimiter: str = "") -> str:
    return delimiter.join(_m_str(x) for x in items)


def _fn_combiner_combinetextbydelimiter(interp, delimiter: str, *_opt):
    return lambda items: delimiter.join(_m_str(x) for x in items)


def _fn_splitter_splitbynothing(interp, *_opt):
    return None


# -- Date/DateTime/Duration
def _fn_date_from(interp, value) -> pd.Timestamp:
    return pd.Timestamp(value).normalize()


def _fn_datetime_localnow(interp) -> pd.Timestamp:
    return pd.Timestamp.now()


def _fn_number_from(interp, value) -> float:
    return float(value) if value is not None else None


def _fn_binary_fromtext(interp, text: str, encoding=None) -> bytes:
    import base64

    return base64.b64decode(text) if encoding == "base64" else bytes.fromhex(text)


def _fn_binary_decompress(interp, data: bytes, compression=None) -> bytes:
    import zlib

    return zlib.decompress(data, -zlib.MAX_WBITS) if compression == "deflate" else zlib.decompress(data)


def _fn_json_document(interp, data) -> Any:
    import json

    text = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else data
    return json.loads(text)


def _fn_csv_document(interp, data, *_opt) -> MTable:
    text = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else data
    df = pd.read_csv(io.StringIO(text), header=None)
    df.columns = [f"Column{i + 1}" for i in range(len(df.columns))]
    return MTable(df)


def _fn_record_fieldordefault(interp, record: dict, field_name: str, default=None) -> Any:
    return record.get(field_name, default) if isinstance(record, dict) else default


def _fn_sql_database(interp, server: str, database: str, *_opt) -> SqlDatabaseHandle:
    return SqlDatabaseHandle(server=server, database=database)


def _fn_odata_feed(interp, url: str, *_opt) -> ODataFeedHandle:
    return ODataFeedHandle(url=url)


def _fn_web_contents(interp, url: str, options=None) -> bytes:
    import requests

    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    return resp.content


def _fn_file_contents(interp, path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def _fn_folder_files(interp, path: str) -> list:
    from pathlib import Path

    out = []
    for p in sorted(Path(path).glob("*")):
        if p.is_file():
            out.append({"Content": p.read_bytes(), "Name": p.name, "Extension": p.suffix, "Folder Path": str(p.parent)})
    return out


def _fn_excel_workbook(interp, binary: bytes, *_opt) -> list:
    sheets = pd.read_excel(io.BytesIO(binary), sheet_name=None)
    return [{"Name": name, "Item": name, "Kind": "Sheet", "Data": MTable(df)} for name, df in sheets.items()]


def _fn_list_accumulate(interp, items: list, seed, fn: MFunction) -> Any:
    state = seed
    for item in items:
        state = fn.call([state, item])
    return state


def _fn_list_contains(interp, items: list, value) -> bool:
    return any(_m_equals(x, value) for x in items)


def _fn_list_first(interp, items: list, default=None) -> Any:
    return items[0] if items else default


def _fn_list_max(interp, items: list) -> Any:
    vals = [x for x in items if not _is_m_null(x)]
    return max(vals) if vals else None


def _fn_table_reordercolumns(interp, table: MTable, cols, *_opt) -> MTable:
    cols = _col_list(cols)
    remaining = [c for c in table.df.columns if c not in cols]
    return MTable(table.df[cols + remaining])


def _fn_table_replaceerrorvalues(interp, table: MTable, replacements: list) -> MTable:
    df = table.df.copy()
    for col, repl in replacements:
        if col in df.columns:
            df[col] = df[col].where(~df[col].isna() if hasattr(df[col], "isna") else True, repl)
    return MTable(df)


def _fn_table_splitcolumn(interp, table: MTable, source_col: str, splitter, names, *_opt) -> MTable:
    df = table.df.copy()
    names = _col_list(names) if not isinstance(names, int) else [f"{source_col}.{i + 1}" for i in range(names)]
    split_values = df[source_col].apply(lambda v: splitter(v) if v is not None else [])
    for i, name in enumerate(names):
        df[name] = split_values.apply(lambda parts, _i=i: parts[_i] if _i < len(parts) else None)
    return MTable(df.drop(columns=[source_col]))


def _fn_table_torows(interp, table: MTable) -> list:
    return table.df.values.tolist()


def _fn_text_afterdelimiter(interp, text: str, delimiter: str, *_opt) -> str:
    if text is None:
        return None
    idx = text.rfind(delimiter)
    return text[idx + len(delimiter) :] if idx != -1 else ""


def _fn_text_beforedelimiter(interp, text: str, delimiter: str, *_opt) -> str:
    if text is None:
        return None
    idx = text.find(delimiter)
    return text[:idx] if idx != -1 else text


def _fn_value_is(interp, value, type_marker) -> bool:
    if value is None:
        return type_marker is None
    checks = {
        "Int64": lambda v: isinstance(v, int) or (isinstance(v, float) and float(v).is_integer()),
        "float": lambda v: isinstance(v, (int, float)),
        "string": lambda v: isinstance(v, str),
        "bool": lambda v: isinstance(v, bool),
        "date": lambda v: isinstance(v, pd.Timestamp),
        "datetime": lambda v: isinstance(v, pd.Timestamp),
    }
    check = checks.get(type_marker)
    return check(value) if check else True


def _fn_splitter_splittextbyeachdelimiter(interp, delimiters: list, *_opt):
    def _split(text: str) -> list:
        if text is None:
            return []
        parts = [text]
        for delim in delimiters:
            new_parts = []
            for p in parts:
                new_parts.extend(p.split(delim))
            parts = new_parts
        return parts

    return _split


def _fn_hash_table(interp, columns, rows) -> MTable:
    if isinstance(columns, (int, float)):
        n = int(columns)
        col_names = [f"Column{i + 1}" for i in range(n)]
    else:
        col_names = _col_list(columns)
    return MTable(pd.DataFrame(rows, columns=col_names))


def _fn_hash_date(interp, year, month, day) -> pd.Timestamp:
    return pd.Timestamp(int(year), int(month), int(day))


def _fn_hash_datetime(interp, year, month, day, hour, minute, second) -> pd.Timestamp:  # noqa: PLR0913, PLR0917
    return pd.Timestamp(int(year), int(month), int(day), int(hour), int(minute), int(second))


def _fn_hash_duration(interp, days, hours, minutes, seconds) -> pd.Timedelta:
    return pd.Timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)


def _default_stdlib() -> dict[str, Callable]:
    return {
        "#table": _fn_hash_table,
        "#date": _fn_hash_date,
        "#datetime": _fn_hash_datetime,
        "#duration": _fn_hash_duration,
        "List.Accumulate": _fn_list_accumulate,
        "List.Contains": _fn_list_contains,
        "List.First": _fn_list_first,
        "List.IsEmpty": lambda i, items: len(items) == 0,
        "List.Max": _fn_list_max,
        "Table.ReorderColumns": _fn_table_reordercolumns,
        "Table.ReplaceErrorValues": _fn_table_replaceerrorvalues,
        "Table.SplitColumn": _fn_table_splitcolumn,
        "Table.ToRows": _fn_table_torows,
        "Text.AfterDelimiter": _fn_text_afterdelimiter,
        "Text.BeforeDelimiter": _fn_text_beforedelimiter,
        "Text.TrimStart": lambda i, s, *_o: s.lstrip() if s is not None else None,
        "Text.TrimEnd": lambda i, s, *_o: s.rstrip() if s is not None else None,
        "Value.Is": _fn_value_is,
        "Splitter.SplitTextByEachDelimiter": _fn_splitter_splittextbyeachdelimiter,
        "Sql.Database": _fn_sql_database,
        "OData.Feed": _fn_odata_feed,
        "Web.Contents": _fn_web_contents,
        "File.Contents": _fn_file_contents,
        "Folder.Files": _fn_folder_files,
        "Excel.Workbook": _fn_excel_workbook,
        "Table.SelectRows": _fn_table_selectrows,
        "Table.AddColumn": _fn_table_addcolumn,
        "Table.SelectColumns": _fn_table_selectcolumns,
        "Table.RemoveColumns": _fn_table_removecolumns,
        "Table.RenameColumns": _fn_table_renamecolumns,
        "Table.Sort": _fn_table_sort,
        "Table.Distinct": _fn_table_distinct,
        "Table.ColumnNames": _fn_table_columnnames,
        "Table.TransformColumnTypes": _fn_table_transformcolumntypes,
        "Table.TransformColumns": _fn_table_transformcolumns,
        "Table.ReplaceValue": _fn_table_replacevalue,
        "Table.NestedJoin": _fn_table_nestedjoin,
        "Table.Join": _fn_table_nestedjoin,
        "Table.ExpandTableColumn": _fn_table_expandtablecolumn,
        "Table.ExpandRecordColumn": _fn_table_expandrecordcolumn,
        "Table.Group": _fn_table_group,
        "Table.CombineColumns": _fn_table_combinecolumns,
        "Table.PromoteHeaders": _fn_table_promoteheaders,
        "Table.Pivot": _fn_table_pivot,
        "Table.FromRecords": _fn_table_fromrecords,
        "Table.FromList": _fn_table_fromlist,
        "Table.FromRows": _fn_table_fromrows,
        "Table.Combine": _fn_table_combine,
        "List.Select": _fn_list_select,
        "List.Transform": _fn_list_transform,
        "List.AnyTrue": _fn_list_anytrue,
        "List.RemoveNulls": _fn_list_removenulls,
        "List.Dates": _fn_list_dates,
        "List.Distinct": _fn_list_distinct,
        "List.Count": _fn_list_count,
        "List.Sum": _fn_list_sum,
        "Text.Combine": _fn_text_combine,
        "Text.Contains": lambda i, s, sub, *_o: (sub in s) if s is not None else False,
        "Text.StartsWith": lambda i, s, sub, *_o: s.startswith(sub) if s is not None else False,
        "Text.EndsWith": lambda i, s, sub, *_o: s.endswith(sub) if s is not None else False,
        "Text.Lower": lambda i, s: s.lower() if s is not None else None,
        "Text.Upper": lambda i, s: s.upper() if s is not None else None,
        "Text.Proper": lambda i, s: s.title() if s is not None else None,
        "Text.Trim": lambda i, s, *_o: s.strip() if s is not None else None,
        "Text.From": lambda i, v, *_o: _m_str(v),
        "Text.Length": lambda i, s: len(s) if s is not None else 0,
        "Text.Replace": lambda i, s, old, new: s.replace(old, new) if s is not None else None,
        "Text.Split": lambda i, s, sep: s.split(sep) if s is not None else [],
        "Text.Middle": lambda i, s, start, count=None: s[start : start + count] if count is not None else s[start:],
        "Text.Start": lambda i, s, count: s[:count] if s is not None else None,
        "Text.End": lambda i, s, count: s[-count:] if s is not None else None,
        "Combiner.CombineTextByDelimiter": _fn_combiner_combinetextbydelimiter,
        "Splitter.SplitByNothing": _fn_splitter_splitbynothing,
        "Date.From": _fn_date_from,
        "Date.Year": lambda i, d: pd.Timestamp(d).year if d is not None else None,
        "Date.Month": lambda i, d: pd.Timestamp(d).month if d is not None else None,
        "Date.Day": lambda i, d: pd.Timestamp(d).day if d is not None else None,
        "Date.DayOfWeek": lambda i, d, *_o: pd.Timestamp(d).dayofweek if d is not None else None,
        "Date.WeekOfYear": lambda i, d: pd.Timestamp(d).isocalendar()[1] if d is not None else None,
        "Date.StartOfWeek": lambda i, d, *_o: (
            pd.Timestamp(d) - pd.Timedelta(days=pd.Timestamp(d).dayofweek)
        ).normalize(),
        "Date.EndOfWeek": lambda i, d, *_o: (
            pd.Timestamp(d) + pd.Timedelta(days=6 - pd.Timestamp(d).dayofweek)
        ).normalize(),
        "Date.ToText": lambda i, d, *_o: pd.Timestamp(d).strftime("%Y-%m-%d") if d is not None else None,
        "DateTime.LocalNow": _fn_datetime_localnow,
        "Duration.Days": lambda i, d: d.days if hasattr(d, "days") else int(d),
        "Number.From": _fn_number_from,
        "Number.Round": lambda i, v, digits=0: round(v, int(digits)) if v is not None else None,
        "Number.Abs": lambda i, v: abs(v) if v is not None else None,
        "Number.IntegerDivide": lambda i, a, b: int(a) // int(b),
        "Record.FieldOrDefault": _fn_record_fieldordefault,
        "Record.Field": lambda i, r, f: r.get(f) if isinstance(r, dict) else None,
        "Binary.FromText": _fn_binary_fromtext,
        "Binary.Decompress": _fn_binary_decompress,
        "Json.Document": _fn_json_document,
        "Csv.Document": _fn_csv_document,
        "__m_error__": lambda i, msg: (_ for _ in ()).throw(MRuntimeError(f"M `error` raised: {msg}")),
    }
