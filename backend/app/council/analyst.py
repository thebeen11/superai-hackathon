"""Tier 3 — the Andie squad (sector analysts).

Three desks, each covering a disjoint set of sectors, each capped at 20 stocks to
keep the LLM's attention sharp (PROJECT_GUIDANCE §3, §12.2). A desk reads only the
`[MICRO]`/`[INDUSTRY]` items for its sectors (the macro bypass keeps `[MACRO]` away
from the analysts) and emits an Investment Highlights & Catalyst Note with a
per-stock conviction. Every conviction must be backed by a real source quote — the
no-orphan guardrail (§12.6) is enforced by mapping each cited source back to one of
the items the desk was actually given.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from ..events import Emit, noop_emit
from ..llm import ReasoningError, converse_structured
from ..models import CleanedItem, Evidence, SectorNote, StockTake
from ..prompts import get_prompt

logger = logging.getLogger(__name__)

# Sector → desk. Disjoint cover of the SECTORS taxonomy; "Unclassified" is ignored.
DESK_SECTORS: dict[str, set[str]] = {
    "TMT": {"Technology", "Communication Services"},
    "Physical": {"Energy", "Industrials", "Basic Materials", "Utilities", "Real Estate"},
    "Capital": {"Financials", "Consumer Discretionary", "Consumer Staples", "Healthcare"},
}
DESK_ORDER = ["TMT", "Physical", "Capital"]
MAX_STOCKS_PER_DESK = 20  # §12.2 — avoid "lost in the middle" context degradation
_SNIPPET = 600            # chars of clean_text shown per item to bound the prompt


class _LLMEvidence(BaseModel):
    quote: str
    source_index: int  # index into the numbered excerpt list shown in the prompt


class _LLMStock(BaseModel):
    ticker: str
    conviction: float
    horizon: str = ""
    rationale: str = ""
    evidence: list[_LLMEvidence] = Field(default_factory=list)


class _AnalystOutput(BaseModel):
    summary: str = ""
    highlights: list[str] = Field(default_factory=list)
    stocks: list[_LLMStock] = Field(default_factory=list)


def route_to_desks(items: list[CleanedItem]) -> dict[str, list[CleanedItem]]:
    """Group MICRO/INDUSTRY items by desk via their `industry` label."""
    buckets: dict[str, list[CleanedItem]] = {desk: [] for desk in DESK_ORDER}
    for it in items:
        for desk, sectors in DESK_SECTORS.items():
            if it.industry in sectors:
                buckets[desk].append(it)
                break
    return buckets


def _digest(items: list[CleanedItem]) -> str:
    """Numbered, length-bounded excerpt list the analyst cites back into."""
    lines: list[str] = []
    for i, it in enumerate(items):
        tickers = ", ".join(e.canonical for e in it.entities if e.canonical.startswith("$"))
        text = it.clean_text[:_SNIPPET].replace("\n", " ")
        lines.append(
            f"[{i}] title={it.title!r} tickers=[{tickers}] url={it.source_url}\n    {text}"
        )
    return "\n".join(lines)


def _ground_stocks(out: _AnalystOutput, items: list[CleanedItem]) -> list[StockTake]:
    """Map cited source indices back to real URLs; drop ungrounded stocks (no-orphan)."""
    stocks: list[StockTake] = []
    for s in out.stocks[:MAX_STOCKS_PER_DESK]:
        evidence: list[Evidence] = []
        for ev in s.evidence:
            if 0 <= ev.source_index < len(items):
                src = items[ev.source_index]
                ts = src.segments[0].start if src.segments else None
                evidence.append(
                    Evidence(quote=ev.quote, source_url=src.source_url, timestamp_start=ts)
                )
        if not evidence:
            logger.info("Dropping ungrounded stock take %s (no valid source)", s.ticker)
            continue
        ticker = s.ticker if s.ticker.startswith("$") else f"${s.ticker.lstrip('$')}"
        stocks.append(
            StockTake(
                ticker=ticker.upper(),
                conviction=max(-1.0, min(1.0, s.conviction)),
                horizon=s.horizon or "—",
                rationale=s.rationale,
                evidence=evidence,
            )
        )
    return stocks


def analyze_desk(desk: str, items: list[CleanedItem]) -> SectorNote:
    """Run one Andie desk over its items. Empty/failed desks return an empty note."""
    if not items:
        return SectorNote(desk=desk)
    try:
        out = converse_structured(_AnalystOutput, get_prompt("council.analyst"), _digest(items))
    except ReasoningError as exc:
        logger.warning("Andie-%s reasoning failed: %s", desk, exc)
        return SectorNote(desk=desk, summary=f"Analysis unavailable ({exc.kind}).")
    return SectorNote(
        desk=desk,
        summary=out.summary,
        highlights=out.highlights,
        stocks=_ground_stocks(out, items),
    )


def run_analysts(micro_items: list[CleanedItem], emit: Emit = noop_emit) -> list[SectorNote]:
    """Tier 3 fan-out: route MICRO items to the 3 desks and analyse each in parallel."""
    from concurrent.futures import ThreadPoolExecutor

    buckets = route_to_desks(micro_items)
    emit("council.analyst", "Andie desks scoring sector notes", status="start",
         desks={d: len(v) for d, v in buckets.items()})

    def _run(desk: str) -> SectorNote:
        note = analyze_desk(desk, buckets[desk])
        emit("council.analyst", f"Andie-{desk}: {len(note.stocks)} stocks", status="ok",
             desk=desk, stocks=len(note.stocks))
        return note

    with ThreadPoolExecutor(max_workers=len(DESK_ORDER)) as pool:
        notes = list(pool.map(_run, DESK_ORDER))
    return notes
