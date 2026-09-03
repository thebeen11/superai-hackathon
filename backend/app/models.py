"""Normalized data shapes shared across the pipeline.

The Discovery layer's only job is to turn a topic query into a list of
`SourceItem`s. From here on, an Exa article and a YouTube transcript look the
same to the rest of the council — the only difference is that a video carries
timestamped `segments` so the UI can deep-link to HH:MM:SS.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, model_validator


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SourceType(str, Enum):
    WEB = "web"
    YOUTUBE = "youtube"


class ClarificationMode(str, Enum):
    """Controls how an ambiguous query is handled (Req 2.4)."""

    INTERACTIVE = "interactive"   # default: pause and ask the Commander
    AUTO_PROCEED = "auto_proceed"  # skip the pause, use a best-effort refined query


class QueryClassification(str, Enum):
    CLEAR = "clear"
    AMBIGUOUS = "ambiguous"


class TranscriptSegment(BaseModel):
    """A timestamped slice of a video transcript (seconds from start)."""

    start: float
    text: str


class SourceItem(BaseModel):
    """One discovered piece of content, normalized across sources."""

    source_type: SourceType
    title: str
    url: str
    text: str
    author: str | None = None          # channel name / article author
    published_at: str | None = None     # ISO date if the source provides one
    segments: list[TranscriptSegment] = Field(default_factory=list)
    retrieved_at: datetime = Field(default_factory=_now)


class SkippedSource(BaseModel):
    """A source/branch we could not ingest — surfaced, never silently dropped."""

    source_type: SourceType
    reason: str


class DiscoveryResult(BaseModel):
    """What the Discovery agent returns for a single topic query."""

    query: str
    items: list[SourceItem] = Field(default_factory=list)
    skipped: list[SkippedSource] = Field(default_factory=list)
    # Audit trail for query refinement (Req 2.3). `query` is the query actually used
    # for fan-out; `original_query` is what the Commander submitted.
    original_query: str | None = None
    refinement_note: str | None = None  # e.g. "proceeded without clarification" / fallback

    @property
    def count(self) -> int:
        return len(self.items)


# --- Query Refinement & Clarification (Req 2) ---

class RefineLLMOutput(BaseModel):
    """Schema enforced on the LLM reply for query refinement."""

    classification: QueryClassification
    refined_query: str
    clarifying_questions: list[str] = Field(default_factory=list)


class Proceed(BaseModel):
    """Refinement decided discovery can proceed with `refined_query`."""

    original_query: str
    refined_query: str
    proceeded_without_clarification: bool = False  # ambiguous + auto-proceed (Req 2.6)
    refinement_failed: bool = False                # LLM failure fallback (Req 2.9)


class Clarify(BaseModel):
    """Refinement needs the Commander to clarify (interactive mode, Req 2.5)."""

    original_query: str
    questions: list[str]
    round: int


# --- Data Engineering (Layer 2) ---

class Stream(str, Enum):
    MACRO = "MACRO"   # economy-wide signal
    MICRO = "MICRO"   # company-specific signal


class ResolvedEntity(BaseModel):
    """A canonical entity (ticker or macro entity) with the aliases that matched it."""

    canonical: str                                   # "$META" or "Federal_Reserve"
    mentions: list[str] = Field(default_factory=list)


class CleanedItem(BaseModel):
    """The unit persisted to Postgres after Data Engineering (Req 14, 15)."""

    source_url: str                                  # non-empty, == origin (Req 13.1)
    source_type: SourceType
    title: str
    clean_text: str
    stream: Stream                                   # MACRO | MICRO
    industry: str                                    # sector or "Unclassified"
    entities: list[ResolvedEntity] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)  # from Market_Theme_Taxonomy
    segments: list[TranscriptSegment] = Field(default_factory=list)  # video provenance
    author: str | None = None                        # byline / channel name, when the source gives one
    published_at: str | None = None                  # ISO8601, nullable (Req 14)
    retrieved_at: datetime | None = None             # UTC when Discovery fetched it
    ingested_at: datetime = Field(default_factory=_now)  # UTC at persist time (Req 14)


class ProcessingFailure(BaseModel):
    """A SourceItem that could not be processed/persisted — surfaced, not hidden."""

    source_url: str | None = None
    reason: str


class DataEngReport(BaseModel):
    """Batch outcome of a Data Engineering run (Req 7.4, 7.5)."""

    persisted: int = 0
    failed: int = 0
    failures: list[ProcessingFailure] = Field(default_factory=list)


class ContextPreview(BaseModel):
    """Best evidence quote for a tracker (theme) + a relevance score (Core Feature §7.1).

    Surfaced by `GET /api/trackers/{tracker}/context`. `score` is a real 0..1 semantic
    relevance of the quote to the tracker concept — never a placeholder. Every preview is
    anchored to a real `source_url`-backed item (no-orphan guardrail §12.6).
    """

    tracker: str
    channel: str            # host of the source (e.g. "youtube.com")
    source_url: str = ""    # the item the quote came from — makes the preview clickable
    date: str               # YYYY-MM-DD, or "" if unknown
    timestamp: str          # HH:MM:SS into the transcript, "00:00:00" for articles
    timestamp_start: float | None = None  # seconds into a video, for a ?t= deep link
    quote: str
    speaker: str            # "Video transcript" | "Article"
    score: float            # 0..1 relevance to the tracker concept


# --- YouTube channel subscriptions (Sources → YouTube) ---
#
# A subscribed channel is a *standing* source: unlike a one-off `/discover` query, it keeps
# producing items. Its videos flow through the same Data Engineering pipeline as everything
# else, so from `cleaned_items` onward a subscription video is indistinguishable from a
# search hit — the only extra is `YoutubeMatch`, which records the specific moment in a
# transcript that discusses a watchlist ticker.


class YoutubeChannel(BaseModel):
    """A channel the Commander subscribed to on the Sources page."""

    channel_id: str                        # canonical "UC…" id from Supadata
    handle: str | None = None              # what the user typed ("@Bloomberg", a URL, …)
    name: str
    thumbnail: str | None = None
    subscriber_count: int | None = None
    enabled: bool = True                   # False = polling paused
    deleted: bool = False                  # tombstone (its cleaned_items are retained)
    added_at: datetime | None = None
    last_polled_at: datetime | None = None
    last_error: str | None = None          # last ingest failure, surfaced in the UI
    video_count: int = 0                   # videos of this channel already in cleaned_items


class YoutubeMatch(BaseModel):
    """One watchlist-relevant moment in one video — the persisted evidence unit.

    `timestamp_start` is resolved with `council.grounding.best_offset`, the same routine the
    analysts use, so a match deep-links to the exact second the ticker was discussed.
    """

    video_url: str                         # == cleaned_items.source_url
    video_id: str
    channel_id: str
    ticker: str                            # canonical "$NVDA"
    quote: str
    timestamp_start: float | None = None   # seconds into the video
    relevance: float = 0.0                 # 0..1, how squarely the moment is about the ticker
    title: str = ""
    channel_name: str | None = None
    published_at: str | None = None
    matched_at: datetime = Field(default_factory=_now)


class YoutubeJobRef(BaseModel):
    """A running (or just-finished) ingest, so a client can attach to its progress stream.

    Ingest takes minutes per video, so it never runs inside a request. The caller gets one
    of these back and follows `GET /api/jobs/{job_id}/stream`; a client that reloads
    mid-ingest finds the same job again through `GET /api/sources/youtube/jobs`.
    """

    job_id: str
    channel_id: str | None = None   # None for a whole-poll job
    status: str = "running"         # running | done | error


class YoutubeIngestReport(BaseModel):
    """Outcome of ingesting one channel (or a whole poll) — surfaced, never silently dropped."""

    channels: int = 0            # channels attempted
    videos_seen: int = 0         # new videos fetched from Supadata
    persisted: int = 0           # rows written to cleaned_items
    failed: int = 0              # items the pipeline rejected
    matched: int = 0             # watchlist moments recorded
    errors: list[str] = Field(default_factory=list)


# --- The Council (Tiers 3–5: Andie analysts, Freddy debate, Winston chairman) ---
#
# Every score the council emits must trace back to a real source quote (no-orphan
# guardrail, PROJECT_GUIDANCE §12.6). `Evidence.source_url` is always one of the
# `cleaned_items` URLs the agents were given — never invented.


class Evidence(BaseModel):
    """A source-anchored quote backing an analyst's call (no-orphan guardrail)."""

    quote: str
    source_url: str                 # must be one of the provided CleanedItem URLs
    timestamp_start: float | None = None  # seconds into a video, when known


