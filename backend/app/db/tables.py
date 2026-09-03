"""SQLAlchemy table definitions (Req 14, 15). Plain Postgres — no embeddings."""
from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class CleanedItemRow(Base):
    __tablename__ = "cleaned_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_url = Column(Text, nullable=False, unique=True)   # upsert key (Req 15.5)
    source_type = Column(String, nullable=False)             # 'web' | 'youtube'
    title = Column(Text, nullable=False)
    clean_text = Column(Text, nullable=False)
    stream = Column(String, nullable=False)                  # 'MACRO' | 'MICRO'
    industry = Column(String, nullable=False)                # sector or 'Unclassified'
    entities = Column(JSONB, nullable=False, default=list)   # [{canonical, mentions[]}]
    themes = Column(JSONB, nullable=False, default=list)     # ["Technology", ...]
    segments = Column(JSONB, nullable=False, default=list)   # [{start, text}]
    author = Column(Text, nullable=True)                     # byline / channel, when given
    published_at = Column(DateTime(timezone=True), nullable=True)   # nullable (Req 14)
    retrieved_at = Column(DateTime(timezone=True), nullable=True)   # UTC at fetch time
    ingested_at = Column(DateTime(timezone=True), nullable=False)   # UTC (Req 14)


# Indexes so later layers can query by stream/industry/ticker/theme without a vector DB.
Index("idx_cleaned_items_stream", CleanedItemRow.stream)
Index("idx_cleaned_items_industry", CleanedItemRow.industry)
Index("idx_cleaned_items_entities", CleanedItemRow.entities, postgresql_using="gin")
Index("idx_cleaned_items_themes", CleanedItemRow.themes, postgresql_using="gin")


class CouncilSnapshotRow(Base):
    """Tiers 3–5 output for one run. The newest row is the current snapshot."""

    __tablename__ = "council_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report = Column(JSONB, nullable=False)                    # serialized CouncilReport
    source_count = Column(Integer, nullable=False, default=0)
    generated_at = Column(DateTime(timezone=True), nullable=False)  # UTC at run time


Index("idx_council_snapshots_generated_at", CouncilSnapshotRow.generated_at)


class ThematicRunRow(Base):
    """One dated Thematic Analysis run (Tier 5, weekly).

    Append-only and read back by id, unlike `council_snapshots` where only the newest row
    is ever served: the whole point of a Run is that last week's themes stay readable.
    `basket_count` is denormalised so the run picker can list every run without touching
    the JSONB payload.
    """

    __tablename__ = "thematic_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run = Column(JSONB, nullable=False)                       # serialized ThematicRun
    basket_count = Column(Integer, nullable=False, default=0)
    source_count = Column(Integer, nullable=False, default=0)
    generated_at = Column(DateTime(timezone=True), nullable=False)  # UTC at run time


Index("idx_thematic_runs_generated_at", ThematicRunRow.generated_at)


class TickerDebateRunRow(Base):
    """One dated single-ticker debate (Tier 4, on demand).

    Append-only and read back by id, the same posture as `thematic_runs`: a user runs a
    debate on a name to compare it with the last one, so overwriting would defeat it.
    `turn_count` is denormalised so the per-ticker run picker can list every run without
    touching the JSONB payload, and the index is composite because every read is scoped to
    one ticker — listing $MU's runs must not scan every other name's.
    """

    __tablename__ = "ticker_debates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(24), nullable=False)               # canonical "$MU"
    run = Column(JSONB, nullable=False)                       # serialized TickerDebateRun
    turn_count = Column(Integer, nullable=False, default=0)
    source_count = Column(Integer, nullable=False, default=0)
    generated_at = Column(DateTime(timezone=True), nullable=False)  # UTC at run time


Index(
    "idx_ticker_debates_ticker_generated_at",
    TickerDebateRunRow.ticker,
    TickerDebateRunRow.generated_at,
)


class PredictionRow(Base):
    """A single resolvable prediction, tracked over its window for the ledger (§7.3).

    Predictions accumulate across council runs (deduped by claim+channel+resolve), are
    resolved True/False once their window passes, and feed the per-channel Brier ledger.
    """

    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    claim = Column(Text, nullable=False)
    channel = Column(String, nullable=False)                  # the `by` field
    resolve = Column(String, nullable=False)                  # raw resolve string, e.g. "01 SEP"
    resolve_at = Column(DateTime(timezone=True), nullable=True)  # parsed due date (UTC)
    probability = Column(Float, nullable=False, default=0.5)  # forecast confidence 0..1
    status = Column(String, nullable=False, default="pending")   # 'pending' | 'resolved'
    outcome = Column(Boolean, nullable=True)                  # True/False once resolved
    created_at = Column(DateTime(timezone=True), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("claim", "channel", "resolve", name="uq_predictions_claim_channel_resolve"),
    )


