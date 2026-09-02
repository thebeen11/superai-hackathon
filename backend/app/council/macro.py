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
  appears exactly once, in checklist order, whatever the model returned. The checklist is
  also appended to the system prompt if an edited prompt dropped the `{signposts}`
  placeholder — the keys are the parser's contract, not presentation.

The composite risk score is computed here, not by the LLM, so it stays consistent with the
statuses it summarises.
"""
from __future__ import annotations

import logging
import re

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


def _norm(text: str) -> str:
    """Fold a label to a comparable token: lowercase, non-alphanumerics collapsed to `_`."""
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")


def _aliases() -> dict[str, str]:
    """Every spelling we will accept for a checklist row → its canonical key.

    The model is told to copy the key verbatim, but a re-worded prompt may get back the
    display name (`Labour Market`) or a cosmetic variant (`Yield-Curve`). Those name the
    same row, so resolving them is not leniency about *what* was graded — only about how
    it was spelled. A key that matches nothing still falls through to "not returned".
    """
    table: dict[str, str] = {}
    for key, name, _trigger in BEAR_SIGNPOSTS:
        table[_norm(key)] = key
        table.setdefault(_norm(name), key)
    return table


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
    alias = _aliases()
    by_key: dict[str, _LLMSignpost] = {}
    unmatched: list[str] = []
    for raw_row in out.signposts:
        canonical = alias.get(_norm(raw_row.key))
        if canonical is None:
            unmatched.append(raw_row.key)
        else:
            by_key.setdefault(canonical, raw_row)
    if unmatched:
        # Almost always a prompt that lost the checklist, so the model invented its own
        # row names. Without this line the tracker just renders empty with no explanation.
        logger.warning(
            "Macro Analyst returned %d signpost(s) matching no checklist key: %s",
            len(unmatched), ", ".join(sorted(unmatched)),
        )

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


def _system_prompt() -> str:
    """The Macro Analyst's prompt, with the checklist guaranteed to be in it.

    `{signposts}` is not decoration — it is the machine contract, because `_reconcile`
    matches on the keys it carries. A console edit that drops the placeholder fills to a
    no-op (`prompts.registry._fill` never errors, so users can paste literal braces), and
    the desk would silently grade a checklist it was never shown. So we append it, the
    same way `llm/vertex.py` appends the JSON output contract outside the prompt catalogue.
    """
    checklist = checklist_prompt()
    system = get_prompt("council.macro", signposts=checklist)
    if checklist in system:
        return system
    logger.warning(
        "The council.macro prompt no longer contains {signposts}; appending the checklist "
        "so the desk still grades the fixed rows."
    )
    return (
        f"{system}\n\nCHECKLIST — grade exactly these rows and only these, copying each "
        f"`key` verbatim into your answer:\n{checklist}"
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
        system = _system_prompt()
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
