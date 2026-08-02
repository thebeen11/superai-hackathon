"""Supadata → SourceItem mapping for channel subscriptions.

The two things that silently break everything downstream if they drift: the millisecond →
second offset conversion (every citation lands ~1000× too deep) and `text` staying the
plain concatenation of segment texts (the Data Engineering guardrail rejects the item).
"""
from __future__ import annotations

import pytest

from app.config import settings
from app.discovery import supadata, youtube_channel
from app.discovery.exa_source import SourceUnavailable
from app.models import SourceType, YoutubeChannel


@pytest.fixture(autouse=True)
def _keyed(monkeypatch):
    """Pretend a Supadata key is configured; every network call is stubbed per-test."""
    monkeypatch.setattr(settings, "supadata_api_key", "test-key")


def _channel() -> YoutubeChannel:
    return YoutubeChannel(channel_id="UCtest", name="Test Channel", handle="@test")


def _entry(video_id: str = "vid1", **video) -> dict:
    return {
        "videoId": video_id,
        "transcript": {
            "content": [
                {"text": "nvidia is power constrained", "offset": 8150, "duration": 1200},
                {"text": "not demand constrained", "offset": 9350, "duration": 1100},
            ],
            "lang": "en",
        },
        "video": {"title": "The bottleneck", "uploadDate": "2026-08-01T00:00:00.000Z",
                  "channel": {"id": "UCtest", "name": "Test Channel"}, **video},
    }


# --- offset conversion (the ?t= deep link depends on this) ---

def test_offsets_are_converted_from_milliseconds_to_seconds(monkeypatch):
    # Chunk cap below the merge threshold so each caption stays its own segment.
    monkeypatch.setattr(settings, "youtube_transcript_chunk_size", 10)
    segments = youtube_channel._segments(_entry()["transcript"])
    assert [s.start for s in segments] == [8.15, 9.35]


# --- re-chunking (raw captions are too granular to be evidence) ---

def test_consecutive_captions_merge_into_evidence_sized_chunks():
    segments = youtube_channel._segments(_entry()["transcript"])
    assert len(segments) == 1
    assert segments[0].text == "nvidia is power constrained not demand constrained"
    # A merged chunk keeps the start of its FIRST caption, so the link lands at the top
    # of the thought rather than midway through it.
    assert segments[0].start == 8.15


def test_merge_starts_a_new_chunk_once_the_cap_is_reached(monkeypatch):
    monkeypatch.setattr(settings, "youtube_transcript_chunk_size", 20)
    transcript = {"content": [
        {"text": "aaaaaaaaaa", "offset": 0},      # 10 chars
        {"text": "bbbbbbbbb", "offset": 1000},    # +1+9 = 20 → fits
        {"text": "cccc", "offset": 2000},         # would exceed → new chunk
    ]}
    segments = youtube_channel._segments(transcript)
    assert [(s.start, s.text) for s in segments] == [
        (0.0, "aaaaaaaaaa bbbbbbbbb"),
        (2.0, "cccc"),
    ]


def test_an_oversized_caption_is_kept_rather_than_dropped(monkeypatch):
    monkeypatch.setattr(settings, "youtube_transcript_chunk_size", 5)
    transcript = {"content": [{"text": "a much longer caption than the cap", "offset": 500}]}
    segments = youtube_channel._segments(transcript)
    assert [(s.start, s.text) for s in segments] == [(0.5, "a much longer caption than the cap")]


def test_plain_text_transcript_degrades_to_one_untimed_segment():
    segments = youtube_channel._segments({"content": "just a wall of text", "lang": "en"})
    assert len(segments) == 1
    assert segments[0].start == 0.0


def test_empty_chunks_are_dropped():
    transcript = {"content": [{"text": "  ", "offset": 0}, {"text": "real", "offset": 500}]}
    segments = youtube_channel._segments(transcript)
    assert [(s.start, s.text) for s in segments] == [(0.5, "real")]


# --- SourceItem shape (the guardrail contract) ---

def test_item_text_is_exactly_the_segment_concatenation():
    item = youtube_channel._to_source_item(_entry(), fallback_channel_name=None)
    assert item is not None
    assert item.text == " ".join(s.text for s in item.segments)


def test_item_carries_youtube_type_url_author_and_published_at():
    item = youtube_channel._to_source_item(_entry(), fallback_channel_name=None)
    assert item.source_type is SourceType.YOUTUBE
    assert item.url == "https://www.youtube.com/watch?v=vid1"
    assert item.author == "Test Channel"
    assert item.published_at == "2026-08-01T00:00:00.000Z"


def test_channel_name_falls_back_when_batch_returns_no_video_metadata():
    """The sequential fallback carries no `video` block — the subscription supplies the name."""
    entry = {"videoId": "vid1", "transcript": _entry()["transcript"], "video": {}}
    item = youtube_channel._to_source_item(entry, fallback_channel_name="Test Channel")
    assert item.author == "Test Channel"
    assert item.title == "vid1"  # no metadata → the id is the honest title


def test_transcriptless_entry_yields_no_item():
    entry = {"videoId": "vid1", "transcript": {"content": []}, "video": {}}
    assert youtube_channel._to_source_item(entry, fallback_channel_name=None) is None


# --- fetch_channel_items ---

def test_already_seen_videos_are_skipped_before_the_transcript_call(monkeypatch):
    """Transcripts are billed per video, so known ids must never reach `transcripts()`."""
    requested: list[list[str]] = []
    monkeypatch.setattr(supadata, "list_channel_video_ids", lambda ident, limit: ["old", "new"])
    monkeypatch.setattr(
        youtube_channel.supadata, "transcripts",
        lambda ids, emit=None: requested.append(list(ids)) or [_entry("new")],
    )

    items = youtube_channel.fetch_channel_items(_channel(), limit=10, skip_video_ids={"old"})

    assert requested == [["new"]]
    assert [i.url for i in items] == ["https://www.youtube.com/watch?v=new"]


