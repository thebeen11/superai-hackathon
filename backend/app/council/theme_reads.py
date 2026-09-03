"""Winston's per-theme stance — the concept trackers' direction (§7.1).

A theme has no direction of its own anywhere upstream: Timo tags items with themes, and
counting those tags says how *loud* a theme is, never which way it leans. So Winston
grades the themes the same way the Macro Analyst grades the bear signposts — against a
*fixed* list (`taxonomy.MARKET_THEME_TAXONOMY`), so the same rows are scored every run and
a theme is comparable run-over-run. The model scores the themes; it never chooses them.

The guardrails are `macro.py`'s, for the same reasons:

- **No orphan calls.** A `Bullish`/`Bearish` stance must cite an excerpt Winston was
  actually given; a cited index that doesn't exist is dropped, and a directional call left
  with no grounded evidence falls back to `Neutral` + `evidenced=False`. He cannot lean on
  something he invented.
- **Always complete.** The result is reconciled against the taxonomy in Python: every theme
  appears exactly once, in taxonomy order, whatever the model returned. The list is also
  appended to the system prompt if an edited prompt dropped the `{themes}` placeholder.

This runs as its own call rather than as more fields on `run_chairman`, because the corpus
differs: the Chairman rules off the macro bypass plus whatever the desks quoted, while a
theme read has to see the micro items the themes were tagged on.
"""
from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field

from ..events import Emit, noop_emit
from ..llm import ReasoningError, converse_structured
from ..models import CleanedItem, SectorNote, ThemeRead
from ..prompts import get_prompt
from ..taxonomy import MARKET_THEME_TAXONOMY, THEME_STANCES
from . import grounding

logger = logging.getLogger(__name__)

_MAX_ITEMS = 40      # cap on the numbered corpus, to bound the prompt
_SNIPPET = 400       # chars per excerpt — shorter than the Chairman's, there are more rows
_UNEVIDENCED = "Not evidenced in the current corpus."
_STAGE = "council.themes"


class _LLMThemeRead(BaseModel):
    theme: str
    stance: str = "Neutral"
    rationale: str = ""
    evidence: list[grounding.LLMEvidence] = Field(default_factory=list)


class _ThemesOutput(BaseModel):
    themes: list[_LLMThemeRead] = Field(default_factory=list)


def theme_prompt(themes: list[str] = MARKET_THEME_TAXONOMY) -> str:
    """The taxonomy, rendered for the `{themes}` placeholder."""
    return "\n".join(f"- {name}" for name in themes)


def _norm(text: str) -> str:
    """Fold a theme label to a comparable token — the same folding `macro._norm` uses."""
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")


def _unevidenced(theme: str, rationale: str = _UNEVIDENCED) -> ThemeRead:
    return ThemeRead(theme=theme, stance="Neutral", rationale=rationale, evidenced=False)


def citable_corpus(items: list[CleanedItem]) -> list[CleanedItem]:
    """The numbered sources Winston may cite, biased toward items that carry a theme.

    An item Timo tagged with no theme can still be quoted — it just cannot be the reason a
    theme was graded — so themed items are offered first and the cap spends its budget on
    material that actually speaks to the list.
    """
    themed = [it for it in items if it.themes]
    untagged = [it for it in items if not it.themes]
    return (themed + untagged)[:_MAX_ITEMS]


def _corpus_digest(items: list[CleanedItem]) -> str:
    """The numbered excerpts, each headed with the themes it was tagged with.

    Winston is grading themes, so the tags are the part of an excerpt that tells him which
    row it bears on — the same trick the analyst desks use to attach tickers to an excerpt.
    """
    return grounding.digest(
        items,
        snippet=_SNIPPET,
        extra=lambda it: f"themes={it.themes}" if it.themes else "themes=[]",
    )


def _notes_digest(notes: list[SectorNote]) -> str:
    """The desks' standing reads, as context only — never a substitute for a citation."""
    lines = [f"Desk {n.desk}: {n.summary}" for n in notes if n.summary]
    return "\n".join(lines) or "No desk notes."


