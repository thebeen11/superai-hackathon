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
from .db.repository import (
    delete_watchlist_entry,
    delete_youtube_channel,
    get_youtube_channel,
    list_cleaned_items,
    list_watchlist_overrides,
    list_youtube_channels,
    list_youtube_matches,
    save_youtube_channel,
    set_watchlist_enabled,
    set_youtube_channel_enabled,
)
from .discovery import discover, discover_with_refinement
from .discovery.refine import QueryValidationError
from .discovery.supadata import SupadataError
from .discovery.youtube_channel import SourceUnavailable, resolve_channel
from .discovery.youtube_ingest import ingest_all_enabled_channels, ingest_channel
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
    YoutubeChannel,
    YoutubeIngestReport,
    YoutubeMatch,
)
from .jobs import create_job, get_job, list_jobs
from .prompts import identity
from .prompts import store as prompt_store
from .prompts.registry import PromptSpec, get_spec, list_prompt_specs
from .sse import sse_from_subscribe, sse_stream
from .youtube_poll import start_youtube_poll_timer, stop_youtube_poll_timer

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
    # No key means no channel ingestion is possible, so don't spin a thread that can only fail.
    if settings.youtube_poll_enabled and settings.supadata_api_key:
        start_youtube_poll_timer()
    yield
    stop_daily_crawl_timer()
    stop_youtube_poll_timer()


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
    """One editable block of an agent's system prompt, for the Agent Console.

    `layer` is which part of the agent it is — "soul", "rules", "mental_model",
    "personality", or "skill" (the task SOP) — and `agent` the roster id that owns it
    (null for the council-wide soul/rules and the shared mental-model library).
    """

    key: str
    label: str
    group: str
    description: str
    placeholders: list[str]
    default_text: str
    current_text: str
    is_overridden: bool
    layer: str
    agent: str | None = None


class PromptUpdate(BaseModel):
    text: str = Field(..., min_length=1, description="The new system-prompt text")


class ToolView(BaseModel):
    """One executable capability an agent can call (read-only in the console)."""

    name: str
    description: str
    io: str
    module: str


class AgentView(BaseModel):
    """One agent on the roster: its place in the council, its layers, and its tools."""

    id: str
    name: str
    role: str
    tier: int
    tier_label: str
    glyph: str
    accent: str
    tools: list[ToolView]
    skill_keys: list[str]
    personality_key: str
    mental_models: list[str]
    available_mental_models: list[str]


class MentalModelUpdate(BaseModel):
    keys: list[str] = Field(
        default_factory=list,
        description="Mental-model keys to enable; unknown keys are ignored",
    )


class PromptSection(BaseModel):
    """One heading + body of a composed system prompt."""

    heading: str
    text: str


class EffectivePrompt(BaseModel):
    """Exactly what an agent's next run sends as its system instruction."""

    agent: str
    key: str
    sections: list[PromptSection]
    text: str


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
        layer=spec.layer,
        agent=spec.agent,
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


# --- Watchlist: per-ticker on/off toggle + delete ----------------------------


class WatchlistEntry(BaseModel):
    """One watchlist override. Absence of an entry means tracked + enabled by default."""

    ticker: str
    enabled: bool
    deleted: bool


class WatchlistUpdate(BaseModel):
    enabled: bool = Field(..., description="False pauses scanning for this ticker")


@app.get("/api/watchlists", response_model=list[WatchlistEntry])
def list_watchlists() -> list[WatchlistEntry]:
    """Every watchlist override — the frontend applies `enabled` and hides `deleted`;
    the per-ticker scan skips any ticker that is disabled or deleted."""
    return [
        WatchlistEntry(ticker=o.ticker, enabled=o.enabled, deleted=o.deleted)
        for o in list_watchlist_overrides()
    ]


@app.put("/api/watchlists/{ticker}", response_model=WatchlistEntry)
def update_watchlist(ticker: str, body: WatchlistUpdate) -> WatchlistEntry:
    """Toggle scanning on/off for one ticker."""
    o = set_watchlist_enabled(ticker.upper(), body.enabled)
    return WatchlistEntry(ticker=o.ticker, enabled=o.enabled, deleted=o.deleted)


@app.delete("/api/watchlists/{ticker}", response_model=WatchlistEntry)
def remove_watchlist(ticker: str) -> WatchlistEntry:
    """Remove a ticker from the watchlist completely (tombstone — stops scanning + hides it)."""
    o = delete_watchlist_entry(ticker.upper())
    return WatchlistEntry(ticker=o.ticker, enabled=o.enabled, deleted=o.deleted)


# --- Sources → YouTube: channel subscriptions -------------------------------


class YoutubeChannelCreate(BaseModel):
    id: str = Field(
        ...,
        description="Channel URL, @handle, or UC… id — anything Supadata can resolve",
    )
    backfill: int | None = Field(
        None, ge=1, le=50,
        description="Videos to pull immediately (default YOUTUBE_CHANNEL_BACKFILL)",
    )


class YoutubeChannelUpdate(BaseModel):
    enabled: bool = Field(..., description="False pauses polling for this channel")


class YoutubeChannelAdded(BaseModel):
    """The new subscription plus what its first ingest actually found."""

    channel: YoutubeChannel
    ingest: YoutubeIngestReport


@app.get("/api/sources/youtube/channels", response_model=list[YoutubeChannel])
def list_youtube_channels_endpoint() -> list[YoutubeChannel]:
    """Every subscribed channel (tombstoned ones excluded), newest first."""
    return list_youtube_channels()


