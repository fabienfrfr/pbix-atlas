"""M ops."""

import io
from collections.abc import Callable
from typing import Any

import pandas as pd


def field(target: Any, name: str) -> Any:
    """Field. Takes `target`, `name`."""
    if isinstance(target, pd.DataFrame):
        return target[name].tolist()
    if isinstance(target, dict):
        return target.get(name)
    return target[name]


def _col_list(value: Any) -> list[str]:
    return [value] if isinstance(value, str) else list(value)


# Table.*
def table_select_rows(df: pd.DataFrame, predicate: Callable) -> pd.DataFrame:
    """Table select rows. Takes `df`, `predicate`."""
    if len(df) == 0:
        return df
    return df[df.apply(lambda row: bool(predicate(row)), axis=1)].reset_index(drop=True)


def table_add_column(df: pd.DataFrame, name: str, fn: Callable) -> pd.DataFrame:
    """Table add column. Takes `df`, `name`, `fn`."""
    out = df.copy()
    out[name] = df.apply(lambda row: fn(row), axis=1) if len(df) else pd.Series(dtype=object)
    return out


def table_select_columns(df: pd.DataFrame, columns, *_opts) -> pd.DataFrame:
    """Table select columns. Takes `df`, `columns`."""
    return df[_col_list(columns)]


def table_remove_columns(df: pd.DataFrame, columns, *_opts) -> pd.DataFrame:
    """Table remove columns. Takes `df`, `columns`."""
    return df.drop(columns=_col_list(columns), errors="ignore")


def table_rename_columns(df: pd.DataFrame, pairs, *_opts) -> pd.DataFrame:
    """Table rename columns. Takes `df`, `pairs`."""
    return df.rename(columns={p[0]: p[1] for p in pairs})


def table_reorder_columns(df: pd.DataFrame, columns) -> pd.DataFrame:
    """Table reorder columns. Takes `df`, `columns`."""
    columns = _col_list(columns)
    return df[columns + [c for c in df.columns if c not in columns]]


def table_sort(df: pd.DataFrame, by, *_opts) -> pd.DataFrame:
    """Table sort. Takes `df`, `by`."""
    cols = [p[0] for p in by]
    ascending = [p[1] != "desc" for p in by]
    return df.sort_values(by=cols, ascending=ascending).reset_index(drop=True)


def table_distinct(df: pd.DataFrame, columns=None, *_opts) -> pd.DataFrame:
    """Table distinct. Takes `df`, `columns`."""
    return df.drop_duplicates(subset=_col_list(columns) if columns else None).reset_index(drop=True)


def table_column_names(df: pd.DataFrame) -> list[str]:
    """Table column names. Takes `df`."""
    return list(df.columns)


_DTYPE_CONVERTERS = {
    "Int64": lambda s: pd.to_numeric(s, errors="coerce").astype("Int64"),
    "float": lambda s: pd.to_numeric(s, errors="coerce"),
    "string": lambda s: s.astype("string"),
    "bool": lambda s: s.astype("boolean"),
    "date": lambda s: pd.to_datetime(s, errors="coerce"),
    "datetime": lambda s: pd.to_datetime(s, errors="coerce"),
    "time": lambda s: pd.to_datetime(s, errors="coerce"),
}


def table_transform_column_types(df: pd.DataFrame, pairs, *_opts) -> pd.DataFrame:
    """Table transform column types. Takes `df`, `pairs`."""
    out = df.copy()
    for pair in pairs:
        col, dtype = pair[0], pair[1]
        if dtype and col in out.columns:
            out[col] = _DTYPE_CONVERTERS[dtype](out[col])
    return out


def table_transform_columns(df: pd.DataFrame, specs, *_opts) -> pd.DataFrame:
    """Table transform columns. Takes `df`, `specs`."""
    out = df.copy()
    for spec in specs:
        col, fn = spec[0], spec[1]
        if col in out.columns:
            out[col] = out[col].apply(fn)
    return out


def _is_m_null(x: Any) -> bool:
    if x is None:
        return True
    try:
        result = pd.isna(x)
        return bool(result) if not hasattr(result, "__len__") else False
    except (TypeError, ValueError):
        return False


