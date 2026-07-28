import io
from datetime import date, datetime

import pandas as pd
import pytest

from pbix_atlas import m_ops


def test_field():
    df = pd.DataFrame({"A": [1, 2]})
    assert m_ops.field(df, "A") == [1, 2]
    assert m_ops.field({"b": 2}, "b") == 2
    assert m_ops.field([1, 2, 3], 1) == 2


def test_table_select_rows():
    df = pd.DataFrame({"A": [1, 2, 3], "B": ["x", "y", "z"]})
    result = m_ops.table_select_rows(df, lambda r: r["A"] > 1)
    assert list(result["A"]) == [2, 3]

    empty = pd.DataFrame({"A": []})
    assert len(m_ops.table_select_rows(empty, lambda r: r["A"] > 1)) == 0


def test_table_add_column():
    df = pd.DataFrame({"A": [1, 2]})
    result = m_ops.table_add_column(df, "B", lambda r: r["A"] * 10)
    assert list(result["B"]) == [10, 20]

    empty = pd.DataFrame({"A": []}).astype({"A": int})
    result_empty = m_ops.table_add_column(empty, "B", lambda r: r["A"])
    assert len(result_empty) == 0


def test_table_select_columns():
    df = pd.DataFrame({"A": [1], "B": [2], "C": [3]})
    result = m_ops.table_select_columns(df, ["A", "C"])
    assert list(result.columns) == ["A", "C"]

    result2 = m_ops.table_select_columns(df, "A")
    assert list(result2.columns) == ["A"]


def test_table_remove_columns():
    df = pd.DataFrame({"A": [1], "B": [2], "C": [3]})
    result = m_ops.table_remove_columns(df, ["A", "C"])
    assert list(result.columns) == ["B"]

    result2 = m_ops.table_remove_columns(df, "X")
    assert list(result2.columns) == ["A", "B", "C"]


def test_table_rename_columns():
    df = pd.DataFrame({"A": [1], "B": [2]})
    result = m_ops.table_rename_columns(df, [["A", "Z"]])
    assert list(result.columns) == ["Z", "B"]


def test_table_reorder_columns():
    df = pd.DataFrame({"A": [1], "B": [2], "C": [3]})
    result = m_ops.table_reorder_columns(df, ["C", "A"])
    assert list(result.columns[:2]) == ["C", "A"]


def test_table_sort():
    df = pd.DataFrame({"A": [3, 1, 2], "B": ["c", "a", "b"]})
    result = m_ops.table_sort(df, [["A", "asc"]])
    assert list(result["A"]) == [1, 2, 3]

    result2 = m_ops.table_sort(df, [["A", "desc"]])
    assert list(result2["A"]) == [3, 2, 1]


def test_table_distinct():
    df = pd.DataFrame({"A": [1, 1, 2], "B": [1, 1, 2]})
    result = m_ops.table_distinct(df)
    assert len(result) == 2

    result2 = m_ops.table_distinct(df, "A")
    assert len(result2) == 2

    result3 = m_ops.table_distinct(df, ["A", "B"])
    assert len(result3) == 2


def test_table_column_names():
    df = pd.DataFrame({"A": [1], "B": [2]})
    assert m_ops.table_column_names(df) == ["A", "B"]


def test_table_transform_column_types():
    df = pd.DataFrame({"A": ["1", "2"], "B": ["3.5", "4.5"]})
    result = m_ops.table_transform_column_types(df, [["A", "Int64"], ["B", "float"]])
    assert result["A"].dtype.name == "Int64"
    assert result["B"].dtype.name == "float64"

    df2 = pd.DataFrame({"A": ["2021-01-01"]})
    result2 = m_ops.table_transform_column_types(df2, [["A", "date"]])
    assert pd.api.types.is_datetime64_any_dtype(result2["A"])

    result3 = m_ops.table_transform_column_types(df, [["X", "Int64"]])
    assert list(result3.columns) == ["A", "B"]


