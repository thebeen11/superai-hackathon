"""Runtime store for user prompt overrides.

The read path (`get_prompt` in `registry.py`) runs on every LLM call, so overrides are
kept in a module-level cache, loaded lazily from the database on first access. Writes
update both the cache and the database.

Graceful degradation: when no database is configured (local dev) or a DB call fails,
overrides live in-process only — the Agent Console still works within a running process,
the edits just don't survive a restart.
"""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

_cache: dict[str, str] = {}
_loaded = False
_lock = threading.Lock()


def _ensure_loaded() -> None:
    """Populate the cache from the DB once. On any failure, fall back to in-memory."""
    global _loaded
    if _loaded:
        return
    with _lock:
        if _loaded:
            return
        try:
            from ..db.repository import get_prompt_overrides

            _cache.update(get_prompt_overrides())
        except Exception as exc:  # no DB configured, table missing, connection error…
            logger.info("Prompt overrides not loaded from DB (%s); using in-memory only", exc)
        _loaded = True


def get_override(key: str) -> str | None:
    """The user's override text for `key`, or None if it uses the default."""
    _ensure_loaded()
    return _cache.get(key)


def all_overrides() -> dict[str, str]:
    """A snapshot of every currently-overridden key → text."""
    _ensure_loaded()
    return dict(_cache)


def set_override(key: str, text: str) -> None:
    """Persist an override (best-effort DB write; always updates the in-memory cache)."""
    _ensure_loaded()
    _cache[key] = text
    try:
        from ..db.repository import set_prompt_override

        set_prompt_override(key, text)
    except Exception as exc:
        logger.warning("Could not persist prompt override %s to DB (%s); kept in-memory", key, exc)


def delete_override(key: str) -> None:
    """Reset `key` to its default (best-effort DB delete; always clears the cache)."""
    _ensure_loaded()
    _cache.pop(key, None)
    try:
        from ..db.repository import delete_prompt_override

        delete_prompt_override(key)
    except Exception as exc:
        logger.warning("Could not delete prompt override %s from DB (%s); cleared in-memory", key, exc)
