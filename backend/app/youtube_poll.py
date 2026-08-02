"""In-process poll timer for YouTube channel subscriptions.

Mirrors `crawl.py`'s daily timer, with one difference: channels are polled on an *interval*
rather than at a wall-clock hour, because "what has this channel published" has no natural
daily boundary the way "yesterday's news" does.

Same single-worker caveat as `app.jobs` and the daily crawl: the timer is process-local. A
scaled-to-zero Cloud Run deploy should leave `YOUTUBE_POLL_ENABLED=false` and let Cloud
Scheduler hit `POST /api/sources/youtube/poll` instead (deploy.sh provisions that job).

Supadata bills per credit, so the default interval is deliberately coarse (24h): each poll
costs at least one credit per channel just to list its videos, before any transcript.
"""
from __future__ import annotations

import logging
import threading

from .config import settings
from .discovery.youtube_ingest import ingest_all_enabled_channels

logger = logging.getLogger(__name__)

_stop = threading.Event()
_thread: threading.Thread | None = None


def _poll_loop() -> None:
    interval_s = max(60, settings.youtube_poll_interval_minutes * 60)
    while True:
        # Wait first: a restart loop must not re-poll (and re-bill) on every boot.
        if _stop.wait(timeout=interval_s):
            return
        try:
            ingest_all_enabled_channels()
        except Exception as exc:  # noqa: BLE001 - a failed poll must not kill the timer
            logger.warning("YouTube channel poll failed: %s", exc)


def start_youtube_poll_timer() -> None:
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_poll_loop, name="youtube-poll", daemon=True)
    _thread.start()
    logger.info(
        "YouTube channel poll timer started (every %d minutes)",
        settings.youtube_poll_interval_minutes,
    )


def stop_youtube_poll_timer() -> None:
    global _thread
    if _thread is None:
        return
    _stop.set()
    _thread.join(timeout=5)
    _thread = None