def test_table_transform_columns():
    df = pd.DataFrame({"A": [1, 2]})
    result = m_ops.table_transform_columns(df, [["A", lambda x: x * 10]])
    assert list(result["A"]) == [10, 20]

    result2 = m_ops.table_transform_columns(df, [["X", lambda x: x]])
    assert list(result2["A"]) == [1, 2]


def test_is_m_null():
    assert m_ops._is_m_null(None) is True
    assert m_ops._is_m_null(float("nan")) is True
    assert m_ops._is_m_null(pd.NA) is True
    assert m_ops._is_m_null(0) is False
    assert m_ops._is_m_null("") is False


def test_default_replacer():
    assert m_ops.default_replacer("a", "a", "b") == "b"
    assert m_ops.default_replacer("a", "x", "b") == "a"
    assert m_ops.default_replacer("a", True, "b") == "b"
    assert m_ops.default_replacer("a", False, "b") == "a"


def test_default_text_replacer():
    assert m_ops.default_text_replacer("hello world", "world", "there") == "hello there"
    assert m_ops.default_text_replacer(42, "world", "there") == 42


def test_table_replace_value():
    df = pd.DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]})
    result = m_ops.table_replace_value(df, 2, 99, m_ops.default_replacer, ["A"])
    assert list(result["A"]) == [1, 99, 3]

    result3 = m_ops.table_replace_value(df, 2, 99, m_ops.default_replacer, ["X"])
    assert list(result3["A"]) == [1, 2, 3]


def test_table_replace_value_predicate():
    df = pd.DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]})
    result = m_ops.table_replace_value(
        df, lambda row: row["A"] > 1, 0, m_ops.default_replacer, ["A", "B"]
    )
    assert list(result["A"]) == [1, 0, 0]
    assert list(result["B"]) == [4, 5, 6]


def test_table_nested_join():
    left = pd.DataFrame({"Key": [1, 2, 3]})
    right = pd.DataFrame({"Key": [1, 2], "Val": ["a", "b"]})
    result = m_ops.table_nested_join(left, "Key", right, "Key", "Joined")
    assert "Joined" in result.columns
    assert len(result) == 3
    assert len(result.iloc[0]["Joined"]) == 1

    result2 = m_ops.table_nested_join(
        left[:0], "Key", right, "Key", "Joined"
    )
    assert len(result2) == 0


def test_table_expand_table_column():
    left = pd.DataFrame({"Key": [1, 2], "Nested": [pd.DataFrame({"V": ["a"]}), pd.DataFrame({"V": ["b"]})]})
    result = m_ops.table_expand_table_column(left, "Nested", ["V"], ["Value"])
    assert list(result["Value"]) == ["a", "b"]
    assert list(result["Key"]) == [1, 2]

    left_with_empty = pd.DataFrame({"Key": [1], "Nested": [pd.DataFrame()]})
    result2 = m_ops.table_expand_table_column(left_with_empty, "Nested", ["V"])
    assert pd.isna(result2.iloc[0]["V"])


def test_table_expand_record_column():
    df = pd.DataFrame({"A": [1], "Rec": [{"x": 10, "y": 20}]})
    result = m_ops.table_expand_record_column(df, "Rec", ["x", "y"], ["Xval", "Yval"])
    assert list(result["Xval"]) == [10]
    assert list(result["Yval"]) == [20]
    assert "Rec" not in result.columns

    df2 = pd.DataFrame({"A": [1], "Rec": [None]})
    result2 = m_ops.table_expand_record_column(df2, "Rec", ["x"])
    assert pd.isna(result2.iloc[0]["x"])


def test_table_group():
    df = pd.DataFrame({"Cat": ["a", "a", "b"], "Val": [1, 2, 3]})
    result = m_ops.table_group(df, ["Cat"], [["Total", lambda sub: sub["Val"].sum()]])
    assert set(result.columns) >= {"Cat", "Total"}
    totals = dict(zip(result["Cat"], result["Total"]))
    assert totals["a"] == 3
    assert totals["b"] == 3

    empty = pd.DataFrame({"Cat": [], "Val": []})
    result2 = m_ops.table_group(empty, ["Cat"], [["Total", lambda sub: 0]])
    assert list(result2.columns) == ["Cat", "Total"]
    assert len(result2) == 0


