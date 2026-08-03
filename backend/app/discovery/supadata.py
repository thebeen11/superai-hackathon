"""Supadata HTTP client — YouTube channel metadata + transcripts.

Pure transport: every function returns Supadata's own JSON shapes and knows nothing
about `SourceItem`, the pipeline, or the watchlist. Domain mapping lives in
`youtube_channel.py`.

Supadata is used only by the *channel subscription* source. The query-driven
`/discover` YouTube branch (`youtube_source.py`) still uses the YouTube Data API +
youtube-transcript-api and is deliberately untouched.

Billing is per credit — 1 credit per transcript and per metadata lookup — and the free
tier is 100 credits/month at 1 request/second. That shapes two decisions here:
`transcripts()` prefers the batch endpoint (one round trip for N videos), and its
sequential fallback is throttled to 1 req/s.

Docs: https://docs.supadata.ai — base https://api.supadata.ai/v1, auth `x-api-key`.
"""
from __future__ import annotations

import logging
import time

from ..config import settings
from ..events import Emit, noop_emit
from .exa_source import SourceUnavailable

logger = logging.getLogger(__name__)

_STAGE = "discover.youtube.channel"

# Batch jobs are async: poll with a bounded backoff rather than hammering the endpoint.
_POLL_INITIAL_S = 2.0
_POLL_MAX_S = 30.0
_POLL_DEADLINE_S = 300.0

# Free-tier rate limit is 1 request/second; the sequential fallback must respect it.
_SEQUENTIAL_GAP_S = 1.1

_TIMEOUT_S = 60.0

# Supadata error codes that mean the key itself is unusable — the whole source is down.
# Only credentials belong here. Two codes look fatal but are not:
#
# `upgrade-required` (HTTP 402) means "this ENDPOINT isn't on your plan" — the signal to
# degrade to a cheaper path, not to give up. The free tier returns it for
# /youtube/transcript/batch while /youtube/transcript works fine.
#
# `limit-exceeded` (HTTP 429) is the REQUEST RATE limit ("Request rate limit on current
# plan was exceeded"), not a credit balance — the free tier allows 1 request/second, so
# hitting it is routine. It is retried with backoff below.
_FATAL_ERRORS = {"unauthorized", "forbidden"}

# Free tier is 1 req/s. Rate-limit rejections are expected, so back off and retry rather
# than failing the channel.
_RATE_LIMIT_RETRIES = 4
_RATE_LIMIT_BACKOFF_S = 1.5


class SupadataError(Exception):
    """A Supadata response we cannot use. `code` is Supadata's own error slug."""

    def __init__(self, message: str, *, code: str = "", status: int = 0) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def _require_key() -> str:
    if not settings.supadata_api_key:
        raise SourceUnavailable("SUPADATA_API_KEY not set")
    return settings.supadata_api_key


def _request(method: str, path: str, **kwargs) -> dict:
    """One Supadata call, retrying rate-limit rejections.

    Raises SourceUnavailable when the credentials themselves are unusable, and SupadataError
    for everything else — including a rate limit that survives every retry, so the caller can
    skip one video or fall back to another endpoint rather than losing the whole source.
    """
    import httpx

    url = f"{settings.supadata_base_url.rstrip('/')}{path}"
    headers = {"x-api-key": _require_key()}

    for attempt in range(_RATE_LIMIT_RETRIES + 1):
        try:
            response = httpx.request(method, url, headers=headers, timeout=_TIMEOUT_S, **kwargs)
        except httpx.HTTPError as exc:
            raise SupadataError(f"Supadata request failed: {exc}") from exc

        if response.status_code < 400:
            return response.json()

        # Supadata's error envelope: {error, message, details, documentationUrl}
        try:
            body = response.json()
        except ValueError:
            body = {}
        code = str(body.get("error") or "")
        message = str(body.get("message") or response.text or f"HTTP {response.status_code}")

        if code == "limit-exceeded" or response.status_code == 429:
            if attempt < _RATE_LIMIT_RETRIES:
                # Honour Retry-After when offered; otherwise back off exponentially.
                retry_after = response.headers.get("Retry-After")
                delay = (
                    float(retry_after)
                    if retry_after and retry_after.replace(".", "", 1).isdigit()
                    else _RATE_LIMIT_BACKOFF_S * (2**attempt)
                )
                logger.debug("Supadata rate-limited on %s; retrying in %.1fs", path, delay)
                time.sleep(delay)
                continue
            raise SupadataError(message, code="limit-exceeded", status=429)

        if code in _FATAL_ERRORS or response.status_code in (401, 403):
            # A rejected key is the same class of problem as an unset one: the whole branch
            # is unusable, so surface it the way every other source does.
            raise SourceUnavailable(
                f"Supadata unavailable ({code or response.status_code}): {message}"
            )
        raise SupadataError(message, code=code, status=response.status_code)

    raise SupadataError(f"Supadata request to {path} exhausted its retries")


def get_channel(ident: str) -> dict:
    """Resolve a channel URL, @handle, or UC… id to {id, name, description, thumbnail, ...}."""
    return _request("GET", "/youtube/channel", params={"id": ident})


def list_channel_video_ids(ident: str, limit: int) -> list[str]:
    """Newest `limit` regular videos for a channel (shorts and livestreams excluded).

    `type=video` keeps shorts out: a 30-second short is not the kind of channel-level
    signal the council should treat as evidence.
    """
    payload = _request(
        "GET", "/youtube/channel/videos", params={"id": ident, "limit": limit, "type": "video"}
    )
    return [v for v in (payload.get("videoIds") or []) if v]


