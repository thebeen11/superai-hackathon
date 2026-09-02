"""Thematic Analysis (Tier 5, weekly) tests.

The LLM and the DB are mocked, so these run with no network or credentials.
"""
from __future__ import annotations

import pytest

from app.council import thematic as thematic_mod
from app.council.grounding import LLMEvidence as _LLMEvidence
from app.council.thematic import _LLMBasket, _ThematicOutput, normalise_timeframe, run_thematic
from app.models import (
    CleanedItem,
    CouncilReport,
    Evidence,
    ResolvedEntity,
    SectorNote,
    SourceType,
    StockTake,
    Stream,
    ThematicRun,
)


def _item(url="u", stream=Stream.MICRO, text="nvidia demand strong"):
    return CleanedItem(
        source_url=url, source_type=SourceType.WEB, title="t", clean_text=text,
        stream=stream, industry="Technology",
        entities=[ResolvedEntity(canonical="$NVDA")],
    )


@pytest.fixture
def saved(monkeypatch):
    """Capture what run_thematic persists, and hand back an id like the database would."""
    box: dict[str, ThematicRun] = {}

    def _save(run: ThematicRun) -> ThematicRun:
        run.id = 7
        box["run"] = run
        return run

    monkeypatch.setattr(thematic_mod, "save_thematic_run", _save)
    monkeypatch.setattr(thematic_mod, "get_latest_council_snapshot", lambda: None)
    return box


# --- Timeframe normalisation -------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("Short Term", "Short Term"),
    ("short term", "Short Term"),
    ("  LONG   TERM ", "Long Term"),
    ("Medium", "Medium Term"),      # the model reaches for the bare word often enough
    ("Long", "Long Term"),
    ("", "Medium Term"),
    ("18 months", "Medium Term"),   # anything unrecognised falls to the middle bucket
    ("Ultra Long Term", "Medium Term"),
])
def test_normalise_timeframe_snaps_to_the_closed_set(raw, expected):
    assert normalise_timeframe(raw) == expected


def test_run_files_an_unrecognised_timeframe_as_medium(monkeypatch, saved):
    monkeypatch.setattr(thematic_mod, "list_cleaned_items", lambda **k: [_item()])
    out = _ThematicOutput(baskets=[_LLMBasket(name="AI Buildout", timeframe="whenever")])
    monkeypatch.setattr(thematic_mod, "converse_structured", lambda *a, **k: out)
    run = run_thematic()
    assert run.baskets[0].timeframe == "Medium Term"


# --- Basket normalisation ----------------------------------------------------

def test_run_clamps_conviction_and_upper_cases_tickers(monkeypatch, saved):
    monkeypatch.setattr(thematic_mod, "list_cleaned_items", lambda **k: [_item()])
    out = _ThematicOutput(baskets=[
        _LLMBasket(name="AI Buildout", stocks=["nvda", "mu"], conviction=1.5,
                   timeframe="Long Term"),
    ])
    monkeypatch.setattr(thematic_mod, "converse_structured", lambda *a, **k: out)
    run = run_thematic()
    assert run.baskets[0].conviction == 1.0        # clamped to [0, 1]
    assert run.baskets[0].stocks == ["NVDA", "MU"]
    assert run.baskets[0].timeframe == "Long Term"


def test_run_grounds_citations_to_real_urls(monkeypatch, saved):
    macro = _item(url="macro-url", stream=Stream.MACRO, text="the fed is on hold")
    monkeypatch.setattr(thematic_mod, "list_cleaned_items", lambda **k: [macro])
    out = _ThematicOutput(baskets=[
        _LLMBasket(name="Rate Cut Beneficiaries",
                   evidence=[_LLMEvidence(quote="on hold", source_index=0)]),
    ])
    monkeypatch.setattr(thematic_mod, "converse_structured", lambda *a, **k: out)
    run = run_thematic()
    assert [e.source_url for e in run.baskets[0].evidence] == ["macro-url"]


