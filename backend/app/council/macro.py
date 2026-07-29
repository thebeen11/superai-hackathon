"""The Macro Analyst — bear-market signpost tracker (macro bypass).

Sits on the macro bypass alongside Winston: it reads only the `[MACRO]` items Timo routed
around the analyst desks, and grades them against a *fixed* checklist of classic
late-cycle signposts (`taxonomy.BEAR_SIGNPOSTS`). Fixing the checklist is the whole point
— the tracker is only meaningful if the same rows are graded every run, so the model may
score the signposts but never choose them.

Two guardrails shape the output:

- **No orphan alarms.** A `Triggered`/`Watch` call must cite an excerpt the desk was
  actually given; a cited index that doesn't exist is dropped, and a signpost left with no
  grounded evidence is downgraded to `Clear` + `evidenced=False`. The model cannot raise
  the alarm on something it invented.
- **Always complete.** The result is reconciled against the checklist in Python: every key
  appears exactly once, in checklist order, whatever the model returned.

The composite risk score is computed here, not by the LLM, so it stays consistent with the
statuses it summarises.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from ..events import Emit, noop_emit
from ..llm import ReasoningError, converse_structured
from ..models import BearSignpostReport, CleanedItem, Signpost
from ..prompts import get_prompt
from ..taxonomy import BEAR_SIGNPOSTS, SIGNPOST_STATUSES
from . import grounding

logger = logging.getLogger(__name__)

_MAX_ITEMS = 25    # macro corpus cap fed into the single reasoning call
_UNEVIDENCED = "Not evidenced in the current corpus."


class _LLMSignpost(BaseModel):
    key: str
    status: str = "Clear"
    rationale: str = ""
    evidence: list[grounding.LLMEvidence] = Field(default_factory=list)


class _MacroOutput(BaseModel):
    signposts: list[_LLMSignpost] = Field(default_factory=list)
    summary: str = ""


def checklist_prompt() -> str:
    """The fixed checklist, rendered for the `{signposts}` placeholder."""
    return "\n".join(f"- {key}  ({name}): {trigger}" for key, name, trigger in BEAR_SIGNPOSTS)


def _label(risk: float) -> str:
    if risk >= 0.60:
        return "LATE CYCLE · ELEVATED"
    if risk >= 0.30:
        return "MID CYCLE · WATCH"
    return "CYCLE RISK CONTAINED"


def _empty_signpost(key: str, name: str, rationale: str = _UNEVIDENCED) -> Signpost:
    return Signpost(key=key, name=name, status="Clear", rationale=rationale, evidenced=False)


def _tally(signposts: list[Signpost], summary: str) -> BearSignpostReport:
    """Score the composite from the statuses — deterministic, never the model's arithmetic."""
    triggered = sum(1 for s in signposts if s.status == "Triggered")
    watch = sum(1 for s in signposts if s.status == "Watch")
    total = len(signposts)
    risk = (triggered + 0.5 * watch) / total if total else 0.0
    risk = max(0.0, min(1.0, risk))
    return BearSignpostReport(
        signposts=signposts,
        triggered=triggered,
        watch=watch,
        total=total,
        risk_score=risk,
        label=_label(risk),
        summary=summary,
    )


def _reconcile(out: _MacroOutput, items: list[CleanedItem]) -> list[Signpost]:
    """One row per checklist entry, in checklist order, each grounded or downgraded."""
    by_key = {s.key.strip().lower(): s for s in out.signposts}
    rows: list[Signpost] = []
    for key, name, _trigger in BEAR_SIGNPOSTS:
        raw = by_key.get(key)
        if raw is None:
            rows.append(_empty_signpost(key, name, "Not returned by the analyst."))
            continue
        status = raw.status.strip().title()
        if status not in SIGNPOST_STATUSES:
            status = "Clear"
        evidence = grounding.ground(raw.evidence, items)
        # An alarm with no surviving source is not an alarm (no-orphan guardrail).
        if status != "Clear" and not evidence:
            logger.info("Downgrading ungrounded signpost %s (%s → Clear)", key, status)
            rows.append(_empty_signpost(key, name))
            continue
        rows.append(
            Signpost(
                key=key,
                name=name,
                status=status,
                rationale=raw.rationale,
                evidence=evidence,
                evidenced=bool(evidence),
            )
        )
    return rows


def _fallback(summary: str) -> BearSignpostReport:
    """A complete, all-unevidenced tracker — used when there is nothing to grade."""
    return _tally(
        [_empty_signpost(key, name) for key, name, _ in BEAR_SIGNPOSTS],
        summary,
    )


def run_macro_analyst(
    macro_items: list[CleanedItem], emit: Emit = noop_emit
) -> BearSignpostReport:
    """Grade the fixed bear-market checklist against the `[MACRO]` corpus."""
    emit("council.macro", "Macro Analyst scanning bear signposts", status="start",
         macro=len(macro_items))

    if not macro_items:
        emit("council.macro", "No macro corpus to grade", status="skip")
        return _fallback("No macro material in this run — the checklist is ungraded, not clear.")

    items = macro_items[:_MAX_ITEMS]
    try:
        system = get_prompt("council.macro", signposts=checklist_prompt())
        out = converse_structured(_MacroOutput, system, grounding.digest(items))
    except ReasoningError as exc:
        logger.warning("Macro Analyst reasoning failed: %s", exc)
        emit("council.macro", f"Macro Analyst unavailable: {exc.kind}", status="skip")
        return _fallback(f"Macro analysis unavailable ({exc.kind}).")

    report = _tally(_reconcile(out, items), out.summary)
    emit("council.macro", f"{report.triggered}/{report.total} signposts triggered", status="ok",
         triggered=report.triggered, watch=report.watch, total=report.total,
         risk_score=report.risk_score, label=report.label)
    return report