class StockTake(BaseModel):
    """One analyst's view on a single ticker."""

    ticker: str                     # e.g. "$NVDA"
    conviction: float               # -1.0 (bearish) .. +1.0 (bullish)
    horizon: str                    # e.g. "6-12M"
    rationale: str = ""
    evidence: list[Evidence] = Field(default_factory=list)


class SectorNote(BaseModel):
    """Tier 3 — an Andie desk's daily Investment Highlights & Catalyst Note."""

    desk: str                       # "TMT" | "Physical" | "Capital"
    summary: str = ""
    highlights: list[str] = Field(default_factory=list)
    stocks: list[StockTake] = Field(default_factory=list)


class DebateSideMeta(BaseModel):
    """A debater's identity (the model family is shown in the UI)."""

    name: str                       # "Freddy-Bull" | "Freddy-Bear"
    model: str                      # human-readable model family, e.g. "Claude Sonnet"
    stance: str = ""                # one-line position


class DebateTurn(BaseModel):
    """One logged turn of the Bull/Bear/Chairman debate (Req: full transcript)."""

    who: str                        # "bull" | "bear" | "winston"
    round: str                      # "R1" .. "R6" | "Verdict"
    label: str                      # e.g. "Bull · proposes"
    text: str


class DebateRecord(BaseModel):
    """Tier 4 — the adversarial debate transcript + Chairman verdict."""

    topic: str = ""
    round: int = 0
    rounds: int = 6
    bull: DebateSideMeta
    bear: DebateSideMeta
    verdict: str = ""               # filled by Winston (Tier 5)
    transcript: list[DebateTurn] = Field(default_factory=list)


