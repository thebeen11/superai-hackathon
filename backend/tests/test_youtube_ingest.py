"""Channel ingest wiring: fetch → pipeline → video ledger → watchlist match → save.

The database and Supadata are both stubbed; what's under test is the orchestration — in
particular that a video whose transcript was paid for gets recorded even when the Data
Engineering guardrail rejects it, so the next poll doesn't buy it again.
"""
from __future__ import annotations

import threading

import pytest

from app.discovery import youtube_ingest
from app.models import (
    CleanedItem,
    DataEngReport,
    ProcessingFailure,
    SourceItem,
    SourceType,
    Stream,
    TranscriptSegment,
    YoutubeChannel,
    YoutubeMatch,
)


def _source_item(video_id: str) -> SourceItem:
    segs = [TranscriptSegment(start=1.0, text="nvidia is power constrained")]
    return SourceItem(
        source_type=SourceType.YOUTUBE,
        title=f"video {video_id}",
        url=f"https://www.youtube.com/watch?v={video_id}",
        text=" ".join(s.text for s in segs),
        author="Test Channel",
        segments=segs,
    )


def _cleaned(url: str) -> CleanedItem:
    return CleanedItem(
        source_url=url, source_type=SourceType.YOUTUBE, title="t", clean_text="c",
        stream=Stream.MICRO, industry="Semiconductors",
    )


@pytest.fixture
def wiring(monkeypatch):
    """Stub every boundary and record what each one was handed."""
    calls: dict = {"recorded": None, "saved": None, "matched_items": None, "polled": []}

    monkeypatch.setattr(youtube_ingest, "known_video_ids", lambda cid: {"seen"})
    monkeypatch.setattr(
        youtube_ingest, "record_youtube_videos",
        lambda rows: calls.__setitem__("recorded", rows),
    )
    monkeypatch.setattr(
        youtube_ingest, "save_youtube_matches",
        lambda ms: (calls.__setitem__("saved", ms), len(ms))[1],
    )
    monkeypatch.setattr(
        youtube_ingest, "mark_youtube_channel_polled",
        lambda cid, error=None: calls["polled"].append((cid, error)),
    )
    monkeypatch.setattr(
        youtube_ingest, "list_cleaned_items_by_urls",
        lambda urls: [_cleaned(u) for u in urls],
    )

    def fake_match(items, *, channel_id, emit=None):
        calls["matched_items"] = [i.source_url for i in items]
        return [
            YoutubeMatch(
                video_url=i.source_url, video_id="x", channel_id=channel_id,
                ticker="$NVDA", quote="q", relevance=0.9, title="t",
            )
            for i in items
        ]

    monkeypatch.setattr(youtube_ingest, "match_items_to_watchlist", fake_match)
    return calls


def _stub_pipeline(monkeypatch, report: DataEngReport):
    monkeypatch.setattr(
        youtube_ingest, "process_discovery_result", lambda result, emit=None: report
    )


def _stub_fetch(monkeypatch, items: list[SourceItem]):
    seen: dict = {}

    def fake(channel, *, limit, skip_video_ids, emit=None):
        seen["limit"] = limit
        seen["skip"] = skip_video_ids
        return items

    monkeypatch.setattr(youtube_ingest.youtube_channel, "fetch_channel_items", fake)
    return seen


def _channel() -> YoutubeChannel:
    return YoutubeChannel(channel_id="UCtest", name="Test Channel")


def test_ingest_persists_matches_and_records_videos(monkeypatch, wiring):
    _stub_fetch(monkeypatch, [_source_item("new1")])
    _stub_pipeline(monkeypatch, DataEngReport(persisted=1, failed=0))

    report = youtube_ingest.ingest_channel(_channel(), limit=5)

    assert (report.videos_seen, report.persisted, report.matched) == (1, 1, 1)
    assert wiring["recorded"] == [{
        "video_id": "new1",
        "channel_id": "UCtest",
        "video_url": "https://www.youtube.com/watch?v=new1",
        "title": "video new1",
        "published_at": None,
        "persisted": True,
    }]
    assert wiring["polled"] == [("UCtest", None)]


def test_guardrail_rejected_video_is_still_recorded_but_not_matched(monkeypatch, wiring):
    """A rejected video is not in cleaned_items — but its credit was already spent."""
    good, bad = _source_item("good"), _source_item("bad")
    _stub_fetch(monkeypatch, [good, bad])
    _stub_pipeline(
        monkeypatch,
        DataEngReport(
            persisted=1, failed=1,
            failures=[ProcessingFailure(source_url=bad.url, reason="cleaned text not found")],
        ),
    )

    report = youtube_ingest.ingest_channel(_channel())

    recorded = {r["video_id"]: r["persisted"] for r in wiring["recorded"]}
    assert recorded == {"good": True, "bad": False}   # both recorded, honestly flagged
    assert wiring["matched_items"] == [good.url]      # only the survivor is matched
    assert report.matched == 1


def test_known_videos_are_passed_as_the_skip_list(monkeypatch, wiring):
    seen = _stub_fetch(monkeypatch, [])
    youtube_ingest.ingest_channel(_channel(), limit=7)
    assert seen["skip"] == {"seen"}
    assert seen["limit"] == 7


