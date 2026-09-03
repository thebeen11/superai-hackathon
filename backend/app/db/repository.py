"""Persistence for Cleaned_Items — idempotent upsert by source_url (Req 15)."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..models import (
    CleanedItem,
    CouncilReport,
    LedgerRow,
    Prediction,
    ResolvedEntity,
    SourceType,
    Stream,
    ThematicRun,
    ThematicRunRef,
    TickerDebateRun,
    TickerDebateRunRef,
    TranscriptSegment,
    YoutubeChannel,
    YoutubeMatch,
)
from .session import get_session
from .tables import (
    CleanedItemRow,
    CouncilSnapshotRow,
    PredictionRow,
    PromptOverrideRow,
    ThematicRunRow,
    TickerDebateRunRow,
    WatchlistOverrideRow,
    YoutubeChannelRow,
    YoutubeMatchRow,
    YoutubeVideoRow,
)

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
        author=row.author,
        published_at=row.published_at.isoformat() if row.published_at else None,
        retrieved_at=row.retrieved_at,
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


def list_cleaned_items_by_urls(urls: list[str]) -> list[CleanedItem]:
    """The persisted rows for specific source URLs, newest first.

    `process_discovery_result` reports counts, not items, so a caller that needs to do more
    with what it just ingested (e.g. match transcripts against the watchlist) reads the rows
    back through this — and gets exactly what survived the guardrail, not what it submitted.
    """
    if not urls:
        return []
    stmt = (
        select(CleanedItemRow)
        .where(CleanedItemRow.source_url.in_(urls))
        .order_by(CleanedItemRow.ingested_at.desc())
    )
    session = get_session()
    try:
        return [_row_to_model(r) for r in session.execute(stmt).scalars().all()]
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
        "author": item.author,
        "published_at": item.published_at,
        "retrieved_at": item.retrieved_at,
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
    """Read back the most recent council snapshot, or None if none exists yet.

    A snapshot the current models can no longer parse is logged and treated as absent
    rather than raised. `None` is a state the whole stack already handles — the Tier 3–5
    cards show their honest "awaiting" state — whereas raising here becomes a 500 that the
    frontend swallows into an identical blank dashboard, with the reason nowhere the
    reader can see it. Known shape drift is migrated in the models themselves; this is the
    backstop for the rest.
    """
    stmt = select(CouncilSnapshotRow).order_by(CouncilSnapshotRow.generated_at.desc()).limit(1)
    session = get_session()
    try:
        row = session.execute(stmt).scalars().first()
        if row is None:
            return None
        try:
            return CouncilReport.model_validate(row.report)
        except ValidationError:
            logger.exception(
                "Council snapshot generated_at=%s does not match the current models; "
                "serving no snapshot. Re-run the council to write a current one.",
                row.generated_at,
            )
            return None
    finally:
        session.close()


# --- Thematic Analysis runs (Tier 5, weekly) --------------------------------
#
# Unlike council snapshots, every row here stays reachable: the run picker lists them and
# reads any one back by id. `_thematic_run` applies the same "unparseable is absent, not
# an error" posture as `get_latest_council_snapshot`.


def save_thematic_run(run: ThematicRun) -> ThematicRun:
    """Append a thematic run and return it carrying the id the database assigned."""
    row = ThematicRunRow(
        run=run.model_dump(mode="json"),
        basket_count=len(run.baskets),
        source_count=run.source_count,
        generated_at=run.generated_at,
    )
    session = get_session()
    try:
        session.add(row)
        session.commit()
        run.id = row.id
        return run
    except Exception:
        session.rollback()
        logger.exception("Failed to persist thematic run")
        raise
    finally:
        session.close()


def list_thematic_runs(limit: int = 52) -> list[ThematicRunRef]:
    """Newest-first run headers for the picker. Never reads the JSONB payload."""
    stmt = (
        select(
            ThematicRunRow.id,
            ThematicRunRow.generated_at,
            ThematicRunRow.basket_count,
        )
        .order_by(ThematicRunRow.generated_at.desc(), ThematicRunRow.id.desc())
        .limit(limit)
    )
    session = get_session()
    try:
        return [
            ThematicRunRef(id=r.id, generated_at=r.generated_at, basket_count=r.basket_count)
            for r in session.execute(stmt).all()
        ]
    finally:
        session.close()


def _thematic_run(row: ThematicRunRow | None) -> ThematicRun | None:
    if row is None:
        return None
    try:
        run = ThematicRun.model_validate(row.run)
    except ValidationError:
        logger.exception(
            "Thematic run id=%s does not match the current models; serving no run.",
            row.id,
        )
        return None
    run.id = row.id  # the payload predates its own row id on the first write
    return run


def get_thematic_run(run_id: int) -> ThematicRun | None:
    """Read one run back by id, or None when it does not exist (or no longer parses)."""
    session = get_session()
    try:
        return _thematic_run(session.get(ThematicRunRow, run_id))
    finally:
        session.close()


def get_latest_thematic_run() -> ThematicRun | None:
    """The most recent thematic run, or None before the first one has been made."""
    stmt = (
        select(ThematicRunRow)
        .order_by(ThematicRunRow.generated_at.desc(), ThematicRunRow.id.desc())
        .limit(1)
    )
    session = get_session()
    try:
        return _thematic_run(session.execute(stmt).scalars().first())
    finally:
        session.close()


# --- Single-ticker debates (Tier 4, on demand) ------------------------------
#
# Same append-only, id-addressable shape as `thematic_runs`: every read is scoped to one
# ticker, so the picker for $MU never has to look at any other name's runs.


def save_ticker_debate_run(run: TickerDebateRun) -> TickerDebateRun:
    """Append a single-ticker debate and return it carrying the id the database assigned."""
    row = TickerDebateRunRow(
        ticker=run.ticker,
        run=run.model_dump(mode="json"),
        turn_count=len(run.debate.transcript),
        source_count=run.source_count,
        generated_at=run.generated_at,
    )
    session = get_session()
    try:
        session.add(row)
        session.commit()
        run.id = row.id
        return run
    except Exception:
        session.rollback()
        logger.exception("Failed to persist ticker debate for %s", run.ticker)
        raise
    finally:
        session.close()


def list_ticker_debate_runs(ticker: str, limit: int = 20) -> list[TickerDebateRunRef]:
    """Newest-first run headers for one ticker's picker. Never reads the JSONB payload."""
    stmt = (
        select(
            TickerDebateRunRow.id,
            TickerDebateRunRow.ticker,
            TickerDebateRunRow.generated_at,
            TickerDebateRunRow.turn_count,
        )
        .where(TickerDebateRunRow.ticker == ticker)
        .order_by(TickerDebateRunRow.generated_at.desc(), TickerDebateRunRow.id.desc())
        .limit(limit)
    )
    session = get_session()
    try:
        return [
            TickerDebateRunRef(
                id=r.id, ticker=r.ticker, generated_at=r.generated_at, turns=r.turn_count
            )
            for r in session.execute(stmt).all()
        ]
    finally:
        session.close()