def default_replacer(current, match_or_old_value, new_value):
    """Default replacer. Takes `current`, `match_or_old_value`, `new_value`."""
    if match_or_old_value is True:
        return new_value
    if match_or_old_value is False:
        return current
    return new_value if current == match_or_old_value else current


def default_text_replacer(current, text_to_find, text_to_replace):
    """Default text replacer. Takes `current`, `text_to_find`, `text_to_replace`."""
    return current.replace(text_to_find, text_to_replace) if isinstance(current, str) else current


def table_replace_value(
    df: pd.DataFrame,
    old_value: Any,
    new_value: Any,
    replacer: Callable,
    columns,
) -> pd.DataFrame:
    """Table replace value. Takes `df`, `old_value`, `new_value`, `replacer`, `columns`."""
    out = df.copy()
    is_selector = callable(old_value)
    for col in _col_list(columns):
        if col not in out.columns:
            continue
        if is_selector:
            out[col] = out.apply(
                lambda row, _c=col: replacer(row[_c], bool(old_value(row)), new_value),
                axis=1,
            )
        else:
            out[col] = out[col].apply(lambda v: replacer(v, old_value, new_value))
    return out


def table_nested_join(  # noqa: PLR0913, PLR0917
    left: pd.DataFrame,
    left_keys,
    right: pd.DataFrame,
    right_keys,
    new_column: str,
    join_kind: str = "left",
) -> pd.DataFrame:
    """Table nested join. Takes `left`, `left_keys`, `right`, `right_keys`, `new_column`, `join_kind`."""
    left_keys, right_keys = _col_list(left_keys), _col_list(right_keys)

    def matches(row):
        """Matches. Takes `row`."""
        mask = pd.Series(True, index=right.index)
        for lk, rk in zip(left_keys, right_keys, strict=False):
            mask &= right[rk] == row[lk]
        return right[mask].reset_index(drop=True)

    out = left.copy()
    out[new_column] = left.apply(matches, axis=1) if len(left) else pd.Series(dtype=object)
    return out


def table_expand_table_column(df: pd.DataFrame, column: str, expand_columns, new_names=None) -> pd.DataFrame:
    """Table expand table column. Takes `df`, `column`, `expand_columns`, `new_names`."""
    expand_columns = _col_list(expand_columns)
    new_names = _col_list(new_names) if new_names else expand_columns
    rows: list[dict] = []
    for _, row in df.iterrows():
        nested = row[column]
        base = {k: v for k, v in row.items() if k != column}
        if nested is None or len(nested) == 0:
            rows.append({**base, **dict.fromkeys(new_names)})
        else:
            for _, nrow in nested.iterrows():
                rows.append({**base, **{nn: nrow.get(ec) for ec, nn in zip(expand_columns, new_names, strict=False)}})
    return pd.DataFrame(rows)


def table_expand_record_column(df: pd.DataFrame, column: str, fields, new_names=None) -> pd.DataFrame:
    """Table expand record column. Takes `df`, `column`, `fields`, `new_names`."""
    fields = _col_list(fields)
    new_names = _col_list(new_names) if new_names else fields
    out = df.copy()
    for field, name in zip(fields, new_names, strict=False):
        out[name] = out[column].apply(lambda rec, _f=field: rec.get(_f) if isinstance(rec, dict) else None)
    return out.drop(columns=[column])


def table_group(df: pd.DataFrame, keys, aggregations) -> pd.DataFrame:
    """Table group. Takes `df`, `keys`, `aggregations`."""
    keys = _col_list(keys)
    agg_pairs = [(row[0], row[1]) for row in aggregations]
    if len(df) == 0:
        return pd.DataFrame(columns=[*keys, *[name for name, _ in agg_pairs]])
    rows = []
    for key_values, sub in df.groupby(keys, dropna=False):
        key_values = key_values if isinstance(key_values, tuple) else (key_values,)
        row = dict(zip(keys, key_values, strict=False))
        sub = sub.reset_index(drop=True)
        for name, agg_fn in agg_pairs:
            row[name] = agg_fn(sub)
        rows.append(row)
    return pd.DataFrame(rows)