def test_table_replace_error_values():
    df = pd.DataFrame({"A": [1, None, 3], "B": [4, 5, None]})
    result = m_ops.table_replace_error_values(df, [["A", 0], ["B", -1]])
    assert result["A"].tolist() == [1.0, 0.0, 3.0]
    assert result["B"].tolist() == [4.0, 5.0, -1.0]

    result2 = m_ops.table_replace_error_values(df, [["X", 0]])
    assert result2["A"].iloc[0] == 1.0
    assert pd.isna(result2["A"].iloc[1])
    assert result2["A"].iloc[2] == 3.0


def test_table_combine_columns():
    df = pd.DataFrame({"First": ["a", "c"], "Last": ["b", "d"]})
    result = m_ops.table_combine_columns(df, ["First", "Last"], lambda vals: "".join(vals), "Full")
    assert list(result["Full"]) == ["ab", "cd"]
    assert "First" not in result.columns


def test_table_promote_headers():
    df = pd.DataFrame({0: ["H1", "a"], 1: ["H2", "b"]})
    result = m_ops.table_promote_headers(df)
    assert list(result.columns) == ["H1", "H2"]
    assert list(result["H1"]) == ["a"]

    empty = pd.DataFrame()
    result2 = m_ops.table_promote_headers(empty)
    assert len(result2) == 0


def test_table_pivot():
    df = pd.DataFrame({"Cat": ["x", "x", "y"], "Attr": ["A", "B", "A"], "Val": [1, 2, 3]})
    result = m_ops.table_pivot(df, "Attr", "Val")
    assert "A" in result.columns
    assert "B" in result.columns


def test_table_from_records():
    result = m_ops.table_from_records([{"a": 1}, {"a": 2}])
    assert list(result["a"]) == [1, 2]


def test_table_from_list():
    result = m_ops.table_from_list([1, 2, 3])
    assert list(result["Column1"]) == [1, 2, 3]


def test_table_from_rows():
    result = m_ops.table_from_rows([[1, "a"], [2, "b"]], columns=["X", "Y"])
    assert list(result["X"]) == [1, 2]

    result2 = m_ops.table_from_rows([[1], [2]])
    assert list(result2.iloc[:, 0]) == [1, 2]


def test_table_combine():
    df1 = pd.DataFrame({"A": [1]})
    df2 = pd.DataFrame({"A": [2]})
    result = m_ops.table_combine([df1, df2])
    assert list(result["A"]) == [1, 2]

    assert len(m_ops.table_combine([])) == 0


def test_table_split_column():
    df = pd.DataFrame({"A": ["a,b", "c,d"]})
    result = m_ops.table_split_column(df, "A", lambda v: v.split(","), ["X", "Y"])
    assert list(result["X"]) == ["a", "c"]
    assert list(result["Y"]) == ["b", "d"]
    assert "A" not in result.columns

    result2 = m_ops.table_split_column(df, "A", lambda v: v.split(","), ["X", "Y", "Z"])

    df_none = pd.DataFrame({"A": [None]})
    result3 = m_ops.table_split_column(df_none, "A", lambda v: v.split(","), 2)
    assert "A.1" in result3.columns


def test_table_to_rows():
    df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
    result = m_ops.table_to_rows(df)
    assert result == [[1, 3], [2, 4]]


