"""Exa branch of Discovery: web search + content crawl for a topic query."""
from __future__ import annotations

import logging

from ..config import settings
from ..events import Emit, noop_emit
from ..models import SourceItem, SourceType

logger = logging.getLogger(__name__)


class SourceUnavailable(Exception):
    """Raised when a branch cannot run (e.g. missing key) — caller skips it."""


def search(
    query: str,
    max_results: int | None = None,
    emit: Emit = noop_emit,
    *,
    start_published_date: str | None = None,
    end_published_date: str | None = None,
) -> list[SourceItem]:
    """Search the web and return crawled article content as SourceItems.

    Raises SourceUnavailable if the Exa key is missing so the agent can record
    a skip reason rather than crashing the whole run.

    `start_published_date`/`end_published_date` (ISO8601, e.g. "2025-06-01") restrict
    results to a published-date window — used for time-bucketed backfills.
    """
    if not settings.exa_api_key:
        raise SourceUnavailable("EXA_API_KEY not set")

    limit = max_results or settings.discovery_max_results_per_source

    # Imported lazily so the app still boots without the dependency installed.
    from exa_py import Exa

    window = ""
    if start_published_date or end_published_date:
        window = f" [{start_published_date or '...'} → {end_published_date or '...'}]"
    emit("discover.web", f"Searching the web via Exa (up to {limit}){window}", status="start")
    exa = Exa(api_key=settings.exa_api_key)
    search_kwargs: dict = {"type": "auto", "num_results": limit, "text": True}
    if start_published_date:
        search_kwargs["start_published_date"] = start_published_date
    if end_published_date:
        search_kwargs["end_published_date"] = end_published_date
    response = exa.search_and_contents(query, **search_kwargs)

    raw_results = getattr(response, "results", []) or []
    emit("discover.web", f"Exa returned {len(raw_results)} hits; crawling content",
         status="progress", hits=len(raw_results))

    items: list[SourceItem] = []
    for r in raw_results:
        text = (getattr(r, "text", None) or "").strip()
        if not text:
            continue  # no usable content — skip this hit
        items.append(
            SourceItem(
                source_type=SourceType.WEB,
                title=getattr(r, "title", None) or r.url,
                url=r.url,
                text=text,
                author=getattr(r, "author", None),
                published_at=getattr(r, "published_date", None),
            )
        )
    logger.info("Exa returned %d usable items for %r", len(items), query)
    emit("discover.web", f"Web branch done: {len(items)} usable articles",
         status="ok", count=len(items))
    return items
