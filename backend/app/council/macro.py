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

**Second pass (`backfill_signposts`).** Pass 1 can only grade what the crawl happened to
bring in, so on most nights several rows come back unevidenced — not because the world is
quiet on them, but because nothing in the corpus mentions them. The second pass searches the
web for each *still-ungraded* row specifically (one deterministic Exa query per gap, built
from the checklist entry itself) and re-grades only those rows against what it fetched. The
same no-orphan rule applies, so an ungrounded alarm is still dropped; and a row can only move
*up* from unevidenced — a row pass 1 already grounded is never re-opened.

Backfill documents are **run-scoped**: they are grounded, cited and recorded in the run's
source manifest, but never written to `cleaned_items`. They were fetched to answer one row of
one run, not to join the corpus the desks and themes read.
"""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field

from ..config import settings
from ..dataeng.guardrail import OrphanDataError, enforce
from ..discovery import exa_source
from ..discovery.exa_source import SourceUnavailable
from ..events import Emit, noop_emit
from ..llm import ReasoningError, converse_structured
from ..models import BearSignpostReport, CleanedItem, Signpost, SourceItem, Stream
from ..prompts import get_prompt
from ..taxonomy import BEAR_SIGNPOSTS, SIGNPOST_STATUSES, UNCLASSIFIED
from . import grounding

logger = logging.getLogger(__name__)

# One checklist entry: (key, display name, what would trigger it) — see taxonomy.py.
Row = tuple[str, str, str]

_MAX_ITEMS = 25    # macro corpus cap fed into the single reasoning call
_UNEVIDENCED = "Not evidenced in the current corpus."
_STAGE = "council.macro"
_MAX_SEARCH_WORKERS = 4   # parallel Exa queries in the second pass
_EXTERNAL_TEXT = 4000     # chars kept per fetched article (excerpts are snippeted anyway)


class _LLMSignpost(BaseModel):
    key: str
    status: str = "Clear"
    rationale: str = ""
    evidence: list[grounding.LLMEvidence] = Field(default_factory=list)


class _MacroOutput(BaseModel):
    signposts: list[_LLMSignpost] = Field(default_factory=list)
    summary: str = ""


def checklist_prompt(rows: tuple[Row, ...] | list[Row] = BEAR_SIGNPOSTS) -> str:
    """The checklist, rendered for the `{signposts}` placeholder.

    `rows` is the whole fixed checklist for pass 1, and just the still-ungraded subset for
    the second pass — which is the only narrowing the desk is ever allowed: the rows are
    still chosen in Python, never by the model.
    """
    return "\n".join(f"- {key}  ({name}): {trigger}" for key, name, trigger in rows)


def _norm(text: str) -> str:
    """Fold a label to a comparable token: lowercase, non-alphanumerics collapsed to `_`."""
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")


def _aliases(rows: tuple[Row, ...] | list[Row] = BEAR_SIGNPOSTS) -> dict[str, str]:
    """Every spelling we will accept for a checklist row → its canonical key.

    The model is told to copy the key verbatim, but a re-worded prompt may get back the
    display name (`Labour Market`) or a cosmetic variant (`Yield-Curve`). Those name the
    same row, so resolving them is not leniency about *what* was graded — only about how
    it was spelled. A key that matches nothing still falls through to "not returned".
    """
    table: dict[str, str] = {}
    for key, name, _trigger in rows:
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


def _reconcile(
    out: _MacroOutput,
    items: list[CleanedItem],
    rows: tuple[Row, ...] | list[Row] = BEAR_SIGNPOSTS,
    *,
    backfilled: bool = False,
) -> list[Signpost]:
    """One row per checklist entry, in checklist order, each grounded or downgraded.

    `rows` narrows the checklist for the second pass; `backfilled` tags the rows it grades,
    so the dashboard can tell a row evidenced by the crawled corpus from one evidenced by
    material the desk went out and fetched for it.
    """
    alias = _aliases(rows)
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

    graded: list[Signpost] = []
    for key, name, _trigger in rows:
        raw = by_key.get(key)
        if raw is None:
            graded.append(_empty_signpost(key, name, "Not returned by the analyst."))
            continue
        status = raw.status.strip().title()
        if status not in SIGNPOST_STATUSES:
            status = "Clear"
        evidence = grounding.ground(raw.evidence, items)
        # An alarm with no surviving source is not an alarm (no-orphan guardrail).
        if status != "Clear" and not evidence:
            logger.info("Downgrading ungrounded signpost %s (%s → Clear)", key, status)
            graded.append(_empty_signpost(key, name))
            continue
        graded.append(
            Signpost(
                key=key,
                name=name,
                status=status,
                rationale=raw.rationale,
                evidence=evidence,
                evidenced=bool(evidence),
                backfilled=backfilled and bool(evidence),
            )
        )
    return graded


def _fallback(summary: str) -> BearSignpostReport:
    """A complete, all-unevidenced tracker — used when there is nothing to grade."""
    return _tally(
        [_empty_signpost(key, name) for key, name, _ in BEAR_SIGNPOSTS],
        summary,
    )


def _system_prompt(
    key: str = "council.macro", rows: tuple[Row, ...] | list[Row] = BEAR_SIGNPOSTS
) -> str:
    """The Macro Analyst's prompt, with the checklist guaranteed to be in it.

    `{signposts}` is not decoration — it is the machine contract, because `_reconcile`
    matches on the keys it carries. A console edit that drops the placeholder fills to a
    no-op (`prompts.registry._fill` never errors, so users can paste literal braces), and
    the desk would silently grade a checklist it was never shown. So we append it, the
    same way `llm/vertex.py` appends the JSON output contract outside the prompt catalogue.
    """
    checklist = checklist_prompt(rows)
    system = get_prompt(key, signposts=checklist)
    if checklist in system:
        return system
    logger.warning(
        "The %s prompt no longer contains {signposts}; appending the checklist "
        "so the desk still grades the fixed rows.", key,
    )
    return (
        f"{system}\n\nCHECKLIST — grade exactly these rows and only these, copying each "
        f"`key` verbatim into your answer:\n{checklist}"
    )


def run_macro_analyst(
    macro_items: list[CleanedItem], emit: Emit = noop_emit
) -> BearSignpostReport:
    """Grade the fixed bear-market checklist against the `[MACRO]` corpus."""
    emit(_STAGE, "Macro Analyst scanning bear signposts", status="start",
         macro=len(macro_items))

    if not macro_items:
        emit(_STAGE, "No macro corpus to grade", status="skip")
        return _fallback("No macro material in this run — the checklist is ungraded, not clear.")

    items = macro_items[:_MAX_ITEMS]
    try:
        system = _system_prompt()
        out = converse_structured(_MacroOutput, system, grounding.digest(items))
    except ReasoningError as exc:
        logger.warning("Macro Analyst reasoning failed: %s", exc)
        emit(_STAGE, f"Macro Analyst unavailable: {exc.kind}", status="skip")
        return _fallback(f"Macro analysis unavailable ({exc.kind}).")

    report = _tally(_reconcile(out, items), out.summary)
    emit(_STAGE, f"{report.triggered}/{report.total} signposts triggered", status="ok",
         triggered=report.triggered, watch=report.watch, total=report.total,
         risk_score=report.risk_score, label=report.label)
    return report


# --- Second pass: fetch external material for the rows nothing spoke to ----------------


def _gap_query(name: str, trigger: str) -> str:
    """The web query for one ungraded row, built from the checklist entry itself.

    Deterministic on purpose: the same gap asks the same question every night, so two runs
    of the tracker differ because the world moved, not because the query drifted.
    """
    return f"{name} latest data: {trigger}"


def _since() -> str:
    """The published-date floor for backfill hits — a signpost is a claim about *now*."""
    days = max(1, settings.macro_backfill_lookback_days)
    return (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()


def _search_gap(query: str, since: str) -> tuple[list[SourceItem], str | None]:
    """Run one gap's web search, converting any failure into a skip reason (never raises)."""
    try:
        hits = exa_source.search(
            query,
            max_results=settings.macro_backfill_results_per_gap,
            # Deliberately not the run's `emit`: Exa's own `discover.web` events would
            # otherwise surface in the activity feed attributed to Wilfred, mid-council.
            start_published_date=since,
        )
        return hits, None
    except SourceUnavailable as exc:
        return [], str(exc)
    except Exception as exc:  # noqa: BLE001 - one failed gap must not kill the pass
        logger.exception("Signpost backfill search failed for %r", query)
        return [], f"unexpected error: {exc}"


