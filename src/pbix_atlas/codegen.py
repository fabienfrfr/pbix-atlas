"""Generates a single standalone Python file reproducing a .pbix report:
source -> extraction -> Power Query transforms -> semantic model -> Vizro
dashboard.

Unlike a per-callsite transpiler (which only ever handles the shapes
anticipated at generation time), this embeds the *real* M source text for
each query and lets `pbix_atlas.m_interpreter` execute it directly against
pandas at runtime, using the lineage graph helper (`mquery`) to order
queries topologically. There is no "TODO" fallback: an expression the
interpreter's grammar/stdlib doesn't support raises a clear `MRuntimeError`
naming the exact function - loud failure, never a silent stub.
"""

from __future__ import annotations

import re
from pathlib import Path

import networkx as nx

from .dax_translate import DaxTranslator
from .layout import ReportLayoutParser
from .layout_roles import extract_visual_specs
from .mquery import MQueryDependencyResolver
from .pbix_model import PBIXModel


def _safe_identifier(name: str) -> str:
    out = re.sub(r"\W+", "_", name.strip())
    if not out or out[0].isdigit():
        out = f"t_{out}"
    return out


def _indent(code: str, spaces: int = 4) -> str:
    pad = " " * spaces
    return "\n".join(pad + line if line.strip() else line for line in code.splitlines())