class TestListOps:
    def test_list_select(self):
        assert m_ops.list_select([1, 2, 3], lambda x: x > 1) == [2, 3]

    def test_list_transform(self):
        assert m_ops.list_transform([1, 2, 3], lambda x: x * 2) == [2, 4, 6]

    def test_list_any_true(self):
        assert m_ops.list_any_true([False, True]) is True
        assert m_ops.list_any_true([False, False]) is False

    def test_list_remove_nulls(self):
        assert m_ops.list_remove_nulls([1, None, 2]) == [1, 2]

    def test_list_dates(self):
        result = m_ops.list_dates("2024-01-01", 3)
        assert len(result) == 3
        assert str(result[0])[:10] == "2024-01-01"

        result2 = m_ops.list_dates("2024-01-01", 2, pd.Timedelta(days=2))
        assert (result2[1] - result2[0]).days == 2

    def test_list_distinct(self):
        assert m_ops.list_distinct([1, 2, 1, 3]) == [1, 2, 3]

    def test_list_accumulate(self):
        result = m_ops.list_accumulate([1, 2, 3], 0, lambda s, x: s + x)
        assert result == 6

    def test_list_contains(self):
        assert m_ops.list_contains([1, 2, 3], 2) is True
        assert m_ops.list_contains([1, 2, 3], 4) is False

    def test_list_first(self):
        assert m_ops.list_first([1, 2]) == 1
        assert m_ops.list_first([]) is None
        assert m_ops.list_first([], default=0) == 0

    def test_list_max(self):
        assert m_ops.list_max([1, 5, 3]) == 5
        assert m_ops.list_max([None, 1]) == 1
        assert m_ops.list_max([]) is None

    def test_list_sum(self):
        assert m_ops.list_sum([1, 2, 3]) == 6
        assert m_ops.list_sum([1, None, 3]) == 4


class TestTextOps:
    def test_text_combine(self):
        assert m_ops.text_combine(["a", "b"], "-") == "a-b"
        assert m_ops.text_combine(["a", None]) == "a"

    def test_combiner_combine_text_by_delimiter(self):
        fn = m_ops.combiner_combine_text_by_delimiter("-")
        assert fn(["a", "b"]) == "a-b"

    def test_splitter_split_by_each_delimiter(self):
        fn = m_ops.splitter_split_by_each_delimiter(["-", " "])
        assert fn("a-b c") == ["a", "b", "c"]
        assert fn(None) == []

    def test_text_contains(self):
        assert m_ops.text_contains("hello", "ell") is True
        assert m_ops.text_contains("hello", "xyz") is False
        assert m_ops.text_contains(None, "x") is False

    def test_text_starts_with(self):
        assert m_ops.text_starts_with("hello", "he") is True
        assert m_ops.text_starts_with(None, "he") is False

    def test_text_ends_with(self):
        assert m_ops.text_ends_with("hello", "lo") is True
        assert m_ops.text_ends_with(None, "lo") is False

    def test_text_lower(self):
        assert m_ops.text_lower("ABC") == "abc"
        assert m_ops.text_lower(None) is None

    def test_text_upper(self):
        assert m_ops.text_upper("abc") == "ABC"
        assert m_ops.text_upper(None) is None

    def test_text_proper(self):
        assert m_ops.text_proper("hello world") == "Hello World"
        assert m_ops.text_proper(None) is None

    def test_text_trim(self):
        assert m_ops.text_trim("  hi  ") == "hi"
        assert m_ops.text_trim(None) is None

    def test_text_trim_start(self):
        assert m_ops.text_trim_start("  hi  ") == "hi  "
        assert m_ops.text_trim_start(None) is None

    def test_text_trim_end(self):
        assert m_ops.text_trim_end("  hi  ") == "  hi"
        assert m_ops.text_trim_end(None) is None

    def test_text_from(self):
        assert m_ops.text_from(42) == "42"
        assert m_ops.text_from(None) == ""

    def test_text_length(self):
        assert m_ops.text_length("abc") == 3
        assert m_ops.text_length(None) == 0

    def test_text_replace(self):
        assert m_ops.text_replace("hello", "l", "x") == "hexxo"
        assert m_ops.text_replace(None, "l", "x") is None

    def test_text_split(self):
        assert m_ops.text_split("a,b,c", ",") == ["a", "b", "c"]
        assert m_ops.text_split(None, ",") == []

    def test_text_middle(self):
        assert m_ops.text_middle("hello", 1, 3) == "ell"
        assert m_ops.text_middle("hello", 1) == "ello"
        assert m_ops.text_middle(None, 1) is None

    def test_text_start(self):
        assert m_ops.text_start("hello", 2) == "he"
        assert m_ops.text_start(None, 2) is None

    def test_text_end(self):
        assert m_ops.text_end("hello", 2) == "lo"
        assert m_ops.text_end(None, 2) is None

    def test_text_after_delimiter(self):
        assert m_ops.text_after_delimiter("a-b-c", "-") == "c"
        assert m_ops.text_after_delimiter("abc", "-") == ""
        assert m_ops.text_after_delimiter(None, "-") is None

    def test_text_before_delimiter(self):
        assert m_ops.text_before_delimiter("a-b-c", "-") == "a"
        assert m_ops.text_before_delimiter("abc", "-") == "abc"
        assert m_ops.text_before_delimiter(None, "-") is None


