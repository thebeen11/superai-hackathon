"""Tier 4 — the Freddy squad (Bull vs Bear debate chamber).

Two adversarial personas argue over the Andie desk notes for six rounds so a single
sycophantic model can't rubber-stamp its own thesis (PROJECT_GUIDANCE §0, §11). The
two sides run on different Gemini models (Bull = Gemini 2.5 Pro, Bear = Gemini 2.5
Flash). NOTE: on the Gemini-only stack these are the same model family, so this is a
weaker anti-collusion guardrail than the original two-family (Claude vs Nova) setup —
an intentional tradeoff. The full transcript is logged and handed up to the Chairman,
who appends the verdict.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel

from ..config import settings
from ..events import Emit, noop_emit
from ..llm import ReasoningError, converse_structured
from ..models import DebateRecord, DebateSideMeta, DebateTurn, SectorNote
from ..prompts import get_prompt

logger = logging.getLogger(__name__)

_BULL_NAME, _BULL_MODEL = "Freddy-Bull", "Gemini 2.5 Pro"
_BEAR_NAME, _BEAR_MODEL = "Freddy-Bear", "Gemini 2.5 Flash"

# The chamber: strict alternation, Bull opens, Bear speaks last before Winston rules.
# `settings.debate_rounds` slices this, so lowering it truncates from the end.
_ROUND_PLAN: tuple[tuple[str, str, str], ...] = (
    ("bull", "Bull · proposes", "propose the trade."),
    ("bear", "Bear · attacks", "attack the thesis: valuation, crowding, failure modes."),
    ("bull", "Bull · defends", "defend or adjust — concede what is fair, keep what holds."),
    ("bear", "Bear · presses", "press the weakest remaining leg; name the trigger that breaks it."),
    ("bull", "Bull · refines", "state your final position and sizing."),
    ("bear", "Bear · closes", "closing risk statement — the one thing Winston must weigh."),
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
    """Multi-round Bull/Bear debate over the desk notes. Verdict is added by Winston."""
    bull = DebateSideMeta(name=_BULL_NAME, model=_BULL_MODEL)
    bear = DebateSideMeta(name=_BEAR_NAME, model=_BEAR_MODEL)
    plan = _ROUND_PLAN[: max(1, settings.debate_rounds)]
    record = DebateRecord(topic=_topic(notes), round=0, rounds=len(plan), bull=bull, bear=bear)

    digest = _notes_digest(notes)

    try:
        for i, (who, label, instruction) in enumerate(plan, start=1):
            emit("council.debate", f"Freddy: {label}, round {i}",
                 status="start" if i == 1 else "progress")

            is_bull = who == "bull"
            schema = _BullTurn if is_bull else _BearTurn
            prompt_key = "council.debate.bull" if is_bull else "council.debate.bear"
            model_id = settings.gemini_bull_model if is_bull else settings.gemini_bear_model

            # Every turn sees the whole exchange so far, so later rounds engage with what
            # was actually said instead of re-arguing the opener.
            so_far = "\n".join(f"[{t.label}] {t.text}" for t in record.transcript)
            user = (
                f"Desk notes:\n{digest}\n\n"
                f"Debate so far:\n{so_far or 'Nothing yet — you open.'}\n\n"
                f"Round {i} of {len(plan)}: {instruction}"
            )
            turn = converse_structured(schema, get_prompt(prompt_key), user, model_id=model_id)

            side = bull if is_bull else bear
            side.stance = turn.stance
            text = turn.argument if is_bull else turn.rebuttal
            record.transcript.append(DebateTurn(who=who, round=f"R{i}", label=label, text=text))
            record.round = i
    except ReasoningError as exc:
        logger.warning("Debate aborted: %s", exc)
        emit("council.debate", f"Debate degraded: {exc.kind}", status="skip")

    emit("council.debate", "Freddy: debate logged", status="ok", turns=len(record.transcript))
    return record