def transcripts(video_ids: list[str], *, emit: Emit = noop_emit) -> list[dict]:
    """Transcripts + video metadata for `video_ids`, as [{videoId, transcript, video}].

    Uses the batch endpoint (1 round trip, 1 credit/video). If batch is not available on
    the current plan, falls back to one sequential `/youtube/transcript` call per video at
    the free-tier rate limit. Videos Supadata cannot transcribe are dropped, not fatal —
    same posture as a caption-less video in `youtube_source.py`.
    """
    if not video_ids:
        return []
    try:
        job_id = _start_batch(video_ids)
    except SupadataError as exc:
        # Batch is an "advanced endpoint" on some plans. Degrade instead of failing.
        # Only a failure to *start* falls back: once a job is accepted its credits are
        # already committed, so retrying the same videos sequentially would bill twice.
        logger.info("Supadata batch unavailable (%s); falling back to sequential", exc.code or exc)
        emit(_STAGE, "Batch transcripts unavailable; fetching one by one", status="info")
        return _transcripts_sequential(video_ids, emit=emit)

    emit(_STAGE, f"Fetching {len(video_ids)} transcripts (batch job)", status="progress",
         videos=len(video_ids), job_id=job_id)
    return _await_batch(job_id, emit=emit)


def _start_batch(video_ids: list[str]) -> str:
    """POST /youtube/transcript/batch → jobId. Raises SupadataError if batch is unusable.

    No `chunkSize` here — the batch endpoint does not accept it (unlike the single-video
    one), so transcripts come back at raw caption cadence. `youtube_channel._segments`
    re-chunks client-side, which keeps both fetch paths at the same evidence granularity.
    """
    started = _request(
        "POST",
        "/youtube/transcript/batch",
        json={"videoIds": video_ids, "lang": "en", "text": False},
    )
    job_id = started.get("jobId")
    if not job_id:
        raise SupadataError("batch job response carried no jobId")
    return job_id


def _await_batch(job_id: str, *, emit: Emit = noop_emit) -> list[dict]:
    """Poll GET /youtube/batch/{jobId} until it completes, fails, or the deadline passes."""

    delay = _POLL_INITIAL_S
    deadline = time.monotonic() + _POLL_DEADLINE_S
    while True:
        payload = _request("GET", f"/youtube/batch/{job_id}")
        status = payload.get("status")
        if status == "completed":
            return _usable_results(payload.get("results") or [], emit=emit)
        if status == "failed":
            raise SupadataError(f"batch job {job_id} failed", code="batch-failed")
        if time.monotonic() >= deadline:
            raise SupadataError(f"batch job {job_id} still {status} after {_POLL_DEADLINE_S:.0f}s")
        time.sleep(min(delay, max(0.0, deadline - time.monotonic())))
        delay = min(delay * 2, _POLL_MAX_S)


def _video_metadata(video_id: str) -> dict:
    """Title / upload date for one video, in the same shape a batch result's `video` block has.

    The single-video transcript endpoint returns no metadata, so without this every video
    ingested on the fallback path would be titled with its raw id. Costs one extra credit per
    video, but only on the path where batch is unavailable — a paid plan gets this bundled
    into the batch result for free. Best-effort: a failure loses the title, not the video.
    """
    time.sleep(_SEQUENTIAL_GAP_S)
    try:
        meta = _request(
            "GET", "/metadata", params={"url": f"https://www.youtube.com/watch?v={video_id}"}
        )
    except SupadataError as exc:
        logger.info("No metadata for video %s: %s", video_id, exc)
        return {}
    return {
        "title": meta.get("title"),
        "uploadDate": meta.get("createdAt"),
        "channel": {"name": (meta.get("author") or {}).get("displayName")},
    }


def _transcripts_sequential(video_ids: list[str], *, emit: Emit = noop_emit) -> list[dict]:
    """One /youtube/transcript call per video, throttled to the free-tier 1 req/s limit."""
    results: list[dict] = []
    for video_id in video_ids:
        # Sleep before the FIRST request too, not just between them: we arrive here straight
        # after a channel listing or a rejected batch attempt, both of which have already
        # spent this second's budget.
        time.sleep(_SEQUENTIAL_GAP_S)
        try:
            payload = _request(
                "GET",
                "/youtube/transcript",
                params={"videoId": video_id, "text": "false", "lang": "en"},
            )
        except SupadataError as exc:
            logger.warning("Skipping video %s: %s", video_id, exc)
            emit(_STAGE, f"Skipped (no transcript): {video_id}", status="skip", video_id=video_id)
            continue
        results.append(
            {"videoId": video_id, "transcript": payload, "video": _video_metadata(video_id)}
        )
    return results


def _usable_results(results: list[dict], *, emit: Emit = noop_emit) -> list[dict]:
    """Drop per-video failures (no captions, private, removed) and report them."""
    usable: list[dict] = []
    for entry in results:
        video_id = entry.get("videoId") or "?"
        error_code = entry.get("errorCode")
        if error_code or not entry.get("transcript"):
            logger.warning("Skipping video %s: %s", video_id, error_code or "no transcript")
            emit(_STAGE, f"Skipped ({error_code or 'no transcript'}): {video_id}",
                 status="skip", video_id=video_id)
            continue
        usable.append(entry)
    return usable


__all__ = [
    "SupadataError",
    "SourceUnavailable",
    "get_channel",
    "list_channel_video_ids",
    "transcripts",
]
