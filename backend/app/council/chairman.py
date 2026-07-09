"""Tier 5 — Winston, the Chairman (final judge & macro allocator).

Winston reads the Bull/Bear transcript and the macro-bypass items routed straight to
him, then: judges the debate into a verdict, assembles the final thematic baskets with
a conviction + hold period, scores the macro indicators for the dashboard, computes the
ACE composite (PROJECT_GUIDANCE §8), writes the daily briefing, and logs resolvable
predictions. Output is capital-preserving and never a price target (Option A, §1).
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
    BriefingItem,
    CleanedItem,
    DebateRecord,
    MacroIndicator,
    Prediction,
    SectorNote,
    ThemeBasket,
)

logger = logging.getLogger(__name__)

_SNIPPET = 500


class _LLMBasket(BaseModel):
    name: str
    risk: str = "Med"
    horizon: str = "—"
    stocks: list[str] = Field(default_factory=list)
    strat: str = ""
    conviction: float = 0.0
    verdict: str = ""
    hold: str = "—"


class _LLMIndicator(BaseModel):
    name: str
    score: float = 0.0
    band: str = "Neutral"
    evidence: str = ""


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


class _LLMPrediction(BaseModel):
    claim: str
    by: str = ""
    resolve: str = ""
    probability: float = 0.5


class _ChairmanOutput(BaseModel):
    verdict: str = ""
    baskets: list[_LLMBasket] = Field(default_factory=list)
    indicators: list[_LLMIndicator] = Field(default_factory=list)
    ace: _LLMAce = Field(default_factory=_LLMAce)
    briefing: list[_LLMBriefing] = Field(default_factory=list)
    predictions: list[_LLMPrediction] = Field(default_factory=list)


class ChairmanVerdict(BaseModel):
    """What Winston returns to the orchestrator (the debate verdict + the dashboard)."""

    verdict: str = ""
    baskets: list[ThemeBasket] = Field(default_factory=list)
    indicators: list[MacroIndicator] = Field(default_factory=list)
    ace: AceIndex | None = None
    briefing: list[BriefingItem] = Field(default_factory=list)
    predictions: list[Prediction] = Field(default_factory=list)


def _macro_digest(macro_items: list[CleanedItem]) -> str:
    if not macro_items:
        return "No macro excerpts provided."
    lines = []
    for it in macro_items[:15]:
        lines.append(f"- {it.title}: {it.clean_text[:_SNIPPET]}".replace("\n", " "))
    return "\n".join(lines)


def _debate_digest(debate: DebateRecord | None) -> str:
    if debate is None or not debate.transcript:
        return "No debate transcript."
    return "\n".join(f"[{t.label}] {t.text}" for t in debate.transcript)


def _notes_digest(notes: list[SectorNote]) -> str:
    lines = []
    for n in notes:
        picks = "; ".join(f"{s.ticker} ({s.conviction:+.2f})" for s in n.stocks[:10])
        if n.summary or picks:
            lines.append(f"Desk {n.desk}: {n.summary} | {picks}")
    return "\n".join(lines) or "No desk notes."


def _band(score: float) -> str:
    return "Positive" if score > 0.2 else "Negative" if score < -0.2 else "Neutral"


def run_chairman(
    notes: list[SectorNote],
    debate: DebateRecord | None,
    macro_items: list[CleanedItem],
    emit: Emit = noop_emit,
) -> ChairmanVerdict:
    """Tier 5 fan-in: judge the debate and build the final dashboard + baskets."""
    emit("council.chairman", "Winston weighing the verdict", status="start")
    user = (
        f"DESK NOTES:\n{_notes_digest(notes)}\n\n"
        f"DEBATE:\n{_debate_digest(debate)}\n\n"
        f"MACRO EXCERPTS:\n{_macro_digest(macro_items)}"
    )
    try:
        out = converse_structured(_ChairmanOutput, get_prompt("council.chairman"), user)
    except ReasoningError as exc:
        logger.warning("Chairman reasoning failed: %s", exc)
        emit("council.chairman", f"Chairman unavailable: {exc.kind}", status="skip")
        return ChairmanVerdict(verdict=f"Verdict unavailable ({exc.kind}).")

    baskets = [
        ThemeBasket(
            name=b.name, risk=b.risk or "Med", horizon=b.horizon or "—",
            stocks=[s.upper() for s in b.stocks], strat=b.strat,
            conviction=max(0.0, min(1.0, b.conviction)),
            verdict=b.verdict, hold=b.hold or "—",
        )
        for b in out.baskets
    ]
    indicators = [
        MacroIndicator(
            name=i.name, score=max(-1.0, min(1.0, i.score)),
            band=i.band if i.band in {"Positive", "Neutral", "Negative"} else _band(i.score),
            evidence=i.evidence,
        )
        for i in out.indicators
    ]
    ace = AceIndex(
        value=max(-1.0, min(1.0, out.ace.value)),
        label=out.ace.label or "—",
        components=[AceComponent(key=c.key, weight=c.weight, score=c.score) for c in out.ace.components],
    )
    briefing = [
        BriefingItem(tone=b.tone if b.tone in {"up", "down", "neutral"} else "neutral", text=b.text)
        for b in out.briefing
    ]
    predictions = [
        Prediction(
            claim=p.claim, by=p.by or "Council", resolve=p.resolve or "—",
            status="pending", probability=max(0.0, min(1.0, p.probability)),
        )
        for p in out.predictions
    ]
    emit("council.chairman", "Winston issued the verdict", status="ok",
         baskets=len(baskets), indicators=len(indicators))
    return ChairmanVerdict(
        verdict=out.verdict, baskets=baskets, indicators=indicators,
        ace=ace, briefing=briefing, predictions=predictions,
    )
