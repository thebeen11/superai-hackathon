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
from typing import Any, Callable

from pydantic import BaseModel
from starlette.responses import StreamingResponse

from .events import ProgressEvent

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


def sse_stream(work: Callable[[Callable[..., None]], Any]) -> StreamingResponse:
    """Stream a blocking `work(emit)` call as Server-Sent Events.

    `work` receives an `emit(stage, message="", *, status="info", **data)` callback and
    returns a JSON-serializable result (pydantic model, list, or dict). Progress is sent
    as `progress` events; the return value as a `result` event; failures as `error`.
    """
    events: queue.Queue = queue.Queue()

    def emit(stage: str, message: str = "", *, status: str = "info", **data: Any) -> None:
        evt = ProgressEvent(stage=stage, status=status, message=message, data=data)
        events.put(("progress", evt.model_dump(mode="json")))

    def runner() -> None:
        try:
            result = work(emit)
            events.put(("result", _jsonable(result)))
        except Exception as exc:  # noqa: BLE001 - surface any failure to the client
            logger.exception("SSE work failed")
            events.put(("error", {"type": type(exc).__name__, "message": str(exc)}))
        finally:
            events.put(_SENTINEL)

    def event_generator():
        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        while True:
            item = events.get()
            if item is _SENTINEL:
                yield _format_sse("done", {})
                break
            event_name, payload = item
            yield _format_sse(event_name, payload)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable proxy buffering (nginx) so events flush
        },
    )
