from __future__ import annotations

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastmcp import FastMCP
from fastmcp.utilities.lifespan import combine_lifespans

from .schemas import (
    BuildGraphRequest,
    ExportRequest,
    ExportResponse,
    GraphSummaryResponse,
    NodeListResponse,
    NodeQuery,
    SearchRequest,
    TreeNode,
    TreeQuery,
)
from .service import LineageGraphCache

load_dotenv()

HOST = os.getenv("PBIX_LINEAGE_HOST", "0.0.0.0")
PORT = int(os.getenv("PBIX_LINEAGE_PORT", "8080"))


@asynccontextmanager
async def lineage_lifespan(app: FastAPI):
    app.state.cache = LineageGraphCache()
    yield


def get_cache(request: Request) -> LineageGraphCache:
    return request.app.state.cache


app = FastAPI(title="PBIX Lineage Gateway", lifespan=lineage_lifespan)


@app.post("/graphs", operation_id="build_graph", response_model=GraphSummaryResponse)
def build_graph(payload: BuildGraphRequest, request: Request) -> GraphSummaryResponse:
    """Parse a .pbix file and build (or reuse) its lineage graph."""
    try:
        summary = get_cache(request).summary(payload.pbix_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return GraphSummaryResponse(pbix_path=payload.pbix_path, **summary)


@app.get("/graphs", operation_id="list_loaded_graphs")
def list_loaded_graphs(request: Request) -> list[str]:
    """List the .pbix files whose graph is already loaded in memory."""
    return get_cache(request).loaded_paths()


@app.post("/search", operation_id="search_nodes", response_model=NodeListResponse)
def search_nodes(payload: SearchRequest, request: Request) -> NodeListResponse:
    """Find nodes (columns, measures, visual fields...) by substring."""
    try:
        nodes = get_cache(request).search(payload.pbix_path, payload.query)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return NodeListResponse(nodes=nodes)


@app.post("/upstream", operation_id="get_upstream", response_model=NodeListResponse)
def get_upstream(payload: NodeQuery, request: Request) -> NodeListResponse:
    """List every node upstream of a given node, i.e. toward the physical source."""
    try:
        nodes = get_cache(request).upstream(payload.pbix_path, payload.node_id, payload.include_relationships)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return NodeListResponse(nodes=nodes)


@app.post("/downstream", operation_id="get_downstream", response_model=NodeListResponse)
def get_downstream(payload: NodeQuery, request: Request) -> NodeListResponse:
    """List every node downstream of a given node, i.e. toward the report display."""
    try:
        nodes = get_cache(request).downstream(payload.pbix_path, payload.node_id, payload.include_relationships)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return NodeListResponse(nodes=nodes)


@app.post("/tree", operation_id="get_lineage_tree", response_model=TreeNode)
def get_lineage_tree(payload: TreeQuery, request: Request) -> TreeNode:
    """Return a nested lineage tree from a node, upstream or downstream."""
    try:
        tree = get_cache(request).tree(
            payload.pbix_path, payload.node_id, payload.direction, payload.max_depth
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return TreeNode(**tree)


@app.post("/export", operation_id="export_graph", response_model=ExportResponse)
def export_graph(payload: ExportRequest, request: Request) -> ExportResponse:
    """Export the lineage graph to GraphML and CSV files on disk."""
    try:
        paths = get_cache(request).export(payload.pbix_path, payload.output_dir)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ExportResponse(**paths)


mcp = FastMCP.from_fastapi(app=app, name="PBIX Lineage")


@mcp.prompt
def lineage_guidance() -> str:
    """Short best-practice guidance for the PBIX Lineage MCP."""
    return """
# PBIX Lineage Guidance

This MCP exposes the data lineage of a Power BI (.pbix) file: from its
physical source, through Power Query and the data model, down to every field
displayed in a report visual. The graph is bidirectional.

## Recommended workflow
1. Call `build_graph` once per .pbix file to parse it and get a summary.
2. Use `search_nodes` to find the node id of a column, measure, or visual
   field you are interested in (node ids look like
   `column::TableName::FieldName` or `measure::TableName::MeasureName`).
3. Use `get_upstream` or `get_lineage_tree` (direction="upstream") to trace a
   displayed field back to its physical source.
4. Use `get_downstream` or `get_lineage_tree` (direction="downstream") to see
   everything a source or column feeds into.
5. Use `export_graph` to write GraphML/CSV files for external tools
   (Gephi, yEd, a BI dashboard, etc.).

## Notes
- Node ids are stable and can be copied directly from `search_nodes` results.
- `get_lineage_tree` is the most convenient call for exploration: it returns
  a full nested tree in one call instead of a flat list of ancestors.
"""


mcp_app = mcp.http_app(path="/")
app.router.lifespan_context = combine_lifespans(lineage_lifespan, mcp_app.lifespan)
app.mount("/mcp/", mcp_app)


def main() -> None:
    import uvicorn

    uvicorn.run("pbix_lineage.api.app:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    main()
