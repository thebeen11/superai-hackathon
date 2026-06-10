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
    published_at = Column(DateTime(timezone=True), nullable=True)   # nullable (Req 14)
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
