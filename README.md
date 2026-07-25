# pbix-lineage

<!-- mcp-name: io.github.fabienfrfr/pbix-lineage -->

Universal lineage graph for Power BI (`.pbix`) files: from physical source to the field displayed in a report visual.

```
source (HTTP, OData, SQL, file...) --> Power Query (M)
    --> column / calculated column --> measure (DAX)
        --> field displayed in a report visual
```

The graph is a standard [`networkx.DiGraph`](https://networkx.org/), natively bidirectional: trace a visual back to its source (`upstream`), or list everything a source feeds (`downstream`).

## Why

`pbixray` (used here) extracts the **data model** (tables, DAX, Power Query, schema) but says nothing about **where** each column or measure ends up displayed — that lives in a separate, undocumented part of the file (`Report/Layout`). `pbix-lineage` connects both into one traversable graph.

## Install

```bash
pip install pbix-lineage
# or
uv add pbix-lineage
```

## Usage

```python
from pbix_lineage import LineageGraphBuilder, upstream, downstream, print_tree, find_nodes

graph = LineageGraphBuilder().build("my_report.pbix")

find_nodes(graph, "customer_name")
# -> ['column::DIM_CUSTOMER::customer_name']

print_tree(graph, "visual_field::my_report.pbix::Page1::16::customer_name", direction="upstream")
print_tree(graph, "source::odata::example.com/odata/", direction="downstream")
```

### Export

```python
from pbix_lineage import export_graphml, export_nodes_csv, export_edges_csv, graph_summary

graph_summary(graph)                       # {'query': 70, 'column': 183, ...}
export_graphml(graph, "lineage.graphml")   # opens in Gephi / yEd
export_nodes_csv(graph, "nodes.csv")
export_edges_csv(graph, "edges.csv")
```

## Source-agnostic

Source detection (`pbix_lineage.sources`) relies only on native M function names (`Web.Contents`, `OData.Feed`, `Sql.Database`, `Folder.Files`, `SharePoint.Files`, `Excel.Workbook`, `AnalysisServices.Database`, ...) — never a specific system or domain. Adding a new source type is one config entry in `MFunctionSourceDetector.DEFAULT_PATTERNS`, no other code touched.

## HTTP API / MCP server

The package also exposes a FastAPI app, mounted as an MCP server via [FastMCP](https://gofastmcp.com/) (`FastMCP.from_fastapi`): every route becomes an MCP tool automatically.

```bash
uv sync --extra api
uv run pbix-lineage    # starts on http://127.0.0.1:8080
```

- REST API: `POST /graphs`, `/search`, `/upstream`, `/downstream`, `/tree`, `/export`, `GET /graphs`.
- MCP server (streamable HTTP) at `http://127.0.0.1:8080/mcp/`: same operations as tools (`build_graph`, `search_nodes`, `get_upstream`, `get_downstream`, `get_lineage_tree`, `export_graph`, `list_loaded_graphs`), plus a `lineage_guidance` prompt.
- Env vars: `PBIX_LINEAGE_HOST` (default `0.0.0.0`), `PBIX_LINEAGE_PORT` (default `8080`).

Each `.pbix` is parsed once and cached in memory (`LineageGraphCache`, framework-agnostic).

## Publish to the MCP registry

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

## License

MIT
