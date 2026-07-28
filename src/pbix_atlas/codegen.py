"""Generates two artifacts from the same lineage graph (`graph_builder`):
a `.graphml`/`.json` file (ETL info: M source per query, DAX per measure),
and a `.py` file read from it - readable pandas code via `m_ops`, specific
to the report.
"""

from __future__ import annotations

import re
from pathlib import Path

import networkx as nx

from .dax_translate import DaxTranslator
from .graph_builder import LineageGraphBuilder
from .layout import ReportLayoutParser
from .layout_roles import extract_visual_specs


def _safe_name(name: str) -> str:
    out = re.sub(r"\W+", "_", name.strip())
    if not out or out[0].isdigit():
        out = f"v_{out}"
    return out


def _indent(code: str, spaces: int = 4) -> str:
    pad = " " * spaces
    return "\n".join(pad + line if line.strip() else line for line in code.splitlines())


class PythonPipelineGenerator:
    """PythonPipelineGenerator (see attributes/methods below)."""

    def __init__(self, pbix_path: str | Path):
        """Initialize."""
        self.pbix_path = Path(pbix_path)
        self.graph = LineageGraphBuilder().build(self.pbix_path)
        self.dax_translator = DaxTranslator()

    def export_graphml(self, path: str | Path) -> Path:
        """Export graphml. Takes `path`."""
        path = Path(path)
        nx.write_graphml(self.graph, path)
        return path

    def export_json(self, path: str | Path) -> Path:
        """Kept for backward compatibility - delegates to `navigation.export_json`,
        which is the canonical implementation (it doesn't need a
        `PythonPipelineGenerator`/pipeline-code machinery at all, just a graph)."""
        from .navigation import export_json as _export_json

        return _export_json(self.graph, path)

    def _query_nodes_in_order(self) -> list[str]:
        query_nodes = [n for n, d in self.graph.nodes(data=True) if d.get("type") == "query"]
        sub = self.graph.subgraph(query_nodes)
        try:
            return list(nx.topological_sort(sub))
        except nx.NetworkXUnfeasible:
            return query_nodes

    def _query_functions_code(self, order: list[str]) -> tuple[str, list[str]]:
        import json

        from .m_parser import ast_from_dict
        from .m_transpile import MTranspiler
        from .m_transpile import _safe_name as t_safe_name

        transpiler = MTranspiler()
        blocks: list[str] = []
        build_calls: list[str] = []
        for qid in order:
            data = self.graph.nodes[qid]
            name = data["label"]
            fn = f"build_{_safe_name(name)}"
            body_json = data.get("body")

            if body_json is None:
                blocks.append(f'def {fn}(model):\n    """"{name}": could not be parsed."""\n    return None\n')
                build_calls.append(f"model[{name!r}] = {fn}(model)")
                continue

            steps = sorted(
                (self.graph.nodes[s] for s in self.graph.successors(qid) if self.graph.nodes[s].get("type") == "step"),
                key=lambda d: d["order"],
            )
            scope: set[str] = set()
            lines: list[str] = []
            for s in steps:
                op_ast = ast_from_dict(json.loads(s["operation"]))
                lines.append(f"{t_safe_name(s['label'])} = {transpiler.expr(op_ast, scope)}  # step: {s['label']!r}")
                scope.add(s["label"])
            return_expr = transpiler.expr(ast_from_dict(json.loads(body_json)), scope)

            body = "\n    ".join(lines) if lines else "pass"
            blocks.append(
                f'def {fn}(model):\n    """Reproduces query "{name}"."""\n    {body}\n    return {return_expr}\n'
            )
            build_calls.append(f"model[{name!r}] = {fn}(model)")
        return "\n\n".join(blocks), build_calls

    def _measures_code(self) -> str:
        measure_nodes = [(n, d) for n, d in self.graph.nodes(data=True) if d.get("type") == "measure"]
        lines = [
            "def compute_measures(model: dict) -> dict:",
            '    """DAX measures, translated where a safe automatic mapping exists',
            "    (aggregations, DIVIDE, simple measure references). Anything else",
            "    raises MeasureNotSupported at call time - naming the exact measure",
            "    and its original DAX, rather than silently returning a wrong number.",
            '    """',
            "    measures: dict = {}",
        ]
        pending = [(d["table"], d["label"], d["dax_expression"]) for _, d in measure_nodes]
        for _ in range(3):
            still = []
            for table, name, expr in pending:
                result = self.dax_translator.translate(expr, default_table=table)
                if result.supported:
                    lines.append(f"    measures[({table!r}, {name!r})] = {result.python_expr}")
                else:
                    still.append((table, name, expr))
            pending = still
        for table, name, expr in pending:
            preview = " ".join(expr.split())[:100]
            lines.append(f"    measures[({table!r}, {name!r})] = MeasureNotSupported({table!r}, {name!r}, {preview!r})")
        lines.append("    return measures")
        return "\n".join(lines) + "\n"

    def _dashboard_code(self) -> str:
        try:
            layout = ReportLayoutParser().load_raw_layout(self.pbix_path)
            visual_specs = extract_visual_specs(layout)
        except KeyError:
            visual_specs = []

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
            page_blocks.append(f"{var} = vm.Page(\n    title={page!r},\n    components=[\n        {joined}\n    ],\n)")

        body = "\n\n".join(page_blocks)
        summary = (
            f"# {skipped['count']} visual(s) not mapped to a Vizro component on purpose: "
            f"multi-table charts (join logic is model-specific), custom visuals "
            f"(Deneb/HTML), images, shapes and slicers are skipped rather than guessed."
        )
        pages = ", ".join(page_vars)
        return f"{body}\n\n{summary}\ndashboard = vm.Dashboard(pages=[{pages}])\n"

    def _visual_component(self, spec, skipped: dict) -> str | None:  # noqa: PLR0911
        gtype = spec.generic_type
        comp_id = f"{_safe_name(spec.page)}_{spec.visual_index}"
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
        """Generate."""
        order = self._query_nodes_in_order()
        query_fn_code, build_calls = self._query_functions_code(order)
        measures_code = self._measures_code()
        dashboard_code = _indent(self._dashboard_code())

        return TEMPLATE.format(
            source_file=self.pbix_path.name,
            query_fn_code=query_fn_code,
            build_calls="\n    ".join(build_calls) or "pass",
            measures_code=measures_code,
            dashboard_code=dashboard_code,
        )