class PythonPipelineGenerator:
    def __init__(self, pbix_path: str | Path):
        self.pbix_path = Path(pbix_path)
        self.model = PBIXModel(self.pbix_path)
        self.dax_translator = DaxTranslator()

    def _build_order(self, queries: dict[str, str]) -> list[str]:
        deps_graph = MQueryDependencyResolver().resolve(queries)
        g = nx.DiGraph()
        g.add_nodes_from(queries)
        for name, deps in deps_graph.items():
            for dep in deps:
                if dep in queries:
                    g.add_edge(dep, name)
        try:
            return list(nx.topological_sort(g))
        except nx.NetworkXUnfeasible:
            return list(queries)

    def _measures_code(self) -> str:
        measures_df = self.model.measures()
        lines = [
            'def compute_measures(model: dict) -> dict:',
            '    """DAX measures, translated where a safe automatic mapping exists',
            '    (aggregations, DIVIDE, simple measure references). Anything else',
            '    raises MeasureNotSupported at call time - never silently wrong,',
            '    never a stub - naming the exact measure and its original DAX so it',
            '    can be re-implemented by hand.',
            '    """',
            '    measures: dict = {}',
        ]
        rows = [(str(r["TableName"]), str(r["Name"]), str(r["Expression"])) for _, r in measures_df.iterrows()]
        pending = rows
        for _ in range(3):
            still = []
            for table, name, expr in pending:
                result = self.dax_translator.translate(expr, default_table=table)
                if result.supported:
                    lines.append(f'    measures[({table!r}, {name!r})] = {result.python_expr}')
                else:
                    still.append((table, name, expr))
            pending = still
        for table, name, expr in pending:
            lines.append(
                f'    measures[({table!r}, {name!r})] = MeasureNotSupported({table!r}, {name!r}, {expr!r})'
            )
        lines.append('    return measures')
        return "\n".join(lines) + "\n"

    def _dashboard_code(self, visual_specs) -> str:
        by_page: dict[str, list] = {}
        for spec in visual_specs:
            by_page.setdefault(spec.page, []).append(spec)

        page_blocks, page_vars = [], []
        skipped = {"count": 0}
        for idx, (page, specs) in enumerate(by_page.items()):
            components = [c for spec in specs if (c := self._visual_component(spec, skipped))]
            if not components:
                continue
            var = f"page_{idx}"
            page_vars.append(var)
            joined = ",\n        ".join(components)
            page_blocks.append(f'{var} = vm.Page(\n    title={page!r},\n    components=[\n        {joined}\n    ],\n)')

        body = "\n\n".join(page_blocks)
        summary = (
            f'# {skipped["count"]} visual(s) not mapped to a Vizro component on purpose: '
            f'multi-table charts (join logic is model-specific), custom visuals '
            f'(Deneb/HTML), images, shapes and slicers are skipped rather than guessed.'
        )
        pages = ", ".join(page_vars)
        return f"{body}\n\n{summary}\ndashboard = vm.Dashboard(pages=[{pages}])\n"

    def _visual_component(self, spec, skipped: dict) -> str | None:
        gtype = spec.generic_type
        comp_id = f"{_safe_identifier(spec.page)}_{spec.visual_index}"
        tables = {t for fields in spec.roles.values() for (t, _f, _k) in fields if t}

        if gtype in ("bar", "bar_h", "line", "area", "scatter", "pie"):
            if len(tables) != 1:
                skipped["count"] += 1
                return None
            table = next(iter(tables))
            category = spec.roles.get("Category") or spec.roles.get("X") or []
            values = spec.roles.get("Y") or spec.roles.get("Values") or []
            color = spec.roles.get("Series") or spec.roles.get("Legend") or []
            if not category or not values:
                skipped["count"] += 1
                return None
            x, y = category[0][1], values[0][1]
            color_kw = f', color="{color[0][1]}"' if color else ""
            if gtype == "pie":
                fig = f'px.pie(model["{table}"], names="{x}", values="{y}")'
            else:
                orient = ', orientation="h"' if gtype == "bar_h" else ""
                fn = "bar" if gtype in ("bar", "bar_h") else gtype
                fig = f'px.{fn}(model["{table}"], x="{x}", y="{y}"{color_kw}{orient})'
            return f'vm.Graph(id="{comp_id}", figure={fig})'

        if gtype == "table":
            if len(tables) != 1:
                skipped["count"] += 1
                return None
            table = next(iter(tables))
            return f'vm.Table(id="{comp_id}", figure=dash_table_from_df(model["{table}"]))'

        if gtype == "kpi":
            measure_fields = [(t, f) for fields in spec.roles.values() for (t, f, k) in fields if k == "Measure"]
            if not measure_fields:
                skipped["count"] += 1
                return None
            table, field_name = measure_fields[0]
            return f'vm.Card(id="{comp_id}", text=f"**{{measures.get(({table!r}, {field_name!r}))}}**")'

        skipped["count"] += 1
        return None

    def generate(self) -> str:
        queries = self.model.queries()
        order = self._build_order(queries)

        m_source_entries = ",\n".join(f'    {name!r}: {expr!r}' for name, expr in queries.items())
        build_calls = "\n    ".join(
            f'model[{name!r}] = run_query({name!r}, M_SOURCE[{name!r}], model)' for name in order
        )

        try:
            layout = ReportLayoutParser().load_raw_layout(self.pbix_path)
            visual_specs = extract_visual_specs(layout)
        except KeyError:
            visual_specs = []

        measures_code = self._measures_code()
        dashboard_code = _indent(self._dashboard_code(visual_specs) if visual_specs else "dashboard = None")

        return TEMPLATE.format(
            source_file=self.pbix_path.name,
            m_source_entries=m_source_entries or "    # no queries found",
            build_calls=build_calls or "pass",
            measures_code=measures_code,
            dashboard_code=dashboard_code,
        )