def _system_prompt(themes: list[str] = MARKET_THEME_TAXONOMY) -> str:
    """The prompt, with the theme list guaranteed to be in it.

    `{themes}` is the machine contract, not decoration — `_reconcile` matches on the names
    it carries. A console edit that drops the placeholder fills to a no-op, and Winston
    would grade a list he was never shown, so we append it. Same guarantee as
    `macro._system_prompt`.
    """
    rendered = theme_prompt(themes)
    system = get_prompt("council.themes", themes=rendered)
    if rendered in system:
        return system
    logger.warning(
        "The council.themes prompt no longer contains {themes}; appending the taxonomy "
        "so Winston still grades the fixed rows."
    )
    return (
        f"{system}\n\nTHEMES — grade exactly these and only these, copying each name "
        f"verbatim into your answer:\n{rendered}"
    )


def _reconcile(
    out: _ThemesOutput,
    items: list[CleanedItem],
    themes: list[str] = MARKET_THEME_TAXONOMY,
) -> list[ThemeRead]:
    """One row per taxonomy entry, in taxonomy order, each grounded or downgraded."""
    alias = {_norm(name): name for name in themes}
    by_theme: dict[str, _LLMThemeRead] = {}
    unmatched: list[str] = []
    for raw in out.themes:
        canonical = alias.get(_norm(raw.theme))
        if canonical is None:
            unmatched.append(raw.theme)
        else:
            by_theme.setdefault(canonical, raw)
    if unmatched:
        # Almost always a prompt that lost the taxonomy, so Winston invented his own themes.
        # Without this line the trackers just render unrated with no explanation.
        logger.warning(
            "Winston returned %d theme(s) matching no taxonomy entry: %s",
            len(unmatched), ", ".join(sorted(unmatched)),
        )

    graded: list[ThemeRead] = []
    for name in themes:
        raw = by_theme.get(name)
        if raw is None:
            graded.append(_unevidenced(name, "Not returned by the Chairman."))
            continue
        stance = raw.stance.strip().title()
        if stance not in THEME_STANCES:
            stance = "Neutral"
        evidence = grounding.ground(raw.evidence, items)
        # A directional call with no surviving source is not a call (no-orphan guardrail).
        if stance != "Neutral" and not evidence:
            logger.info("Downgrading ungrounded theme read %s (%s → Neutral)", name, stance)
            graded.append(_unevidenced(name))
            continue
        graded.append(
            ThemeRead(
                theme=name,
                stance=stance,
                rationale=raw.rationale,
                evidence=evidence,
                evidenced=bool(evidence),
            )
        )
    return graded


def _fallback(rationale: str = _UNEVIDENCED) -> list[ThemeRead]:
    """A complete, all-unevidenced set — used when there is nothing to grade."""
    return [_unevidenced(name, rationale) for name in MARKET_THEME_TAXONOMY]


def run_theme_reads(
    items: list[CleanedItem],
    notes: list[SectorNote] | None = None,
    emit: Emit = noop_emit,
) -> list[ThemeRead]:
    """Grade the fixed theme taxonomy against the corpus. Always returns every theme."""
    emit(_STAGE, "Winston reading the themes", status="start", themes=len(MARKET_THEME_TAXONOMY))
    corpus = citable_corpus(items)
    if not corpus:
        emit(_STAGE, "No corpus to read themes from", status="ok", evidenced=0)
        return _fallback()

    user = (
        f"DESK NOTES:\n{_notes_digest(notes or [])}\n\n"
        "SOURCES (cite these by index):\n" + _corpus_digest(corpus)
    )
    try:
        out = converse_structured(_ThemesOutput, _system_prompt(), user)
    except ReasoningError as exc:
        logger.warning("Theme reads failed: %s", exc)
        emit(_STAGE, f"Theme reads unavailable: {exc.kind}", status="skip")
        return _fallback(f"Theme read unavailable ({exc.kind}).")

    reads = _reconcile(out, corpus)
    evidenced = sum(1 for r in reads if r.evidenced)
    emit(_STAGE, "Winston graded the themes", status="ok",
         themes=len(reads), evidenced=evidenced)
    return reads
