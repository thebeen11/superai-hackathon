"""Background job execution — the detached runner and its shared recording path.

Ingest takes minutes per video, so it never runs inside a request. What matters here is
that the caller is released immediately, that the outcome still lands in the job, and that
a failure is recorded rather than lost with the thread.
"""
from __future__ import annotations

import threading
import time

from app.jobs import create_job
from app.sse import run_detached


def _wait_for(job, statuses: set[str], timeout: float = 3.0) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if job.status in statuses:
            return job.status
        time.sleep(0.01)
    raise AssertionError(f"job stayed {job.status!r} for {timeout}s")


def test_caller_is_released_before_the_work_finishes():
    job = create_job("youtube", "UCtest")
    started = threading.Event()
    release = threading.Event()

    def work(emit):
        started.set()
        release.wait(timeout=3)
        return {"persisted": 1}

    run_detached(job, work)

    assert started.wait(timeout=3), "work never started"
    assert job.status == "running"      # returned while work is still going
    release.set()
    assert _wait_for(job, {"done"}) == "done"


def test_result_and_events_land_on_the_job():
    job = create_job("youtube", "UCtest")

    def work(emit):
        emit("discover.youtube.channel", "start", status="start")
        emit("discover.youtube.channel", "done", status="ok", count=2)
        return {"persisted": 2, "matched": 1}

    run_detached(job, work)
    _wait_for(job, {"done"})

    assert job.result == {"persisted": 2, "matched": 1}
    assert [e["status"] for e in job.events] == ["start", "ok"]
    assert job.events[1]["data"]["count"] == 2


def test_a_raising_work_marks_the_job_failed():
    job = create_job("youtube", "UCtest")

    def work(emit):
        raise RuntimeError("supadata exploded")

    run_detached(job, work)
    _wait_for(job, {"error"})

    assert job.error == {"type": "RuntimeError", "message": "supadata exploded"}
    assert job.result is None


def test_pydantic_results_are_serialized():
    """The job stores JSON, not models — a reconnecting client gets the same shape."""
    from app.models import YoutubeIngestReport

    job = create_job("youtube", "UCtest")
    run_detached(job, lambda emit: YoutubeIngestReport(channels=1, persisted=3, matched=2))
    _wait_for(job, {"done"})

    assert job.result["persisted"] == 3
    assert job.result["matched"] == 2


def test_a_subscriber_attaching_late_still_sees_the_whole_run():
    """Reattaching after a reload must replay from the start, not just the tail."""
    job = create_job("youtube", "UCtest")

    def work(emit):
        emit("discover.youtube.channel", "one", status="progress")
        emit("discover.youtube.channel", "two", status="progress")
        return {"persisted": 1}

    run_detached(job, work)
    _wait_for(job, {"done"})

    events = list(job.subscribe())
    names = [name for name, _ in events]
    assert names == ["progress", "progress", "result", "done"]