def test_run_keeps_a_basket_whose_citation_does_not_resolve(monkeypatch, saved):
    """An ungrounded basket survives un-anchored, as a Chairman indicator does.

    The thesis still means something without the quote, and the UI shows it as unsourced
    rather than hiding that it was made at all.
    """
    monkeypatch.setattr(thematic_mod, "list_cleaned_items",
                        lambda **k: [_item(url="macro-url", stream=Stream.MACRO)])
    out = _ThematicOutput(baskets=[
        _LLMBasket(name="AI Buildout",
                   evidence=[_LLMEvidence(quote="fake", source_index=99)]),
    ])
    monkeypatch.setattr(thematic_mod, "converse_structured", lambda *a, **k: out)
    run = run_thematic()
    assert len(run.baskets) == 1 and run.baskets[0].evidence == []


# --- The run itself ----------------------------------------------------------

def test_run_persists_a_dated_run_with_a_source_manifest(monkeypatch, saved):
    items = [_item(url="cited"), _item(url="unused")]
    monkeypatch.setattr(thematic_mod, "list_cleaned_items", lambda **k: items)
    out = _ThematicOutput(baskets=[
        _LLMBasket(name="AI Buildout",
                   evidence=[_LLMEvidence(quote="demand strong", source_index=0)]),
    ])
    monkeypatch.setattr(thematic_mod, "converse_structured", lambda *a, **k: out)
    run = run_thematic()

    assert saved["run"] is run and run.id == 7
    assert run.source_count == 2
    assert run.generated_at is not None
    # Every document read is listed; only the cited one carries an attribution (§12.6).
    manifest = {s.url: s.cited_by for s in run.sources}
    assert manifest == {"cited": ["Winston"], "unused": []}


def test_run_borrows_the_latest_council_snapshot_for_context(monkeypatch, saved):
    """The desks' cited micro sources must be citable, or a basket could anchor to nothing."""
    micro = _item(url="micro-cited")
    monkeypatch.setattr(thematic_mod, "list_cleaned_items", lambda **k: [micro])
    monkeypatch.setattr(thematic_mod, "get_latest_council_snapshot", lambda: CouncilReport(
        sector_notes=[SectorNote(desk="TMT", stocks=[
            StockTake(ticker="$NVDA", conviction=0.5, horizon="6M",
                      evidence=[Evidence(quote="q", source_url="micro-cited")]),
        ])],
    ))
    seen: dict[str, str] = {}

    def _fake(schema, system, user):
        seen["user"] = user
        return _ThematicOutput(baskets=[
            _LLMBasket(name="AI Buildout",
                       evidence=[_LLMEvidence(quote="demand strong", source_index=0)]),
        ])

    monkeypatch.setattr(thematic_mod, "converse_structured", _fake)
    run = run_thematic()
    assert "Desk TMT" in seen["user"]                      # notes reached the prompt
    assert [e.source_url for e in run.baskets[0].evidence] == ["micro-cited"]


def test_empty_corpus_saves_an_honest_empty_run(monkeypatch, saved):
    """"Ran, found nothing" beats leaving last week's themes standing as if current."""
    monkeypatch.setattr(thematic_mod, "list_cleaned_items", lambda **k: [])
    monkeypatch.setattr(thematic_mod, "converse_structured",
                        lambda *a, **k: pytest.fail("must not call the LLM with no corpus"))
    run = run_thematic()
    assert run.baskets == [] and run.source_count == 0
    assert saved["run"] is run


def test_reasoning_failure_still_saves_a_run(monkeypatch, saved):
    from app.llm import ReasoningError

    monkeypatch.setattr(thematic_mod, "list_cleaned_items", lambda **k: [_item()])

    def _boom(*a, **k):
        raise ReasoningError("bad json", kind="schema_validation")

    monkeypatch.setattr(thematic_mod, "converse_structured", _boom)
    run = run_thematic()
    assert run.baskets == [] and run.source_count == 1
    assert saved["run"] is run


def test_micro_items_are_citable_without_a_council_snapshot(monkeypatch, saved):
    """A first-ever run has no desk notes to borrow, so it must still cite what it read."""
    monkeypatch.setattr(thematic_mod, "list_cleaned_items",
                        lambda **k: [_item(url="micro-only", stream=Stream.MICRO)])
    out = _ThematicOutput(baskets=[
        _LLMBasket(name="AI Buildout",
                   evidence=[_LLMEvidence(quote="demand strong", source_index=0)]),
    ])
    monkeypatch.setattr(thematic_mod, "converse_structured", lambda *a, **k: out)
    run = run_thematic()
    assert [e.source_url for e in run.baskets[0].evidence] == ["micro-only"]
