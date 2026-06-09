"""Server-Sent Events plumbing.

`sse_stream(work)` runs a synchronous `work(emit)` function on a background thread and
streams every `ProgressEvent` it emits to the client as it happens. When `work` returns,
its value is streamed as a terminal `result` event; if it raises, an `error` event is
sent instead. A final `done` event always closes the stream.

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

    def emit(stage: str, message: str = "", *, status: str = "info", **data: Any) -> None:
        evt = ProgressEvent(stage=stage, status=status, message=message, data=data)
        payload = evt.model_dump(mode="json")
        events.put(("progress", payload))
        if job is not None:
            job.add_event(payload)

    def runner() -> None:
        try:
            result = work(emit)
            payload = _jsonable(result)
            events.put(("result", payload))
            if job is not None:
                job.finish(payload)
        except Exception as exc:  # noqa: BLE001 - surface any failure to the client
            logger.exception("SSE work failed")
            err = {"type": type(exc).__name__, "message": str(exc)}
            events.put(("error", err))
            if job is not None:
                job.fail(err)
        finally:
            events.put(_SENTINEL)

    def event_generator():
        thread = threading.Thread(target=runner, daemon=True)
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