def table_replace_error_values(df: pd.DataFrame, replacements) -> pd.DataFrame:
    """Table replace error values. Takes `df`, `replacements`."""
    out = df.copy()
    for pair in replacements:
        col, repl = pair[0], pair[1]
        if col in out.columns:
            out[col] = out[col].where(~out[col].isna(), repl)
    return out


def table_combine_columns(df: pd.DataFrame, columns, combiner: Callable, new_column: str) -> pd.DataFrame:
    """Table combine columns. Takes `df`, `columns`, `combiner`, `new_column`."""
    columns = _col_list(columns)
    out = df.copy()
    out[new_column] = out[columns].apply(lambda vals: combiner(list(vals)), axis=1)
    return out.drop(columns=columns)


def table_promote_headers(df: pd.DataFrame, *_opts) -> pd.DataFrame:
    """Table promote headers. Takes `df`."""
    if len(df) == 0:
        return df
    out = df.iloc[1:].reset_index(drop=True)
    out.columns = [str(v) for v in df.iloc[0]]
    return out


def table_pivot(df: pd.DataFrame, pivot_column: str, value_column: str) -> pd.DataFrame:
    """Table pivot. Takes `df`, `pivot_column`, `value_column`."""
    group_cols = [c for c in df.columns if c not in (pivot_column, value_column)]
    pivoted = df.pivot_table(index=group_cols or None, columns=pivot_column, values=value_column, aggfunc="first")
    return pivoted.reset_index()


def table_from_records(records: list[dict]) -> pd.DataFrame:
    """Table from records. Takes `records`."""
    return pd.DataFrame(records)


def table_from_list(items: list, *_opts) -> pd.DataFrame:
    """Table from list. Takes `items`."""
    return pd.DataFrame({"Column1": items})


def table_from_rows(rows: list, columns=None) -> pd.DataFrame:
    """Table from rows. Takes `rows`, `columns`."""
    return pd.DataFrame(rows, columns=_col_list(columns) if columns else None)


def table_combine(tables: list[pd.DataFrame]) -> pd.DataFrame:
    """Table combine. Takes `tables`."""
    return pd.concat(tables, ignore_index=True) if tables else pd.DataFrame()


def table_split_column(df: pd.DataFrame, column: str, splitter: Callable, names) -> pd.DataFrame:
    """Table split column. Takes `df`, `column`, `splitter`, `names`."""
    out = df.copy()
    names = _col_list(names) if not isinstance(names, int) else [f"{column}.{i + 1}" for i in range(names)]
    parts = out[column].apply(lambda v: splitter(v) if v is not None else [])
    for i, name in enumerate(names):
        out[name] = parts.apply(lambda p, _i=i: p[_i] if _i < len(p) else None)
    return out.drop(columns=[column])


def table_to_rows(df: pd.DataFrame) -> list:
    """Table to rows. Takes `df`."""
    return df.values.tolist()


# List.*
def list_select(items: list, predicate: Callable) -> list:
    """List select. Takes `items`, `predicate`."""
    return [x for x in items if predicate(x)]


def list_transform(items: list, fn: Callable) -> list:
    """List transform. Takes `items`, `fn`."""
    return [fn(x) for x in items]


def list_any_true(items: list) -> bool:
    """List any true. Takes `items`."""
    return any(bool(x) for x in items)


def list_remove_nulls(items: list) -> list:
    """List remove nulls. Takes `items`."""
    return [x for x in items if x is not None]


def list_dates(start, count: int, step=None) -> list:
    """List dates. Takes `start`, `count`, `step`."""
    ts = pd.Timestamp(start)
    step_td = step if isinstance(step, pd.Timedelta) else pd.Timedelta(days=step or 1)
    return [ts + step_td * i for i in range(int(count))]


def list_distinct(items: list) -> list:
    """List distinct. Takes `items`."""
    seen: list = []
    for x in items:
        if x not in seen:
            seen.append(x)
    return seen


def list_accumulate(items: list, seed, fn: Callable) -> Any:
    """List accumulate. Takes `items`, `seed`, `fn`."""
    state = seed
    for item in items:
        state = fn(state, item)
    return state


def list_contains(items: list, value) -> bool:
    """List contains. Takes `items`, `value`."""
    return any(x == value for x in items)


def list_first(items: list, default=None) -> Any:
    """List first. Takes `items`, `default`."""
    return items[0] if items else default


