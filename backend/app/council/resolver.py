"""Tier 3 rubric scoring — resolve due predictions True/False (PROJECT_GUIDANCE §7.3).

Once a prediction's resolve window has passed, this judges it against the persisted
corpus and records the outcome, feeding the per-channel Brier ledger. Predictions the
evidence can't settle stay `pending` (an honest "unknown" rather than a coin flip).
"""
from __future__ import annotations

import logging

from pydantic import BaseModel

from ..db.repository import list_due_predictions, resolve_prediction
from ..events import Emit, noop_emit
from ..llm import ReasoningError, converse_structured
from ..models import CleanedItem
from ..prompts import get_prompt

logger = logging.getLogger(__name__)

_SNIPPET = 400
_MAX_DIGEST = 25  # corpus items shown to the judge


class _RubricVerdict(BaseModel):
    outcome: str = "unknown"  # 'true' | 'false' | 'unknown'
    rationale: str = ""


def _corpus_digest(corpus: list[CleanedItem]) -> str:
    if not corpus:
        return "No recent evidence available."
    lines = [f"- {it.title}: {it.clean_text[:_SNIPPET]}".replace("\n", " ") for it in corpus[:_MAX_DIGEST]]
    return "\n".join(lines)


def resolve_due_predictions(corpus: list[CleanedItem], emit: Emit = noop_emit) -> int:
    """Judge every prediction whose window has passed. Returns the number resolved."""
    due = list_due_predictions()
    if not due:
        return 0
    emit("council.resolve", f"Scoring {len(due)} due predictions", status="start", due=len(due))
    digest = _corpus_digest(corpus)
    resolved = 0
    for p in due:
        user = f"PREDICTION (by {p.channel}):\n{p.claim}\n\nEVIDENCE:\n{digest}"
        try:
            verdict = converse_structured(_RubricVerdict, get_prompt("council.resolver"), user)
        except ReasoningError as exc:
            logger.warning("Rubric scoring failed for prediction %s: %s", p.id, exc)
            continue
        outcome = verdict.outcome.strip().lower()
        if outcome == "true":
            resolve_prediction(p.id, True)
            resolved += 1
        elif outcome == "false":
            resolve_prediction(p.id, False)
            resolved += 1
        # 'unknown' → leave pending for a later run with more evidence.
    emit("council.resolve", f"Resolved {resolved} predictions", status="ok", resolved=resolved)
    return resolved
