"""In-memory registry of streaming discovery jobs.

A streaming `/dataeng/process/stream` run records its progress into a `Job` here so a
client that reloads the page mid-run can reconnect (via `/dataeng/jobs/{id}/stream`) and
resume the live indicator. The registry is process-local (single uvicorn worker in dev);
a multi-worker deploy would need shared storage.
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Iterator

# Keep finished jobs around briefly so a reconnect right after completion still works,
# then prune so the registry can't grow without bound.
_FINISHED_TTL_SECONDS = 30 * 60
_MAX_JOBS = 100
# How long a reconnect subscriber blocks waiting for the next event before re-checking
# (also bounds shutdown latency).
_WAIT_TIMEOUT_SECONDS = 15.0


class Job:
    """One streaming discovery run: its progress events, terminal result, and status."""

    def __init__(self, kind: str, label: str) -> None:
        self.id = uuid.uuid4().hex
        self.kind = kind
        self.label = label
        self.status = "running"  # running | done | error
        self.created_at = time.time()
        self.events: list[dict] = []
        self.result: Any = None
        self.error: dict | None = None
        self._cond = threading.Condition()

    def add_event(self, payload: dict) -> None:
        with self._cond:
            self.events.append(payload)
            self._cond.notify_all()

    def finish(self, result: Any) -> None:
        with self._cond:
            self.result = result
            self.status = "done"
            self._cond.notify_all()

    def fail(self, error: dict) -> None:
        with self._cond:
            self.error = error
            self.status = "error"
            self._cond.notify_all()

    def summary(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "query": self.label,
            "status": self.status,
            "created_at": self.created_at,
        }

    def subscribe(self) -> Iterator[tuple[str, Any]]:
        """Yield `(event_name, payload)` for a (possibly late) subscriber.

        Replays buffered progress from the start, then streams new events live until the
        job reaches a terminal state, finishing with a `result`/`error` and a `done`.
        Events are collected under the lock and yielded outside it.
        """
        idx = 0
        while True:
            batch: list[tuple[str, Any]] = []
            terminal: str | None = None
            with self._cond:
                while idx >= len(self.events) and self.status == "running":
                    self._cond.wait(timeout=_WAIT_TIMEOUT_SECONDS)
                while idx < len(self.events):
                    batch.append(("progress", self.events[idx]))
                    idx += 1
                if idx >= len(self.events) and self.status != "running":
                    terminal = self.status
            for item in batch:
                yield item
            if terminal:
                if terminal == "done":
                    yield ("result", self.result)
                else:
                    yield ("error", self.error or {"message": "job failed"})
                yield ("done", {})
                return


_jobs: dict[str, Job] = {}
_lock = threading.Lock()


def _prune_locked() -> None:
    """Drop finished jobs past their TTL, then cap total size (oldest finished first)."""
    now = time.time()
    stale = [
        jid for jid, j in _jobs.items()
        if j.status != "running" and now - j.created_at > _FINISHED_TTL_SECONDS
    ]
    for jid in stale:
        del _jobs[jid]
    if len(_jobs) > _MAX_JOBS:
        finished = sorted(
            (j for j in _jobs.values() if j.status != "running"),
            key=lambda j: j.created_at,
        )
        for j in finished[: len(_jobs) - _MAX_JOBS]:
            _jobs.pop(j.id, None)


def create_job(kind: str, label: str) -> Job:
    job = Job(kind, label)
    with _lock:
        _prune_locked()
        _jobs[job.id] = job
    return job


def get_job(job_id: str) -> Job | None:
    with _lock:
        return _jobs.get(job_id)


def list_jobs(status: str | None = None) -> list[dict]:
    with _lock:
        jobs = list(_jobs.values())
    return [j.summary() for j in jobs if status is None or j.status == status]
