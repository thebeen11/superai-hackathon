"""Watchlist moment matching — when does a video actually talk about something we track?

A watchlist item in this app is a ticker, derived from `entities[].canonical` mentions
across `cleaned_items`. So "this transcript is relevant to the watchlist" reduces to: did
Data Engineering resolve a ticker on this item that the Commander is currently tracking?

Two stages, deliberately in this order:

1. **Entity intersection — free.** The pipeline already resolved this item's entities, and
   `watchlist_overrides` already says what is paused or deleted. A video with no watchlist
   ticker costs zero LLM calls. This matters: a channel poll touches every new video, but
   only a fraction discuss anything tracked.
2. **LLM judge — once per (video, matched ticker).** A ticker appearing in an item's entity
   list only means it was *mentioned*; it does not say where, or whether the mention was
   substantive. The judge picks the chunk and scores it, exactly as `insights/context.py`
   does for a theme.

The timestamp is never taken from the model — it is resolved with `grounding.best_offset`,
the same routine the analyst desks use, so a match deep-links to the right second.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel

from ..council import grounding
from ..db.repository import list_watchlist_overrides
from ..discovery.youtube_channel import video_id_from_url
from ..events import Emit, noop_emit
from ..llm import ReasoningError, converse_structured
from ..models import CleanedItem, TranscriptSegment, YoutubeMatch
from ..prompts import get_prompt
from ..taxonomy import COMPANY_ALIASES

logger = logging.getLogger(__name__)

_STAGE = "youtube.match"
_MAX_CHUNKS = 40      # cap chunks shown to the judge to bound the prompt
_MAX_QUOTE = 300      # chars — matches the insights.context contract
_MIN_RELEVANCE = 0.4  # below this a mention is a name-drop, not evidence


class _Pick(BaseModel):
    """The judge's verdict: which chunk, the quote, and how squarely it is about the ticker."""

    chunk_index: int
    quote: str
    relevance: float
    reason: str = ""


def untracked_tickers() -> set[str]:
    """Canonical "$TICK" symbols the Commander has paused or deleted.

    The watchlist is derived, not enumerated: absence of an override row means a ticker is
    tracked by default (see `WatchlistOverrideRow`). So the only thing that can be listed is
    the *exclusion* set, and matching is "every resolved ticker except these".
    """
    return {
        f"${o.ticker.lstrip('$').upper()}"
        for o in list_watchlist_overrides()
        if o.deleted or not o.enabled
    }


def matched_tickers(item: CleanedItem) -> list[str]:
    """Watchlist tickers this item mentions, in the item's own entity order.

    Every resolved `$…` entity counts unless the Commander explicitly paused or deleted it —
    which is what "tracked by default" means for this watchlist.
    """
    untracked = untracked_tickers()
    seen: list[str] = []
    for entity in item.entities:
        canonical = entity.canonical
        if not canonical.startswith("$") or canonical in untracked or canonical in seen:
            continue
        seen.append(canonical)
    return seen


def _aliases(ticker: str) -> list[str]:
    """Known spoken forms of a ticker, deterministically ordered.

    The alias table mixes company names with the people who stand in for them ("nvidia",
    "jensen"), and picking one would be an arbitrary tie-break — so callers get all of them:
    the prompt uses them as a hint and `_fallback_chunk` uses them as needles.
    """
    return sorted(alias for alias, canonical in COMPANY_ALIASES.items() if canonical == ticker)


def _company_hint(ticker: str) -> str:
    """How the judge is told to recognise the company when it isn't called by its ticker."""
    aliases = _aliases(ticker)
    return ", ".join(a.title() for a in aliases) if aliases else ticker.lstrip("$").upper()


def _chunks(item: CleanedItem) -> list[TranscriptSegment]:
    """The transcript chunks the judge chooses between (capped for prompt size)."""
    return list(item.segments[:_MAX_CHUNKS])


def _digest(chunks: list[TranscriptSegment]) -> str:
    """Numbered chunk list the judge cites back into (mirrors insights.context `_digest`)."""
    return "\n".join(f"[{i}] {c.text.strip()}" for i, c in enumerate(chunks))


def _fallback_chunk(chunks: list[TranscriptSegment], ticker: str) -> TranscriptSegment:
    """First chunk that names the ticker or its alias, else the first chunk.

    Deterministic, so a Gemini outage degrades the quote's precision rather than dropping the
    match entirely — the same posture as `insights/context.py::_fallback`.
    """
    needles = {ticker.lower(), ticker.lstrip("$").lower(), *_aliases(ticker)}
    for chunk in chunks:
        lowered = chunk.text.lower()
        if any(n in lowered for n in needles if n):
            return chunk
    return chunks[0]


def _match(
    item: CleanedItem, ticker: str, channel_id: str, chunks: list[TranscriptSegment]
) -> YoutubeMatch | None:
    """Judge one (video, ticker) pair into a persisted-shaped match, or None if too weak."""
    try:
        pick = converse_structured(
            _Pick,
            get_prompt("insights.watchlist_match", ticker=ticker, company=_company_hint(ticker)),
            _digest(chunks),
        )
        relevance = pick.relevance
        quote = pick.quote.strip()
        chunk = (
            chunks[pick.chunk_index]
            if 0 <= pick.chunk_index < len(chunks)
            else _fallback_chunk(chunks, ticker)
        )
    except ReasoningError as exc:
        logger.warning(
            "Watchlist judge unavailable for %s on %s (%s); using rule fallback",
            ticker, item.source_url, exc.kind,
        )
        chunk = _fallback_chunk(chunks, ticker)
        quote, relevance = "", 0.5

    # Anti-fabrication: a quote the model did not copy from the chunk is not evidence.
    if not quote or quote not in chunk.text:
        quote = chunk.text.strip()[:_MAX_QUOTE]
    if relevance < _MIN_RELEVANCE:
        return None

    return YoutubeMatch(
        video_url=item.source_url,
        video_id=video_id_from_url(item.source_url),
        channel_id=channel_id,
        ticker=ticker,
        quote=quote[:_MAX_QUOTE],
        # Resolved from the transcript, never from the model.
        timestamp_start=grounding.best_offset(item, quote),
        relevance=max(0.0, min(1.0, relevance)),
        title=item.title,
        channel_name=item.author,
        published_at=item.published_at,
    )


def match_items_to_watchlist(
    items: list[CleanedItem], *, channel_id: str, emit: Emit = noop_emit
) -> list[YoutubeMatch]:
    """Watchlist moments across `items`. Items with no tracked ticker cost no LLM calls."""
    matches: list[YoutubeMatch] = []
    for item in items:
        chunks = _chunks(item)
        if not chunks:
            continue  # no transcript, no moment to point at
        tickers = matched_tickers(item)
        if not tickers:
            continue
        emit(_STAGE, f"{item.title}: checking {', '.join(tickers)}",
             status="progress", tickers=tickers, source_url=item.source_url)
        for ticker in tickers:
            match = _match(item, ticker, channel_id, chunks)
            if match is None:
                emit(_STAGE, f"{ticker} only mentioned in passing in {item.title}",
                     status="skip", ticker=ticker, source_url=item.source_url)
                continue
            matches.append(match)
            emit(_STAGE, f"{ticker} evidence at {match.timestamp_start or 0:.0f}s in {item.title}",
                 status="ok", ticker=ticker, source_url=item.source_url,
                 relevance=match.relevance)
    return matches


__all__ = ["match_items_to_watchlist", "matched_tickers", "untracked_tickers"]
