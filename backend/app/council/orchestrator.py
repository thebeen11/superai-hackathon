"""The council DAG (Tiers 3→5).

Reads the persisted corpus, fans out to the three Andie desks, runs the Freddy
debate, then fans in to Winston. The pipeline is a strict DAG: Winston can't run
until Freddy finishes, Freddy can't run until the Andies finish (PROJECT_GUIDANCE §6).
The macro bypass routes `[MACRO]` items straight to Winston, never to the analysts.

The assembled `CouncilReport` is persisted as the latest snapshot. The whole thing is
fault-isolated by callers (the discovery endpoint) so a council failure never breaks
the upstream discovery.
"""
from __future__ import annotations

import logging

from ..db.repository import get_latest_council_snapshot, list_cleaned_items, save_council_snapshot
from ..events import Emit, noop_emit
from ..models import CouncilReport, DebateTurn, Stream
from .analyst import run_analysts
from .chairman import run_chairman
from .debate import run_debate

logger = logging.getLogger(__name__)

_MAX_ITEMS = 200  # corpus cap fed into the council


def run_council(emit: Emit = noop_emit) -> CouncilReport:
    """Run Tiers 3–5 over the persisted corpus and save the snapshot."""
    items = list_cleaned_items(limit=_MAX_ITEMS)
    micro = [it for it in items if it.stream == Stream.MICRO]
    macro = [it for it in items if it.stream == Stream.MACRO]
    emit("council", f"Convening the council over {len(items)} items", status="start",
         total=len(items), micro=len(micro), macro=len(macro))

    if not items:
        emit("council", "No corpus to analyse", status="ok", total=0)
        report = CouncilReport(source_count=0)
        save_council_snapshot(report)
        return report

    # Tier 3 — Andie desks (fan-out). Macro bypass: desks see MICRO only.
    notes = run_analysts(micro, emit=emit)
    # Tier 4 — Freddy debate.
    debate = run_debate(notes, emit=emit)
    # Tier 5 — Winston chairman (fan-in) + macro bypass.
    verdict = run_chairman(notes, debate, macro, emit=emit)

    # Stitch the Chairman's verdict back onto the debate transcript.
    debate.verdict = verdict.verdict
    if verdict.verdict:
        debate.transcript.append(
            DebateTurn(who="winston", round="Verdict", label="Winston · rules", text=verdict.verdict)
        )

    report = CouncilReport(
        sector_notes=notes,
        debate=debate,
        baskets=verdict.baskets,
        indicators=verdict.indicators,
        ace=verdict.ace,
        briefing=verdict.briefing,
        predictions=verdict.predictions,
        source_count=len(items),
    )
    save_council_snapshot(report)
    emit("council", "Council snapshot ready", status="ok",
         baskets=len(report.baskets), briefing=len(report.briefing))
    return report


def latest_council() -> CouncilReport | None:
    """Return the most recent persisted council snapshot, if any."""
    return get_latest_council_snapshot()