class TestNumberOps:
    def test_number_from(self):
        assert m_ops.number_from("42") == 42.0
        assert m_ops.number_from(None) is None

    def test_number_round(self):
        assert m_ops.number_round(3.14159, 2) == 3.14
        assert m_ops.number_round(None) is None

    def test_number_abs(self):
        assert m_ops.number_abs(-5) == 5
        assert m_ops.number_abs(None) is None

    def test_number_integer_divide(self):
        assert m_ops.number_integer_divide(7, 3) == 2


class TestDateOps:
    def test_date_from(self):
        result = m_ops.date_from("2024-01-15")
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_date_year(self):
        assert m_ops.date_year(pd.Timestamp("2024-06-15")) == 2024
        assert m_ops.date_year(None) is None

    def test_date_month(self):
        assert m_ops.date_month(pd.Timestamp("2024-06-15")) == 6
        assert m_ops.date_month(None) is None

    def test_date_day(self):
        assert m_ops.date_day(pd.Timestamp("2024-06-15")) == 15
        assert m_ops.date_day(None) is None

    def test_date_day_of_week(self):
        assert m_ops.date_day_of_week(pd.Timestamp("2024-01-01")) is not None
        assert m_ops.date_day_of_week(None) is None

    def test_date_week_of_year(self):
        assert m_ops.date_week_of_year(pd.Timestamp("2024-01-01")) is not None
        assert m_ops.date_week_of_year(None) is None

    def test_date_start_of_week(self):
        result = m_ops.date_start_of_week("2024-01-10")
        assert result.dayofweek == 0

    def test_date_end_of_week(self):
        result = m_ops.date_end_of_week("2024-01-10")
        assert result.dayofweek == 6

    def test_date_to_text(self):
        assert m_ops.date_to_text(pd.Timestamp("2024-06-15")) == "2024-06-15"
        assert m_ops.date_to_text(None) is None

    def test_datetime_local_now(self):
        result = m_ops.datetime_local_now()
        assert isinstance(result, pd.Timestamp)

    def test_duration_days(self):
        assert m_ops.duration_days(pd.Timedelta(days=5)) == 5
        assert m_ops.duration_days(3) == 3


class TestRecordOps:
    def test_record_field_or_default(self):
        assert m_ops.record_field_or_default({"a": 1}, "a") == 1
        assert m_ops.record_field_or_default({"a": 1}, "b") is None
        assert m_ops.record_field_or_default({"a": 1}, "b", 42) == 42
        assert m_ops.record_field_or_default(None, "a") is None

    def test_record_field(self):
        assert m_ops.record_field({"a": 1}, "a") == 1
        assert m_ops.record_field({"a": 1}, "b") is None
        assert m_ops.record_field(None, "a") is None


class TestValueOps:
    def test_value_is(self):
        assert m_ops.value_is(42, "Int64") is True
        assert m_ops.value_is(3.14, "float") is True
        assert m_ops.value_is("hi", "string") is True
        assert m_ops.value_is(True, "bool") is True
        assert m_ops.value_is(pd.Timestamp.now(), "date") is True
        assert m_ops.value_is("hi", "Int64") is False
        assert m_ops.value_is(None, None) is True
        assert m_ops.value_is(None, "string") is False
        assert m_ops.value_is(42, "unknown_type") is True


