"""Channel ingestion: Supadata → Data Engineering → watchlist moments.

One channel's newest videos are pulled, run through the *existing* pipeline
(`process_discovery_result` — redact, entities, labels, themes, guardrail, upsert), read
back, and matched against the watchlist. Nothing about the pipeline is special-cased for
channels; a subscription video is just another `SourceItem`.

Fault isolation follows the house rule: one bad channel must never abort a poll, so
`ingest_all_enabled_channels` catches per channel and records the reason on the row — the
same posture as `crawl.run_council_safe`.
"""
from __future__ import annotations

import logging

from ..config import settings
from ..dataeng import process_discovery_result
from ..db.repository import (
    known_video_ids,
    list_cleaned_items_by_urls,
    list_youtube_channels,
    mark_youtube_channel_polled,
    record_youtube_videos,
    save_youtube_matches,
)
from ..events import Emit, noop_emit
from ..insights.watchlist_match import match_items_to_watchlist
from ..models import DiscoveryResult, YoutubeChannel, YoutubeIngestReport
from . import youtube_channel

logger = logging.getLogger(__name__)

_STAGE = "discover.youtube.channel"


def ingest_channel(
    channel: YoutubeChannel, *, limit: int | None = None, emit: Emit = noop_emit
) -> YoutubeIngestReport:
    """Pull, persist, and watchlist-match one channel's new videos."""
    report = YoutubeIngestReport(channels=1)

    items = youtube_channel.fetch_channel_items(
        channel,
        limit=limit or settings.youtube_poll_limit,
        skip_video_ids=known_video_ids(channel.channel_id),
        emit=emit,
    )
    report.videos_seen = len(items)
    if not items:
        mark_youtube_channel_polled(channel.channel_id, error=None)
        return report

    dataeng = process_discovery_result(
        DiscoveryResult(query=f"channel:{channel.channel_id}", items=items), emit=emit
    )
    report.persisted = dataeng.persisted
    report.failed = dataeng.failed

    # Record every video a transcript credit was spent on — including ones the guardrail
    # rejected — so the next poll does not pay for them again.
    failed_urls = {f.source_url for f in dataeng.failures}
    record_youtube_videos(
        [
            {
                "video_id": youtube_channel.video_id_from_url(item.url),
                "channel_id": channel.channel_id,
                "video_url": item.url,
                "title": item.title,
                "published_at": item.published_at,
                "persisted": item.url not in failed_urls,
            }
            for item in items
        ]
    )

    persisted_items = list_cleaned_items_by_urls([i.url for i in items if i.url not in failed_urls])
    matches = match_items_to_watchlist(persisted_items, channel_id=channel.channel_id, emit=emit)
    report.matched = save_youtube_matches(matches)

    mark_youtube_channel_polled(channel.channel_id, error=None)
    emit(_STAGE, f"{channel.name}: {report.persisted} ingested, {report.matched} watchlist match(es)",
         status="ok", channel_id=channel.channel_id,
         persisted=report.persisted, matched=report.matched)
    return report


def ingest_all_enabled_channels(emit: Emit = noop_emit) -> YoutubeIngestReport:
    """Poll every enabled subscription. A failing channel is recorded, not fatal."""
    channels = [c for c in list_youtube_channels() if c.enabled]
    total = YoutubeIngestReport()
    if not channels:
        emit(_STAGE, "No YouTube channels subscribed", status="ok", channels=0)
        return total

    emit(_STAGE, f"Polling {len(channels)} channel(s)", status="start", channels=len(channels))
    for channel in channels:
        try:
            one = ingest_channel(channel, emit=emit)
        except Exception as exc:  # noqa: BLE001 - one bad channel must not abort the poll
            logger.warning("Channel %s failed: %s", channel.channel_id, exc)
            emit(_STAGE, f"{channel.name} failed: {exc}", status="error",
                 channel_id=channel.channel_id, reason=str(exc))
            total.errors.append(f"{channel.name}: {exc}")
            mark_youtube_channel_polled(channel.channel_id, error=str(exc))
            total.channels += 1
            continue
        total.channels += one.channels
        total.videos_seen += one.videos_seen
        total.persisted += one.persisted
        total.failed += one.failed
        total.matched += one.matched

    emit(_STAGE, f"Poll done: {total.persisted} ingested, {total.matched} watchlist match(es)",
         status="ok", persisted=total.persisted, matched=total.matched, channels=total.channels)
    return total


__all__ = ["ingest_channel", "ingest_all_enabled_channels"]
