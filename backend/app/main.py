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
from .council import (
    latest_council,
    resolve_ledger,
    run_council,
    run_thematic,
    run_ticker_debate,
)
from .crawl import (
    run_council_safe as _run_council_safe,
    run_daily_crawl,
    start_daily_crawl_timer,
    stop_daily_crawl_timer,
)
from .dataeng import process_discovery_result
from .db.repository import (
    delete_watchlist_entries,
    delete_watchlist_entry,
    delete_youtube_channel,
    get_latest_thematic_run,
    get_latest_ticker_debate_run,
    get_thematic_run,
    get_ticker_debate_run,
    get_youtube_channel,
    list_cleaned_items,
    list_thematic_runs,
    list_ticker_debate_runs,
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
    ThematicRun,
    ThematicRunRef,
    TickerDebateRun,
    TickerDebateRunRef,
    YoutubeChannel,
    YoutubeIngestReport,
    YoutubeJobRef,
    YoutubeMatch,
)
from .jobs import create_job, get_job, list_jobs
from .prompts import identity
from .prompts import store as prompt_store
from .prompts.registry import PromptSpec, get_spec, list_prompt_specs
from .sse import run_detached, sse_from_subscribe, sse_stream
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
    """Override one prompt with user-supplied text (takes effect on the next agent run).

    A declared placeholder is refused if the new text drops it. Substitution is a plain
    token replace that never errors (`prompts.registry._fill`), so a prompt missing its
    `{signposts}` / `{taxonomy}` / `{sectors}` block does not fail — it quietly ships
    without the fixed list the downstream parser matches against, and the agent returns
    nothing the dashboard can render. Catching it at save time is the only honest moment.
    """
    spec = get_spec(key)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Unknown prompt key: {key!r}")
    missing = [p for p in spec.placeholders if "{" + p + "}" not in body.text]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{spec.label} must keep its placeholder(s): "
                + ", ".join("{" + p + "}" for p in missing)
                + " — the text that replaces them is what the agent grades against."
            ),
        )
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


class WatchlistBulkDelete(BaseModel):
    tickers: list[str] = Field(
        default_factory=list,
        description="Tickers to remove; case and a leading '$' are normalised away",
    )


def _normalise_ticker(raw: str) -> str:
    """The frontend sends the bare form ('NVDA'), the corpus the canonical one ('$NVDA')."""
    return raw.strip().lstrip("$").upper()


def _canonical_ticker(raw: str) -> str:
    """The '$NVDA' form `cleaned_items.entities` is keyed on, from either input form."""
    return f"${_normalise_ticker(raw)}"


@app.get("/api/watchlists", response_model=list[WatchlistEntry])
def list_watchlists() -> list[WatchlistEntry]:
    """Every watchlist override — the frontend applies `enabled` and hides `deleted`;
    the per-ticker scan skips any ticker that is disabled or deleted."""
    return [
        WatchlistEntry(ticker=o.ticker, enabled=o.enabled, deleted=o.deleted)
        for o in list_watchlist_overrides()
    ]


