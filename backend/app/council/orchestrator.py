"""The council DAG (Tiers 3→5).

Reads the persisted corpus, fans out to the three Andie desks, runs the Freddy
debate, then fans in to Winston. The pipeline is a strict DAG: Winston can't run
until Freddy finishes, Freddy can't run until the Andies finish (PROJECT_GUIDANCE §6).
The macro bypass routes `[MACRO]` items past the analysts to the Macro Analyst (which
grades the bear-signpost checklist) and to Winston.

The assembled `CouncilReport` is persisted as the latest snapshot. The whole thing is
fault-isolated by callers (the discovery endpoint) so a council failure never breaks
the upstream discovery.
"""
from __future__ import annotations

import logging

from ..db.repository import (
    compute_ledger,
    get_latest_council_snapshot,
    list_cleaned_items,
    save_council_snapshot,
    save_predictions,
)
from ..events import Emit, noop_emit
from ..models import CleanedItem, CouncilReport, DebateTurn, SourceRef, Stream
from .analyst import run_analysts
from .chairman import run_chairman
from .debate import run_debate
from .macro import run_macro_analyst
from .resolver import resolve_due_predictions

logger = logging.getLogger(__name__)

_MAX_ITEMS = 200  # corpus cap fed into the council


def _build_manifest(items: list[CleanedItem], report: CouncilReport) -> list[SourceRef]:
    """One row per document the council read, tagged with the agents that quoted it.

    This is the audit trail the UI's Sources page renders (§12.6). It is recorded on the
    snapshot rather than recomputed from the live corpus, so a saved run still reports what
    it was actually based on after the corpus moves on. Documents nobody cited are kept —
    "read but not used" is a fact worth showing, not one to hide.
    """
    cited: dict[str, set[str]] = {}

    def _mark(agent: str, evidence) -> None:
        for ev in evidence:
            cited.setdefault(ev.source_url, set()).add(agent)

    for note in report.sector_notes:
        for stock in note.stocks:
            _mark(f"Andie-{note.desk}", stock.evidence)
    if report.macro:
        for signpost in report.macro.signposts:
            _mark("Macro Analyst", signpost.evidence)
    for group in (report.indicators, report.baskets, report.briefing, report.predictions):
        for claim in group:
            _mark("Winston", claim.evidence)

    return [
        SourceRef(
            url=it.source_url,
            title=it.title,
            source_type=it.source_type,
            stream=it.stream,
            author=it.author,
            published_at=it.published_at,
            themes=list(it.themes),
            cited_by=sorted(cited.get(it.source_url, ())),
        )
        for it in items
    ]


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
    # Macro bypass — the Macro Analyst grades the bear-signpost checklist off the same
    # `[MACRO]` slice Winston sees, and hands him the tracker so his indicators agree with it.
    macro_report = run_macro_analyst(macro, emit=emit)
    # Tier 5 — Winston chairman (fan-in) + macro bypass.
    verdict = run_chairman(
        notes, debate, macro, emit=emit, macro_report=macro_report, micro_items=micro
    )

    # Stitch the Chairman's verdict back onto the debate transcript.
    debate.verdict = verdict.verdict
    if verdict.verdict:
        debate.transcript.append(
            DebateTurn(who="winston", round="Verdict", label="Winston · rules", text=verdict.verdict)
        )

    # Tier 3 rubric scoring: persist new predictions, resolve any whose window passed,
    # then recompute the per-channel Brier ledger. Fault-isolated — scoring must never
    # break the council run (§7.3).
    ledger = []
    try:
        save_predictions(verdict.predictions)
        resolve_due_predictions(items, emit=emit)
        ledger = compute_ledger(get_latest_council_snapshot())
    except Exception:
        logger.exception("Prediction ledger scoring failed; continuing without it")

    report = CouncilReport(
        sector_notes=notes,
        debate=debate,
        baskets=verdict.baskets,
        indicators=verdict.indicators,
        macro=macro_report,
        ace=verdict.ace,
        briefing=verdict.briefing,
        predictions=verdict.predictions,
        ledger=ledger,
        source_count=len(items),
    )
    report.sources = _build_manifest(items, report)
    save_council_snapshot(report)
    emit("council", "Council snapshot ready", status="ok",
         baskets=len(report.baskets), briefing=len(report.briefing),
         sources=len(report.sources),
         cited=sum(1 for s in report.sources if s.cited_by))
    return report


def latest_council() -> CouncilReport | None:
    """Return the most recent persisted council snapshot, if any."""
    return get_latest_council_snapshot()


def resolve_ledger(emit: Emit = noop_emit) -> int:
    """Score due predictions against the current corpus and refresh the ledger snapshot.

    Standalone counterpart to a full council run — useful to settle predictions whose
    window has passed without re-running Tiers 3–5. Returns the number resolved.
    """
    corpus = list_cleaned_items(limit=_MAX_ITEMS)
    resolved = resolve_due_predictions(corpus, emit=emit)
    prev = get_latest_council_snapshot()
    ledger = compute_ledger(prev)
    # Don't manufacture an empty snapshot when nothing has run and nothing scored.
    if prev is None and not ledger:
        return resolved
    report = prev or CouncilReport()
    report.ledger = ledger
    save_council_snapshot(report)
    return resolved