def list_max(items: list) -> Any:
    """List max. Takes `items`."""
    vals = [x for x in items if x is not None]
    return max(vals) if vals else None


def list_sum(items: list) -> Any:
    """List sum. Takes `items`."""
    return sum(x for x in items if x is not None)


# Text.*
def text_combine(items: list, delimiter: str = "") -> str:
    """Text combine. Takes `items`, `delimiter`."""
    return delimiter.join("" if x is None else str(x) for x in items)


def combiner_combine_text_by_delimiter(delimiter: str) -> Callable:
    """Combiner combine text by delimiter. Takes `delimiter`."""
    return lambda items: text_combine(items, delimiter)


def splitter_split_by_each_delimiter(delimiters: list) -> Callable:
    """Splitter split by each delimiter. Takes `delimiters`."""

    def split(text: str) -> list:
        """Split. Takes `text`."""
        if text is None:
            return []
        parts = [text]
        for delim in delimiters:
            parts = [p for part in parts for p in part.split(delim)]
        return parts

    return split


# I/O sources
class SqlDatabaseHandle:
    """SqlDatabaseHandle (see attributes/methods below)."""

    __slots__ = ("database", "server")

    def __init__(self, server: str, database: str):
        """Initialize."""
        self.server, self.database = server, database


class ODataFeedHandle:
    """ODataFeedHandle (see attributes/methods below)."""

    __slots__ = ("url",)

    def __init__(self, url: str):
        """Initialize."""
        self.url = url


def sql_database_handle(server: str, database: str, *_opts) -> SqlDatabaseHandle:
    """Sql database handle. Takes `server`, `database`."""
    return SqlDatabaseHandle(server, database)


def odata_feed_handle(url: str, *_opts) -> ODataFeedHandle:
    """Odata feed handle. Takes `url`."""
    return ODataFeedHandle(url)


def item_access(target: Any, index: Any) -> Any:
    """Item access. Takes `target`, `index`."""
    if isinstance(target, SqlDatabaseHandle):
        name = index.get("Item") or index.get("Name") if isinstance(index, dict) else index
        schema = index.get("Schema") if isinstance(index, dict) else None
        return sql_query(target.server, target.database, name, schema)
    if isinstance(target, ODataFeedHandle):
        name = index.get("Name") if isinstance(index, dict) else index
        return {"Name": name, "Data": odata_entity(target.url, name)}
    if isinstance(target, list):
        if isinstance(index, dict):
            for item in target:
                if isinstance(item, dict) and all(item.get(k) == v for k, v in index.items()):
                    return item
            raise KeyError(f"No item matching {index!r}")
        return target[int(index)]
    if isinstance(target, pd.DataFrame):
        return target.iloc[int(index)]
    return target[index]


def sql_query(server: str, database: str, table_or_query: str, schema: str | None = None) -> pd.DataFrame:
    """Sql query. Takes `server`, `database`, `table_or_query`, `schema`."""
    import sqlalchemy

    engine = sqlalchemy.create_engine(
        f"mssql+pyodbc://{server}/{database}?driver=ODBC+Driver+17+for+SQL+Server",
    )
    ref = f"[{schema}].[{table_or_query}]" if schema else table_or_query
    if table_or_query.strip().upper().startswith("SELECT"):
        return pd.read_sql(table_or_query, engine)
    return pd.read_sql(f"SELECT * FROM {ref}", engine)


def odata_entity(url: str, entity_set: str) -> pd.DataFrame:
    """Odata entity. Takes `url`, `entity_set`."""
    import requests

    resp = requests.get(f"{url.rstrip('/')}/{entity_set}", timeout=60)
    resp.raise_for_status()
    payload = resp.json()
    return pd.json_normalize(payload.get("value", payload))


def web_contents(url: str) -> bytes:
    """Web contents. Takes `url`."""
    import requests

    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    return resp.content


def file_contents(path: str) -> bytes:
    """File contents. Takes `path`."""
    with open(path, "rb") as fh:
        return fh.read()


def folder_files(path: str) -> list[dict]:
    """Folder files. Takes `path`."""
    from pathlib import Path

    return [
        {"Content": p.read_bytes(), "Name": p.name, "Extension": p.suffix, "Folder Path": str(p.parent)}
        for p in sorted(Path(path).glob("*"))
        if p.is_file()
    ]