# The three timeframes a basket may be filed under. Free-text `horizon`/`hold` say how
# long Winston would *carry* the position; `timeframe` is the coarse bucket the dashboard
# groups and filters by, so it is a closed set — anything else normalises to the middle.
TIMEFRAMES = ("Short Term", "Medium Term", "Long Term")
DEFAULT_TIMEFRAME = "Medium Term"


class ThemeBasket(BaseModel):
    """Tier 5 — a thematic basket with the Chairman's conviction, timeframe + hold period."""

    name: str
    risk: str = "Med"               # Low | Med | High
    timeframe: str = DEFAULT_TIMEFRAME   # Short Term (1M) | Medium Term (1Q) | Long Term (1Y)
    horizon: str = "—"
    stocks: list[str] = Field(default_factory=list)
    strat: str = ""
    conviction: float = 0.0         # 0..1 confidence
    verdict: str = ""               # the Chairman's call
    hold: str = "—"                 # hold period, e.g. "6–12M"
    evidence: list[Evidence] = Field(default_factory=list)


class MacroIndicator(BaseModel):
    """Tier 5 — a macro indicator score for the dashboard."""

    name: str                       # e.g. "Inflation Trajectory"
    score: float                    # -1.0 .. +1.0
    band: str                       # Positive | Neutral | Negative
    rationale: str = ""             # one line explaining the score
    evidence: list[Evidence] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_evidence(cls, data):
        """Read snapshots written before `evidence` became a list of citations.

        A whole CouncilReport is persisted as JSON and read back through this model, so
        narrowing a field's type here retroactively invalidates every stored run — which
        surfaces as a blank dashboard rather than an error anyone can act on. The old
        free-text `evidence` really was a rationale, so that is where it lands: the
        indicator keeps its explanatory line and simply carries no citation, which is the
        honest rendering of a run made before citations existed.
        """
        if isinstance(data, dict) and isinstance(data.get("evidence"), str):
            legacy = data["evidence"]
            data = {**data, "rationale": data.get("rationale") or legacy, "evidence": []}
        return data


class Signpost(BaseModel):
    """One row of the bear-market signpost checklist (app/taxonomy.py BEAR_SIGNPOSTS)."""

    key: str                        # stable checklist id, e.g. "yield_curve"
    name: str                       # display name
    status: str                     # Triggered | Watch | Clear
    rationale: str = ""             # one line, grounded in the excerpts
    evidence: list[Evidence] = Field(default_factory=list)
    evidenced: bool = True          # False → nothing in the corpus speaks to it
    # True → graded on the Macro Analyst's second pass, from material fetched for this row
    # rather than from the crawled corpus. Defaulted, so snapshots written before the second
    # pass existed still validate (same posture as the deprecated `CouncilReport.baskets`).
    backfilled: bool = False


class BearSignpostReport(BaseModel):
    """The Macro Analyst's bear-market signpost tracker for one council run."""

    signposts: list[Signpost] = Field(default_factory=list)
    triggered: int = 0
    watch: int = 0
    total: int = 0
    risk_score: float = 0.0         # 0.0 (contained) .. 1.0 (every signpost lit)
    label: str = "—"                # e.g. "LATE CYCLE · ELEVATED"
    summary: str = ""


class AceComponent(BaseModel):
    key: str                        # e.g. "AI Sentiment"
    weight: float
    score: float                    # -1.0 .. +1.0


class AceIndex(BaseModel):
    """Tier 5 — the composite AI Capital Environment index (PROJECT_GUIDANCE §8)."""

    value: float                    # -1.0 (capital starved) .. +1.0 (abundant)
    label: str                      # e.g. "CAPITAL ABUNDANT"
    delta: float = 0.0
    components: list[AceComponent] = Field(default_factory=list)