def _ticker_debate_run(row: TickerDebateRunRow | None) -> TickerDebateRun | None:
    if row is None:
        return None
    try:
        run = TickerDebateRun.model_validate(row.run)
    except ValidationError:
        logger.exception(
            "Ticker debate id=%s does not match the current models; serving no run.",
            row.id,
        )
        return None
    run.id = row.id  # the payload predates its own row id on the first write
    return run


def get_ticker_debate_run(run_id: int) -> TickerDebateRun | None:
    """Read one debate back by id, or None when it does not exist (or no longer parses)."""
    session = get_session()
    try:
        return _ticker_debate_run(session.get(TickerDebateRunRow, run_id))
    finally:
        session.close()


def get_latest_ticker_debate_run(ticker: str) -> TickerDebateRun | None:
    """The most recent debate on a ticker, or None before one has been run."""
    stmt = (
        select(TickerDebateRunRow)
        .where(TickerDebateRunRow.ticker == ticker)
        .order_by(TickerDebateRunRow.generated_at.desc(), TickerDebateRunRow.id.desc())
        .limit(1)
    )
    session = get_session()
    try:
        return _ticker_debate_run(session.execute(stmt).scalars().first())
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


# --- Watchlist overrides (per-ticker on/off toggle + delete) ----------------


@dataclass(frozen=True)
class WatchlistOverride:
    """One user override for a watchlist ticker (absence = tracked + enabled)."""

    ticker: str
    enabled: bool
    deleted: bool


