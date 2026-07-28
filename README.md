# pbix-atlas

<!-- mcp-name: io.github.fabienfrfr/pbix-atlas -->

Universal lineage graph for Power BI `.pbix` files: source to visual field in one traversable graph.

```
source (HTTP, OData, SQL, file...) --> Power Query (M)
    --> column / calculated column --> measure (DAX)
        --> field displayed in a report visual
```

## Install

```bash
pip install pbix-atlas
# or
uv add pbix-atlas
```

## Quick start

```python
from pbix_atlas import LineageGraphBuilder, upstream, downstream, print_tree, find_nodes

graph = LineageGraphBuilder().build("my_report.pbix")

find_nodes(graph, "customer_name")
print_tree(graph, "visual_field::my_report.pbix::Page1::16::customer_name", direction="upstream")
print_tree(graph, "source::odata::example.com/odata/", direction="downstream")
```

## Export

```python
from pbix_atlas import export_graphml, export_nodes_csv, export_edges_csv, graph_summary

graph_summary(graph)  # {'query': 70, 'column': 183, ...}
export_graphml(graph, "lineage.graphml")  # Gephi / yEd
export_nodes_csv(graph, "nodes.csv")
export_edges_csv(graph, "edges.csv")
```

## Codegen — standalone Python pipeline

Generates a single Python file reproducing a report's full chain: source → extraction → Power Query → semantic model → Vizro dashboard. The M source is executed at runtime by the built-in interpreter, not pattern-matched. Unimplemented functions raise `MRuntimeError` (no silent stubs).

```bash
pip install "pbix-atlas[codegen]"
pbix-atlas-codegen my_report.pbix -o pipeline.py
```

```python
from pbix_atlas import generate_python_pipeline

generate_python_pipeline("my_report.pbix", "pipeline.py")
```

## HTTP API / MCP server

```bash
uv sync --extra api
uv run pbix-atlas    # http://127.0.0.1:8080
```

- REST: `POST /graphs`, `/search`, `/upstream`, `/downstream`, `/tree`, `/export`, `/codegen`
- MCP (streamable HTTP): `http://127.0.0.1:8080/mcp/`
- Env vars: `PBIX_LINEAGE_HOST`, `PBIX_LINEAGE_PORT`

## Architecture

| Module | Responsibility |
|---|---|
| `models.py` | Node/edge types and shared data structures |
| `sources.py` | Physical source detection (configurable patterns) |
| `pbix_model.py` | Adapter isolating from `pbixray` |
| `m_lexer.py` / `m_parser.py` | Built-in M tokenizer and parser |
| `m_interpreter.py` | M runtime interpreter + stdlib |
| `dax_translate.py` | DAX → Python (supported subset) |
| `dax.py` | DAX reference parsing |
| `mquery.py` | Power Query dependencies (table-level) |
| `layout.py` | Internal `Report/Layout` format parsing |
| `graph_builder.py` | Orchestrator: builds the `networkx.DiGraph` |
| `navigation.py` | Upstream/downstream traversal, search, export |
| `codegen.py` | Python pipeline code generation |
| `api/app.py` | FastAPI + MCP mount ([FastMCP](https://gofastmcp.com/)) |

## Sample files

- [Retail Analysis Sample PBIX](https://download.microsoft.com/download/9/6/D/96DDC2FF-2568-491D-AAFA-AFDD6F763AE3/Retail%20Analysis%20Sample%20PBIX.pbix) (Microsoft)
- [Sales & Returns Sample v201912](https://github.com/microsoft/powerbi-desktop-samples/raw/refs/heads/main/Sample%20Reports/Sales%20%26%20Returns%20Sample%20v201912.pbix) (Microsoft)

## Development

```bash
uv sync --extra dev
uv run pytest
uv build
```