def test_no_new_videos_makes_no_transcript_call(monkeypatch):
    called = False

    def _fail(ids, emit=None):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(supadata, "list_channel_video_ids", lambda ident, limit: ["old"])
    monkeypatch.setattr(youtube_channel.supadata, "transcripts", _fail)

    assert youtube_channel.fetch_channel_items(_channel(), limit=10, skip_video_ids={"old"}) == []
    assert called is False


def test_missing_key_raises_source_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "supadata_api_key", None)
    with pytest.raises(SourceUnavailable):
        youtube_channel.fetch_channel_items(_channel(), limit=5, skip_video_ids=set())


# --- resolve_channel ---

def test_resolve_channel_maps_supadata_payload(monkeypatch):
    monkeypatch.setattr(
        youtube_channel.supadata, "get_channel",
        lambda ident: {"id": "UCabc", "name": "Bloomberg", "subscriberCount": 4200,
                       "thumbnail": "https://img/x.jpg"},
    )
    channel = youtube_channel.resolve_channel("@Bloomberg")
    assert channel.channel_id == "UCabc"
    assert channel.name == "Bloomberg"
    assert channel.handle == "@Bloomberg"   # what the user typed is preserved
    assert channel.subscriber_count == 4200


def test_resolve_channel_without_an_id_is_an_error(monkeypatch):
    monkeypatch.setattr(youtube_channel.supadata, "get_channel", lambda ident: {"name": "?"})
    with pytest.raises(supadata.SupadataError):
        youtube_channel.resolve_channel("nonsense")


# --- video id round-trip ---

@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.youtube.com/watch?v=abc123", "abc123"),
        ("https://www.youtube.com/watch?v=abc123&t=90s", "abc123"),
        ("https://example.com/article", "https://example.com/article"),
    ],
)
def test_video_id_from_url(url, expected):
    assert youtube_channel.video_id_from_url(url) == expected


# --- batch vs sequential (billing-sensitive: a started job's credits are committed) ---

def _batch_result(video_id: str = "vid1") -> dict:
    return {"status": "completed", "results": [_entry(video_id)], "stats": {"succeeded": 1}}


def test_batch_is_used_when_available(monkeypatch):
    seen: list[tuple[str, str]] = []

    def fake_request(method, path, **kw):
        seen.append((method, path))
        if path == "/youtube/transcript/batch":
            return {"jobId": "job-1"}
        return _batch_result()

    monkeypatch.setattr(supadata, "_request", fake_request)
    results = supadata.transcripts(["vid1"])

    assert [r["videoId"] for r in results] == ["vid1"]
    assert seen == [("POST", "/youtube/transcript/batch"), ("GET", "/youtube/batch/job-1")]


def test_batch_start_failure_falls_back_to_sequential(monkeypatch):
    """Batch is an advanced endpoint on some plans — degrade rather than fail."""
    monkeypatch.setattr(supadata.time, "sleep", lambda s: None)
    calls: list[str] = []

    def fake_request(method, path, **kw):
        calls.append(path)
        if path == "/youtube/transcript/batch":
            raise supadata.SupadataError("upgrade required", code="upgrade-required")
        return _entry()["transcript"]

    monkeypatch.setattr(supadata, "_request", fake_request)
    results = supadata.transcripts(["vid1", "vid2"])

    assert [r["videoId"] for r in results] == ["vid1", "vid2"]
    assert calls == ["/youtube/transcript/batch", "/youtube/transcript", "/youtube/transcript"]


def test_started_job_failure_does_not_re_bill_via_sequential(monkeypatch):
    """Once a job is accepted its credits are spent; retrying sequentially would bill twice."""
    calls: list[str] = []

    def fake_request(method, path, **kw):
        calls.append(path)
        if path == "/youtube/transcript/batch":
            return {"jobId": "job-1"}
        return {"status": "failed"}

    monkeypatch.setattr(supadata, "_request", fake_request)
    with pytest.raises(supadata.SupadataError):
        supadata.transcripts(["vid1"])
    assert "/youtube/transcript" not in calls   # the single-video endpoint was never hit


def test_per_video_errors_are_skipped_not_fatal(monkeypatch):
    def fake_request(method, path, **kw):
        if path == "/youtube/transcript/batch":
            return {"jobId": "job-1"}
        return {
            "status": "completed",
            "results": [
                _entry("good"),
                {"videoId": "bad", "errorCode": "transcript-unavailable"},
                {"videoId": "empty", "transcript": None},
            ],
        }

    monkeypatch.setattr(supadata, "_request", fake_request)
    assert [r["videoId"] for r in supadata.transcripts(["good", "bad", "empty"])] == ["good"]


def test_sequential_skips_videos_that_error(monkeypatch):
    monkeypatch.setattr(supadata.time, "sleep", lambda s: None)

    def fake_request(method, path, **kw):
        if path == "/youtube/transcript/batch":
            raise supadata.SupadataError("no batch", code="upgrade-required")
        if kw.get("params", {}).get("videoId") == "bad":
            raise supadata.SupadataError("no captions", code="transcript-unavailable")
        return _entry()["transcript"]

    monkeypatch.setattr(supadata, "_request", fake_request)
    assert [r["videoId"] for r in supadata.transcripts(["good", "bad"])] == ["good"]


def test_empty_video_list_makes_no_call(monkeypatch):
    monkeypatch.setattr(
        supadata, "_request",
        lambda *a, **k: pytest.fail("no request should be made for an empty list"),
    )
    assert supadata.transcripts([]) == []
