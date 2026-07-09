"""Day-to-day ingestion: crawl one calendar day's news through the full pipeline.

`run_daily_crawl` pulls a single published-date window (one UTC day) through the
existing Discovery → Data Engineering → Council chain. It is exposed as
`POST /crawl/daily` — the hook for Cloud Scheduler / external cron / manual runs —
and, when `DAILY_CRAWL_ENABLED` is set, fired by an in-process daily timer for
local/docker runs. Persistence is an upsert by URL, so re-crawling a day is
idempotent.

The timer is process-local (same single-worker caveat as `app.jobs`); a
scaled-to-zero Cloud Run deploy should use Cloud Scheduler instead — that is why
`daily_crawl_enabled` defaults to off.
"""
from __future__ import annotations

import logging
import threading
from datetime import date, datetime, timedelta, timezone

from .config import settings
from .council import run_council
from .dataeng import process_discovery_result
from .discovery import discover
from .events import Emit, noop_emit
from .models import DataEngReport

logger = logging.getLogger(__name__)


def run_council_safe(emit: Emit = noop_emit) -> None:
    """Run Tiers 3–5 after discovery, fault-isolated so it never breaks ingestion."""
    try:
        run_council(emit=emit)
    except Exception as exc:  # noqa: BLE001 - council failure must not fail discovery
        logger.warning("Council run failed: %s", exc)
        emit("council", f"Council failed: {exc}", status="error", reason=str(exc))


def default_crawl_day() -> date:
    """Yesterday (UTC) — the most recent *complete* published-date window."""
    return datetime.now(timezone.utc).date() - timedelta(days=1)


def crawl_window(day: date) -> tuple[str, str]:
    """First instant .. last instant of `day` as ISO8601 published-date bounds."""
    return f"{day:%Y-%m-%d}T00:00:00.000Z", f"{day:%Y-%m-%d}T23:59:59.999Z"


def run_daily_crawl(day: date | None = None, emit: Emit = noop_emit) -> DataEngReport:
    """Crawl one day's news (default: yesterday UTC) and persist it, then convene the council."""
    day = day or default_crawl_day()
    start, end = crawl_window(day)
    emit("crawl.daily", f"Daily crawl for {day:%Y-%m-%d}", status="start", day=f"{day:%Y-%m-%d}")
    result = discover(
        settings.daily_crawl_query,
        max_results=settings.daily_crawl_max_results,
        emit=emit,
        start_published_date=start,
        end_published_date=end,
    )
    report = process_discovery_result(result, emit=emit)
    run_council_safe(emit)
    emit("crawl.daily", f"Daily crawl for {day:%Y-%m-%d} done: "
         f"{report.persisted} persisted, {report.failed} failed",
         status="ok", persisted=report.persisted, failed=report.failed)
    return report


# --- In-process daily timer ---------------------------------------------------

_stop = threading.Event()
_thread: threading.Thread | None = None


def _seconds_until_next_run(now: datetime, hour_utc: int) -> float:
    """Seconds from `now` (aware, UTC) to the next occurrence of `hour_utc`:00."""
    target = now.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def _timer_loop() -> None:
    while True:
        delay = _seconds_until_next_run(
            datetime.now(timezone.utc), settings.daily_crawl_hour_utc
        )
        if _stop.wait(timeout=delay):
            return
        try:
            run_daily_crawl()
        except Exception as exc:  # noqa: BLE001 - a failed day must not kill the timer
            logger.warning("Daily crawl failed: %s", exc)


def start_daily_crawl_timer() -> None:
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_timer_loop, name="daily-crawl", daemon=True)
    _thread.start()
    logger.info(
        "Daily crawl timer started (fires daily at %02d:00 UTC)",
        settings.daily_crawl_hour_utc,
    )


def stop_daily_crawl_timer() -> None:
    global _thread
    if _thread is None:
        return
    _stop.set()
    _thread.join(timeout=5)
    _thread = None
