"""Tracker Context Preview — the best evidence quote for a concept + a real score.

Backs `GET /api/trackers/{tracker}/context` (Core Feature §7.1). A "tracker" is a market
THEME (e.g. "Solar"); items are theme-tagged at ingest, so we pull the theme's items and
ask the LLM to act as a semantic judge: pick the single most relevant excerpt and score
how strongly it is *about* the concept (meaning, not literal word overlap — §7.1).

The chosen quote is grounded back to a real item (no-orphan guardrail §12.6, same pattern
as `council/analyst.py`). If the LLM is unavailable we fall back to a deterministic,
theme-coverage score — still computed, never a hardcoded placeholder.
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

from pydantic import BaseModel

from ..db.repository import list_cleaned_items
from ..llm import ReasoningError, converse_structured
from ..models import CleanedItem, ContextPreview

logger = logging.getLogger(__name__)

_MAX_CANDIDATES = 12   # cap items shown to the judge to bound the prompt
_SNIPPET = 400         # chars of clean_text per candidate when no transcript segment


class _Pick(BaseModel):
    """The judge's verdict: which excerpt, the quote, and its relevance."""

    source_index: int
    quote: str
    relevance: float
    reason: str = ""


def _system(tracker: str) -> str:
    return (
        f"You are a research analyst scoring how strongly each excerpt is ABOUT the concept "
        f"{tracker!r}. Judge meaning and synonyms, not literal word overlap. You are given a "
        f"numbered list of excerpts. Pick the SINGLE most relevant one and return: its integer "
        f"index, a verbatim quote (<=300 chars) copied exactly from that excerpt, and a relevance "
        f"score from 0.0 (unrelated) to 1.0 (squarely about the concept). Never invent text — "
        f"copy the quote exactly from the chosen excerpt."
    )


def _snippet(item: CleanedItem) -> str:
    """Best short evidence text for an item: first transcript segment, else clean_text head."""
    if item.segments:
        return item.segments[0].text.strip()
    return item.clean_text[:_SNIPPET].replace("\n", " ").strip()


def _digest(items: list[CleanedItem]) -> str:
    """Numbered excerpt list the judge cites back into (mirrors analyst `_digest`)."""
    lines: list[str] = []
    for i, it in enumerate(items):
        lines.append(f"[{i}] title={it.title!r} url={it.source_url}\n    {_snippet(it)}")
    return "\n".join(lines)


def _host(url: str) -> str:
    try:
        return urlparse(url).hostname or url
    except ValueError:
        return url


def _timestamp(item: CleanedItem) -> str:
    s = int(item.segments[0].start) if item.segments else 0
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def _preview(item: CleanedItem, tracker: str, quote: str, score: float) -> ContextPreview:
    date = (item.published_at or item.ingested_at.isoformat())[:10]
    return ContextPreview(
        tracker=tracker,
        channel=_host(item.source_url),
        date=date,
        timestamp=_timestamp(item),
        quote=f'"{quote}"' if not quote.startswith('"') else quote,
        speaker="Video transcript" if item.source_type.value == "youtube" else "Article",
        score=max(0.0, min(1.0, score)),
    )


def _fallback(items: list[CleanedItem], tracker: str) -> ContextPreview:
    """Deterministic relevance when the LLM is unavailable: theme dominance × coverage.

    dominance = 1 / (#themes on the item)  → higher when the tracker is the item's main theme
    coverage  = #items carrying the theme / total fetched  → how present the concept is
    """
    coverage = sum(1 for it in items if tracker in (it.themes or [])) / max(len(items), 1)
    best = max(items, key=lambda it: 1.0 / max(len(it.themes or [tracker]), 1))
    dominance = 1.0 / max(len(best.themes or [tracker]), 1)
    return _preview(best, tracker, _snippet(best)[:300], 0.5 * dominance + 0.5 * coverage)


def tracker_context(tracker: str) -> ContextPreview | None:
    """Best evidence quote for a tracker theme + a real relevance score, or None if no items."""
    items = list_cleaned_items(theme=tracker, limit=30)
    if not items:
        return None
    candidates = items[:_MAX_CANDIDATES]

    try:
        pick = converse_structured(_Pick, _system(tracker), _digest(candidates))
    except ReasoningError as exc:
        logger.warning("Context judge unavailable for %r (%s); using rule fallback", tracker, exc.kind)
        return _fallback(items, tracker)

    # Ground the cited index back to a real item; fall back to its snippet if the quote
    # wasn't copied from the source (no-orphan / anti-fabrication, §12.6).
    if not (0 <= pick.source_index < len(candidates)):
        return _fallback(items, tracker)
    item = candidates[pick.source_index]
    quote = pick.quote.strip()
    if quote not in item.clean_text and quote not in _snippet(item):
        quote = _snippet(item)[:300]
    return _preview(item, tracker, quote, pick.relevance)