def excel_workbook(binary: bytes) -> dict[str, pd.DataFrame]:
    """Excel workbook. Takes `binary`."""
    return pd.read_excel(io.BytesIO(binary), sheet_name=None)


def csv_document(data) -> pd.DataFrame:
    """Csv document. Takes `data`."""
    text = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else data
    df = pd.read_csv(io.StringIO(text), header=None)
    df.columns = [f"Column{i + 1}" for i in range(len(df.columns))]
    return df


def json_document(data) -> Any:
    """Json document. Takes `data`."""
    import json

    text = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else data
    return json.loads(text)


# Text.*
def text_contains(s, sub, *_comparer) -> bool:
    """Text contains. Takes `s`, `sub`."""
    return (sub in s) if s is not None else False


def text_starts_with(s, sub, *_comparer) -> bool:
    """Text starts with. Takes `s`, `sub`."""
    return s.startswith(sub) if s is not None else False


def text_ends_with(s, sub, *_comparer) -> bool:
    """Text ends with. Takes `s`, `sub`."""
    return s.endswith(sub) if s is not None else False


def text_lower(s):
    """Text lower. Takes `s`."""
    return s.lower() if s is not None else None


def text_upper(s):
    """Text upper. Takes `s`."""
    return s.upper() if s is not None else None


def text_proper(s):
    """Text proper. Takes `s`."""
    return s.title() if s is not None else None


def text_trim(s, *_chars):
    """Text trim. Takes `s`."""
    return s.strip() if s is not None else None


def text_trim_start(s, *_chars):
    """Text trim start. Takes `s`."""
    return s.lstrip() if s is not None else None


def text_trim_end(s, *_chars):
    """Text trim end. Takes `s`."""
    return s.rstrip() if s is not None else None


def text_from(value, *_culture) -> str:
    """Text from. Takes `value`."""
    return "" if value is None else str(value)


def text_length(s) -> int:
    """Text length. Takes `s`."""
    return len(s) if s is not None else 0


def text_replace(s, old, new):
    """Text replace. Takes `s`, `old`, `new`."""
    return s.replace(old, new) if s is not None else None


def text_split(s, sep) -> list:
    """Text split. Takes `s`, `sep`."""
    return s.split(sep) if s is not None else []


def text_middle(s, start, count=None):
    """Text middle. Takes `s`, `start`, `count`."""
    if s is None:
        return None
    return s[start : start + count] if count is not None else s[start:]


def text_start(s, count):
    """Text start. Takes `s`, `count`."""
    return s[:count] if s is not None else None


def text_end(s, count):
    """Text end. Takes `s`, `count`."""
    return s[-count:] if s is not None else None


def text_after_delimiter(s, delimiter, *_index):
    """Text after delimiter. Takes `s`, `delimiter`."""
    if s is None:
        return None
    idx = s.rfind(delimiter)
    return s[idx + len(delimiter) :] if idx != -1 else ""


def text_before_delimiter(s, delimiter, *_index):
    """Text before delimiter. Takes `s`, `delimiter`."""
    if s is None:
        return None
    idx = s.find(delimiter)
    return s[:idx] if idx != -1 else s


# Number.*
def number_from(value) -> float | None:
    """Number from. Takes `value`."""
    return float(value) if value is not None else None


def number_round(value, digits=0):
    """Number round. Takes `value`, `digits`."""
    return round(value, int(digits)) if value is not None else None


def number_abs(value):
    """Number abs. Takes `value`."""
    return abs(value) if value is not None else None


def number_integer_divide(a, b) -> int:
    """Number integer divide. Takes `a`, `b`."""
    return int(a) // int(b)


# Date.*
def date_from(value) -> pd.Timestamp:
    """Date from. Takes `value`."""
    return pd.Timestamp(value).normalize()


def date_year(d):
    """Date year. Takes `d`."""
    return pd.Timestamp(d).year if d is not None else None


def date_month(d):
    """Date month. Takes `d`."""
    return pd.Timestamp(d).month if d is not None else None


