# pbix-atlas

<!-- mcp-name: io.github.fabienfrfr/pbix-atlas -->

Universal lineage graph for Power BI (`.pbix`) files: from physical source to the field displayed in a report visual.

```
source (HTTP, OData, SQL, file...) --> Power Query (M)
    --> column / calculated column --> measure (DAX)
        --> field displayed in a report visual
```

The graph is a standard [`networkx.DiGraph`](https://networkx.org/), natively bidirectional: trace a visual back to its source (`upstream`), or list everything a source feeds (`downstream`).

## Why

`pbixray` (used here) extracts the **data model** (tables, DAX, Power Query, schema) but says nothing about **where** each column or measure ends up displayed — that lives in a separate, undocumented part of the file (`Report/Layout`). `pbix-atlas` connects both into one traversable graph.

## Install

```bash
pip install pbix-atlas
# or
uv add pbix-atlas
```

## Usage

```python
from pbix_atlas import LineageGraphBuilder, upstream, downstream, print_tree, find_nodes

graph = LineageGraphBuilder().build("my_report.pbix")

find_nodes(graph, "customer_name")
# -> ['column::DIM_CUSTOMER::customer_name']

print_tree(graph, "visual_field::my_report.pbix::Page1::16::customer_name", direction="upstream")
print_tree(graph, "source::odata::example.com/odata/", direction="downstream")
```

### Export

```python
from pbix_atlas import export_graphml, export_nodes_csv, export_edges_csv, graph_summary

graph_summary(graph)                       # {'query': 70, 'column': 183, ...}
export_graphml(graph, "lineage.graphml")   # opens in Gephi / yEd
export_nodes_csv(graph, "nodes.csv")
export_edges_csv(graph, "edges.csv")
```

## Source-agnostic

Source detection (`pbix_atlas.sources`) relies only on native M function names (`Web.Contents`, `OData.Feed`, `Sql.Database`, `Folder.Files`, `SharePoint.Files`, `Excel.Workbook`, `AnalysisServices.Database`, ...) — never a specific system or domain. Adding a new source type is one config entry in `MFunctionSourceDetector.DEFAULT_PATTERNS`, no other code touched.

## HTTP API / MCP server

The package also exposes a FastAPI app, mounted as an MCP server via [FastMCP](https://gofastmcp.com/) (`FastMCP.from_fastapi`): every route becomes an MCP tool automatically.

```bash
uv sync --extra api
uv run pbix-atlas    # starts on http://127.0.0.1:8080
```

- REST API: `POST /graphs`, `/search`, `/upstream`, `/downstream`, `/tree`, `/export`, `/codegen`, `GET /graphs`.
- MCP server (streamable HTTP) at `http://127.0.0.1:8080/mcp/`: same operations as tools (`build_graph`, `search_nodes`, `get_upstream`, `get_downstream`, `get_lineage_tree`, `export_graph`, `convert_pbix_to_python`, `list_loaded_graphs`), plus a `lineage_guidance` prompt.
- Env vars: `PBIX_LINEAGE_HOST` (default `0.0.0.0`), `PBIX_LINEAGE_PORT` (default `8080`).

Each `.pbix` is parsed once and cached in memory (`LineageGraphCache`, framework-agnostic).

`POST /codegen` (`convert_pbix_to_python`) generates the standalone Python
pipeline described below and returns `{output_path, stats}`, where `stats`
gives a quick coverage readout (M steps / DAX measures translated vs. left
as TODO, visuals mapped vs. skipped) without having to open the file first.

## Generate a standalone Python pipeline

Beyond the lineage graph, `pbix-atlas` can generate a **single Python file**
reproducing a report's full chain: source -> extraction -> Power Query
transformations -> semantic model (columns/measures) -> Vizro dashboard.

```bash
pip install "pbix-atlas[codegen]"
pbix-atlas-codegen my_report.pbix -o pipeline.py
```

or from Python:

```python
from pbix_atlas import generate_python_pipeline

generate_python_pipeline("my_report.pbix", "pipeline.py")
```

This is **not a per-step transpiler** - it's a real M interpreter:

- The actual M source of every query is embedded verbatim in the generated
  file (`M_SOURCE`) and executed at runtime by `pbix_atlas.m_interpreter`
  (own lexer/parser/interpreter - see [Architecture](#architecture)), the
  same way regardless of how a step happens to be phrased. Rename, filter,
  join, group-by, custom replace-value logic, multi-param lambdas: all run
  through the same engine, not a fixed set of recognized patterns.
- **There is no `TODO` anywhere in the generated file.** A step whose M
  function or operator genuinely isn't implemented raises `MRuntimeError`
  naming the exact function - loud and specific, never a silent stub.
- DAX measures: a curated subset (`SUM`, `AVERAGE`, `COUNTROWS`,
  `DISTINCTCOUNT`, `DIVIDE`, simple measure references) is translated to
  Python; anything more complex raises `MeasureNotSupported(table, name,
  original_dax)` the moment it's read, rather than silently returning a
  wrong number. Full DAX (filter-context propagation, time intelligence,
  `CALCULATE` with real filter semantics) is a much larger undertaking and
  intentionally out of scope for now.
- **Real connection info** (URL, `server;database`, file path) detected in
  the `.pbix` is embedded as-is in the M source, so the file runs against
  the same systems the report used - edit the `M_SOURCE` strings directly
  to point elsewhere.
- Charts spanning more than one semantic table, or using a visual type with
  no Vizro equivalent (custom visuals, images, shapes, slicers), are
  skipped rather than guessed; a summary comment reports how many.

Modules involved: `m_lexer.py` / `m_parser.py` (M tokenizer/parser, built
in-house - see below), `m_interpreter.py` (runtime interpreter + stdlib:
`Table.*`, `List.*`, `Text.*`, `Date.*`, plus real I/O for
`Sql.Database`/`OData.Feed`/`Web.Contents`/`Excel.Workbook`/`File.Contents`),
`dax_translate.py` (DAX -> Python for the supported subset), `layout_roles.py`
(visual roles/filters), `codegen.py` (orchestrator, uses `mquery.py` for
topological query ordering).

> **Why a hand-built M parser?** An earlier version of this depended on a
> published M-parsing package (`pbi-parsers`). It turned out to be missing
> the `<`/`<=` operators entirely and couldn't parse multi-parameter or
> typed lambdas - real gaps that would have meant hardcoding workarounds
> around someone else's incomplete grammar. `m_lexer.py`/`m_parser.py` are
> small, scoped to what Power Query Desktop actually emits, and verified
> against real-world `.pbix` files rather than the full (unpublished) M
> grammar.

Tried against real-world files (not part of CI, just concrete examples you
can try yourself):
- [Retail Analysis Sample PBIX](https://download.microsoft.com/download/9/6/D/96DDC2FF-2568-491D-AAFA-AFDD6F763AE3/Retail%20Analysis%20Sample%20PBIX.pbix) (Microsoft)
- [Sales & Returns Sample v201912](https://github.com/microsoft/powerbi-desktop-samples/raw/refs/heads/main/Sample%20Reports/Sales%20%26%20Returns%20Sample%20v201912.pbix) (Microsoft)

This is also exposed as an HTTP/MCP endpoint - see below.



[`server.json`](./server.json) describes this server for [registry.modelcontextprotocol.io](https://registry.modelcontextprotocol.io). After replacing `votre-org` with your GitHub account everywhere:

```bash
uv build && uv publish          # publish the package to PyPI first
mcp-publisher login github
mcp-publisher publish --dry-run
mcp-publisher publish
```

The registry verifies PyPI ownership via the `<!-- mcp-name: ... -->` marker at the top of this README. The name in `server.json`, this marker, and your authenticated GitHub namespace must all match.

## Architecture

| Module               | Responsibility                                         |
| -------------------- | ------------------------------------------------------ |
| `models.py`        | Node/edge types and shared data structures             |
| `sources.py`       | Physical source detection (agnostic, configurable)     |
| `pbix_model.py`    | Adapter isolating the rest of the code from`pbixray` |
| `dax.py`           | DAX reference parsing (`Table[Field]` / `[Field]`) |
| `mquery.py`        | Dependencies between Power Query queries (table-level) |
| `layout.py`        | Parsing of the internal`Report/Layout` format        |
| `graph_builder.py` | Orchestrator: builds the`networkx.DiGraph`           |
| `navigation.py`    | Upstream/downstream traversal, search, export          |
| `api/schemas.py`   | Pydantic request/response models                       |
| `api/service.py`   | Graph cache, framework-agnostic                        |
| `api/app.py`       | FastAPI app + MCP mount (FastMCP)                      |

## Known limitations

- M query dependencies are resolved at **table level**, not step-by-step inside a single `let ... in` query.
- A source reached only through a literal M parameter may be tagged with a generic system (`http`) instead of the exact consumer connector (`odata`, etc.).
- Unqualified DAX references (`[MeasureName]`) are resolved same-table first, then globally; homonyms across tables resolve to the first match.

## Development

```bash
uv sync --extra dev
uv run pytest     # BDD tests (pytest-bdd) under tests/features/*.feature
uv build          # produces dist/*.whl and dist/*.tar.gz
```

## AI Setup

```bash
# Install Spec Kit CLI
uv tool install specify-cli

# Initialize project with opencode integration
specify init . --here --integration opencode --script py
```

