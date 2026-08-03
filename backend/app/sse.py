"""Running blocking work in the background, and streaming its progress.

`sse_stream(work)` runs a synchronous `work(emit)` function on a background thread and
streams every `ProgressEvent` it emits to the client as it happens. When `work` returns,
its value is streamed as a terminal `result` event; if it raises, an `error` event is
sent instead. A final `done` event always closes the stream.

`run_detached(job, work)` runs the same shape of work with no client attached, for callers
that cannot consume a stream (Cloud Scheduler). Both record into a `Job`, so an observer
can attach — or re-attach after a reload — via `Job.subscribe()`.

This lets the existing blocking pipelines report progress without being rewritten as
async generators — they just call `emit(...)` at each stage.
"""
from __future__ import annotations

import json
import logging
import queue
import threading
from typing import Any, Callable, Iterable

from pydantic import BaseModel
from starlette.responses import StreamingResponse

from .events import ProgressEvent
from .jobs import Job

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # disable proxy buffering (nginx) so events flush
}

logger = logging.getLogger(__name__)

_SENTINEL = object()


def _jsonable(obj: Any) -> Any:
    """Recursively convert pydantic models / containers into JSON-safe values."""
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, (list, tuple)):
        return [_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    return obj


def _format_sse(event: str, data: Any) -> str:
    """Encode one SSE frame (`event:` + `data:` lines, blank-line terminated)."""
    return f"event: {event}\ndata: {json.dumps(_jsonable(data))}\n\n"


def _record(job: Job | None, sink: Callable[[str, Any], None] | None = None):
    """Build the `(emit, runner)` pair that turns `work(emit)` into recorded job events.

    Single definition of what a run writes where, so the streaming and detached paths can
    never drift on event shape, result serialization, or failure handling. `sink` is an
    optional extra consumer (the SSE queue); `job` is the durable record an observer
    attaches to later.
    """

    def emit(stage: str, message: str = "", *, status: str = "info", **data: Any) -> None:
        evt = ProgressEvent(stage=stage, status=status, message=message, data=data)
        payload = evt.model_dump(mode="json")
        if sink is not None:
            sink("progress", payload)
        if job is not None:
            job.add_event(payload)

    def runner(work: Callable[[Callable[..., None]], Any]) -> None:
        try:
            payload = _jsonable(work(emit))
            if sink is not None:
                sink("result", payload)
            if job is not None:
                job.finish(payload)
        except Exception as exc:  # noqa: BLE001 - surface any failure to the client/job
            logger.exception("Background work failed")
            err = {"type": type(exc).__name__, "message": str(exc)}
            if sink is not None:
                sink("error", err)
            if job is not None:
                job.fail(err)

    return emit, runner


def run_detached(job: Job, work: Callable[[Callable[..., None]], Any]) -> None:
    """Start `work(emit)` on a daemon thread and return immediately.

    For callers that cannot hold a stream open — Cloud Scheduler hitting a cron endpoint.
    Progress, the result and any failure land in `job`, so the UI can attach afterwards via
    `Job.subscribe()`.

    NOTE: this relies on the Cloud Run service running with `--min-instances=1` and
    `--no-cpu-throttling` (see deploy.sh). With CPU throttled between requests, or an
    instance free to scale to zero, a detached thread is frozen or killed mid-run.
    """
    _, runner = _record(job)
    threading.Thread(target=runner, args=(work,), name=f"job-{job.id[:8]}", daemon=True).start()


def sse_stream(
    work: Callable[[Callable[..., None]], Any], *, job: Job | None = None
) -> StreamingResponse:
    """Stream a blocking `work(emit)` call as Server-Sent Events.

    `work` receives an `emit(stage, message="", *, status="info", **data)` callback and
    returns a JSON-serializable result (pydantic model, list, or dict). Progress is sent
    as `progress` events; the return value as a `result` event; failures as `error`.

    When a `job` is supplied, every event is also recorded into it (and its id is sent as
    a leading `job` frame) so a client that reconnects later can replay/resume the run.
    """
    events: queue.Queue = queue.Queue()
    _, runner = _record(job, sink=lambda name, payload: events.put((name, payload)))

    def run_then_close() -> None:
        # The queue is unbounded and the thread never reads the response, so work runs to
        # completion — and keeps recording into `job` — even if the client disconnects.
        try:
            runner(work)
        finally:
            events.put(_SENTINEL)

    def event_generator():
        thread = threading.Thread(target=run_then_close, daemon=True)
        thread.start()
        if job is not None:
            yield _format_sse("job", {"id": job.id})
        while True:
            item = events.get()
            if item is _SENTINEL:
                yield _format_sse("done", {})
                break
            event_name, payload = item
            yield _format_sse(event_name, payload)

    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=_SSE_HEADERS)


def sse_from_subscribe(events_iter: Iterable[tuple[str, Any]]) -> StreamingResponse:
    """Format a `(event_name, payload)` iterable as an SSE response.

    Used to replay/resume a recorded `Job` (see `Job.subscribe`) to a reconnecting client.
    """

    def gen():
        for event_name, payload in events_iter:
            yield _format_sse(event_name, payload)

    return StreamingResponse(gen(), media_type="text/event-stream", headers=_SSE_HEADERS)
