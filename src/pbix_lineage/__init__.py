"""
pbix_lineage
============

Turns a Power BI file (.pbix) into a universal lineage graph, from the
physical source down to the field displayed in a report visual:

    source -> query (Power Query / M) -> column / calculated column
           -> measure (DAX) -> field displayed in a visual

Minimal usage::

    from pbix_lineage import LineageGraphBuilder, print_tree

    graph = LineageGraphBuilder().build("my_report.pbix")
    print_tree(graph, "column::DA_GLD::demandeur", direction="downstream")

The returned graph is a standard ``networkx.DiGraph``.
"""

from .dax import DaxReferenceParser
from .graph_builder import LineageGraphBuilder
from .layout import ReportLayoutParser
from .models import DaxReference, EdgeType, NodeType, SourceRef, VisualFieldUsage, node_id
from .mquery import MQueryDependencyResolver
from .navigation import (
    downstream,
    export_edges_csv,
    export_graphml,
    export_nodes_csv,
    find_nodes,
    graph_summary,
    print_tree,
    upstream,
)
from .pbix_model import PBIXModel
from .sources import (
    LiteralUrlFallbackDetector,
    MFunctionSourceDetector,
    SourceDetector,
    SourceDetectorRegistry,
    normalize_source_identifier,
)

__version__ = "0.1.0"

__all__ = [
    "LineageGraphBuilder",
    "PBIXModel",
    "ReportLayoutParser",
    "DaxReferenceParser",
    "MQueryDependencyResolver",
    "SourceDetector",
    "MFunctionSourceDetector",
    "LiteralUrlFallbackDetector",
    "SourceDetectorRegistry",
    "normalize_source_identifier",
    "NodeType",
    "EdgeType",
    "SourceRef",
    "DaxReference",
    "VisualFieldUsage",
    "node_id",
    "upstream",
    "downstream",
    "find_nodes",
    "print_tree",
    "export_graphml",
    "export_edges_csv",
    "export_nodes_csv",
    "graph_summary",
    "__version__",
]
