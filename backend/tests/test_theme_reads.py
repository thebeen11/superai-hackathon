"""Winston's per-theme stance — the concept trackers' direction.

The LLM is mocked, so these run with no network or credentials, like the other
council tests. The guardrails mirror the Macro Analyst's signpost tracker
(tests/test_macro.py), because they are the same two rules: always complete, and no
directional call without a source.
"""
from __future__ import annotations

from app.council import theme_reads as themes_mod
from app.council.grounding import LLMEvidence as _LLMEvidence
from app.council.theme_reads import (
    _LLMThemeRead,
    _ThemesOutput,
    citable_corpus,
    run_theme_reads,
    theme_prompt,
)
from app.llm import ReasoningError
from app.models import CleanedItem, SourceType, Stream
from app.taxonomy import MARKET_THEME_TAXONOMY


def _item(url="u", text="memory pricing is inflecting hard", themes=("Semiconductors",)):
    return CleanedItem(
        source_url=url, source_type=SourceType.WEB, title="t", clean_text=text,
        stream=Stream.MICRO, industry="Technology", themes=list(themes),
    )


def _out(*reads: _LLMThemeRead) -> _ThemesOutput:
    return _ThemesOutput(themes=list(reads))


def test_taxonomy_is_always_complete_and_in_order(monkeypatch):
    # Two rows, out of taxonomy order, plus a theme that isn't in the taxonomy at all.
    monkeypatch.setattr(themes_mod, "converse_structured", lambda *a, **k: _out(
        _LLMThemeRead(theme="Semiconductors", stance="Bullish", rationale="supply tight",
                      evidence=[_LLMEvidence(quote="memory pricing", source_index=0)]),
        _LLMThemeRead(theme="Technology", stance="Bearish", rationale="multiples",
                      evidence=[_LLMEvidence(quote="pricing is inflecting", source_index=0)]),
        _LLMThemeRead(theme="Crypto Winter", stance="Bearish"),
    ))
    reads = run_theme_reads([_item()])

    assert [r.theme for r in reads] == MARKET_THEME_TAXONOMY  # every row, taxonomy order
    by = {r.theme: r for r in reads}
    assert by["Technology"].stance == "Bearish"
    assert by["Semiconductors"].stance == "Bullish"
    # The invented theme is dropped rather than appended.
    assert not any(r.theme == "Crypto Winter" for r in reads)
    # Rows the model never returned are unrated, not quietly Neutral-with-an-opinion.
    assert by["Healthcare"].stance == "Neutral" and not by["Healthcare"].evidenced


def test_ungrounded_directional_call_is_downgraded_not_reported(monkeypatch):
    """A stance with no surviving source is not a stance (no-orphan guardrail §12.6)."""
    monkeypatch.setattr(themes_mod, "converse_structured", lambda *a, **k: _out(
        # index 9 does not exist in a one-item corpus — an invented citation.
        _LLMThemeRead(theme="Energy", stance="Bullish", rationale="crude",
                      evidence=[_LLMEvidence(quote="made up", source_index=9)]),
        _LLMThemeRead(theme="Financials", stance="Bearish", rationale="no quote at all"),
    ))
    by = {r.theme: r for r in run_theme_reads([_item()])}

    for theme in ("Energy", "Financials"):
        assert by[theme].stance == "Neutral"
        assert by[theme].evidenced is False
        assert not by[theme].evidence
        # The downgrade says why, rather than leaving the model's stranded rationale.
        assert by[theme].rationale == "Not evidenced in the current corpus."


def test_a_neutral_call_survives_without_evidence(monkeypatch):
    """Neutral is a real reading, so it is not required to cite — only a direction is."""
    monkeypatch.setattr(themes_mod, "converse_structured", lambda *a, **k: _out(
        _LLMThemeRead(theme="Utilities", stance="Neutral", rationale="genuinely two-sided"),
    ))
    read = {r.theme: r for r in run_theme_reads([_item()])}["Utilities"]
    assert read.stance == "Neutral" and read.rationale == "genuinely two-sided"
    assert read.evidenced is False  # honest: nothing anchored it


