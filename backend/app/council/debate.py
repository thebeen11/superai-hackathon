"""Tier 4 — the Freddy squad (Bull vs Bear debate chamber).

Two adversarial personas argue over the Andie desk notes for three rounds so a single
sycophantic model can't rubber-stamp its own thesis (PROJECT_GUIDANCE §0, §11). The
two sides run on *different* Bedrock model families (Bull = Claude Opus, Bear =
Amazon Nova Pro — the families the workshop account permits) to curb collusion. The
full transcript is logged and handed up to the Chairman, who appends the verdict.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel

from ..config import settings
from ..events import Emit, noop_emit
from ..llm import BedrockReasoningError, converse_structured
from ..models import DebateRecord, DebateSideMeta, DebateTurn, SectorNote

logger = logging.getLogger(__name__)

_BULL_NAME, _BULL_MODEL = "Freddy-Bull", "Claude Opus"
_BEAR_NAME, _BEAR_MODEL = "Freddy-Bear", "Amazon Nova Pro"

_BULL_SYSTEM = (
    "You are Freddy-Bull, a growth/momentum portfolio manager. Argue why the analyst desk "
    "notes justify going long specific themes and tickers. Be concrete and cite the desks' "
    "evidence. Give a one-line stance and a tight argument (<120 words)."
)
_BEAR_SYSTEM = (
    "You are Freddy-Bear, a value/risk portfolio manager. Attack the bull thesis: valuation, "
    "macro headwinds, crowded positioning, ways it fails. Cite the desk notes where you can. "
    "Give a one-line stance and a tight rebuttal (<120 words)."
)


class _BullTurn(BaseModel):
    stance: str
    argument: str


class _BearTurn(BaseModel):
    stance: str
    rebuttal: str


def _notes_digest(notes: list[SectorNote]) -> str:
    lines: list[str] = []
    for n in notes:
        if not n.stocks and not n.summary:
            continue
        picks = "; ".join(
            f"{s.ticker} conv={s.conviction:+.2f} ({s.horizon})" for s in n.stocks[:10]
        )
        lines.append(f"Desk {n.desk}: {n.summary}\n  picks: {picks or 'none'}")
    return "\n".join(lines) or "No actionable desk notes."


def _topic(notes: list[SectorNote]) -> str:
    tickers = [s.ticker for n in notes for s in n.stocks]
    top = tickers[:3]
    return f"Basket debate: {', '.join(top)}" if top else "Sector outlook debate"


def run_debate(notes: list[SectorNote], emit: Emit = noop_emit) -> DebateRecord:
    """Three-round Bull/Bear debate over the desk notes. Verdict is added by Winston."""
    bull = DebateSideMeta(name=_BULL_NAME, model=_BULL_MODEL)
    bear = DebateSideMeta(name=_BEAR_NAME, model=_BEAR_MODEL)
    record = DebateRecord(topic=_topic(notes), round=0, rounds=3, bull=bull, bear=bear)

    digest = _notes_digest(notes)
    emit("council.debate", "Freddy: Bull vs Bear, round 1", status="start")

    try:
        r1 = converse_structured(
            _BullTurn, _BULL_SYSTEM, f"Desk notes:\n{digest}\n\nRound 1: propose the trade.",
            model_id=settings.bedrock_bull_model_id,
        )
        bull.stance = r1.stance
        record.transcript.append(
            DebateTurn(who="bull", round="R1", label="Bull · proposes", text=r1.argument)
        )
        record.round = 1

        emit("council.debate", "Freddy: Bear rebuts, round 2", status="progress")
        r2 = converse_structured(
            _BearTurn, _BEAR_SYSTEM,
            f"Desk notes:\n{digest}\n\nBull proposed: {r1.stance}\n{r1.argument}\n\n"
            "Round 2: attack the thesis.",
            model_id=settings.bedrock_bear_model_id,
        )
        bear.stance = r2.stance
        record.transcript.append(
            DebateTurn(who="bear", round="R2", label="Bear · attacks", text=r2.rebuttal)
        )
        record.round = 2

        emit("council.debate", "Freddy: Bull defends, round 3", status="progress")
        r3 = converse_structured(
            _BullTurn, _BULL_SYSTEM,
            f"Desk notes:\n{digest}\n\nYour thesis: {r1.argument}\n\n"
            f"Bear countered: {r2.rebuttal}\n\nRound 3: defend or adjust.",
            model_id=settings.bedrock_bull_model_id,
        )
        record.transcript.append(
            DebateTurn(who="bull", round="R3", label="Bull · defends", text=r3.argument)
        )
        record.round = 3
    except BedrockReasoningError as exc:
        logger.warning("Debate aborted: %s", exc)
        emit("council.debate", f"Debate degraded: {exc.kind}", status="skip")

    emit("council.debate", "Freddy: debate logged", status="ok", turns=len(record.transcript))
    return record