def date_day(d):
    """Date day. Takes `d`."""
    return pd.Timestamp(d).day if d is not None else None


def date_day_of_week(d, *_first_day):
    """Date day of week. Takes `d`."""
    return pd.Timestamp(d).dayofweek if d is not None else None


def date_week_of_year(d, *_first_day):
    """Date week of year. Takes `d`."""
    return pd.Timestamp(d).isocalendar()[1] if d is not None else None


def date_start_of_week(d, *_first_day):
    """Date start of week. Takes `d`."""
    ts = pd.Timestamp(d)
    return (ts - pd.Timedelta(days=ts.dayofweek)).normalize()


def date_end_of_week(d, *_first_day):
    """Date end of week. Takes `d`."""
    ts = pd.Timestamp(d)
    return (ts + pd.Timedelta(days=6 - ts.dayofweek)).normalize()


def date_to_text(d, *_format_and_culture):
    """Date to text. Takes `d`."""
    return pd.Timestamp(d).strftime("%Y-%m-%d") if d is not None else None


def datetime_local_now() -> pd.Timestamp:
    """Datetime local now."""
    return pd.Timestamp.now()


def duration_days(d) -> int:
    """Duration days. Takes `d`."""
    return d.days if hasattr(d, "days") else int(d)


# Record.*
def record_field_or_default(record: dict, field_name: str, default=None):
    """Record field or default. Takes `record`, `field_name`, `default`."""
    return record.get(field_name, default) if isinstance(record, dict) else default


def record_field(record: dict, field_name: str):
    """Record field. Takes `record`, `field_name`."""
    return record.get(field_name) if isinstance(record, dict) else None


# Value.*
def value_is(value, type_marker) -> bool:
    """Value is. Takes `value`, `type_marker`."""
    if value is None:
        return type_marker is None
    checks: dict[str, Callable] = {
        "Int64": lambda v: isinstance(v, int) or (isinstance(v, float) and float(v).is_integer()),
        "float": lambda v: isinstance(v, (int, float)),
        "string": lambda v: isinstance(v, str),
        "bool": lambda v: isinstance(v, bool),
        "date": lambda v: isinstance(v, pd.Timestamp),
        "datetime": lambda v: isinstance(v, pd.Timestamp),
    }
    check = checks.get(type_marker)
    return check(value) if check else True


def splitter_split_by_nothing(*_opts) -> Callable:
    """Splitter split by nothing."""
    return lambda text: [text]


def hash_table(columns, rows) -> pd.DataFrame:
    """Hash table. Takes `columns`, `rows`."""
    if isinstance(columns, (int, float)):
        col_names = [f"Column{i + 1}" for i in range(int(columns))]
    else:
        col_names = _col_list(columns)
    return pd.DataFrame(rows, columns=col_names)


def hash_date(year, month, day) -> pd.Timestamp:
    """Hash date. Takes `year`, `month`, `day`."""
    return pd.Timestamp(int(year), int(month), int(day))


def hash_datetime(year, month, day, hour, minute, second) -> pd.Timestamp:  # noqa: PLR0913, PLR0917
    """Hash datetime. Takes `year`, `month`, `day`, `hour`, `minute`, `second`."""
    return pd.Timestamp(int(year), int(month), int(day), int(hour), int(minute), int(second))


def hash_duration(days, hours, minutes, seconds) -> pd.Timedelta:
    """Hash duration. Takes `days`, `hours`, `minutes`, `seconds`."""
    return pd.Timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)


def try_or(fn: Callable, otherwise: Callable):
    """Try or. Takes `fn`, `otherwise`."""
    try:
        return fn()
    except Exception:
        return otherwise()


def raise_m_error(message):
    """Raise m error. Takes `message`."""
    raise RuntimeError(f"M `error` raised: {message}")


def binary_from_text(text: str, encoding=None) -> bytes:
    """Binary from text. Takes `text`, `encoding`."""
    import base64

    return base64.b64decode(text) if encoding == "base64" else bytes.fromhex(text)


def binary_decompress(data: bytes, compression=None) -> bytes:
    """Binary decompress. Takes `data`, `compression`."""
    import zlib

    return zlib.decompress(data, -zlib.MAX_WBITS) if compression == "deflate" else zlib.decompress(data)