class BriefingItem(BaseModel):
    """Tier 5 — one line of the Chairman's daily briefing."""

    tone: str                       # up | down | neutral
    text: str
    evidence: list[Evidence] = Field(default_factory=list)


class Prediction(BaseModel):
    """Tier 5 — a resolvable prediction destined for the ledger (Req 7.3)."""

    claim: str
    by: str                         # source/channel making the call
    resolve: str                    # e.g. "01 SEP"
    status: str = "pending"
    probability: float = 0.5        # forecast confidence 0..1 (for Brier scoring)
    outcome: bool | None = None     # True/False once resolved, else None
    resolved_at: datetime | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class LedgerRow(BaseModel):
    """One channel's prediction track record (PROJECT_GUIDANCE §7.3 — Brier-scored)."""

    rank: int
    name: str                       # channel / analyst name
    acc: float                      # accuracy 0..1
    n: int                          # number of resolved predictions
    brier: float                    # mean Brier score (lower is better)
    trend: str = "flat"             # "up" | "down" | "flat" vs the previous snapshot


class SourceRef(BaseModel):
    """One document the council read on a given run — the audit manifest (§12.6).

    Recorded per run rather than derived from the live corpus, so a snapshot still says
    what it was actually based on after the corpus moves on. `cited_by` lists the agents
    that quoted it; an empty list means the council read the document but nothing in the
    final report leans on it, which is worth showing rather than hiding.
    """

    url: str
    title: str
    source_type: SourceType
    stream: Stream
    author: str | None = None
    published_at: str | None = None
    themes: list[str] = Field(default_factory=list)
    cited_by: list[str] = Field(default_factory=list)  # e.g. ["Andie-TMT", "Winston"]


class CouncilReport(BaseModel):
    """The full Tier 3–5 output for one run, persisted as the latest snapshot."""

    sector_notes: list[SectorNote] = Field(default_factory=list)
    debate: DebateRecord | None = None
    # Deprecated: thematic baskets moved to their own weekly run (`ThematicRun`). Kept so
    # snapshots written before the split still validate — dropping the field would fail
    # `model_validate` on every historical row, which `repository` reports as "no snapshot".
    baskets: list[ThemeBasket] = Field(default_factory=list)
    indicators: list[MacroIndicator] = Field(default_factory=list)
    macro: BearSignpostReport | None = None
    ace: AceIndex | None = None
    briefing: list[BriefingItem] = Field(default_factory=list)
    predictions: list[Prediction] = Field(default_factory=list)
    ledger: list[LedgerRow] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)  # every document read this run
    source_count: int = 0
    generated_at: datetime = Field(default_factory=_now)


# --- Thematic Analysis (Tier 5, weekly) --------------------------------------
#
# Winston's baskets run on their own cadence, not the nightly crawl's: a theme needs
# more than one day of corpus to change meaningfully. Each execution is persisted whole
# and dated, so the dashboard can read back what was believed on a given week rather
# than only what is believed now.


class ThematicRun(BaseModel):
    """One dated Thematic Analysis run — the baskets plus the corpus they were drawn from."""

    id: int | None = None           # assigned on persist; None before the row exists
    baskets: list[ThemeBasket] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)  # every document read this run
    source_count: int = 0
    generated_at: datetime = Field(default_factory=_now)


class ThematicRunRef(BaseModel):
    """A run as it appears in the picker — enough to label it, without reading the payload."""

    id: int
    generated_at: datetime
    basket_count: int = 0


# --- Single-ticker Debate Chamber (Tier 4, on demand) ------------------------
#
# The nightly council debates one basket drawn from the top names across every desk, so
# it says nothing about a ticker that did not make that cut. A single-emiten debate is a
# question a user asks about one name, answered against just the corpus that mentions it.
# Like a thematic run — and unlike `council_snapshots`, where only the newest row is ever
# served — each execution is persisted whole and dated, so a past debate on a ticker stays
# readable next to the one you just ran.


class TickerDebateRun(BaseModel):
    """One dated single-ticker debate — the transcript plus the corpus it was drawn from."""

    id: int | None = None           # assigned on persist; None before the row exists
    ticker: str                     # canonical "$MU"
    debate: DebateRecord
    # Winston's citations for the closing verdict. Held here rather than on `DebateRecord`
    # so snapshots written before this feature still validate against the unchanged model.
    verdict_evidence: list[Evidence] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)  # every document read this run
    source_count: int = 0
    generated_at: datetime = Field(default_factory=_now)


class TickerDebateRunRef(BaseModel):
    """A run as it appears in the picker — enough to label it, without reading the payload."""

    id: int
    ticker: str
    generated_at: datetime
    turns: int = 0
