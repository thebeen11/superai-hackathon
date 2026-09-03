"""Tier 4 — the Freddy squad (Bull vs Bear debate chamber).

Two adversarial personas argue over the Andie desk notes for six rounds so a single
sycophantic model can't rubber-stamp its own thesis (PROJECT_GUIDANCE §0, §11). The
two sides run on different Gemini models (Bull = Gemini 3.1 Pro, Bear = Gemini 3.6
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

_BULL_NAME, _BULL_MODEL = "Freddy-Bull", "Gemini 3.1 Pro"
_BEAR_NAME, _BEAR_MODEL = "Freddy-Bear", "Gemini 3.6 Flash"

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


def run_rounds(
    topic: str,
    brief: str,
    *,
    bull_key: str = "council.debate.bull",
    bear_key: str = "council.debate.bear",
    prompt_values: dict[str, str] | None = None,
    subject: str = "",
    emit: Emit = noop_emit,
) -> DebateRecord:
    """Run the chamber's alternating turns over `brief` and log the transcript.

    The protocol — who opens, how many turns, that every speaker sees the whole exchange —
    belongs to the chamber, not to what is being argued about. So the council-wide debate
    and the single-ticker one (`council.ticker_debate`) share this loop and differ only in
    the `brief` they argue over and the prompts they argue with.

    `brief` is the whole context block, already rendered by the caller. `subject` is an
    optional tag for the progress messages ("$MU"), so a ticker run reads as its own in the
    activity feed; the stage stays `council.debate` either way, which is what routes these
    events to Freddy in the UI. The verdict is added by Winston, not here.
    """
    bull = DebateSideMeta(name=_BULL_NAME, model=_BULL_MODEL)
    bear = DebateSideMeta(name=_BEAR_NAME, model=_BEAR_MODEL)
    plan = _ROUND_PLAN[: max(1, settings.debate_rounds)]
    record = DebateRecord(topic=topic, round=0, rounds=len(plan), bull=bull, bear=bear)
    values = prompt_values or {}
    tag = f"{subject} · " if subject else ""

    try:
        for i, (who, label, instruction) in enumerate(plan, start=1):
            emit("council.debate", f"Freddy: {tag}{label}, round {i}",
                 status="start" if i == 1 else "progress")

            is_bull = who == "bull"
            schema = _BullTurn if is_bull else _BearTurn
            prompt_key = bull_key if is_bull else bear_key
            model_id = settings.gemini_bull_model if is_bull else settings.gemini_bear_model

            # Every turn sees the whole exchange so far, so later rounds engage with what
            # was actually said instead of re-arguing the opener.
            so_far = "\n".join(f"[{t.label}] {t.text}" for t in record.transcript)
            user = (
                f"{brief}\n\n"
                f"Debate so far:\n{so_far or 'Nothing yet — you open.'}\n\n"
                f"Round {i} of {len(plan)}: {instruction}"
            )
            turn = converse_structured(
                schema, get_prompt(prompt_key, **values), user, model_id=model_id
            )

            side = bull if is_bull else bear
            side.stance = turn.stance
            text = turn.argument if is_bull else turn.rebuttal
            record.transcript.append(DebateTurn(who=who, round=f"R{i}", label=label, text=text))
            record.round = i
    except ReasoningError as exc:
        logger.warning("Debate aborted: %s", exc)
        emit("council.debate", f"Debate degraded: {exc.kind}", status="skip")

    emit("council.debate", f"Freddy: {tag}debate logged", status="ok",
         turns=len(record.transcript))
    return record


def run_debate(notes: list[SectorNote], emit: Emit = noop_emit) -> DebateRecord:
    """Multi-round Bull/Bear debate over the desk notes. Verdict is added by Winston."""
    return run_rounds(_topic(notes), f"Desk notes:\n{_notes_digest(notes)}", emit=emit)