def test_no_new_videos_short_circuits_before_the_pipeline(monkeypatch, wiring):
    _stub_fetch(monkeypatch, [])

    report = youtube_ingest.ingest_channel(_channel())

    assert (report.videos_seen, report.persisted, report.matched) == (0, 0, 0)
    assert wiring["recorded"] is None     # nothing fetched → nothing to record
    assert wiring["saved"] is None
    assert wiring["polled"] == [("UCtest", None)]


def test_a_failing_channel_does_not_abort_the_poll(monkeypatch, wiring):
    channels = [_channel(), YoutubeChannel(channel_id="UCok", name="Fine")]
    monkeypatch.setattr(youtube_ingest, "list_youtube_channels", lambda: channels)

    def flaky(channel, *, limit=None, emit=None):
        if channel.channel_id == "UCtest":
            raise RuntimeError("supadata exploded")
        return __import__("app.models", fromlist=["x"]).YoutubeIngestReport(
            channels=1, videos_seen=2, persisted=2, matched=1
        )

    monkeypatch.setattr(youtube_ingest, "ingest_channel", flaky)

    total = youtube_ingest.ingest_all_enabled_channels()

    assert total.channels == 2
    assert total.persisted == 2 and total.matched == 1
    assert total.errors == ["Test Channel: supadata exploded"]
    assert ("UCtest", "supadata exploded") in wiring["polled"]


def test_disabled_channels_are_not_polled(monkeypatch, wiring):
    monkeypatch.setattr(
        youtube_ingest, "list_youtube_channels",
        lambda: [YoutubeChannel(channel_id="UCoff", name="Paused", enabled=False)],
    )
    monkeypatch.setattr(
        youtube_ingest, "ingest_channel",
        lambda *a, **k: pytest.fail("a paused channel must never be ingested"),
    )
    assert youtube_ingest.ingest_all_enabled_channels().channels == 0


# --- API: subscribing must not ingest, and a channel must not ingest twice at once ---

@pytest.fixture(autouse=True)
def _clean_job_registry():
    """The job registry is process-global; a job left running would leak into other tests."""
    from app import jobs

    jobs._jobs.clear()
    yield
    jobs._jobs.clear()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app import main

    return TestClient(main.app)


def test_subscribing_does_not_ingest(client, monkeypatch):
    """The whole point of the split: following a channel must not wait on transcripts."""
    from app import main

    monkeypatch.setattr(main, "resolve_channel", lambda ident: _channel())
    monkeypatch.setattr(main, "get_youtube_channel", lambda cid: None)
    monkeypatch.setattr(main, "save_youtube_channel", lambda ch: ch)
    monkeypatch.setattr(
        main, "ingest_channel",
        lambda *a, **k: pytest.fail("subscribing must not trigger an ingest"),
    )

    res = client.post("/api/sources/youtube/channels", json={"id": "@test"})

    assert res.status_code == 200
    assert res.json()["channel_id"] == "UCtest"


def test_a_second_stream_attaches_to_the_running_job(client, monkeypatch):
    """Two concurrent ingests would re-buy every transcript before either records them."""
    from app import main
    from app.jobs import create_job

    monkeypatch.setattr(main, "get_youtube_channel", lambda cid: _channel())
    monkeypatch.setattr(
        main, "ingest_channel",
        lambda *a, **k: pytest.fail("a second ingest must not start"),
    )
    # Still running when the request arrives — that is what triggers the attach. Finished
    # from another thread so the replayed stream reaches its terminal frame and closes.
    running = create_job("youtube", "UCtest")
    running.add_event({"stage": "discover.youtube.channel", "status": "progress",
                       "message": "already going", "data": {}, "ts": 0})
    threading.Timer(0.15, lambda: running.finish({"persisted": 0})).start()

    with client.stream(
        "POST", "/api/sources/youtube/channels/UCtest/refresh/stream"
    ) as res:
        assert res.status_code == 200
        body = "".join(res.iter_text())
    assert "already going" in body      # replayed what the running job had already done
    assert "event: result" in body


def test_blocking_refresh_conflicts_while_a_job_runs(client, monkeypatch):
    from app import main
    from app.jobs import create_job

    monkeypatch.setattr(main, "get_youtube_channel", lambda cid: _channel())
    create_job("youtube", "UCtest")
    monkeypatch.setattr(
        main, "ingest_channel",
        lambda *a, **k: pytest.fail("a second ingest must not start"),
    )

    res = client.post("/api/sources/youtube/channels/UCtest/refresh")

    assert res.status_code == 409
    assert "Already fetching" in res.json()["detail"]


def test_poll_returns_immediately_and_registers_a_job(client, monkeypatch):
    from app import main

    slow = threading.Event()
    monkeypatch.setattr(
        main, "ingest_all_enabled_channels", lambda emit=None: slow.wait(timeout=2)
    )

    res = client.post("/api/sources/youtube/poll")

    assert res.status_code == 202
    job_id = res.json()["job_id"]
    listed = client.get("/api/sources/youtube/jobs").json()
    assert any(j["job_id"] == job_id and j["channel_id"] is None for j in listed)
    slow.set()