def _as_cleaned(item: SourceItem) -> CleanedItem | None:
    """A fetched article as a citable, run-scoped `CleanedItem` — or None if unusable.

    No LLM runs here. The text is kept verbatim (truncated), which is exactly what the
    no-orphan-data guardrail wants to see, and the stream is known from the outset: this
    material was fetched *because* it is macro. Nothing is persisted — see the module
    docstring for why these documents stay out of `cleaned_items`.
    """
    text = (item.text or "").strip()[:_EXTERNAL_TEXT]
    if not text:
        return None
    cleaned = CleanedItem(
        source_url=item.url,
        source_type=item.source_type,
        title=item.title,
        clean_text=text,
        stream=Stream.MACRO,
        industry=UNCLASSIFIED,
        author=item.author,
        published_at=item.published_at,
        retrieved_at=item.retrieved_at,
    )
    try:
        return enforce(cleaned, item)
    except OrphanDataError as exc:
        logger.info("Dropping backfill item %s: %s", item.url, exc)
        return None


def _fetch_gap_items(
    gap_rows: list[Row], corpus: list[CleanedItem], emit: Emit
) -> list[CleanedItem]:
    """Search the web once per gap and return the usable, deduped, capped result."""
    since = _since()
    queries = [_gap_query(name, trigger) for _key, name, trigger in gap_rows]
    with ThreadPoolExecutor(max_workers=min(len(queries), _MAX_SEARCH_WORKERS)) as pool:
        outcomes = list(pool.map(lambda q: _search_gap(q, since), queries))

    seen = {it.source_url for it in corpus}
    items: list[CleanedItem] = []
    unavailable: list[str] = []
    for (key, _name, _trigger), (hits, error) in zip(gap_rows, outcomes):
        if error is not None:
            unavailable.append(f"{key}: {error}")
            continue
        for hit in hits:
            if len(items) >= settings.macro_backfill_max_items:
                break
            if hit.url in seen:
                continue      # already in the corpus, or already fetched for another gap
            cleaned = _as_cleaned(hit)
            if cleaned is None:
                continue
            seen.add(hit.url)
            items.append(cleaned)

    if unavailable:
        # Reported as progress, not skip: the pass may still have material from other gaps,
        # and a terminal status here would park the desk's live dot early.
        emit(_STAGE, f"Web search unavailable for {len(unavailable)} signpost(s)",
             status="progress", phase="backfill", reasons=unavailable)
    return items


