"""Persistence for Cleaned_Items — idempotent upsert by source_url (Req 15)."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..models import (
    CleanedItem,
    CouncilReport,
    LedgerRow,
    Prediction,
    ResolvedEntity,
    SourceType,
    Stream,
    TranscriptSegment,
)
from .session import get_session
from .tables import CleanedItemRow, CouncilSnapshotRow, PredictionRow, PromptOverrideRow

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


# --- Prompt overrides (Agent Console) ---------------------------------------


def get_prompt_overrides() -> dict[str, str]:
    """Every overridden prompt as key → text (absent keys use their registry default)."""
    stmt = select(PromptOverrideRow.key, PromptOverrideRow.text)
    session = get_session()
    try:
        return {key: text for key, text in session.execute(stmt)}
    finally:
        session.close()


def set_prompt_override(key: str, text: str) -> None:
    """Upsert a single prompt override by key."""
    now = datetime.now(timezone.utc)
    stmt = pg_insert(PromptOverrideRow).values(key=key, text=text, updated_at=now)
    stmt = stmt.on_conflict_do_update(
        index_elements=["key"], set_={"text": text, "updated_at": now}
    )
    session = get_session()
    try:
        session.execute(stmt)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Failed to persist prompt override %s", key)
        raise
    finally:
        session.close()


def delete_prompt_override(key: str) -> None:
    """Remove a prompt override so its key reverts to the registry default."""
    session = get_session()
    try:
        row = session.get(PromptOverrideRow, key)
        if row is not None:
            session.delete(row)
            session.commit()
    except Exception:
        session.rollback()
        logger.exception("Failed to delete prompt override %s", key)
        raise
    finally:
        session.close()


# --- Predictions & the Brier ledger (Tier 3 rubric scoring, §7.3) ------------

_MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


def _parse_resolve_date(raw: str, now: datetime) -> datetime | None:
    """Parse a resolve string into the upcoming UTC date it refers to.

    Handles ISO ("2025-12-15") exactly, and free-form ("01 SEP", "Dec 15") by picking
    the next occurrence on/after `now` (a prediction's window is in the future when made).
    Returns None when no date can be read — such rows simply never become resolvable.
    """
    s = (raw or "").strip()
    iso = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if iso:
        y, m, d = int(iso[1]), int(iso[2]), int(iso[3])
        try:
            return datetime(y, m, d, tzinfo=timezone.utc)
        except ValueError:
            return None
    mon = re.search(r"(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)", s.upper())
    day = re.search(r"\b(\d{1,2})\b", s)
    if not mon or not day:
        return None
    m, d = _MONTHS[mon[1]], int(day[1])
    try:
        candidate = datetime(now.year, m, d, tzinfo=timezone.utc)
    except ValueError:
        return None
    # The window is forward-looking from when the prediction was made.
    if candidate < now:
        try:
            candidate = datetime(now.year + 1, m, d, tzinfo=timezone.utc)
        except ValueError:
            return None
    return candidate


@dataclass(frozen=True)
class DuePrediction:
    """A pending prediction whose resolve window has passed — ready to be judged."""

    id: int
    claim: str
    channel: str


def save_predictions(preds: list[Prediction]) -> int:
    """Append new predictions, deduped by (claim, channel, resolve). Returns rows inserted."""
    if not preds:
        return 0
    now = datetime.now(timezone.utc)
    rows = [
        {
            "claim": p.claim,
            "channel": p.by,
            "resolve": p.resolve,
            "resolve_at": _parse_resolve_date(p.resolve, now),
            "probability": max(0.0, min(1.0, p.probability)),
            "status": "pending",
            "outcome": None,
            "created_at": now,
            "resolved_at": None,
        }
        for p in preds
    ]
    stmt = pg_insert(PredictionRow).values(rows).on_conflict_do_nothing(
        constraint="uq_predictions_claim_channel_resolve"
    )
    session = get_session()
    try:
        result = session.execute(stmt)
        session.commit()
        return result.rowcount or 0
    except Exception:
        session.rollback()
        logger.exception("Failed to persist predictions")
        raise
    finally:
        session.close()


def list_due_predictions(now: datetime | None = None) -> list[DuePrediction]:
    """Pending predictions whose resolve date has passed (ready for rubric scoring)."""
    now = now or datetime.now(timezone.utc)
    stmt = (
        select(PredictionRow.id, PredictionRow.claim, PredictionRow.channel)
        .where(PredictionRow.status == "pending")
        .where(PredictionRow.resolve_at.is_not(None))
        .where(PredictionRow.resolve_at <= now)
        .order_by(PredictionRow.resolve_at.asc())
    )
    session = get_session()
    try:
        return [DuePrediction(id=r.id, claim=r.claim, channel=r.channel) for r in session.execute(stmt)]
    finally:
        session.close()


def resolve_prediction(prediction_id: int, outcome: bool) -> None:
    """Mark a prediction resolved with its True/False outcome."""
    session = get_session()
    try:
        row = session.get(PredictionRow, prediction_id)
        if row is None:
            return
        row.outcome = outcome
        row.status = "resolved"
        row.resolved_at = datetime.now(timezone.utc)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Failed to resolve prediction %s", prediction_id)
        raise
    finally:
        session.close()


def compute_ledger(prev: CouncilReport | None = None) -> list[LedgerRow]:
    """Per-channel accuracy + Brier over all resolved predictions, ranked best-first.

    `acc` = correct / n; `brier` = mean((probability − outcome)²). `trend` compares each
    channel's accuracy to its row in the previous snapshot (±0.02 band → up/down/flat).
    """
    stmt = (
        select(PredictionRow.channel, PredictionRow.probability, PredictionRow.outcome)
        .where(PredictionRow.status == "resolved")
        .where(PredictionRow.outcome.is_not(None))
    )
    session = get_session()
    try:
        rows = session.execute(stmt).all()
    finally:
        session.close()

    by_channel: dict[str, list[tuple[float, bool]]] = {}
    for channel, probability, outcome in rows:
        by_channel.setdefault(channel, []).append((probability, bool(outcome)))

    prev_acc = {r.name: r.acc for r in (prev.ledger if prev else [])}

    stats = []
    for channel, obs in by_channel.items():
        n = len(obs)
        correct = sum(1 for _, o in obs if o)
        acc = correct / n
        brier = sum((p - (1.0 if o else 0.0)) ** 2 for p, o in obs) / n
        prior = prev_acc.get(channel)
        trend = "flat" if prior is None else "up" if acc > prior + 0.02 else "down" if acc < prior - 0.02 else "flat"
        stats.append((channel, acc, n, brier, trend))

    # Best accuracy first; break ties by the lower (better) Brier score.
    stats.sort(key=lambda s: (-s[1], s[3]))
    return [
        LedgerRow(rank=i + 1, name=c, acc=round(acc, 2), n=n, brier=round(brier, 2), trend=trend)
        for i, (c, acc, n, brier, trend) in enumerate(stats)
    ]