@app.post("/api/sources/youtube/channels", response_model=YoutubeChannelAdded)
def add_youtube_channel(body: YoutubeChannelCreate) -> YoutubeChannelAdded:
    """Subscribe to a channel and immediately backfill its most recent videos.

    Re-adding a tombstoned channel revives it rather than duplicating it, and the backfill
    skips videos already ingested — so an accidental delete costs no Supadata credits.
    """
    try:
        resolved = resolve_channel(body.id.strip())
    except SourceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SupadataError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    existing = get_youtube_channel(resolved.channel_id)
    if existing and not existing.deleted:
        raise HTTPException(
            status_code=409,
            detail=f"Already following {existing.name}",
        )

    channel = save_youtube_channel(resolved)
    try:
        report = ingest_channel(
            channel, limit=body.backfill or settings.youtube_channel_backfill
        )
    except Exception as exc:  # noqa: BLE001 - the subscription stands even if the first pull fails
        # The channel row is already committed, so failing the request here would leave the
        # user with an error and a subscription that appears on the next load. Report the
        # failure in the payload instead; the next poll retries.
        logging.getLogger(__name__).warning(
            "Backfill failed for %s: %s", resolved.channel_id, exc
        )
        report = YoutubeIngestReport(channels=1, errors=[str(exc)])
    return YoutubeChannelAdded(channel=channel, ingest=report)


@app.put("/api/sources/youtube/channels/{channel_id}", response_model=YoutubeChannel)
def update_youtube_channel(channel_id: str, body: YoutubeChannelUpdate) -> YoutubeChannel:
    """Pause or resume polling for one channel."""
    return set_youtube_channel_enabled(channel_id, body.enabled)


@app.delete("/api/sources/youtube/channels/{channel_id}", response_model=YoutubeChannel)
def remove_youtube_channel(channel_id: str) -> YoutubeChannel:
    """Unfollow a channel (tombstone — stops polling; its ingested videos are retained)."""
    return delete_youtube_channel(channel_id)


@app.post("/api/sources/youtube/channels/{channel_id}/refresh", response_model=YoutubeIngestReport)
def refresh_youtube_channel(channel_id: str) -> YoutubeIngestReport:
    """Pull one channel's new videos now, without waiting for the poll interval."""
    channel = get_youtube_channel(channel_id)
    if channel is None or channel.deleted:
        raise HTTPException(status_code=404, detail=f"Unknown channel: {channel_id!r}")
    try:
        return ingest_channel(channel)
    except SourceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/sources/youtube/poll", response_model=YoutubeIngestReport)
def poll_youtube_channels() -> YoutubeIngestReport:
    """Poll every enabled channel — the Cloud Scheduler hook (see deploy.sh).

    Cloud Run scales to zero, so the in-process timer is for local runs only; in prod this
    endpoint is the real trigger.
    """
    return ingest_all_enabled_channels()


@app.get("/api/sources/youtube/matches", response_model=list[YoutubeMatch])
def list_youtube_matches_endpoint(
    ticker: str | None = Query(None, description="Canonical symbol, e.g. $NVDA"),
    channel_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> list[YoutubeMatch]:
    """Watchlist moments found in subscribed channels' transcripts, newest first."""
    return list_youtube_matches(ticker=ticker, channel_id=channel_id, limit=limit)


# --- Agent Console: the roster (soul, mental models, personality, tools) -----


def _agent_view(spec: identity.AgentSpec) -> AgentView:
    """Build the console view for one agent, including its enabled frameworks."""
    return AgentView(
        id=spec.id,
        name=spec.name,
        role=spec.role,
        tier=spec.tier,
        tier_label=spec.tier_label,
        glyph=spec.glyph,
        accent=spec.accent,
        tools=[ToolView(**vars(t)) for t in spec.tools],
        skill_keys=identity.skills_for(spec.id),
        personality_key=identity.personality_key(spec.id),
        mental_models=identity.mental_models_for(spec.id),
        available_mental_models=[s.key for s in identity.mental_model_specs()],
    )


@app.get("/api/agents", response_model=list[AgentView])
def list_agents() -> list[AgentView]:
    """The agent roster in council order (Tier 1 → Tier 5)."""
    return [_agent_view(spec) for spec in identity.AGENTS]


@app.put("/api/agents/{agent_id}/mental-models", response_model=AgentView)
def set_agent_mental_models(agent_id: str, body: MentalModelUpdate) -> AgentView:
    """Choose which reasoning frameworks this agent runs (takes effect on the next run)."""
    spec = identity.get_agent(agent_id)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent_id!r}")
    identity.set_mental_models(agent_id, body.keys)
    return _agent_view(spec)


@app.delete("/api/agents/{agent_id}/mental-models", response_model=AgentView)
def reset_agent_mental_models(agent_id: str) -> AgentView:
    """Restore this agent's built-in set of frameworks."""
    spec = identity.get_agent(agent_id)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent_id!r}")
    identity.reset_mental_models(agent_id)
    return _agent_view(spec)


@app.get("/api/agents/{agent_id}/effective-prompt", response_model=EffectivePrompt)
def agent_effective_prompt(
    agent_id: str,
    key: str = Query(..., description="A skill prompt key owned by this agent"),
) -> EffectivePrompt:
    """The fully composed system prompt this agent will send for `key`.

    Placeholders are left as literal tokens (their values are only known mid-run), and the
    JSON output contract that `llm/vertex.py` appends is not included.
    """
    agent = identity.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent_id!r}")
    skill = get_spec(key)
    if skill is None or key not in identity.skills_for(agent_id):
        raise HTTPException(
            status_code=404, detail=f"{agent_id!r} does not run a skill named {key!r}"
        )
    sections = identity.compose(skill, agent_id)
    return EffectivePrompt(
        agent=agent_id,
        key=key,
        sections=[PromptSection(heading=h, text=t) for h, t in sections],
        text=identity.render(sections),
    )


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
