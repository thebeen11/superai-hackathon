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

from ..config import settings
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


def _merge_segments(segments: list[TranscriptSegment], max_chars: int) -> list[TranscriptSegment]:
    """Glue caption-sized segments into quotable chunks, keeping each chunk's start time.

    Items arrive with segments at the source's caption granularity — a few words each —
    because that is what survives redaction's verbatim check. A judge shown fragments that
    short cannot tell what is being discussed, so they are merged here instead, where the
    result is only ever read by the model and never persisted.
    """
    merged: list[TranscriptSegment] = []
    for segment in segments:
        if merged and len(merged[-1].text) + 1 + len(segment.text) <= max_chars:
            # Keep the earlier start: a chunk begins where its first sentence was said.
            merged[-1] = TranscriptSegment(
                start=merged[-1].start, text=f"{merged[-1].text} {segment.text}"
            )
        else:
            merged.append(segment)
    return merged


def _chunks(item: CleanedItem, ticker: str) -> list[TranscriptSegment]:
    """The chunks the judge chooses between, prioritised by where the ticker is named.

    A two-hour broadcast merges into far more chunks than fit in a prompt, and the minute
    that discusses a given company is rarely in the first few. Chunks that name the ticker
    or one of its aliases go first, then the rest fill the budget in order — so the judge
    still sees surrounding context, but never misses the one passage that mattered.
    """
    merged = _merge_segments(item.segments, settings.youtube_transcript_chunk_size)
    needles = {ticker.lower(), ticker.lstrip("$").lower(), *_aliases(ticker)}
    hits = [c for c in merged if any(n in c.text.lower() for n in needles if n)]
    rest = [c for c in merged if c not in hits]
    # Choose by relevance, then restore chronological order: the judge reads the digest as a
    # narrative, and a shuffled transcript reads as a different (and confusing) conversation.
    return sorted((hits + rest)[:_MAX_CHUNKS], key=lambda c: c.start)


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
    """Watchlist moments across `items`. Items with no tracked ticker cost no LLM calls.

    Logs each decision at INFO. "Nothing matched" is the feature's most common outcome and
    has several innocent causes — no transcript, no tracked ticker, or a mention the judge
    scored as a passing one — which are indistinguishable from a broken pipeline unless the
    reason is recorded. `emit` only reaches a caller that opened an SSE stream, and the poll
    path has none.
    """
    matches: list[YoutubeMatch] = []
    for item in items:
        if not item.segments:
            logger.info("No transcript segments on %s; nothing to anchor to", item.source_url)
            continue
        tickers = matched_tickers(item)
        if not tickers:
            logger.info("No watchlist ticker in %s; skipping the judge", item.source_url)
            continue
        logger.info("Judging %s for %s", item.source_url, ", ".join(tickers))
        emit(_STAGE, f"{item.title}: checking {', '.join(tickers)}",
             status="progress", tickers=tickers, source_url=item.source_url)
        for ticker in tickers:
            # Chunks are selected per ticker, so each judge sees the passages naming its own.
            match = _match(item, ticker, channel_id, _chunks(item, ticker))
            if match is None:
                logger.info("%s scored below the %.1f floor on %s — passing mention",
                            ticker, _MIN_RELEVANCE, item.source_url)
                emit(_STAGE, f"{ticker} only mentioned in passing in {item.title}",
                     status="skip", ticker=ticker, source_url=item.source_url)
                continue
            matches.append(match)
            logger.info("%s matched %s at %.0fs (relevance %.2f)",
                        ticker, item.source_url, match.timestamp_start or 0.0, match.relevance)
            emit(_STAGE, f"{ticker} evidence at {match.timestamp_start or 0:.0f}s in {item.title}",
                 status="ok", ticker=ticker, source_url=item.source_url,
                 relevance=match.relevance)
    return matches


__all__ = ["match_items_to_watchlist", "matched_tickers", "untracked_tickers"]
