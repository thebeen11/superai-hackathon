"""Tier 5 — Winston, the Chairman (final judge & macro allocator).

Winston reads the Bull/Bear transcript and the macro-bypass items routed straight to
him, then: judges the debate into a verdict, scores the macro indicators for the
dashboard, computes the ACE composite (PROJECT_GUIDANCE §8), writes the daily briefing,
and logs resolvable predictions. Output is capital-preserving and never a price target
(Option A, §1).

The thematic baskets are *not* produced here. They run on a weekly cadence of their own
in `council/thematic.py`, which reuses this module's `citable_corpus`.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from ..events import Emit, noop_emit
from ..llm import ReasoningError, converse_structured
from ..prompts import get_prompt
from ..models import (
    AceComponent,
    AceIndex,
    BearSignpostReport,
    BriefingItem,
    CleanedItem,
    DebateRecord,
    MacroIndicator,
    Prediction,
    SectorNote,
)
from . import grounding

logger = logging.getLogger(__name__)

_SNIPPET = 500
_MAX_CITABLE = 40  # cap on the numbered corpus, to bound the prompt


class _LLMIndicator(BaseModel):
    name: str
    score: float = 0.0
    band: str = "Neutral"
    rationale: str = ""
    evidence: list[grounding.LLMEvidence] = Field(default_factory=list)


class _LLMAceComponent(BaseModel):
    key: str
    weight: float
    score: float


class _LLMAce(BaseModel):
    value: float = 0.0
    label: str = "—"
    components: list[_LLMAceComponent] = Field(default_factory=list)


class _LLMBriefing(BaseModel):
    tone: str = "neutral"
    text: str
    evidence: list[grounding.LLMEvidence] = Field(default_factory=list)


class _LLMPrediction(BaseModel):
    claim: str
    by: str = ""
    resolve: str = ""
    probability: float = 0.5
    evidence: list[grounding.LLMEvidence] = Field(default_factory=list)


class _ChairmanOutput(BaseModel):
    verdict: str = ""
    indicators: list[_LLMIndicator] = Field(default_factory=list)
    ace: _LLMAce = Field(default_factory=_LLMAce)
    briefing: list[_LLMBriefing] = Field(default_factory=list)
    predictions: list[_LLMPrediction] = Field(default_factory=list)


class ChairmanVerdict(BaseModel):
    """What Winston returns to the orchestrator (the debate verdict + the dashboard)."""

    verdict: str = ""
    indicators: list[MacroIndicator] = Field(default_factory=list)
    ace: AceIndex | None = None
    briefing: list[BriefingItem] = Field(default_factory=list)
    predictions: list[Prediction] = Field(default_factory=list)


def citable_corpus(
    macro_items: list[CleanedItem],
    notes: list[SectorNote],
    micro_items: list[CleanedItem] | None = None,
) -> list[CleanedItem]:
    """The numbered sources Winston is allowed to cite.

    Shared with the weekly thematic run (`council.thematic`), which cites the same corpus.

    The macro bypass gives him raw `[MACRO]` items, but his ruling comes out of the debate
    — which is built on the desks' micro reads, not on anything in front of him. So the
    corpus also carries the *real* micro items the desks quoted, looked up by the URLs in
    their already-grounded `StockTake.evidence`. Passing the real items (rather than
    rebuilding stubs from the quotes) keeps the transcript segments, which is what lets a
    citation deep-link to the right second of a video.
    """
    corpus: list[CleanedItem] = []
    seen: set[str] = set()
    for it in macro_items:
        if it.source_url not in seen:
            seen.add(it.source_url)
            corpus.append(it)

    cited = {ev.source_url for n in notes for s in n.stocks for ev in s.evidence}
    for it in micro_items or []:
        if it.source_url in cited and it.source_url not in seen:
            seen.add(it.source_url)
            corpus.append(it)
    return corpus[:_MAX_CITABLE]


def macro_digest(macro_items: list[CleanedItem]) -> str:
    """Macro excerpts as reasoning context (shared with the weekly thematic run)."""
    if not macro_items:
        return "No macro excerpts provided."
    lines = []
    for it in macro_items[:15]:
        lines.append(f"- {it.title}: {it.clean_text[:_SNIPPET]}".replace("\n", " "))
    return "\n".join(lines)


def debate_digest(debate: DebateRecord | None) -> str:
    if debate is None or not debate.transcript:
        return "No debate transcript."
    return "\n".join(f"[{t.label}] {t.text}" for t in debate.transcript)


def notes_digest(notes: list[SectorNote]) -> str:
    lines = []
    for n in notes:
        picks = "; ".join(f"{s.ticker} ({s.conviction:+.2f})" for s in n.stocks[:10])
        if n.summary or picks:
            lines.append(f"Desk {n.desk}: {n.summary} | {picks}")
    return "\n".join(lines) or "No desk notes."


def _signpost_digest(report: BearSignpostReport | None) -> str:
    """The Macro Analyst's tracker, so Winston's indicators can't contradict it."""
    if report is None or not report.signposts:
        return ""
    lines = [
        f"{report.triggered}/{report.total} triggered ({report.watch} on watch) · {report.label}",
        *(
            f"- {s.name}: {s.status}"
            + ("" if s.evidenced else " [unevidenced]")
            + (f" — {s.rationale}" if s.rationale else "")
            for s in report.signposts
        ),
    ]
    if report.summary:
        lines.append(report.summary)
    return "\n".join(lines)