def list_watchlist_overrides() -> list[WatchlistOverride]:
    """Every watchlist override row (paused and/or deleted tickers)."""
    stmt = select(
        WatchlistOverrideRow.ticker,
        WatchlistOverrideRow.enabled,
        WatchlistOverrideRow.deleted,
    )
    session = get_session()
    try:
        return [
            WatchlistOverride(ticker=t, enabled=e, deleted=d)
            for t, e, d in session.execute(stmt)
        ]
    finally:
        session.close()


def _upsert_watchlist_override(ticker: str, values: dict) -> WatchlistOverride:
    """Insert or update one override by ticker, returning the actual persisted row.

    On insert the untouched field takes its column default; on conflict only the given
    field (plus updated_at) is written, so the other field's prior value is preserved.
    RETURNING reflects whichever branch ran, so the reported row is always accurate.
    """
    now = datetime.now(timezone.utc)
    insert_values = {"ticker": ticker, **values, "updated_at": now}
    stmt = (
        pg_insert(WatchlistOverrideRow)
        .values(**insert_values)
        .on_conflict_do_update(index_elements=["ticker"], set_={**values, "updated_at": now})
        .returning(
            WatchlistOverrideRow.ticker,
            WatchlistOverrideRow.enabled,
            WatchlistOverrideRow.deleted,
        )
    )
    session = get_session()
    try:
        t, enabled, deleted = session.execute(stmt).one()
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Failed to persist watchlist override %s", ticker)
        raise
    finally:
        session.close()
    return WatchlistOverride(ticker=t, enabled=enabled, deleted=deleted)


def set_watchlist_enabled(ticker: str, enabled: bool) -> WatchlistOverride:
    """Toggle scanning on/off for a ticker (preserves any existing `deleted` state)."""
    return _upsert_watchlist_override(ticker, {"enabled": enabled})


def delete_watchlist_entry(ticker: str) -> WatchlistOverride:
    """Soft-delete a ticker: tombstone it so it leaves the watchlist and stops being scanned."""
    return _upsert_watchlist_override(ticker, {"deleted": True})


def delete_watchlist_entries(tickers: list[str]) -> list[WatchlistOverride]:
    """Soft-delete several tickers in one statement (bulk form of `delete_watchlist_entry`).

    Callers pass tickers already normalised (upper-cased, no `$`). Duplicates are collapsed
    here because Postgres refuses an ON CONFLICT DO UPDATE that would touch the same row
    twice within a single multi-row INSERT.
    """
    unique = list(dict.fromkeys(tickers))  # dedupe, preserving the caller's order
    if not unique:
        return []  # `.values([])` is not valid SQL — nothing to persist

    now = datetime.now(timezone.utc)
    stmt = (
        pg_insert(WatchlistOverrideRow)
        .values([{"ticker": t, "deleted": True, "updated_at": now} for t in unique])
        .on_conflict_do_update(index_elements=["ticker"], set_={"deleted": True, "updated_at": now})
        .returning(
            WatchlistOverrideRow.ticker,
            WatchlistOverrideRow.enabled,
            WatchlistOverrideRow.deleted,
        )
    )
    session = get_session()
    try:
        rows = session.execute(stmt).all()
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Failed to persist %d watchlist tombstones", len(unique))
        raise
    finally:
        session.close()
    return [WatchlistOverride(ticker=t, enabled=e, deleted=d) for t, e, d in rows]


# --- YouTube channel subscriptions (Sources → YouTube) ----------------------


def _channel_to_model(row: YoutubeChannelRow, video_count: int = 0) -> YoutubeChannel:
    return YoutubeChannel(
        channel_id=row.channel_id,
        handle=row.handle,
        name=row.name,
        thumbnail=row.thumbnail,
        subscriber_count=row.subscriber_count,
        enabled=row.enabled,
        deleted=row.deleted,
        added_at=row.added_at,
        last_polled_at=row.last_polled_at,
        last_error=row.last_error,
        video_count=video_count,
    )


