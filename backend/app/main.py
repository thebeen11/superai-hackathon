"""FastAPI entrypoint. Exposes Discovery (Layer 1) and Data Engineering (Layer 2)."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import settings
from .council import latest_council, resolve_ledger, run_council
from .crawl import (
    run_council_safe as _run_council_safe,
    run_daily_crawl,
    start_daily_crawl_timer,
    stop_daily_crawl_timer,
)
from .dataeng import process_discovery_result
from .db.repository import list_cleaned_items
from .discovery import discover, discover_with_refinement
from .discovery.refine import QueryValidationError
from .events import Emit
from .insights.context import tracker_context
from .models import (
    CleanedItem,
    Clarify,
    ClarificationMode,
    ContextPreview,
    CouncilReport,
    DataEngReport,
    DiscoveryResult,
)
from .jobs import create_job, get_job, list_jobs
from .prompts import store as prompt_store
from .prompts.registry import PromptSpec, get_spec, list_prompt_specs
from .sse import sse_from_subscribe, sse_stream

logging.basicConfig(level=logging.INFO)


def _operation_id(route: APIRoute) -> str:
    """Use the route's function name as the OpenAPI operationId.

    Keeps the generated frontend SDK names clean (e.g. `listItems`,
    `discoverPost`) instead of FastAPI's verbose `list_items_items_get`.
    """
    return route.name


@asynccontextmanager
async def _lifespan(app: FastAPI):
    if settings.daily_crawl_enabled:
        start_daily_crawl_timer()
    yield
    stop_daily_crawl_timer()


app = FastAPI(
    title="Hedge Fund AI Agent Council — API",
    version="0.1.0",
    docs_url="/docs",       # Swagger UI
    redoc_url=None,         # disabled here; served below from a self-hosted bundle
    generate_unique_id_function=_operation_id,
    lifespan=_lifespan,
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


class PromptView(BaseModel):
    """One editable system prompt + its current/default text for the Agent Console."""

    key: str
    label: str
    group: str
    description: str
    placeholders: list[str]
    default_text: str
    current_text: str
    is_overridden: bool


class PromptUpdate(BaseModel):
    text: str = Field(..., min_length=1, description="The new system-prompt text")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/discover", response_model=DiscoveryResult)
def discover_get(
    query: str = Query(..., description="Research topic, e.g. 'AI memory chip demand'"),
    max_results: int | None = Query(None, ge=1, le=50),
    start_published_date: str | None = Query(
        None, description="ISO date lower bound on published date, e.g. '2025-06-01'"
    ),
    end_published_date: str | None = Query(
        None, description="ISO date upper bound on published date, e.g. '2025-06-30'"
    ),
) -> DiscoveryResult:
    """Plain fan-out without refinement — kept for the CLI / back-compat / backfills."""
    try:
        return discover(
            query,
            max_results=max_results,
            start_published_date=start_published_date,
            end_published_date=end_published_date,
        )
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


@app.post("/crawl/daily", response_model=DataEngReport)
def crawl_daily(
    day: str | None = Query(
        None, description="UTC day to crawl (YYYY-MM-DD). Default: yesterday (UTC)."
    ),
) -> DataEngReport:
    """Crawl one day's news through the full pipeline (Cloud Scheduler / cron hook)."""
    try:
        parsed = date.fromisoformat(day) if day else None
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"Invalid day {day!r}: expected YYYY-MM-DD"
        ) from exc
    return run_daily_crawl(parsed)


@app.post("/dataeng/process", response_model=DataEngReport)
def dataeng_process(result: DiscoveryResult) -> DataEngReport:
    """Run Layer 2 (clean + label + theme + persist), then convene the council."""
    report = process_discovery_result(result)
    _run_council_safe()  # auto-chain Tiers 3–5 over the freshly persisted corpus
    return report


@app.get("/items", response_model=list[CleanedItem])
def list_items(
    stream: str | None = Query(None, description="Filter by MACRO or MICRO"),
    theme: str | None = Query(None, description="Filter by a market theme, e.g. 'Solar'"),
    ticker: str | None = Query(None, description="Filter by a resolved entity, e.g. '$META'"),
    limit: int = Query(50, ge=1, le=200),
) -> list[CleanedItem]:
    """Read persisted, cleaned + labelled items (newest first), with optional filters."""
    return list_cleaned_items(stream=stream, theme=theme, ticker=ticker, limit=limit)