@app.post("/api/watchlists/bulk-delete", response_model=list[WatchlistEntry])
def bulk_delete_watchlists(body: WatchlistBulkDelete) -> list[WatchlistEntry]:
    """Remove several tickers at once (same tombstone as the single-ticker DELETE).

    Declared ahead of the `{ticker}` routes so the literal path segment reads as the more
    specific match. Like those routes it never 404s: any ticker is upsertable, so an unknown
    one simply gets a tombstone of its own.
    """
    tickers = [t for t in (_normalise_ticker(r) for r in body.tickers) if t]
    return [
        WatchlistEntry(ticker=o.ticker, enabled=o.enabled, deleted=o.deleted)
        for o in delete_watchlist_entries(tickers)
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
#
# Ingest never runs inside a request: four Gemini calls per video plus a judge call per
# matched ticker puts a five-video backfill in the tens of minutes. Subscribing is instant;
# fetching is a background job the client attaches to (streamed) or polls for (detached).

# Label for the whole-poll job, distinguishing it from per-channel jobs (labelled by id).
_POLL_JOB_LABEL = "*all-channels*"


class YoutubeChannelCreate(BaseModel):
    id: str = Field(
        ...,
        description="Channel URL, @handle, or UC… id — anything Supadata can resolve",
    )
    # No `backfill` here: subscribing no longer fetches anything. Pass `?limit=` to
    # `/channels/{id}/refresh/stream` to choose how much of the back catalogue to pull.


class YoutubeChannelUpdate(BaseModel):
    enabled: bool = Field(..., description="False pauses polling for this channel")


def _running_youtube_job(channel_id: str | None) -> dict | None:
    """The in-flight ingest for `channel_id` (or the whole-poll job), if there is one.

    Ingesting the same channel twice concurrently would fetch every transcript twice before
    either run records to `youtube_videos` — Supadata bills per transcript, so the guard is
    a cost control, not just tidiness.
    """
    label = channel_id or _POLL_JOB_LABEL
    for summary in list_jobs(status="running"):
        if summary["kind"] == "youtube" and summary["query"] == label:
            return summary
    return None


@app.get("/api/sources/youtube/channels", response_model=list[YoutubeChannel])
def list_youtube_channels_endpoint() -> list[YoutubeChannel]:
    """Every subscribed channel (tombstoned ones excluded), newest first."""
    return list_youtube_channels()


@app.post("/api/sources/youtube/channels", response_model=YoutubeChannel)
def add_youtube_channel(body: YoutubeChannelCreate) -> YoutubeChannel:
    """Subscribe to a channel. Returns as soon as the channel resolves — no ingest here.

    Pulling the backfill takes minutes per video (four Gemini calls each, plus a judge call
    per matched ticker), so it is a separate streamed call: follow up with
    `POST /api/sources/youtube/channels/{id}/refresh/stream` to watch it run.

    Re-adding a tombstoned channel revives it rather than duplicating it.
    """
    try:
        resolved = resolve_channel(body.id.strip())
    except SourceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SupadataError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    existing = get_youtube_channel(resolved.channel_id)
    if existing and not existing.deleted:
        raise HTTPException(status_code=409, detail=f"Already following {existing.name}")

    return save_youtube_channel(resolved)


@app.put("/api/sources/youtube/channels/{channel_id}", response_model=YoutubeChannel)
def update_youtube_channel(channel_id: str, body: YoutubeChannelUpdate) -> YoutubeChannel:
    """Pause or resume polling for one channel."""
    return set_youtube_channel_enabled(channel_id, body.enabled)


@app.delete("/api/sources/youtube/channels/{channel_id}", response_model=YoutubeChannel)
def remove_youtube_channel(channel_id: str) -> YoutubeChannel:
    """Unfollow a channel (tombstone — stops polling; its ingested videos are retained)."""
    return delete_youtube_channel(channel_id)


def _channel_or_404(channel_id: str) -> YoutubeChannel:
    channel = get_youtube_channel(channel_id)
    if channel is None or channel.deleted:
        raise HTTPException(status_code=404, detail=f"Unknown channel: {channel_id!r}")
    return channel


@app.post("/api/sources/youtube/channels/{channel_id}/refresh", response_model=YoutubeIngestReport)
def refresh_youtube_channel(channel_id: str) -> YoutubeIngestReport:
    """Pull one channel's new videos now, blocking until done.

    Kept for scripted callers that want the report in the response. Interactive clients
    should use the `/stream` variant — this one can take minutes per video.
    """
    channel = _channel_or_404(channel_id)
    running = _running_youtube_job(channel_id)
    if running is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Already fetching {channel.name}; follow /api/jobs/{running['id']}/stream",
        )
    try:
        return ingest_channel(channel)
    except SourceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/sources/youtube/channels/{channel_id}/refresh/stream")
def refresh_youtube_channel_stream(
    channel_id: str,
    limit: int | None = Query(None, ge=1, le=50, description="Videos to pull (default: poll limit)"),
):
    """Pull one channel's new videos, streaming progress as SSE.

    The work runs on a background thread that outlives the response, so closing the tab
    does not abandon a half-finished ingest — reattach later via
    `GET /api/jobs/{job_id}/stream`. The job id arrives as a leading `job` frame.
    """
    channel = _channel_or_404(channel_id)

    # Already fetching this channel: attach to that run instead of starting a second one,
    # which would re-buy every transcript. `subscribe()` replays what it has missed first,
    # so a second viewer sees the whole run, not just the tail.
    running = _running_youtube_job(channel_id)
    if running is not None:
        existing = get_job(running["id"])
        if existing is not None:
            return sse_from_subscribe(existing.subscribe())

    job = create_job("youtube", channel_id)

    def work(emit: Emit) -> YoutubeIngestReport:
        return ingest_channel(channel, limit=limit, emit=emit)

    return sse_stream(work, job=job)


@app.post("/api/sources/youtube/poll", response_model=YoutubeJobRef, status_code=202)
def poll_youtube_channels() -> YoutubeJobRef:
    """Poll every enabled channel — the Cloud Scheduler hook (see deploy.sh).

    Returns 202 immediately and runs detached: a poll over several channels can exceed
    Scheduler's attempt deadline, and a timeout there would retry the whole thing and
    re-buy transcripts. Per-channel failures are recorded on the channel row (`last_error`)
    and shown in the UI; overall progress is on the returned job.
    """
    running = _running_youtube_job(None)
    if running is not None:
        return YoutubeJobRef(job_id=running["id"], status=running["status"])

    job = create_job("youtube", _POLL_JOB_LABEL)
    run_detached(job, ingest_all_enabled_channels)
    return YoutubeJobRef(job_id=job.id)


