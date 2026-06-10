"""The Discovery agent.

Given a single topic query, fan out to every source branch in parallel, merge
the results into one normalized list, dedupe by URL, and record a reason for any
branch that could not run. The user picks the *topic*; the agent picks the
*sources*.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from ..events import Emit, noop_emit
from ..models import (
    Clarify,
    ClarificationMode,
    DiscoveryResult,
    Proceed,
    SkippedSource,
    SourceItem,
    SourceType,
)
from . import exa_source, youtube_source
from .exa_source import SourceUnavailable
from .refine import refine_query

logger = logging.getLogger(__name__)


def _branches():
    """Branch table, resolved at call time so the source functions stay swappable.

    Each entry: (source_type, callable(query, max_results) -> list[SourceItem]).
    """
    return (
        (SourceType.WEB, exa_source.search),
        (SourceType.YOUTUBE, youtube_source.search),
    )


def discover_with_refinement(
    query: str,
    mode: ClarificationMode = ClarificationMode.INTERACTIVE,
    round: int = 0,
    max_results: int | None = None,
    emit: Emit = noop_emit,
) -> DiscoveryResult | Clarify:
    """Full Discovery entrypoint: refine the query, then fan out (Req 2, 4).

    Returns a `Clarify` (interactive mode, ambiguous query) when the Commander must
    disambiguate before fan-out, otherwise a `DiscoveryResult` carrying the
    original/refined query audit trail.
    """
    emit("refine", f"Analyzing query: {query!r}", status="start")
    outcome = refine_query(query, mode, round=round)
    if isinstance(outcome, Clarify):
        emit("refine", "Query is ambiguous; clarification needed",
             status="ok", questions=outcome.questions)
        return outcome

    assert isinstance(outcome, Proceed)
    emit("refine", f"Using refined query: {outcome.refined_query!r}",
         status="ok", refined_query=outcome.refined_query,
         refinement_failed=outcome.refinement_failed,
         proceeded_without_clarification=outcome.proceeded_without_clarification)
    result = discover(outcome.refined_query, max_results=max_results, emit=emit)

    # Audit trail (Req 2.3): record what the Commander submitted + any refinement note.
    result.original_query = outcome.original_query
    if outcome.refinement_failed:
        result.refinement_note = "refinement failed; used original query"
    elif outcome.proceeded_without_clarification:
        result.refinement_note = "proceeded without clarification"
    return result


def discover(
    query: str,
    max_results: int | None = None,
    emit: Emit = noop_emit,
    *,
    start_published_date: str | None = None,
    end_published_date: str | None = None,
) -> DiscoveryResult:
    """Run all source branches for a topic and return a merged result.

    `start_published_date`/`end_published_date` (ISO8601) optionally restrict results
    to a published-date window, enabling time-bucketed backfills.
    """
    query = query.strip()
    if not query:
        raise ValueError("query must not be empty")
    if max_results is not None and not (1 <= max_results <= 50):
        raise ValueError("max_results must be an integer between 1 and 50")

    result = DiscoveryResult(query=query)

    def _run(branch):
        source_type, fn = branch
        return source_type, fn, _safe_call(
            fn, query, max_results, emit,
            start_published_date=start_published_date,
            end_published_date=end_published_date,
        )

    branches = _branches()
    emit("discover", f"Fanning out to {len(branches)} sources", status="start",
         query=query, sources=[st.value for st, _ in branches])
    with ThreadPoolExecutor(max_workers=len(branches)) as pool:
        for source_type, _fn, outcome in pool.map(_run, branches):
            items, error = outcome
            if error is not None:
                emit("discover", f"Source {source_type.value} skipped: {error}",
                     status="skip", source_type=source_type.value, reason=error)
                result.skipped.append(
                    SkippedSource(source_type=source_type, reason=error)
                )
            else:
                result.items.extend(items)

    before = len(result.items)
    result.items = _dedupe(result.items)
    emit("discover", f"Deduplicated {before} → {len(result.items)} items",
         status="progress", before=before, after=len(result.items))
    logger.info(
        "Discovery for %r: %d items, %d skipped",
        query,
        len(result.items),
        len(result.skipped),
    )
    emit("discover", f"Discovery complete: {len(result.items)} items, "
         f"{len(result.skipped)} skipped", status="ok",
         items=len(result.items), skipped=len(result.skipped))
    return result


def _safe_call(
    fn, query, max_results, emit: Emit = noop_emit,
    *,
    start_published_date: str | None = None,
    end_published_date: str | None = None,
) -> tuple[list[SourceItem], str | None]:
    """Run a branch, converting failures into a skip reason."""
    try:
        return fn(
            query, max_results, emit,
            start_published_date=start_published_date,
            end_published_date=end_published_date,
        ), None
    except SourceUnavailable as exc:
        return [], str(exc)
    except Exception as exc:  # noqa: BLE001 - never let one branch kill the run
        logger.exception("Discovery branch failed")
        return [], f"unexpected error: {exc}"


def _dedupe(items: list[SourceItem]) -> list[SourceItem]:
    seen: set[str] = set()
    out: list[SourceItem] = []
    for item in items:
        if item.url in seen:
            continue
        seen.add(item.url)
        out.append(item)
    return out
