"""pbix-atlas: bidirectional data-lineage graph for Power BI (.pbix) files.

Traces the full chain from a physical source (HTTP, OData, SQL, file...)
through Power Query (M) transforms, into the semantic model (columns,
calculated columns, DAX measures), and out to every field displayed in a
report visual - and back again. Public surface:

- `LineageGraphBuilder` builds a `networkx.DiGraph` from a `.pbix` path.
- `upstream`/`downstream`/`find_nodes`/`print_tree`/`build_tree` navigate it.
- `source_schema`/`print_source_schema`/`write_source_tree_report` describe
  the source side (which tables/columns come from where).
- `export_graphml`/`export_nodes_csv`/`export_edges_csv`/`export_json`
  serialize the graph for external tools.
- `generate_python_pipeline` (codegen) emits a standalone Python script that
  reproduces the report end-to-end.

See `pbix_atlas.api.app` for the HTTP/MCP server built on top of this.
"""

from .codegen import PythonPipelineGenerator, generate_python_pipeline
from .dax import DaxReferenceParser
from .graph_builder import LineageGraphBuilder
from .layout import ReportLayoutParser
from .levels import get_level, list_sources
from .models import DaxReference, EdgeType, NodeType, SourceRef, VisualFieldUsage, node_id
from .mquery import MQueryDependencyResolver
from .navigation import (
    downstream,
    export_edges_csv,
    export_graphml,
    export_json,
    export_nodes_csv,
    find_nodes,
    graph_summary,
    output_schema,
    print_output_schema,
    print_source_schema,
    print_tree,
    render_source_tree_lines,
    source_schema,
    upstream,
)
from .pbix_model import PBIXModel
from .reports import render_source_tree_markdown, write_source_tree_report
from .sources import (
    LiteralUrlFallbackDetector,
    MFunctionSourceDetector,
    SourceDetector,
    SourceDetectorRegistry,
    normalize_source_identifier,
)

__version__ = "1.0.1"

__all__ = [
    "DaxReference",
    "DaxReferenceParser",
    "EdgeType",
    "LineageGraphBuilder",
    "LiteralUrlFallbackDetector",
    "MFunctionSourceDetector",
    "MQueryDependencyResolver",
    "NodeType",
    "PBIXModel",
    "PythonPipelineGenerator",
    "ReportLayoutParser",
    "SourceDetector",
    "SourceDetectorRegistry",
    "SourceRef",
    "VisualFieldUsage",
    "__version__",
    "downstream",
    "export_edges_csv",
    "export_graphml",
    "export_json",
    "export_nodes_csv",
    "find_nodes",
    "generate_python_pipeline",
    "get_level",
    "graph_summary",
    "list_sources",
    "node_id",
    "normalize_source_identifier",
    "output_schema",
    "print_output_schema",
    "print_source_schema",
    "print_tree",
    "render_source_tree_lines",
    "render_source_tree_markdown",
    "source_schema",
    "upstream",
    "write_source_tree_report",
]
