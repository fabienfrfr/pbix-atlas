"""Pydantic request/response models for the HTTP API.

Every model here is also what `FastMCP.from_fastapi` (see `app.py`) uses to
auto-generate the MCP tool schemas, so field descriptions double as the
guidance an MCP client/LLM sees for each parameter.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class BuildGraphRequest(BaseModel):
    """Request to parse a .pbix file and (re)build its lineage graph."""

    pbix_path: str = Field(description="Path to a .pbix file on the server's filesystem")
    force_rebuild: bool = Field(
        default=False,
        description="Rebuild even if a cached graph exists and the file's mtime hasn't changed. "
        "Normally unnecessary: the cache already auto-invalidates on mtime change.",
    )


class InvalidateRequest(BaseModel):
    """Request to evict a specific cached graph, forcing a rebuild on its
    next use."""

    pbix_path: str = Field(description="Path to the .pbix file whose cached graph should be dropped")


class InvalidateResponse(BaseModel):
    """Whether a cached graph was actually evicted for the requested path."""

    pbix_path: str
    evicted: bool


class InvalidateAllResponse(BaseModel):
    """How many cached graphs were dropped by a full cache reset."""

    evicted_count: int


class GraphSummaryResponse(BaseModel):
    """Node/edge counts for a built graph, broken down by node type."""

    pbix_path: str
    node_counts: dict[str, int] = Field(description="Node count per type, e.g. {'column': 838, 'measure': 51}")
    edge_count: int


class SearchRequest(BaseModel):
    """Case-insensitive substring search over node ids of a built graph."""

    pbix_path: str
    query: str = Field(description="Case-insensitive substring to search for in node ids")


class NodeListResponse(BaseModel):
    """A flat list of node ids, e.g. from search/upstream/downstream."""

    nodes: list[str]


class NodeQuery(BaseModel):
    """A single node id to traverse from, upstream or downstream."""

    pbix_path: str
    node_id: str
    include_relationships: bool = Field(
        default=False, description="Also traverse model relationships (RELATES_TO edges), not just data lineage"
    )


class TreeQuery(BaseModel):
    """A node id to render as a nested lineage tree."""

    pbix_path: str
    node_id: str
    direction: str = Field(
        default="downstream", description="'downstream' (toward the display) or 'upstream' (toward the source)"
    )
    max_depth: int = 12


class TreeNode(BaseModel):
    """One node in a nested lineage tree, with its traversed children."""

    id: str
    type: str
    children: list[TreeNode] = []


TreeNode.model_rebuild()


class ExportRequest(BaseModel):
    """Where to write the full graph export (GraphML + CSV + JSON)."""

    pbix_path: str
    output_dir: str = Field(default=".", description="Directory where export files will be written")


class ExportResponse(BaseModel):
    """Paths to every file written by an export."""

    graphml_path: str
    nodes_csv_path: str
    edges_csv_path: str
    json_path: str


class SourceSchemaRequest(BaseModel):
    """Request for the source-side lineage report of a .pbix file."""

    pbix_path: str
    title: str = Field(default="Source Lineage Report", description="Title used in the generated Markdown report")


class SourceSchemaResponse(BaseModel):
    """Markdown report describing every physical source down to its tables
    and columns, plus the same data as structured JSON for programmatic
    use."""

    markdown: str = Field(description="Full report as GitHub-flavored Markdown (see `reports.py`)")
    schema_data: dict = Field(description="Source -> table -> {columns, view, names_reliable, renamed_columns}")


class CodegenRequest(BaseModel):
    """Request to generate a standalone Python pipeline from a .pbix file."""

    pbix_path: str = Field(description="Path to a .pbix file on the server's filesystem")
    output_path: str = Field(
        default="",
        description="Where to write the generated .py file. Defaults to "
        "'<pbix name>_pipeline.py' next to the input file.",
    )


class CodegenResponse(BaseModel):
    """Path to the generated pipeline file plus a coverage summary."""

    output_path: str
    stats: dict[str, int] = Field(
        description="Coverage counters: translated vs. TODO for M steps and DAX measures, "
        "and how many visuals were mapped to a Vizro component vs. skipped."
    )