TEMPLATE = '''"""Pipeline reproducing "{source_file}", generated by pbix-atlas from its
lineage graph (see the companion .graphml/.json). Readable pandas per step
(m_ops), no embedded AST, no raw M re-parsed at runtime.

No TODO: unsupported M raises at generation time; unsupported DAX raises
MeasureNotSupported naming the measure (full DAX in the graph file).

Real connection info from the .pbix is embedded as-is below.
Requires: pip install pbix-atlas pandas vizro plotly dash
"""

from __future__ import annotations

from pbix_atlas import m_ops

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
            f"Measure {{self.table}}[{{self.name}}] has no automatic DAX translation "
            f"(DAX preview: {{self.dax_expression}}... - full expression in the .graphml)"
        )


# --------------------------------------------------------------------------
# 1. Extraction + transformation - one readable function per Power Query
# --------------------------------------------------------------------------

{query_fn_code}


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


def generate_pipeline(pbix_path: str | Path, graphml_path: str | Path, py_path: str | Path) -> tuple[Path, Path]:
    """Writes both artifacts derived from the same lineage graph: the
    `.graphml` and the report-specific `.py`."""
    gen = PythonPipelineGenerator(pbix_path)
    graphml_out = gen.export_graphml(graphml_path)
    code = gen.generate()
    py_out = Path(py_path)
    py_out.write_text(code, encoding="utf-8")
    return graphml_out, py_out


def generate_python_pipeline(pbix_path: str | Path, output_path: str | Path) -> Path:
    """Back-compat single-file entry point (graphml written alongside, same stem)."""
    output_path = Path(output_path)
    graphml_path = output_path.with_suffix(".graphml")
    _, py_out = generate_pipeline(pbix_path, graphml_path, output_path)
    return py_out


def _compute_stats(code: str, graph) -> dict[str, int]:
    return {
        "queries": sum(1 for _, d in graph.nodes(data=True) if d.get("type") == "query"),
        "measures_translated": len(re.findall(r"measures\[\([^)]+\)\] = (?!MeasureNotSupported)", code)),
        "measures_unsupported": len(re.findall(r"MeasureNotSupported\(", code)),
        "visuals_mapped": (
            len(re.findall(r"vm\.Graph\(", code))
            + len(re.findall(r"vm\.Card\(", code))
            + len(re.findall(r"vm\.Table\(", code))
        ),
        "visuals_skipped": int(m.group(1)) if (m := re.search(r"# (\d+) visual\(s\) not mapped", code)) else 0,
    }


def generate_python_pipeline_with_stats(pbix_path: str | Path, output_path: str | Path) -> tuple[Path, dict[str, int]]:
    """Generate python pipeline with stats. Takes `pbix_path`, `output_path`."""
    output_path = Path(output_path)
    graphml_path = output_path.with_suffix(".graphml")
    gen = PythonPipelineGenerator(pbix_path)
    gen.export_graphml(graphml_path)
    code = gen.generate()
    output_path.write_text(code, encoding="utf-8")
    return output_path, _compute_stats(code, gen.graph)