def _merge(report: BearSignpostReport, graded: list[Signpost], sources: int) -> BearSignpostReport:
    """Fold the second pass's rows into the tracker — upgrades only, then re-tally.

    A pass-2 row replaces its pass-1 counterpart *only* when it came back grounded. A gap the
    web could not settle keeps pass 1's wording ("Not evidenced in the current corpus"), which
    is still the honest answer, rather than being overwritten by a second empty row.
    """
    upgrades = {row.key: row for row in graded if row.evidenced}
    merged = [upgrades.get(row.key, row) for row in report.signposts]
    summary = report.summary
    if upgrades:
        # A deterministic sentence, not model prose: the pass-1 summary describes the regime,
        # this only records how much of the tracker was filled in afterwards.
        note = (
            f"Second pass: {len(upgrades)} signpost(s) graded from {sources} externally "
            f"fetched source(s)."
        )
        summary = f"{summary} {note}".strip()
    return _tally(merged, summary)


def backfill_signposts(
    report: BearSignpostReport,
    corpus: list[CleanedItem],
    emit: Emit = noop_emit,
) -> tuple[BearSignpostReport, list[CleanedItem]]:
    """Re-grade the still-ungraded rows against material fetched for them (pass 2).

    Returns the merged tracker and the documents the pass read — the caller puts those in
    front of the Chairman and into the run's source manifest, so a backfilled citation
    resolves like any other. Degrades to `(report, [])` at every failure point: disabled,
    nothing to fill, no Exa key, no usable hits, reasoning unavailable.
    """
    if not settings.macro_backfill_enabled:
        emit(_STAGE, "Signpost backfill disabled", status="skip", phase="backfill")
        return report, []

    ungraded = {row.key for row in report.signposts if not row.evidenced}
    gap_rows: list[Row] = [row for row in BEAR_SIGNPOSTS if row[0] in ungraded]
    # Capped rather than run wholesale: when pass 1 fails outright every row is a gap, and
    # searching all ten would spend a full crawl's worth of queries on a broken run.
    gap_rows = gap_rows[: max(0, settings.macro_backfill_max_gaps)]
    if not gap_rows:
        emit(_STAGE, "Every signpost is evidenced; no second pass needed",
             status="skip", phase="backfill")
        return report, []

    emit(_STAGE, f"Second pass: searching for {len(gap_rows)} ungraded signpost(s)",
         status="start", phase="backfill", gaps=[key for key, _n, _t in gap_rows])
    fetched = _fetch_gap_items(gap_rows, corpus, emit)
    if not fetched:
        emit(_STAGE, "Second pass found no usable external sources",
             status="skip", phase="backfill")
        return report, []

    try:
        system = _system_prompt("council.macro_backfill", gap_rows)
        out = converse_structured(_MacroOutput, system, grounding.digest(fetched))
    except ReasoningError as exc:
        logger.warning("Macro Analyst second pass reasoning failed: %s", exc)
        emit(_STAGE, f"Second pass unavailable: {exc.kind}", status="skip", phase="backfill")
        return report, fetched   # read but uncited — the manifest still records them

    merged = _merge(report, _reconcile(out, fetched, gap_rows, backfilled=True), len(fetched))
    filled = sum(1 for row in merged.signposts if row.backfilled)
    emit(_STAGE, f"Second pass graded {filled}/{len(gap_rows)} ungraded signpost(s)",
         status="ok", phase="backfill", filled=filled, gaps=len(gap_rows),
         sources=len(fetched), triggered=merged.triggered, watch=merged.watch,
         risk_score=merged.risk_score, label=merged.label)
    return merged, fetched
