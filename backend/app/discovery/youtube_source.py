"""YouTube branch of Discovery: video search (Data API) + transcript fetch.

Finding videos needs the YouTube Data API key; pulling transcripts uses
youtube-transcript-api (no key, no audio download). A video with no captions is
skipped individually so the rest of the run continues.
"""
from __future__ import annotations

import logging

from ..config import settings
from ..events import Emit, noop_emit
from ..models import SourceItem, SourceType, TranscriptSegment
from .exa_source import SourceUnavailable

logger = logging.getLogger(__name__)


def _search_video_ids(query: str, limit: int) -> list[dict]:
    """Return [{id, title, channel, published_at}] via the YouTube Data API."""
    from googleapiclient.discovery import build

    yt = build("youtube", "v3", developerKey=settings.youtube_api_key)
    resp = (
        yt.search()
        .list(q=query, part="snippet", type="video", maxResults=limit)
        .execute()
    )
    videos = []
    for item in resp.get("items", []):
        vid = item.get("id", {}).get("videoId")
        if not vid:
            continue
        snip = item.get("snippet", {})
        videos.append(
            {
                "id": vid,
                "title": snip.get("title", vid),
                "channel": snip.get("channelTitle"),
                "published_at": snip.get("publishedAt"),
            }
        )
    return videos


def _fetch_transcript(video_id: str) -> list[TranscriptSegment]:
    """Fetch a transcript, tolerating both old and new youtube-transcript-api APIs."""
    from youtube_transcript_api import YouTubeTranscriptApi

    raw: list[dict]
    try:
        # youtube-transcript-api >= 1.0 (instance-based)
        raw = [
            {"text": s.text, "start": s.start}
            for s in YouTubeTranscriptApi().fetch(video_id)
        ]
    except (AttributeError, TypeError):
        # older API (classmethod returning list[dict])
        raw = YouTubeTranscriptApi.get_transcript(video_id)

    return [
        TranscriptSegment(start=float(s["start"]), text=s["text"])
        for s in raw
        if s.get("text", "").strip()
    ]


def search(
    query: str,
    max_results: int | None = None,
    emit: Emit = noop_emit,
    *,
    start_published_date: str | None = None,
    end_published_date: str | None = None,
) -> list[SourceItem]:
    """Search YouTube and return transcript-backed SourceItems.

    Raises SourceUnavailable if the key is missing. Individual videos without
    captions are skipped (logged), not fatal.

    Date-window kwargs are accepted for interface parity with the web branch; the
    YouTube branch does not currently filter by published date.
    """
    if not settings.youtube_api_key:
        raise SourceUnavailable("YOUTUBE_API_KEY not set")

    limit = max_results or settings.discovery_max_results_per_source
    emit("discover.youtube", f"Searching YouTube (up to {limit} videos)", status="start")
    videos = _search_video_ids(query, limit)
    emit("discover.youtube", f"Found {len(videos)} videos; fetching transcripts",
         status="progress", videos=len(videos))

    items: list[SourceItem] = []
    for v in videos:
        try:
            segments = _fetch_transcript(v["id"])
        except Exception as exc:  # noqa: BLE001 - third-party raises many types
            logger.warning("Skipping video %s (no transcript): %s", v["id"], exc)
            emit("discover.youtube", f"Skipped (no transcript): {v['title']}",
                 status="skip", video_id=v["id"])
            continue
        if not segments:
            emit("discover.youtube", f"Skipped (empty transcript): {v['title']}",
                 status="skip", video_id=v["id"])
            continue
        items.append(
            SourceItem(
                source_type=SourceType.YOUTUBE,
                title=v["title"],
                url=f"https://www.youtube.com/watch?v={v['id']}",
                text=" ".join(s.text for s in segments),
                author=v.get("channel"),
                published_at=v.get("published_at"),
                segments=segments,
            )
        )
        emit("discover.youtube", f"Transcribed: {v['title']}",
             status="progress", video_id=v["id"], segments=len(segments))
    logger.info("YouTube returned %d transcript-backed items for %r", len(items), query)
    emit("discover.youtube", f"YouTube branch done: {len(items)} transcripts",
         status="ok", count=len(items))
    return items


__all__ = ["search", "SourceUnavailable"]