Index("idx_predictions_status", PredictionRow.status)
Index("idx_predictions_channel", PredictionRow.channel)


class PromptOverrideRow(Base):
    """A user's edited system prompt, keyed by the registry prompt key (Agent Console).

    Absence of a row means the prompt uses its registry default; one row per overridden
    key (upserted on save, deleted on reset).
    """

    __tablename__ = "prompt_overrides"

    key = Column(String, primary_key=True)                          # registry PromptSpec.key
    text = Column(Text, nullable=False)                             # the override text
    updated_at = Column(DateTime(timezone=True), nullable=False)    # UTC of last edit


class WatchlistOverrideRow(Base):
    """A user's per-ticker watchlist override (on/off toggle + delete).

    The watchlist itself is derived from ticker mentions in cleaned_items, so absence of a
    row means the ticker's default: tracked and enabled. A row records a user action —
    `enabled=false` pauses scanning for that ticker; `deleted=true` is a tombstone that hides
    it from the watchlist and stops it being re-discovered (its cleaned_items are retained).
    """

    __tablename__ = "watchlist_overrides"

    ticker = Column(String, primary_key=True)                       # e.g. "NVDA" (no $)
    enabled = Column(Boolean, nullable=False, default=True)         # False = scanning paused
    deleted = Column(Boolean, nullable=False, default=False)        # True = removed (tombstone)
    updated_at = Column(DateTime(timezone=True), nullable=False)    # UTC of last change


class YoutubeChannelRow(Base):
    """A YouTube channel the Commander subscribed to (Sources → YouTube).

    Unlike `watchlist_overrides` — where absence of a row means "tracked by default" — a row
    here IS the subscription: no row means the channel was never added. `deleted=true` is a
    tombstone rather than a hard delete so re-adding the same channel restores its history
    instead of re-ingesting videos already in `cleaned_items`.
    """

    __tablename__ = "youtube_channels"

    channel_id = Column(String, primary_key=True)                   # canonical "UC…" id
    handle = Column(String, nullable=True)                          # what the user typed
    name = Column(Text, nullable=False)
    thumbnail = Column(Text, nullable=True)
    subscriber_count = Column(Integer, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)         # False = polling paused
    deleted = Column(Boolean, nullable=False, default=False)        # True = unsubscribed
    added_at = Column(DateTime(timezone=True), nullable=False)      # UTC when subscribed
    last_polled_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)                        # last ingest failure


class YoutubeVideoRow(Base):
    """Every video we have already pulled a transcript for, per channel.

    This is a *credit ledger*, not a copy of `cleaned_items`. Supadata bills per transcript,
    so a poll must never re-fetch a video it has already seen — including one whose transcript
    the Data Engineering guardrail later rejected (that video is not in `cleaned_items`, but
    re-fetching it every 6 hours would burn a credit every time). It also carries the
    channel→video link, which `cleaned_items` does not record.
    """

    __tablename__ = "youtube_videos"

    video_id = Column(String, primary_key=True)
    channel_id = Column(String, nullable=False)
    video_url = Column(Text, nullable=False)
    title = Column(Text, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    persisted = Column(Boolean, nullable=False, default=False)      # survived the pipeline
    fetched_at = Column(DateTime(timezone=True), nullable=False)


Index("idx_youtube_videos_channel", YoutubeVideoRow.channel_id)


class YoutubeMatchRow(Base):
    """One watchlist-relevant moment in one video — the persisted evidence unit.

    `video_url` references `cleaned_items.source_url` by value, not by foreign key (this
    schema keeps every cross-table link by value — see `predictions`, `council_snapshots`).
    A purge of `cleaned_items` therefore leaves orphan matches behind; they are harmless
    (the row carries its own title/quote/timestamp) but will point at a URL with no
    corresponding document.
    """

    __tablename__ = "youtube_matches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_url = Column(Text, nullable=False)                        # == cleaned_items.source_url
    video_id = Column(String, nullable=False)
    channel_id = Column(String, nullable=False)
    ticker = Column(String, nullable=False)                         # canonical "$NVDA"
    quote = Column(Text, nullable=False)
    timestamp_start = Column(Float, nullable=True)                  # seconds into the video
    relevance = Column(Float, nullable=False, default=0.0)          # 0..1
    title = Column(Text, nullable=False)
    channel_name = Column(Text, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    matched_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        # One moment per (video, ticker): re-running a match updates it rather than piling up.
        UniqueConstraint("video_id", "ticker", name="uq_youtube_match_video_ticker"),
    )


Index("idx_youtube_matches_ticker", YoutubeMatchRow.ticker)
Index("idx_youtube_matches_channel", YoutubeMatchRow.channel_id)
Index("idx_youtube_matches_matched_at", YoutubeMatchRow.matched_at)
