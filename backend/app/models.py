"""Normalized data shapes shared across the pipeline.

The Discovery layer's only job is to turn a topic query into a list of
`SourceItem`s. From here on, an Exa article and a YouTube transcript look the
same to the rest of the council — the only difference is that a video carries
timestamped `segments` so the UI can deep-link to HH:MM:SS.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


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
    """Schema enforced on the Bedrock reply for query refinement."""

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
    published_at: str | None = None                  # ISO8601, nullable (Req 14)
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
    date: str               # YYYY-MM-DD, or "" if unknown
    timestamp: str          # HH:MM:SS into the transcript, "00:00:00" for articles
    quote: str
    speaker: str            # "Video transcript" | "Article"
    score: float            # 0..1 relevance to the tracker concept


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
    round: str                      # "R1" | "R2" | "R3" | "Verdict"
    label: str                      # e.g. "Bull · proposes"
    text: str


class DebateRecord(BaseModel):
    """Tier 4 — the adversarial debate transcript + Chairman verdict."""

    topic: str = ""
    round: int = 0
    rounds: int = 3
    bull: DebateSideMeta
    bear: DebateSideMeta
    verdict: str = ""               # filled by Winston (Tier 5)
    transcript: list[DebateTurn] = Field(default_factory=list)


class ThemeBasket(BaseModel):
    """Tier 5 — a final thematic basket with the Chairman's conviction + hold period."""

    name: str
    risk: str = "Med"               # Low | Med | High
    horizon: str = "—"
    stocks: list[str] = Field(default_factory=list)
    strat: str = ""
    conviction: float = 0.0         # 0..1 confidence
    verdict: str = ""               # the Chairman's call
    hold: str = "—"                 # hold period, e.g. "6–12M"


class MacroIndicator(BaseModel):
    """Tier 5 — a macro/financial indicator score for the dashboard."""

    name: str                       # e.g. "Inflation Trajectory"
    score: float                    # -1.0 .. +1.0
    band: str                       # Positive | Neutral | Negative
    evidence: str = ""              # short evidence summary


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


class Prediction(BaseModel):
    """Tier 5 — a resolvable prediction destined for the ledger (Req 7.3)."""

    claim: str
    by: str                         # source/channel making the call
    resolve: str                    # e.g. "01 SEP"
    status: str = "pending"


class CouncilReport(BaseModel):
    """The full Tier 3–5 output for one run, persisted as the latest snapshot."""

    sector_notes: list[SectorNote] = Field(default_factory=list)
    debate: DebateRecord | None = None
    baskets: list[ThemeBasket] = Field(default_factory=list)
    indicators: list[MacroIndicator] = Field(default_factory=list)
    ace: AceIndex | None = None
    briefing: list[BriefingItem] = Field(default_factory=list)
    predictions: list[Prediction] = Field(default_factory=list)
    source_count: int = 0
    generated_at: datetime = Field(default_factory=_now)