class TestIOCreateOps:
    def test_sql_database_handle(self):
        h = m_ops.sql_database_handle("myserver", "mydb")
        assert h.server == "myserver"
        assert h.database == "mydb"

    def test_odata_feed_handle(self):
        h = m_ops.odata_feed_handle("https://example.com/odata")
        assert h.url == "https://example.com/odata"


def test_item_access():
    lst = [{"id": 1, "val": "a"}, {"id": 2, "val": "b"}]
    assert m_ops.item_access(lst, 0) == {"id": 1, "val": "a"}
    assert m_ops.item_access(lst, {"id": 2}) == {"id": 2, "val": "b"}
    with pytest.raises(KeyError):
        m_ops.item_access(lst, {"id": 99})

    df = pd.DataFrame({"A": [10, 20]})
    result = m_ops.item_access(df, 0)
    assert result["A"] == 10

    d = {"key": "value"}
    assert m_ops.item_access(d, "key") == "value"


def test_file_contents(tmp_path):
    p = tmp_path / "test.txt"
    p.write_bytes(b"hello")
    assert m_ops.file_contents(str(p)) == b"hello"


def test_folder_files(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"a")
    (tmp_path / "b.csv").write_bytes(b"b,c")
    files = m_ops.folder_files(str(tmp_path))
    assert len(files) == 2
    names = {f["Name"] for f in files}
    assert names == {"a.txt", "b.csv"}


def test_excel_workbook():
    pytest.importorskip("openpyxl")
    df = pd.DataFrame({"A": [1]})
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Sheet1", index=False)
    buf.seek(0)
    result = m_ops.excel_workbook(buf.getvalue())
    assert "Sheet1" in result
    assert list(result["Sheet1"]["A"]) == [1]


def test_csv_document():
    result = m_ops.csv_document(b"a,b\n1,2\n3,4")
    assert list(result["Column1"]) == ["a", "1", "3"]
    assert list(result["Column2"]) == ["b", "2", "4"]

    result2 = m_ops.csv_document("x,y\n1,2")
    assert list(result2["Column1"]) == ["x", "1"]


def test_json_document():
    result = m_ops.json_document(b'{"a": 1}')
    assert result == {"a": 1}

    result2 = m_ops.json_document('{"b": 2}')
    assert result2 == {"b": 2}


class TestSpecialOps:
    def test_splitter_split_by_nothing(self):
        fn = m_ops.splitter_split_by_nothing()
        assert fn("hello") == ["hello"]

    def test_hash_table(self):
        result = m_ops.hash_table(["A", "B"], [[1, 2], [3, 4]])
        assert list(result["A"]) == [1, 3]

        result2 = m_ops.hash_table(2, [[1, 2]])
        assert list(result2.columns) == ["Column1", "Column2"]

    def test_hash_date(self):
        result = m_ops.hash_date(2024, 1, 15)
        assert result.year == 2024

    def test_hash_datetime(self):
        result = m_ops.hash_datetime(2024, 1, 15, 10, 30, 0)
        assert result.hour == 10

    def test_hash_duration(self):
        result = m_ops.hash_duration(1, 2, 3, 4)
        assert result.days == 1

    def test_try_or_success(self):
        assert m_ops.try_or(lambda: 42, lambda: 0) == 42

    def test_try_or_failure(self):
        assert m_ops.try_or(lambda: 1 / 0, lambda: -1) == -1

    def test_raise_m_error(self):
        with pytest.raises(RuntimeError, match="M `error` raised"):
            m_ops.raise_m_error("test error")

    def test_binary_from_text(self):
        import base64
        result = m_ops.binary_from_text("aGVsbG8=", "base64")
        assert result == b"hello"
        result2 = m_ops.binary_from_text("68656c6c6f")
        assert result2 == b"hello"

    def test_binary_decompress(self):
        import zlib
        data = zlib.compress(b"hello")
        result = m_ops.binary_decompress(data)
        assert result == b"hello"

        data2 = zlib.compress(b"world")[2:-4]
        result2 = m_ops.binary_decompress(data2, "deflate")
        assert result2 == b"world"
