"""Pydantic request/response models for the HTTP API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BuildGraphRequest(BaseModel):
    pbix_path: str = Field(description="Path to a .pbix file on the server's filesystem")


class GraphSummaryResponse(BaseModel):
    pbix_path: str
    node_counts: dict[str, int]
    edge_count: int


class SearchRequest(BaseModel):
    pbix_path: str
    query: str = Field(description="Case-insensitive substring to search for in node ids")


class NodeListResponse(BaseModel):
    nodes: list[str]


class NodeQuery(BaseModel):
    pbix_path: str
    node_id: str
    include_relationships: bool = False


class TreeQuery(BaseModel):
    pbix_path: str
    node_id: str
    direction: str = Field(
        default="downstream", description="'downstream' (toward the display) or 'upstream' (toward the source)"
    )
    max_depth: int = 12


class TreeNode(BaseModel):
    id: str
    type: str
    children: list[TreeNode] = []


TreeNode.model_rebuild()


class ExportRequest(BaseModel):
    pbix_path: str
    output_dir: str = Field(default=".", description="Directory where export files will be written")


class ExportResponse(BaseModel):
    graphml_path: str
    nodes_csv_path: str
    edges_csv_path: str


class CodegenRequest(BaseModel):
    pbix_path: str = Field(description="Path to a .pbix file on the server's filesystem")
    output_path: str = Field(
        default="",
        description="Where to write the generated .py file. Defaults to "
        "'<pbix name>_pipeline.py' next to the input file.",
    )


class CodegenResponse(BaseModel):
    output_path: str
    stats: dict[str, int] = Field(
        description="Coverage counters: translated vs. TODO for M steps and DAX measures, "
        "and how many visuals were mapped to a Vizro component vs. skipped."
    )
