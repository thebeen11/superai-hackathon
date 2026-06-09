"""FastAPI entrypoint. Exposes Discovery (Layer 1) and Data Engineering (Layer 2)."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .dataeng import process_discovery_result
from .db.repository import list_cleaned_items
from .discovery import discover, discover_with_refinement
from .discovery.refine import QueryValidationError
from .models import (
    CleanedItem,
    Clarify,
    ClarificationMode,
    DataEngReport,
    DiscoveryResult,
)
from .sse import sse_stream

logging.basicConfig(level=logging.INFO)


def _operation_id(route: APIRoute) -> str:
    """Use the route's function name as the OpenAPI operationId.

    Keeps the generated frontend SDK names clean (e.g. `listItems`,
    `discoverPost`) instead of FastAPI's verbose `list_items_items_get`.
    """
    return route.name


app = FastAPI(
    title="Hedge Fund AI Agent Council — API",
    version="0.1.0",
    docs_url="/docs",       # Swagger UI
    redoc_url=None,         # disabled here; served below from a self-hosted bundle
    generate_unique_id_function=_operation_id,
)

# Serve static assets (self-hosted ReDoc bundle) so the API reference renders
# without depending on an external CDN (works offline / behind restricted networks).
_STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/redoc", include_in_schema=False)
def redoc_html():
    """ReDoc API reference, rendered from the locally bundled JS (no CDN)."""
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} — ReDoc",
        redoc_js_url="/static/redoc.standalone.js",
        with_google_fonts=False,
    )

# CORS so the Next.js frontend can consume the JSON and SSE endpoints. For the
# hackathon this is permissive; tighten `allow_origins` before any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- request bodies ---

class DiscoverRequest(BaseModel):
    query: str
    mode: ClarificationMode = ClarificationMode.INTERACTIVE
    max_results: int | None = Field(default=None, ge=1, le=50)


class ClarifyRequest(BaseModel):
    clarified_query: str
    round: int = Field(default=1, ge=1)
    mode: ClarificationMode = ClarificationMode.INTERACTIVE
    max_results: int | None = Field(default=None, ge=1, le=50)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/discover", response_model=DiscoveryResult)
def discover_get(
    query: str = Query(..., description="Research topic, e.g. 'AI memory chip demand'"),
    max_results: int | None = Query(None, ge=1, le=50),
) -> DiscoveryResult:
    """Plain fan-out without refinement — kept for the CLI / back-compat."""
    try:
        return discover(query, max_results=max_results)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/discover")
def discover_post(body: DiscoverRequest) -> DiscoveryResult | Clarify:
    """Refine the query, then fan out. May return clarifying questions (interactive)."""
    try:
        return discover_with_refinement(
            body.query, mode=body.mode, round=0, max_results=body.max_results
        )
    except QueryValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/discover/clarify")
def discover_clarify(body: ClarifyRequest) -> DiscoveryResult | Clarify:
    """Resume an interactive run with a clarified query (round cap enforced in refine)."""
    try:
        return discover_with_refinement(
            body.clarified_query, mode=body.mode, round=body.round,
            max_results=body.max_results,
        )
    except QueryValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/dataeng/process", response_model=DataEngReport)
def dataeng_process(result: DiscoveryResult) -> DataEngReport:
    """Run Layer 2 (clean + label + theme + persist) over a DiscoveryResult."""
    return process_discovery_result(result)


@app.get("/items", response_model=list[CleanedItem])
def list_items(
    stream: str | None = Query(None, description="Filter by MACRO or MICRO"),
    theme: str | None = Query(None, description="Filter by a market theme, e.g. 'Solar'"),
    ticker: str | None = Query(None, description="Filter by a resolved entity, e.g. '$META'"),
    limit: int = Query(50, ge=1, le=200),
) -> list[CleanedItem]:
    """Read persisted, cleaned + labelled items (newest first), with optional filters."""
    return list_cleaned_items(stream=stream, theme=theme, ticker=ticker, limit=limit)


# --- SSE streaming variants -------------------------------------------------
# Each mirrors a JSON endpoint above but streams behind-the-scenes progress as
# Server-Sent Events, ending with a terminal `result` (or `error`) event.
# Consume from the browser via EventSource (GET) or fetch + ReadableStream (POST).


@app.get("/discover/stream")
def discover_get_stream(
    query: str = Query(..., description="Research topic, e.g. 'AI memory chip demand'"),
    max_results: int | None = Query(None, ge=1, le=50),
):
    """Streaming version of GET /discover (plain fan-out, no refinement)."""
    return sse_stream(lambda emit: discover(query, max_results=max_results, emit=emit))


@app.post("/discover/stream")
def discover_post_stream(body: DiscoverRequest):
    """Streaming version of POST /discover (refine, then fan out)."""
    return sse_stream(
        lambda emit: discover_with_refinement(
            body.query, mode=body.mode, round=0, max_results=body.max_results, emit=emit
        )
    )


@app.post("/discover/clarify/stream")
def discover_clarify_stream(body: ClarifyRequest):
    """Streaming version of POST /discover/clarify."""
    return sse_stream(
        lambda emit: discover_with_refinement(
            body.clarified_query, mode=body.mode, round=body.round,
            max_results=body.max_results, emit=emit,
        )
    )


@app.post("/dataeng/process/stream")
def dataeng_process_stream(result: DiscoveryResult):
    """Streaming version of POST /dataeng/process (per-item progress)."""
    return sse_stream(lambda emit: process_discovery_result(result, emit=emit))


@app.get("/items/stream")
def list_items_stream(
    stream: str | None = Query(None, description="Filter by MACRO or MICRO"),
    theme: str | None = Query(None, description="Filter by a market theme, e.g. 'Solar'"),
    ticker: str | None = Query(None, description="Filter by a resolved entity, e.g. '$META'"),
    limit: int = Query(50, ge=1, le=200),
):
    """Streaming version of GET /items (emits a query step, then the rows)."""

    def work(emit):
        emit("items", "Querying persisted items", status="start",
             filters={"stream": stream, "theme": theme, "ticker": ticker, "limit": limit})
        items = list_cleaned_items(stream=stream, theme=theme, ticker=ticker, limit=limit)
        emit("items", f"Found {len(items)} items", status="ok", count=len(items))
        return items

    return sse_stream(work)
