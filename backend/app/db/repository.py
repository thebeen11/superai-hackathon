"""Persistence for Cleaned_Items — idempotent upsert by source_url (Req 15)."""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..models import CleanedItem, CouncilReport, ResolvedEntity, SourceType, Stream, TranscriptSegment
from .session import get_session
from .tables import CleanedItemRow, CouncilSnapshotRow

logger = logging.getLogger(__name__)


def _row_to_model(row: CleanedItemRow) -> CleanedItem:
    return CleanedItem(
        source_url=row.source_url,
        source_type=SourceType(row.source_type),
        title=row.title,
        clean_text=row.clean_text,
        stream=Stream(row.stream),
        industry=row.industry,
        entities=[ResolvedEntity(**e) for e in (row.entities or [])],
        themes=list(row.themes or []),
        segments=[TranscriptSegment(**s) for s in (row.segments or [])],
        published_at=row.published_at.isoformat() if row.published_at else None,
        ingested_at=row.ingested_at,
    )


def list_cleaned_items(
    *,
    stream: str | None = None,
    theme: str | None = None,
    ticker: str | None = None,
    limit: int = 50,
) -> list[CleanedItem]:
    """Read persisted Cleaned_Items, newest first, with optional filters."""
    stmt = select(CleanedItemRow).order_by(CleanedItemRow.ingested_at.desc())
    if stream:
        stmt = stmt.where(CleanedItemRow.stream == stream)
    # JSONB containment: themes is a JSON array, entities is [{canonical,...}].
    if theme:
        stmt = stmt.where(CleanedItemRow.themes.contains([theme]))
    if ticker:
        stmt = stmt.where(CleanedItemRow.entities.contains([{"canonical": ticker}]))
    stmt = stmt.limit(limit)

    session = get_session()
    try:
        rows = session.execute(stmt).scalars().all()
        return [_row_to_model(r) for r in rows]
    finally:
        session.close()


def _row_values(item: CleanedItem) -> dict:
    return {
        "source_url": item.source_url,
        "source_type": item.source_type.value,
        "title": item.title,
        "clean_text": item.clean_text,
        "stream": item.stream.value,
        "industry": item.industry,
        "entities": [e.model_dump() for e in item.entities],
        "themes": list(item.themes),
        "segments": [s.model_dump() for s in item.segments],
        "published_at": item.published_at,
        "ingested_at": item.ingested_at,
    }


def upsert_cleaned_item(item: CleanedItem) -> None:
    """Insert or update by `source_url` so exactly one row exists per URL (Req 15.5).

    On a write failure, roll back so no partial row is persisted and re-raise so the
    pipeline can record the failure and continue (Req 15.6).
    """
    values = _row_values(item)
    stmt = pg_insert(CleanedItemRow).values(**values)
    update_cols = {k: v for k, v in values.items() if k != "source_url"}
    stmt = stmt.on_conflict_do_update(index_elements=["source_url"], set_=update_cols)

    session = get_session()
    try:
        session.execute(stmt)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Failed to persist cleaned item %s", item.source_url)
        raise
    finally:
        session.close()


# --- Council snapshots (Tiers 3–5) ------------------------------------------


def save_council_snapshot(report: CouncilReport) -> None:
    """Append the latest council run. The newest row is the current snapshot."""
    row = CouncilSnapshotRow(
        report=report.model_dump(mode="json"),
        source_count=report.source_count,
        generated_at=report.generated_at,
    )
    session = get_session()
    try:
        session.add(row)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Failed to persist council snapshot")
        raise
    finally:
        session.close()


def get_latest_council_snapshot() -> CouncilReport | None:
    """Read back the most recent council snapshot, or None if none exists yet."""
    stmt = select(CouncilSnapshotRow).order_by(CouncilSnapshotRow.generated_at.desc()).limit(1)
    session = get_session()
    try:
        row = session.execute(stmt).scalars().first()
        return CouncilReport.model_validate(row.report) if row else None
    finally:
        session.close()