@app.get("/api/trackers/{tracker}/context", response_model=ContextPreview)
def tracker_context_endpoint(tracker: str) -> ContextPreview:
    """Best evidence quote for a tracker (theme) + a real 0..1 relevance score (§7.1)."""
    preview = tracker_context(tracker)
    if preview is None:
        raise HTTPException(status_code=404, detail=f"No stored items for tracker {tracker!r}")
    return preview


# --- Agent Console: editable system prompts ---------------------------------


def _prompt_view(spec: PromptSpec) -> PromptView:
    """Build the console view for one prompt (override text if set, else the default)."""
    override = prompt_store.get_override(spec.key)
    return PromptView(
        key=spec.key,
        label=spec.label,
        group=spec.group,
        description=spec.description,
        placeholders=list(spec.placeholders),
        default_text=spec.default_template,
        current_text=override if override is not None else spec.default_template,
        is_overridden=override is not None,
    )


@app.get("/api/prompts", response_model=list[PromptView])
def list_prompts() -> list[PromptView]:
    """Every agent system prompt with its default and current (possibly overridden) text."""
    return [_prompt_view(spec) for spec in list_prompt_specs()]


@app.put("/api/prompts/{key}", response_model=PromptView)
def update_prompt(key: str, body: PromptUpdate) -> PromptView:
    """Override one prompt with user-supplied text (takes effect on the next agent run)."""
    spec = get_spec(key)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Unknown prompt key: {key!r}")
    prompt_store.set_override(key, body.text)
    return _prompt_view(spec)


@app.delete("/api/prompts/{key}", response_model=PromptView)
def reset_prompt(key: str) -> PromptView:
    """Reset one prompt back to its built-in default."""
    spec = get_spec(key)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Unknown prompt key: {key!r}")
    prompt_store.delete_override(key)
    return _prompt_view(spec)


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
    """Streaming version of POST /dataeng/process (per-item progress).

    Registers a Job so a client that reloads mid-run can reconnect via
    /dataeng/jobs/{id}/stream. The job id is sent as a leading `job` SSE frame.
    """
    label = result.query or result.original_query or "discovery"
    job = create_job("dataeng", label)

    def work(emit: Emit) -> DataEngReport:
        report = process_discovery_result(result, emit=emit)
        _run_council_safe(emit)  # auto-chain Tiers 3–5 on the same SSE stream
        return report

    return sse_stream(work, job=job)


@app.get("/dataeng/jobs")
def dataeng_jobs(status: str | None = Query("running", description="Filter by job status")):
    """List tracked discovery jobs (running by default) so a reloaded client can find one."""
    return list_jobs(status=status)


@app.get("/dataeng/jobs/{job_id}/stream")
def dataeng_job_stream(job_id: str):
    """Reconnect to a job: replay its progress so far, then stream live to completion."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Unknown job: {job_id}")
    return sse_from_subscribe(job.subscribe())


# --- Council (Tiers 3–5: Andie / Freddy / Winston) --------------------------


@app.post("/council/run", response_model=CouncilReport)
def run_council_endpoint() -> CouncilReport:
    """Run Tiers 3–5 on-demand over the persisted corpus and return the snapshot."""
    return run_council()


@app.post("/council/run/stream")
def run_council_stream():
    """Streaming version of /council/run (per-tier progress + job reconnect)."""
    job = create_job("council", "council")
    return sse_stream(lambda emit: run_council(emit=emit), job=job)


@app.get("/council/latest", response_model=CouncilReport | None)
def council_latest() -> CouncilReport | None:
    """The most recent council snapshot, or null if none has run yet."""
    return latest_council()


@app.post("/council/resolve")
def council_resolve() -> dict[str, int]:
    """Score predictions whose window has passed and refresh the Brier ledger."""
    return {"resolved": resolve_ledger()}


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