def list_youtube_channels(*, include_deleted: bool = False) -> list[YoutubeChannel]:
    """Subscribed channels, newest first, each with its ingested-video count."""
    stmt = select(YoutubeChannelRow).order_by(YoutubeChannelRow.added_at.desc())
    if not include_deleted:
        stmt = stmt.where(YoutubeChannelRow.deleted.is_(False))

    counts_stmt = select(
        YoutubeVideoRow.channel_id, func.count(YoutubeVideoRow.video_id)
    ).group_by(YoutubeVideoRow.channel_id)

    session = get_session()
    try:
        counts = dict(session.execute(counts_stmt).all())
        rows = session.execute(stmt).scalars().all()
        return [_channel_to_model(r, counts.get(r.channel_id, 0)) for r in rows]
    finally:
        session.close()


def get_youtube_channel(channel_id: str) -> YoutubeChannel | None:
    """One channel by id, including tombstoned ones (so re-adding can revive them)."""
    stmt = select(YoutubeChannelRow).where(YoutubeChannelRow.channel_id == channel_id)
    session = get_session()
    try:
        row = session.execute(stmt).scalars().first()
        return _channel_to_model(row) if row else None
    finally:
        session.close()


_CHANNEL_COLUMNS = (
    YoutubeChannelRow.channel_id,
    YoutubeChannelRow.handle,
    YoutubeChannelRow.name,
    YoutubeChannelRow.thumbnail,
    YoutubeChannelRow.subscriber_count,
    YoutubeChannelRow.enabled,
    YoutubeChannelRow.deleted,
    YoutubeChannelRow.added_at,
    YoutubeChannelRow.last_polled_at,
    YoutubeChannelRow.last_error,
)


def _upsert_youtube_channel(channel_id: str, values: dict) -> YoutubeChannel:
    """Insert or update one channel, returning the actual persisted row.

    Mirrors `_upsert_watchlist_override`: only `values` is written on conflict, so a toggle
    that supplies just `{enabled: False}` preserves the channel's name, thumbnail and poll
    history. `name` is NOT NULL, so an insert that never happens through `save_youtube_channel`
    (e.g. toggling a channel that was purged from the table) needs a placeholder — it is an
    insert-only default and is never allowed into the conflict update.
    """
    now = datetime.now(timezone.utc)
    insert_values = {
        "channel_id": channel_id,
        "name": channel_id,   # insert-only placeholder; overwritten by the real subscribe
        "added_at": now,
        **values,
    }
    stmt = (
        pg_insert(YoutubeChannelRow)
        .values(**insert_values)
        .on_conflict_do_update(index_elements=["channel_id"], set_=values)
        .returning(*_CHANNEL_COLUMNS)
    )
    session = get_session()
    try:
        row = session.execute(stmt).one()
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Failed to persist YouTube channel %s", channel_id)
        raise
    finally:
        session.close()
    return _channel_to_model(row)


def save_youtube_channel(channel: YoutubeChannel) -> YoutubeChannel:
    """Subscribe to a channel (or revive a tombstoned one, refreshing its metadata)."""
    return _upsert_youtube_channel(
        channel.channel_id,
        {
            "handle": channel.handle,
            "name": channel.name,
            "thumbnail": channel.thumbnail,
            "subscriber_count": channel.subscriber_count,
            "enabled": True,
            "deleted": False,
        },
    )


def set_youtube_channel_enabled(channel_id: str, enabled: bool) -> YoutubeChannel:
    """Pause or resume polling for one channel (preserves any existing `deleted` state)."""
    return _upsert_youtube_channel(channel_id, {"enabled": enabled})


def delete_youtube_channel(channel_id: str) -> YoutubeChannel:
    """Unsubscribe: tombstone the channel so polling stops (its cleaned_items are retained)."""
    return _upsert_youtube_channel(channel_id, {"deleted": True})


