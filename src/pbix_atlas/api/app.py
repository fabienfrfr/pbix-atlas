"""App."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastmcp import FastMCP
from fastmcp.utilities.lifespan import combine_lifespans

from .schemas import (
    BuildGraphRequest,
    CodegenRequest,
    CodegenResponse,
    ExportRequest,
    ExportResponse,
    GraphSummaryResponse,
    InvalidateAllResponse,
    InvalidateRequest,
    InvalidateResponse,
    NodeListResponse,
    NodeQuery,
    SearchRequest,
    SourceSchemaRequest,
    SourceSchemaResponse,
    TreeNode,
    TreeQuery,
)
from .service import LineageGraphCache

load_dotenv()

HOST = os.getenv("PBIX_LINEAGE_HOST", "0.0.0.0")
PORT = int(os.getenv("PBIX_LINEAGE_PORT", "8080"))


@asynccontextmanager
async def lineage_lifespan(app: FastAPI):
    """Lineage lifespan. Takes `app`."""
    app.state.cache = LineageGraphCache()
    yield


def get_cache(request: Request) -> LineageGraphCache:
    """Get cache. Takes `request`."""
    return request.app.state.cache


app = FastAPI(title="PBIX Lineage Gateway", lifespan=lineage_lifespan)


@app.post("/graphs", operation_id="build_graph", response_model=GraphSummaryResponse)
def build_graph(payload: BuildGraphRequest, request: Request) -> GraphSummaryResponse:
    """Parse a .pbix file (or return its cached summary) and report node/edge counts."""
    try:
        summary = get_cache(request).summary(payload.pbix_path, force_rebuild=payload.force_rebuild)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return GraphSummaryResponse(pbix_path=payload.pbix_path, **summary)


@app.get("/graphs", operation_id="list_loaded_graphs")
def list_loaded_graphs(request: Request) -> list[str]:
    """List the resolved paths of every .pbix currently cached in memory."""
    return get_cache(request).loaded_paths()


@app.post("/graphs/invalidate", operation_id="invalidate_graph", response_model=InvalidateResponse)
def invalidate_graph(payload: InvalidateRequest, request: Request) -> InvalidateResponse:
    """Evict the cached graph for one .pbix file, forcing a rebuild next time
    it's used. Normally unnecessary - the cache auto-invalidates when the
    file's mtime changes - but useful to free memory or force a rebuild for
    a file whose mtime didn't change (e.g. content restored from backup)."""
    evicted = get_cache(request).invalidate(payload.pbix_path)
    return InvalidateResponse(pbix_path=payload.pbix_path, evicted=evicted)


@app.post("/graphs/invalidate-all", operation_id="invalidate_all_graphs", response_model=InvalidateAllResponse)
def invalidate_all_graphs(request: Request) -> InvalidateAllResponse:
    """Evict every cached graph, e.g. to free memory after a batch job."""
    return InvalidateAllResponse(evicted_count=get_cache(request).invalidate_all())


@app.post("/search", operation_id="search_nodes", response_model=NodeListResponse)
def search_nodes(payload: SearchRequest, request: Request) -> NodeListResponse:
    """Search nodes. Takes `payload`, `request`."""
    try:
        nodes = get_cache(request).search(payload.pbix_path, payload.query)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return NodeListResponse(nodes=nodes)


@app.post("/upstream", operation_id="get_upstream", response_model=NodeListResponse)
def get_upstream(payload: NodeQuery, request: Request) -> NodeListResponse:
    """Get upstream. Takes `payload`, `request`."""
    try:
        nodes = get_cache(request).upstream(payload.pbix_path, payload.node_id, payload.include_relationships)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return NodeListResponse(nodes=nodes)


@app.post("/downstream", operation_id="get_downstream", response_model=NodeListResponse)
def get_downstream(payload: NodeQuery, request: Request) -> NodeListResponse:
    """Get downstream. Takes `payload`, `request`."""
    try:
        nodes = get_cache(request).downstream(payload.pbix_path, payload.node_id, payload.include_relationships)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return NodeListResponse(nodes=nodes)


