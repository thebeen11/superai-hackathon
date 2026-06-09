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