def mark_youtube_channel_polled(channel_id: str, error: str | None = None) -> None:
    """Stamp the last poll time and its outcome. Never raises — this is bookkeeping."""
    now = datetime.now(timezone.utc)
    stmt = (
        pg_insert(YoutubeChannelRow)
        .values(
            channel_id=channel_id,
            name=channel_id,
            added_at=now,
            last_polled_at=now,
            last_error=error,
        )
        .on_conflict_do_update(
            index_elements=["channel_id"],
            set_={"last_polled_at": now, "last_error": error},
        )
    )
    session = get_session()
    try:
        session.execute(stmt)
        session.commit()
    except Exception:
        session.rollback()
        logger.warning("Could not stamp poll time for channel %s", channel_id, exc_info=True)
    finally:
        session.close()


def known_video_ids(channel_id: str) -> set[str]:
    """Videos already fetched for this channel — the credit-saving skip list."""
    stmt = select(YoutubeVideoRow.video_id).where(YoutubeVideoRow.channel_id == channel_id)
    session = get_session()
    try:
        return {v for (v,) in session.execute(stmt)}
    finally:
        session.close()


def record_youtube_videos(rows: list[dict]) -> None:
    """Record videos we spent a transcript credit on, whether or not they survived the pipeline.

    Idempotent by `video_id`: re-recording refreshes `persisted` (an item that failed the
    guardrail on one run may succeed after a prompt change) without re-inserting.
    """
    if not rows:
        return
    now = datetime.now(timezone.utc)
    values = [{**r, "fetched_at": now} for r in rows]
    stmt = pg_insert(YoutubeVideoRow).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["video_id"],
        set_={
            "persisted": stmt.excluded.persisted,
            "title": stmt.excluded.title,
            "fetched_at": stmt.excluded.fetched_at,
        },
    )
    session = get_session()
    try:
        session.execute(stmt)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Failed to record %d YouTube videos", len(rows))
        raise
    finally:
        session.close()


def _match_to_model(row: YoutubeMatchRow) -> YoutubeMatch:
    return YoutubeMatch(
        video_url=row.video_url,
        video_id=row.video_id,
        channel_id=row.channel_id,
        ticker=row.ticker,
        quote=row.quote,
        timestamp_start=row.timestamp_start,
        relevance=row.relevance,
        title=row.title,
        channel_name=row.channel_name,
        published_at=row.published_at.isoformat() if row.published_at else None,
        matched_at=row.matched_at,
    )


def save_youtube_matches(matches: list[YoutubeMatch]) -> int:
    """Upsert watchlist moments, one per (video, ticker). Returns how many were written."""
    if not matches:
        return 0
    values = [
        {
            "video_url": m.video_url,
            "video_id": m.video_id,
            "channel_id": m.channel_id,
            "ticker": m.ticker,
            "quote": m.quote,
            "timestamp_start": m.timestamp_start,
            "relevance": m.relevance,
            "title": m.title,
            "channel_name": m.channel_name,
            "published_at": m.published_at,
            "matched_at": m.matched_at,
        }
        for m in matches
    ]
    stmt = pg_insert(YoutubeMatchRow).values(values)
    update_cols = {
        c: getattr(stmt.excluded, c)
        for c in ("quote", "timestamp_start", "relevance", "title", "channel_name", "matched_at")
    }
    stmt = stmt.on_conflict_do_update(
        constraint="uq_youtube_match_video_ticker", set_=update_cols
    )
    session = get_session()
    try:
        session.execute(stmt)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Failed to persist %d YouTube watchlist matches", len(matches))
        raise
    finally:
        session.close()
    return len(matches)


def list_youtube_matches(
    *, ticker: str | None = None, channel_id: str | None = None, limit: int = 50
) -> list[YoutubeMatch]:
    """Watchlist moments, strongest-first within newest-first, with optional filters."""
    stmt = select(YoutubeMatchRow).order_by(
        YoutubeMatchRow.matched_at.desc(), YoutubeMatchRow.relevance.desc()
    )
    if ticker:
        stmt = stmt.where(YoutubeMatchRow.ticker == ticker)
    if channel_id:
        stmt = stmt.where(YoutubeMatchRow.channel_id == channel_id)
    stmt = stmt.limit(limit)

    session = get_session()
    try:
        return [_match_to_model(r) for r in session.execute(stmt).scalars().all()]
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