@app.post("/tree", operation_id="get_lineage_tree", response_model=TreeNode)
def get_lineage_tree(payload: TreeQuery, request: Request) -> TreeNode:
    """Get lineage tree. Takes `payload`, `request`."""
    try:
        tree = get_cache(request).tree(payload.pbix_path, payload.node_id, payload.direction, payload.max_depth)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TreeNode(**tree)


@app.post("/export", operation_id="export_graph", response_model=ExportResponse)
def export_graph(payload: ExportRequest, request: Request) -> ExportResponse:
    """Export graph. Takes `payload`, `request`."""
    try:
        paths = get_cache(request).export(payload.pbix_path, payload.output_dir)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ExportResponse(**paths)


@app.post("/source-schema", operation_id="get_source_schema", response_model=SourceSchemaResponse)
def get_source_schema(payload: SourceSchemaRequest, request: Request) -> SourceSchemaResponse:
    try:
        result = get_cache(request).source_schema(payload.pbix_path, payload.title)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SourceSchemaResponse(**result)


@app.post("/codegen", operation_id="convert_pbix_to_python", response_model=CodegenResponse)
def convert_pbix_to_python(payload: CodegenRequest, request: Request) -> CodegenResponse:
    """Convert pbix to python. Takes `payload`, `request`."""
    try:
        result = get_cache(request).codegen(payload.pbix_path, payload.output_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CodegenResponse(**result)


mcp = FastMCP.from_fastapi(app=app, name="PBIX Lineage")


@mcp.prompt
def lineage_guidance() -> str:
    """Lineage guidance."""
    return """
# PBIX Lineage Guidance

This MCP exposes the data lineage of a Power BI (.pbix) file: from its
physical source, through Power Query and the data model, down to every field
displayed in a report visual. The graph is bidirectional.

## Recommended workflow
1. Call `build_graph` once per .pbix file to parse it and get a summary.
   The graph is cached in memory and auto-rebuilt if the file changes on
   disk (mtime check) - you don't need to call it again just to "refresh".
2. Use `search_nodes` to find the node id of a column, measure, or visual
   field you are interested in (node ids look like
   `column::TableName::FieldName` or `measure::TableName::MeasureName`).
3. Use `get_upstream` or `get_lineage_tree` (direction="upstream") to trace a
   displayed field back to its physical source.
4. Use `get_downstream` or `get_lineage_tree` (direction="downstream") to see
   everything a source or column feeds into.
5. Use `export_graph` to write GraphML/CSV files for external tools
   (Gephi, yEd, a BI dashboard, etc.).
6. Use `get_source_schema` for a human-readable audit of every physical
   source down to its tables and columns (Markdown report + structured
   JSON) - useful to answer "where does this report's data actually come
   from?" without walking individual nodes.
7. Use `convert_pbix_to_python` to generate a single standalone Python file
   that reproduces the report end-to-end (extraction, Power Query
   transforms, measures, Vizro dashboard). It's best-effort: check the
   returned `stats` and search the file for "TODO" for anything that needs
   manual completion (custom M/DAX business logic has no safe automatic
   translation and is never guessed).

## Notes
- Node ids are stable and can be copied directly from `search_nodes` results.
- `get_lineage_tree` is the most convenient call for exploration: it returns
  a full nested tree in one call instead of a flat list of ancestors.
- Use `invalidate_graph`/`invalidate_all_graphs` to force a rebuild if a
  file's content changed without its mtime changing, or to free memory.
- `convert_pbix_to_python` embeds the real source connection info (URLs,
  server names, paths) it detects in the .pbix, so the generated file runs
  as-is; each one is also overridable via an environment variable.
"""


mcp_app = mcp.http_app(path="/")
app.router.lifespan_context = combine_lifespans(lineage_lifespan, mcp_app.lifespan)
app.mount("/mcp/", mcp_app)


def main() -> None:
    """Main."""
    import uvicorn

    uvicorn.run("pbix_atlas.api.app:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    main()