def _band(score: float) -> str:
    return "Positive" if score > 0.2 else "Negative" if score < -0.2 else "Neutral"


def run_chairman(
    notes: list[SectorNote],
    debate: DebateRecord | None,
    macro_items: list[CleanedItem],
    emit: Emit = noop_emit,
    macro_report: BearSignpostReport | None = None,
    micro_items: list[CleanedItem] | None = None,
) -> ChairmanVerdict:
    """Tier 5 fan-in: judge the debate and build the dashboard (indicators, ACE, briefing)."""
    emit("council.chairman", "Winston weighing the verdict", status="start")
    signposts = _signpost_digest(macro_report)
    # The desk notes, debate and signposts are reasoning context; only SOURCES is numbered,
    # and it is the only thing Winston may cite (no-orphan guardrail §12.6).
    corpus = citable_corpus(macro_items, notes, micro_items)
    user = (
        f"DESK NOTES:\n{notes_digest(notes)}\n\n"
        f"DEBATE:\n{debate_digest(debate)}\n\n"
        f"MACRO EXCERPTS:\n{macro_digest(macro_items)}"
        + (f"\n\nBEAR SIGNPOSTS:\n{signposts}" if signposts else "")
        + "\n\nSOURCES (cite these by index):\n"
        + (grounding.digest(corpus, snippet=_SNIPPET) or "No citable sources provided.")
    )
    try:
        out = converse_structured(_ChairmanOutput, get_prompt("council.chairman"), user)
    except ReasoningError as exc:
        logger.warning("Chairman reasoning failed: %s", exc)
        emit("council.chairman", f"Chairman unavailable: {exc.kind}", status="skip")
        return ChairmanVerdict(verdict=f"Verdict unavailable ({exc.kind}).")

    # Winston's claims keep their citations where they resolve. Unlike a desk's stock take —
    # which is dropped outright when ungrounded, because a conviction with no source is
    # worthless — a briefing line or indicator still carries meaning without one, so it
    # survives and the UI renders it visibly un-anchored instead.
    indicators = [
        MacroIndicator(
            name=i.name, score=max(-1.0, min(1.0, i.score)),
            band=i.band if i.band in {"Positive", "Neutral", "Negative"} else _band(i.score),
            rationale=i.rationale,
            evidence=grounding.ground(i.evidence, corpus),
        )
        for i in out.indicators
    ]
    ace = AceIndex(
        value=max(-1.0, min(1.0, out.ace.value)),
        label=out.ace.label or "—",
        components=[AceComponent(key=c.key, weight=c.weight, score=c.score) for c in out.ace.components],
    )
    briefing = [
        BriefingItem(
            tone=b.tone if b.tone in {"up", "down", "neutral"} else "neutral",
            text=b.text,
            evidence=grounding.ground(b.evidence, corpus),
        )
        for b in out.briefing
    ]
    predictions = [
        Prediction(
            claim=p.claim, by=p.by or "Council", resolve=p.resolve or "—",
            status="pending", probability=max(0.0, min(1.0, p.probability)),
            evidence=grounding.ground(p.evidence, corpus),
        )
        for p in out.predictions
    ]
    emit("council.chairman", "Winston issued the verdict", status="ok",
         indicators=len(indicators), predictions=len(predictions))
    return ChairmanVerdict(
        verdict=out.verdict, indicators=indicators,
        ace=ace, briefing=briefing, predictions=predictions,
    )
