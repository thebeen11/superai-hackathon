"""Tier 5 (weekly) — Winston's Thematic Analysis.

The council runs nightly, but a *theme* does not change nightly: a basket built on one
day's headlines is noise dressed as conviction. So the baskets came out of the Chairman's
fan-in (`chairman.py`) and onto their own weekly cadence here, triggered by the
`thematic-weekly` Cloud Scheduler job against `POST /api/thematic/run`.

This is a single LLM call, not a DAG. It reads the persisted corpus directly and borrows
the freshest council snapshot for reasoning context — the desk notes and the debate
Winston already ruled on — rather than re-running Tiers 3–4 a second time each week. When
no snapshot exists yet the run still proceeds on the corpus alone; a first-ever run must
produce something rather than nothing.

Every execution is persisted whole and dated (`ThematicRun`), so the dashboard can read
back the themes of a given week instead of only the current ones.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from ..db.repository import (
    get_latest_council_snapshot,
    list_cleaned_items,
    save_thematic_run,
)
from ..events import Emit, noop_emit
from ..llm import ReasoningError, converse_structured
from ..models import (
    DEFAULT_TIMEFRAME,
    TIMEFRAMES,
    CleanedItem,
    CouncilReport,
    DebateRecord,
    SectorNote,
    Stream,
    ThemeBasket,
    ThematicRun,
)
from ..prompts import get_prompt
from . import grounding
from .chairman import citable_corpus, debate_digest, macro_digest, notes_digest

logger = logging.getLogger(__name__)

_STAGE = "council.thematic"
_MAX_ITEMS = 200   # corpus cap, matching the council DAG
_MAX_CITABLE = 40  # cap on the numbered corpus, to bound the prompt
_SNIPPET = 500     # chars per numbered excerpt, matching the Chairman's


class _LLMBasket(BaseModel):
    name: str
    risk: str = "Med"
    timeframe: str = DEFAULT_TIMEFRAME
    horizon: str = "—"
    stocks: list[str] = Field(default_factory=list)
    strat: str = ""
    conviction: float = 0.0
    verdict: str = ""
    hold: str = "—"
    evidence: list[grounding.LLMEvidence] = Field(default_factory=list)


class _ThematicOutput(BaseModel):
    baskets: list[_LLMBasket] = Field(default_factory=list)


def normalise_timeframe(value: str) -> str:
    """Snap the model's timeframe onto the closed set, defaulting to the middle bucket.

    The dashboard groups and filters on this, so an unrecognised value would silently
    create a fourth bucket nothing can select. Matching is case- and whitespace-tolerant,
    and a bare "Short"/"Medium"/"Long" is accepted — the model reaches for it often enough
    that rejecting it would lose real signal.
    """
    cleaned = " ".join((value or "").split()).casefold()
    for timeframe in TIMEFRAMES:
        if cleaned in (timeframe.casefold(), timeframe.split()[0].casefold()):
            return timeframe
    return DEFAULT_TIMEFRAME


def _corpus(
    macro: list[CleanedItem], notes: list[SectorNote], micro: list[CleanedItem]
) -> list[CleanedItem]:
    """The numbered sources a thematic run may cite.

    Starts from the Chairman's corpus — macro-bypass items plus the micro items the desks
    already quoted — then tops up with the remaining micro items. That top-up is the
    difference that matters here: the Chairman only rules on a debate, so the desks'
    citations are the whole of his world, but a thematic run reads the corpus directly and
    must be able to cite what it read. Without it, a week with no council snapshot yet
    could only ever produce unsourced baskets.
    """
    corpus = citable_corpus(macro, notes, micro)
    seen = {it.source_url for it in corpus}
    for it in micro:
        if len(corpus) >= _MAX_CITABLE:
            break
        if it.source_url not in seen:
            seen.add(it.source_url)
            corpus.append(it)
    return corpus


def _context(report: CouncilReport | None) -> tuple[list[SectorNote], DebateRecord | None]:
    """Desk notes + debate from the latest council snapshot, or empties when there is none."""
    if report is None:
        return [], None
    return list(report.sector_notes), report.debate


def run_thematic(emit: Emit = noop_emit) -> ThematicRun:
    """Build this week's thematic baskets over the persisted corpus and save the run."""
    emit(_STAGE, "Winston opening the thematic review", status="start")
    items = list_cleaned_items(limit=_MAX_ITEMS)
    if not items:
        # Same posture as the council's empty-corpus short circuit: persist an honest empty
        # run so the dashboard shows "ran, found nothing" rather than a stale week.
        emit(_STAGE, "No corpus to analyse", status="skip")
        run = ThematicRun(source_count=0)
        save_thematic_run(run)
        return run

    micro = [it for it in items if it.stream == Stream.MICRO]
    macro = [it for it in items if it.stream == Stream.MACRO]
    notes, debate = _context(get_latest_council_snapshot())

    corpus = _corpus(macro, notes, micro)
    user = (
        f"DESK NOTES:\n{notes_digest(notes)}\n\n"
        f"DEBATE:\n{debate_digest(debate)}\n\n"
        f"MACRO EXCERPTS:\n{macro_digest(macro)}\n\n"
        "SOURCES (cite these by index):\n"
        + (grounding.digest(corpus, snippet=_SNIPPET) or "No citable sources provided.")
    )
    try:
        out = converse_structured(_ThematicOutput, get_prompt("council.thematic"), user)
    except ReasoningError as exc:
        logger.warning("Thematic reasoning failed: %s", exc)
        emit(_STAGE, f"Thematic analysis unavailable: {exc.kind}", status="skip")
        run = ThematicRun(source_count=len(items))
        save_thematic_run(run)
        return run

    # A basket whose citation doesn't resolve survives un-anchored, exactly as a Chairman
    # indicator does: the thesis still means something without the quote, and the UI shows
    # it as unsourced rather than hiding that it was made.
    baskets = [
        ThemeBasket(
            name=b.name, risk=b.risk or "Med",
            timeframe=normalise_timeframe(b.timeframe),
            horizon=b.horizon or "—",
            stocks=[t.upper() for t in b.stocks], strat=b.strat,
            conviction=max(0.0, min(1.0, b.conviction)),
            verdict=b.verdict, hold=b.hold or "—",
            evidence=grounding.ground(b.evidence, corpus),
        )
        for b in out.baskets
    ]

    cited: dict[str, set[str]] = {}
    for basket in baskets:
        grounding.attribute(cited, "Winston", basket.evidence)

    run = ThematicRun(
        baskets=baskets,
        sources=grounding.source_manifest(items, cited),
        source_count=len(items),
    )
    save_thematic_run(run)
    emit(_STAGE, f"Thematic run ready: {len(baskets)} baskets", status="ok",
         baskets=len(baskets),
         cited=sum(1 for s in run.sources if s.cited_by))
    return run
