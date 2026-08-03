"""Channel-subscription branch of Discovery: Supadata → transcript-backed SourceItems.

This is the *standing* YouTube source. Where `youtube_source.py` answers "find me videos
about X", this one answers "what has this channel published since I last looked" — the
channel-level tracking PROJECT_GUIDANCE §421 asks for ("never track isolated single
transcripts").

The `SourceItem`s it emits are deliberately identical in shape to the ones the search
branch emits, so everything downstream — redaction, entity resolution, the no-orphan
guardrail, `best_offset` timestamp resolution — works unchanged.
"""
from __future__ import annotations

import logging

from ..config import settings
from ..events import Emit, noop_emit
from ..models import SourceItem, SourceType, TranscriptSegment, YoutubeChannel
from . import supadata
from .exa_source import SourceUnavailable

logger = logging.getLogger(__name__)

_STAGE = "discover.youtube.channel"


def resolve_channel(ident: str) -> YoutubeChannel:
    """Resolve any Supadata-supported identifier (URL, @handle, UC… id) to a channel.

    Raises SourceUnavailable when the key is missing/exhausted and SupadataError when the
    identifier simply doesn't resolve — the API layer turns the latter into a 400.
    """
    payload = supadata.get_channel(ident)
    channel_id = payload.get("id")
    if not channel_id:
        raise supadata.SupadataError(f"Could not resolve a channel from {ident!r}")
    return YoutubeChannel(
        channel_id=channel_id,
        handle=ident,
        name=payload.get("name") or channel_id,
        thumbnail=payload.get("thumbnail"),
        subscriber_count=payload.get("subscriberCount"),
    )


def _video_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def video_id_from_url(url: str) -> str:
    """The `v=` id from a watch URL — the stable key videos and matches are deduped on.

    The inverse of `_video_url`. Returns the URL unchanged if it carries no `v=`, so a
    caller never ends up with an empty key.
    """
    _, _, tail = url.partition("v=")
    return tail.split("&")[0] if tail else url


def _segments(transcript: dict) -> list[TranscriptSegment]:
    """Supadata transcript content → fine-grained, timestamped TranscriptSegments.

    Two things this must get right:

    `offset` is in MILLISECONDS while `TranscriptSegment.start` is seconds — the unit
    `sourceHref` turns into a `?t=Ns` deep link. Getting it wrong silently sends every
    citation ~1000x too deep into the video.

    Segments stay at the source's own caption granularity and are NOT merged here. The
    redaction step keeps only segments whose text survives verbatim in the LLM's cleaned
    output (`dataeng/redact.py`), and a merged ~1000-char block never survives that check —
    the model reflows the prose — so merging at ingest silently strips every timestamp from
    the item. Chunks big enough to judge for relevance are assembled later, at matching time,
    from these fine-grained segments.
    """
    content = transcript.get("content")
    if isinstance(content, str):
        # text=true was honoured despite our request — one untimed segment is better than none.
        text = content.strip()
        return [TranscriptSegment(start=0.0, text=text)] if text else []

    segments: list[TranscriptSegment] = []
    for chunk in content or []:
        text = (chunk.get("text") or "").strip()
        if not text:
            continue
        segments.append(TranscriptSegment(start=float(chunk.get("offset") or 0) / 1000.0, text=text))
    return segments


def _to_source_item(entry: dict, *, fallback_channel_name: str | None) -> SourceItem | None:
    """One Supadata batch result → a SourceItem, or None when there's nothing usable."""
    video_id = entry.get("videoId")
    if not video_id:
        return None
    segments = _segments(entry.get("transcript") or {})
    if not segments:
        return None

    video = entry.get("video") or {}
    channel_name = (video.get("channel") or {}).get("name") or fallback_channel_name
    return SourceItem(
        source_type=SourceType.YOUTUBE,
        title=video.get("title") or video_id,
        url=_video_url(video_id),
        # MUST stay the plain concatenation of segment texts: the Data Engineering guardrail
        # checks that cleaned text is grounded in this string and that every retained segment
        # appears in it (guardrail.enforce). Any reformatting here shows up as a rejected item.
        text=" ".join(s.text for s in segments),
        author=channel_name,
        published_at=video.get("uploadDate"),
        segments=segments,
    )


def fetch_channel_items(
    channel: YoutubeChannel,
    *,
    limit: int | None = None,
    skip_video_ids: set[str] | None = None,
    emit: Emit = noop_emit,
) -> list[SourceItem]:
    """Transcript-backed SourceItems for a channel's newest videos.

    `skip_video_ids` is the credit saver: listing a channel's videos costs 1 credit, but each
    transcript costs another, so already-seen videos are dropped BEFORE the transcript call.
    Videos without captions are skipped individually (logged + emitted), never fatal.
    """
    if not settings.supadata_api_key:
        raise SourceUnavailable("SUPADATA_API_KEY not set")

    limit = limit or settings.youtube_poll_limit
    skip = skip_video_ids or set()

    emit(_STAGE, f"Checking {channel.name} for new videos (up to {limit})",
         status="start", channel_id=channel.channel_id)
    video_ids = supadata.list_channel_video_ids(channel.channel_id, limit)
    fresh = [v for v in video_ids if v not in skip]
    if not fresh:
        emit(_STAGE, f"{channel.name}: no new videos", status="ok",
             channel_id=channel.channel_id, count=0)
        return []

    emit(_STAGE, f"{channel.name}: {len(fresh)} new video(s); fetching transcripts",
         status="progress", channel_id=channel.channel_id, videos=len(fresh))
    results = supadata.transcripts(fresh, emit=emit)

    items: list[SourceItem] = []
    for entry in results:
        item = _to_source_item(entry, fallback_channel_name=channel.name)
        if item is None:
            emit(_STAGE, f"Skipped (empty transcript): {entry.get('videoId')}",
                 status="skip", video_id=entry.get("videoId"))
            continue
        items.append(item)
        emit(_STAGE, f"Transcribed: {item.title}", status="progress",
             video_id=entry.get("videoId"), segments=len(item.segments))

    logger.info("Channel %s returned %d transcript-backed items", channel.channel_id, len(items))
    emit(_STAGE, f"{channel.name}: {len(items)} transcript(s) ready",
         status="ok", channel_id=channel.channel_id, count=len(items))
    return items


__all__ = ["resolve_channel", "fetch_channel_items", "video_id_from_url", "SourceUnavailable"]
