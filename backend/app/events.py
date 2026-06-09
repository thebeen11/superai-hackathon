"""Progress events for SSE streaming.

The pipelines (Discovery, Data Engineering) are plain synchronous functions. To give
the UI visibility into what's happening behind the scenes, each stage can call an
`emit` callback that publishes a `ProgressEvent`. By default the callback is a no-op,
so the same functions remain usable in non-streaming contexts (CLI, tests, the
back-compat JSON endpoints).
"""
from __future__ import annotations

import time
from typing import Any, Callable

from pydantic import BaseModel, Field


class ProgressEvent(BaseModel):
    """A single behind-the-scenes progress signal streamed to the client."""

    stage: str                       # logical step, e.g. "refine", "discover.web", "dataeng.item"
    status: str = "info"             # start | progress | ok | skip | error | info
    message: str = ""                # human-readable description
    data: dict[str, Any] = Field(default_factory=dict)  # structured extras (counts, urls, ...)
    ts: float = Field(default_factory=lambda: time.time())  # epoch seconds


# An `emit` callable: emit(stage, message="", *, status="info", **data) -> None
Emit = Callable[..., None]


def noop_emit(stage: str, message: str = "", *, status: str = "info", **data: Any) -> None:
    """Default emitter — does nothing. Used when no SSE consumer is attached."""
    return None


def call_maybe_emit(fn: Callable, *args: Any, emit: Emit) -> Any:
    """Call `fn(*args, emit)` if `fn` accepts the extra `emit` argument, else `fn(*args)`.

    Lets us thread the progress emitter through pipeline helpers while staying
    compatible with callables (and test stubs) that use the older emit-less signature.
    """
    import inspect

    try:
        sig = inspect.signature(fn)
        params = list(sig.parameters.values())
        accepts_var = any(p.kind == p.VAR_POSITIONAL for p in params)
        positional = sum(
            1 for p in params
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        )
        if accepts_var or positional >= len(args) + 1:
            return fn(*args, emit)
    except (TypeError, ValueError):
        pass
    return fn(*args)