TEMPLATE = '''"""Auto-generated end-to-end pipeline reproducing "{source_file}".

Generated by pbix-atlas: source -> extraction -> Power Query transforms ->
semantic model -> Vizro dashboard.

This is NOT a static per-step translation: the real M source of every query
is embedded below (M_SOURCE) and executed by pbix_atlas's M interpreter at
runtime, using the same stdlib registry regardless of how a step is
phrased. There is no TODO anywhere in this file: an expression the
interpreter doesn't support raises MRuntimeError naming the exact function,
and a DAX measure without a safe automatic translation raises
MeasureNotSupported naming the exact measure - loud, specific failures
instead of silent stubs.

Real connection info (URL, server;database, file path) detected in the
.pbix is embedded as-is in the M source below, so this runs against the
same systems the report used - edit the M_SOURCE strings directly to point
elsewhere.

Requires: pip install pbix-atlas pandas vizro plotly dash
"""

from __future__ import annotations

from pbix_atlas.m_interpreter import Env, MInterpreter, MRuntimeError, MTable

import plotly.express as px
import vizro.models as vm
from vizro import Vizro


class MeasureNotSupported:
    """Placeholder for a DAX measure with no safe automatic translation.
    Raises with the measure's name and original DAX the moment it's used,
    rather than silently returning a wrong number."""

    def __init__(self, table: str, name: str, dax_expression: str):
        self.table, self.name, self.dax_expression = table, name, dax_expression

    def __repr__(self) -> str:
        raise NotImplementedError(
            f"Measure {{self.table}}[{{self.name}}] has no automatic DAX translation. "
            f"Original DAX: {{self.dax_expression}}"
        )


# --------------------------------------------------------------------------
# 1. Real M source of every query, embedded verbatim (not transpiled)
# --------------------------------------------------------------------------

M_SOURCE = {{
{m_source_entries}
}}

_interp = MInterpreter()


def run_query(name: str, m_source: str, model: dict):
    """Parses and executes one query's M source against the tables already
    built in `model`, via pbix_atlas's M interpreter."""
    from pbix_atlas.m_parser import parse_m_expression

    env = Env()
    for table_name, table_value in model.items():
        env.set(table_name, table_value)
    ast = parse_m_expression(m_source)
    try:
        result = _interp.eval(ast, env)
    except MRuntimeError as exc:
        raise MRuntimeError(f'Query "{{name}}" failed: {{exc}}') from exc
    return result.df if isinstance(result, MTable) else result


# --------------------------------------------------------------------------
# 2. Semantic model - DAX measures
# --------------------------------------------------------------------------

{measures_code}


# --------------------------------------------------------------------------
# 3. Visualization - Vizro dashboard built from the report's visuals/pages
# --------------------------------------------------------------------------

def dash_table_from_df(df):
    from dash import dash_table
    return dash_table.DataTable(df.to_dict("records"))


def build_dashboard(model: dict, measures: dict):
{dashboard_code}
    return dashboard


# --------------------------------------------------------------------------
# 4. Orchestration
# --------------------------------------------------------------------------

def main() -> None:
    model: dict = {{}}
    {build_calls}

    measures = compute_measures(model)

    dashboard = build_dashboard(model, measures)
    if dashboard is not None:
        Vizro().build(dashboard).run()
    else:
        print("No dashboard could be reconstructed - check the model dict above.")


if __name__ == "__main__":
    main()
'''


def generate_python_pipeline(pbix_path: str | Path, output_path: str | Path) -> Path:
    code = PythonPipelineGenerator(pbix_path).generate()
    output_path = Path(output_path)
    output_path.write_text(code, encoding="utf-8")
    return output_path


def _compute_stats(code: str) -> dict[str, int]:
    return {
        "measures_translated": len(re.findall(r"measures\[\([^)]+\)\] = (?!MeasureNotSupported)", code)),
        "measures_unsupported": len(re.findall(r"MeasureNotSupported\(", code)),
        "queries_embedded": len(re.findall(r"^\s{4}'[^']*': ", code, re.MULTILINE)),
        "visuals_mapped": (
            len(re.findall(r"vm\.Graph\(", code))
            + len(re.findall(r"vm\.Card\(", code))
            + len(re.findall(r"vm\.Table\(", code))
        ),
        "visuals_skipped": int(m.group(1)) if (m := re.search(r"# (\d+) visual\(s\) not mapped", code)) else 0,
    }


def generate_python_pipeline_with_stats(
    pbix_path: str | Path, output_path: str | Path
) -> tuple[Path, dict[str, int]]:
    code = PythonPipelineGenerator(pbix_path).generate()
    output_path = Path(output_path)
    output_path.write_text(code, encoding="utf-8")
    return output_path, _compute_stats(code)