def test_unknown_stance_falls_back_to_neutral(monkeypatch):
    monkeypatch.setattr(themes_mod, "converse_structured", lambda *a, **k: _out(
        _LLMThemeRead(theme="Solar", stance="Mildly Constructive",
                      evidence=[_LLMEvidence(quote="memory pricing", source_index=0)]),
        # Casing and stray whitespace are spelling, not a different call.
        _LLMThemeRead(theme="Materials", stance="  bullish ", rationale="r",
                      evidence=[_LLMEvidence(quote="memory pricing", source_index=0)]),
    ))
    by = {r.theme: r for r in run_theme_reads([_item()])}
    assert by["Solar"].stance == "Neutral"
    assert by["Materials"].stance == "Bullish"


def test_reasoning_failure_returns_a_complete_unevidenced_set(monkeypatch):
    def boom(*a, **k):
        raise ReasoningError("upstream 503", kind="unavailable")

    monkeypatch.setattr(themes_mod, "converse_structured", boom)
    reads = run_theme_reads([_item()])
    assert [r.theme for r in reads] == MARKET_THEME_TAXONOMY
    assert all(not r.evidenced and r.stance == "Neutral" for r in reads)
    assert "unavailable" in reads[0].rationale


def test_empty_corpus_skips_the_llm():
    # No monkeypatch: a call to the real LLM would fail, so reaching it fails the test.
    reads = run_theme_reads([])
    assert [r.theme for r in reads] == MARKET_THEME_TAXONOMY
    assert all(not r.evidenced for r in reads)


def test_theme_prompt_lists_every_theme():
    rendered = theme_prompt()
    for name in MARKET_THEME_TAXONOMY:
        assert f"- {name}" in rendered


def test_taxonomy_reaches_the_model_even_if_the_prompt_drops_the_placeholder(monkeypatch):
    """The theme list is the parser's contract, so a console edit can't drop it."""
    monkeypatch.setattr(themes_mod, "get_prompt", lambda key, **kw: "Grade the themes.")
    seen: dict = {}

    def capture(schema, system, user):
        seen["system"] = system
        return _out()

    monkeypatch.setattr(themes_mod, "converse_structured", capture)
    run_theme_reads([_item()])
    for name in MARKET_THEME_TAXONOMY:
        assert name in seen["system"]


def test_a_prompt_that_keeps_the_placeholder_is_not_appended_to(monkeypatch):
    monkeypatch.setattr(themes_mod, "get_prompt",
                        lambda key, **kw: f"Grade:\n{kw['themes']}")
    seen: dict = {}

    def capture(schema, system, user):
        seen["system"] = system
        return _out()

    monkeypatch.setattr(themes_mod, "converse_structured", capture)
    run_theme_reads([_item()])
    assert seen["system"].count("Technology") == 1  # appended once, not twice


def test_excerpts_carry_their_theme_tags(monkeypatch):
    """Winston grades themes, so the tag is what tells him which row an excerpt bears on."""
    seen: dict = {}

    def capture(schema, system, user):
        seen["user"] = user
        return _out()

    monkeypatch.setattr(themes_mod, "converse_structured", capture)
    run_theme_reads([_item(themes=("Energy", "Oil & Gas"))])
    assert "themes=['Energy', 'Oil & Gas']" in seen["user"]


def test_themed_items_are_offered_to_the_model_first():
    """The corpus cap should be spent on material that actually speaks to the taxonomy."""
    untagged = [_item(url=f"bare-{i}", themes=()) for i in range(40)]
    tagged = _item(url="tagged", themes=("Energy",))
    corpus = citable_corpus(untagged + [tagged])
    assert corpus[0].source_url == "tagged"
    assert len(corpus) == 40  # still capped