@app.get("/api/sources/youtube/jobs", response_model=list[YoutubeJobRef])
def list_youtube_jobs() -> list[YoutubeJobRef]:
    """In-flight ingests, so a client that reloads mid-run can reattach to their streams."""
    return [
        YoutubeJobRef(
            job_id=j["id"],
            channel_id=None if j["query"] == _POLL_JOB_LABEL else j["query"],
            status=j["status"],
        )
        for j in list_jobs(status="running")
        if j["kind"] == "youtube"
    ]


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
    """Reconnect to a job: replay its progress so far, then stream live to completion.

    Kept at this path for existing clients; `/api/jobs/{id}/stream` is the same thing under
    a name that isn't specific to Data Engineering.
    """
    return job_stream(job_id)


@app.get("/api/jobs/{job_id}/stream")
def job_stream(job_id: str):
    """Attach to any background job: replay its progress, then stream live to completion."""
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


# --- Thematic Analysis (Tier 5, weekly) -------------------------------------
#
# `/latest` is declared before `/{run_id}` so the literal segment wins the match, the same
# ordering rule as /api/watchlists/bulk-delete.


@app.post("/api/thematic/run", response_model=ThematicRun)
def run_thematic_endpoint() -> ThematicRun:
    """Run this week's Thematic Analysis and persist it as a dated run.

    The target of the weekly `thematic-weekly` Cloud Scheduler job, and the manual trigger.
    """
    return run_thematic()


@app.post("/api/thematic/run/stream")
def run_thematic_stream():
    """Streaming version of /api/thematic/run (progress + job reconnect)."""
    job = create_job("thematic", "thematic")
    return sse_stream(lambda emit: run_thematic(emit=emit), job=job)


@app.get("/api/thematic/runs", response_model=list[ThematicRunRef])
def list_thematic_runs_endpoint(
    limit: int = Query(52, ge=1, le=200, description="How many runs to list, newest first"),
) -> list[ThematicRunRef]:
    """Dated run headers for the run picker, newest first."""
    return list_thematic_runs(limit=limit)


@app.get("/api/thematic/runs/latest", response_model=ThematicRun | None)
def latest_thematic_run() -> ThematicRun | None:
    """The most recent thematic run, or null before the first one has been made."""
    return get_latest_thematic_run()


@app.get("/api/thematic/runs/{run_id}", response_model=ThematicRun)
def get_thematic_run_endpoint(run_id: int) -> ThematicRun:
    """One past run, by id."""
    run = get_thematic_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"No thematic run with id {run_id}")
    return run


# --- Single-ticker Debate Chamber (Tier 4, on demand) ------------------------
#
# The council-wide debate lives on /council/*; this is the same chamber pointed at one
# name, run from that ticker's page. `/latest` is declared before `/{run_id}` so the
# literal segment wins the match, the same ordering rule as /api/thematic/runs/latest.


@app.post("/api/tickers/{ticker}/debate", response_model=TickerDebateRun)
def run_ticker_debate_endpoint(ticker: str) -> TickerDebateRun:
    """Debate one ticker over the corpus that mentions it, and persist a dated run."""
    return run_ticker_debate(_canonical_ticker(ticker))


@app.post("/api/tickers/{ticker}/debate/stream")
def run_ticker_debate_stream(ticker: str):
    """Streaming version of the ticker debate (per-round progress + job reconnect)."""
    symbol = _canonical_ticker(ticker)
    job = create_job("ticker-debate", symbol)
    return sse_stream(lambda emit: run_ticker_debate(symbol, emit=emit), job=job)


@app.get("/api/tickers/{ticker}/debates", response_model=list[TickerDebateRunRef])
def list_ticker_debates(
    ticker: str,
    limit: int = Query(20, ge=1, le=200, description="How many runs to list, newest first"),
) -> list[TickerDebateRunRef]:
    """Dated run headers for this ticker's run picker, newest first."""
    return list_ticker_debate_runs(_canonical_ticker(ticker), limit=limit)


@app.get("/api/tickers/{ticker}/debates/latest", response_model=TickerDebateRun | None)
def latest_ticker_debate(ticker: str) -> TickerDebateRun | None:
    """The most recent debate on this ticker, or null before one has been run."""
    return get_latest_ticker_debate_run(_canonical_ticker(ticker))


@app.get("/api/tickers/{ticker}/debates/{run_id}", response_model=TickerDebateRun)
def get_ticker_debate(ticker: str, run_id: int) -> TickerDebateRun:
    """One past debate, by id. 404s when the id belongs to a different ticker."""
    run = get_ticker_debate_run(run_id)
    if run is None or run.ticker != _canonical_ticker(ticker):
        raise HTTPException(status_code=404, detail=f"No debate with id {run_id} for {ticker}")
    return run


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
