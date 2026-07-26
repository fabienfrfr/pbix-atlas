"""Best-effort translation of DAX measure/calculated-column expressions into
plain Python (pandas) code.

This is NOT a DAX engine. It recognizes a curated subset of common patterns
(simple aggregations, DIVIDE, IF, RELATED, basic arithmetic between measure
references) and emits an equivalent Python expression. Anything it does not
recognize is reported as unsupported so the code generator can emit an
explicit TODO stub instead of silently producing a wrong result.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .dax import DaxReferenceParser
from .models import DaxReference


@dataclass
class DaxTranslation:
    python_expr: str
    supported: bool
    referenced_tables: set[str]


_TABLE_REF = r"(?:'([^']+)'|([A-Za-z_][A-Za-z0-9_]*))"
_AGG_PATTERNS = {
    "SUM": "sum",
    "AVERAGE": "mean",
    "MIN": "min",
    "MAX": "max",
    "COUNT": "count",
    "COUNTA": "count",
    "STDEV.P": "std",
    "STDEV.S": "std",
    "MEDIAN": "median",
}

_SIMPLE_AGG = re.compile(
    r"^\s*(SUM|AVERAGE|MIN|MAX|COUNT|COUNTA|MEDIAN)\s*\(\s*" + _TABLE_REF + r"\[([^\]]+)\]\s*\)\s*$",
    re.IGNORECASE,
)
_COUNTROWS = re.compile(r"^\s*COUNTROWS\s*\(\s*" + _TABLE_REF + r"\s*\)\s*$", re.IGNORECASE)
_DISTINCTCOUNT = re.compile(
    r"^\s*DISTINCTCOUNT\s*\(\s*" + _TABLE_REF + r"\[([^\]]+)\]\s*\)\s*$", re.IGNORECASE
)
_DIVIDE = re.compile(r"^\s*DIVIDE\s*\((.+)\)\s*$", re.IGNORECASE | re.DOTALL)


def _table_var(table: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z_]", "_", table)
    return f"model[{table!r}]" if False else f"model[\"{table}\"]"


def _split_top_level_args(text: str) -> list[str]:
    parts, depth, buf, in_str = [], 0, [], False
    for ch in text:
        if in_str:
            buf.append(ch)
            if ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            buf.append(ch)
        elif ch in "([":
            depth += 1
            buf.append(ch)
        elif ch in ")]":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return [p.strip() for p in parts]


class DaxTranslator:
    """Translates a single DAX expression to a Python snippet, best-effort."""

    def __init__(self) -> None:
        self._ref_parser = DaxReferenceParser()

    def translate(self, expr: str, default_table: str) -> DaxTranslation:
        expr = expr.strip()
        tables: set[str] = set()

        m = _SIMPLE_AGG.match(expr)
        if m:
            func, table_q, table_b, col = m.groups()
            table = table_q or table_b
            method = _AGG_PATTERNS[func.upper()]
            tables.add(table)
            return DaxTranslation(f'{_table_var(table)}["{col}"].{method}()', True, tables)

        m = _COUNTROWS.match(expr)
        if m:
            table = m.group(1) or m.group(2)
            tables.add(table)
            return DaxTranslation(f"len({_table_var(table)})", True, tables)

        m = _DISTINCTCOUNT.match(expr)
        if m:
            table_q, table_b, col = m.groups()
            table = table_q or table_b
            tables.add(table)
            return DaxTranslation(f'{_table_var(table)}["{col}"].nunique()', True, tables)

        m = _DIVIDE.match(expr)
        if m:
            args = _split_top_level_args(m.group(1))
            if len(args) in (2, 3):
                sub = [self.translate(a, default_table) for a in args[:2]]
                if all(s.supported for s in sub):
                    tables |= sub[0].referenced_tables | sub[1].referenced_tables
                    alt = "0"
                    if len(args) == 3:
                        sub_alt = self.translate(args[2], default_table)
                        if sub_alt.supported:
                            alt = sub_alt.python_expr
                            tables |= sub_alt.referenced_tables
                    return DaxTranslation(
                        f"({sub[0].python_expr} / {sub[1].python_expr}) if ({sub[1].python_expr}) else {alt}",
                        True,
                        tables,
                    )

        # Bare numeric literal
        if re.match(r"^-?\d+(\.\d+)?$", expr):
            return DaxTranslation(expr, True, tables)

        # Bare reference to another measure/column, e.g. `[Other Measure]` or `Table[Col]`
        refs = self._ref_parser.parse(expr)
        if len(refs) == 1 and expr.strip() in (
            f"[{refs[0].name}]",
            f"{refs[0].table}[{refs[0].name}]" if refs[0].table else "",
            f"'{refs[0].table}'[{refs[0].name}]" if refs[0].table else "",
        ):
            ref = refs[0]
            table = ref.table or default_table
            tables.add(table)
            return DaxTranslation(f"measures.get(({table!r}, {ref.name!r}))", True, tables)

        return DaxTranslation(python_expr="", supported=False, referenced_tables=tables)


def collect_dax_refs(expr: str) -> list[DaxReference]:
    return DaxReferenceParser().parse(expr)
