"""Tier 4 (on demand) — the single-ticker Debate Chamber.

The nightly council debates one basket drawn from the strongest names across all three
desks (`debate._topic`), so it says nothing about a ticker that did not make that cut —
and every ticker page showing that same transcript tells you nothing about the ticker you
opened. This module answers the narrower question instead: Bull and Bear argue over one
name, against only the corpus that actually mentions it.

Like the weekly thematic run (`council.thematic`) this is *not* part of the `run_council`
DAG. It is a question a user asks about one name, on their clock, not a nightly fan-in —
so it reads the persisted corpus directly, borrows the freshest council snapshot for the
desk's standing call on the ticker, and does not re-run Tiers 3–4 to get there. When no
snapshot exists yet the debate still proceeds on the corpus alone.

The chamber protocol itself is shared with the council-wide debate (`debate.run_rounds`);
only the brief and the prompts differ. Winston closes with a verdict scoped to the ticker,
appended to the transcript exactly as the orchestrator appends his council-wide one, and
that verdict is the only part that cites — the Bull/Bear turns are free argument here just
as they are upstairs. Every execution is persisted whole and dated (`TickerDebateRun`), so
last week's debate on a name stays readable next to today's.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from ..db.repository import (
    get_latest_council_snapshot,
    list_cleaned_items,
    save_ticker_debate_run,
)
from ..events import Emit, noop_emit
from ..llm import ReasoningError, converse_structured
from ..models import (
    CleanedItem,
    CouncilReport,
    DebateRecord,
    DebateSideMeta,
    DebateTurn,
    TickerDebateRun,
)
from ..prompts import get_prompt
from . import grounding
from .debate import run_rounds

logger = logging.getLogger(__name__)

_STAGE = "council.chairman"   # the verdict is Winston's; the rounds emit as council.debate
_MAX_ITEMS = 60      # corpus cap for one ticker
_MAX_CITABLE = 30    # cap on the numbered corpus, to bound the prompt
_SNIPPET = 500       # chars per numbered excerpt, matching the Chairman's


class _TickerVerdict(BaseModel):
    verdict: str = ""
    evidence: list[grounding.LLMEvidence] = Field(default_factory=list)


def canonical(ticker: str) -> str:
    """The `$MU` form entities are resolved to, from whatever the caller had."""
    return f"${ticker.strip().lstrip('$').upper()}"


def _desk_call(ticker: str, report: CouncilReport | None) -> str:
    """The desks' standing call on this ticker, as reasoning context for both sides.

    Reads the latest snapshot rather than re-running Tier 3: the desks already formed a
    view on this name, and a debate that ignores it argues from less than the fund knows.
    """
    if report is None:
        return "No desk call on this ticker yet."
    lines: list[str] = []
    for note in report.sector_notes:
        for stock in note.stocks:
            if stock.ticker.upper() != ticker:
                continue
            lines.append(
                f"Desk {note.desk}: conviction {stock.conviction:+.2f} ({stock.horizon})"
                + (f" — {stock.rationale}" if stock.rationale else "")
            )
    return "\n".join(lines) or "No desk call on this ticker yet."


def _brief(ticker: str, desk_call: str, corpus: list[CleanedItem]) -> str:
    """The context block both sides argue over: the ticker, the desk call, the sources."""
    return (
        f"TICKER UNDER DEBATE: {ticker}\n\n"
        f"DESK CALL:\n{desk_call}\n\n"
        "SOURCES (cite these by index):\n"
        + (grounding.digest(corpus, snippet=_SNIPPET) or "No citable sources provided.")
    )


def _rule(
    ticker: str,
    desk_call: str,
    record: DebateRecord,
    corpus: list[CleanedItem],
    emit: Emit,
) -> _TickerVerdict:
    """Winston's closing ruling on the ticker. A failed call is a skip, not an exception."""
    emit(_STAGE, f"Winston ruling on {ticker}", status="start")
    transcript = "\n".join(f"[{t.label}] {t.text}" for t in record.transcript)
    user = (
        f"TICKER: {ticker}\n\n"
        f"DESK CALL:\n{desk_call}\n\n"
        f"DEBATE:\n{transcript or 'No debate transcript.'}\n\n"
        "SOURCES (cite these by index):\n"
        + (grounding.digest(corpus, snippet=_SNIPPET) or "No citable sources provided.")
    )
    try:
        return converse_structured(
            _TickerVerdict, get_prompt("council.chairman.ticker", ticker=ticker), user
        )
    except ReasoningError as exc:
        # The transcript above has already been paid for; losing it because the ruling
        # failed would be the worse outcome. The run persists with an empty verdict.
        logger.warning("Ticker verdict failed for %s: %s", ticker, exc)
        emit(_STAGE, f"Verdict unavailable: {exc.kind}", status="skip")
        return _TickerVerdict()


def _empty_record(ticker: str) -> DebateRecord:
    """A chamber that never sat — so an empty run still round-trips through the UI."""
    return DebateRecord(
        topic=f"{ticker} · Bull vs Bear",
        rounds=0,
        bull=DebateSideMeta(name="Freddy-Bull", model="—"),
        bear=DebateSideMeta(name="Freddy-Bear", model="—"),
    )


def run_ticker_debate(ticker: str, emit: Emit = noop_emit) -> TickerDebateRun:
    """Debate one ticker over the corpus that mentions it, and save the dated run."""
    ticker = canonical(ticker)
    emit("council.debate", f"Freddy: opening the chamber on {ticker}", status="start")

    items = list_cleaned_items(ticker=ticker, limit=_MAX_ITEMS)
    if not items:
        # Same posture as the council's and the thematic run's empty-corpus short circuit:
        # persist an honest empty run so the page shows "ran, found nothing" rather than a
        # debate invented out of a corpus that never mentioned this name.
        emit("council.debate", f"No sources mention {ticker}", status="skip")
        return save_ticker_debate_run(
            TickerDebateRun(ticker=ticker, debate=_empty_record(ticker), source_count=0)
        )

    corpus = items[:_MAX_CITABLE]
    desk_call = _desk_call(ticker, get_latest_council_snapshot())

    record = run_rounds(
        f"{ticker} · Bull vs Bear",
        _brief(ticker, desk_call, corpus),
        bull_key="council.debate.ticker.bull",
        bear_key="council.debate.ticker.bear",
        prompt_values={"ticker": ticker},
        subject=ticker,
        emit=emit,
    )

    ruling = _rule(ticker, desk_call, record, corpus, emit)
    # Stitched on exactly as the orchestrator stitches Winston onto the council debate, so
    # the card and the transcript modal render this run with no special case.
    record.verdict = ruling.verdict
    if ruling.verdict:
        record.transcript.append(
            DebateTurn(who="winston", round="Verdict", label="Winston · rules", text=ruling.verdict)
        )

    # A citation that doesn't resolve is dropped and the verdict shows un-anchored, the
    # same call the Chairman's indicators make: the ruling still means something.
    evidence = grounding.ground(ruling.evidence, corpus)
    cited: dict[str, set[str]] = {}
    grounding.attribute(cited, "Winston", evidence)

    run = save_ticker_debate_run(
        TickerDebateRun(
            ticker=ticker,
            debate=record,
            verdict_evidence=evidence,
            sources=grounding.source_manifest(items, cited),
            source_count=len(items),
        )
    )
    emit(_STAGE, f"Verdict on {ticker} logged", status="ok",
         turns=len(record.transcript),
         cited=sum(1 for s in run.sources if s.cited_by))
    return run
