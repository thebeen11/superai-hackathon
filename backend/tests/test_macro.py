"""Macro Analyst — bear-market signpost tracker.

The LLM is mocked, so these run with no network or credentials, like the other
council tests.
"""
from __future__ import annotations

import pytest

from app.config import settings
from app.council import macro as macro_mod
from app.council.grounding import LLMEvidence as _LLMEvidence
from app.council.macro import _LLMSignpost, _MacroOutput, run_macro_analyst
from app.discovery.exa_source import SourceUnavailable
from app.llm import ReasoningError
from app.models import CleanedItem, SourceItem, SourceType, Stream
from app.taxonomy import BEAR_SIGNPOSTS


def _item(url="macro-url", text="the curve has been inverted for 14 months"):
    return CleanedItem(
        source_url=url, source_type=SourceType.WEB, title="t", clean_text=text,
        stream=Stream.MACRO, industry="Unclassified",
    )


def _out(*signposts: _LLMSignpost, summary: str = "s") -> _MacroOutput:
    return _MacroOutput(signposts=list(signposts), summary=summary)


def test_checklist_is_always_complete_and_in_order(monkeypatch):
    # The model returns two rows out of order plus a key that isn't on the checklist.
    monkeypatch.setattr(macro_mod, "converse_structured", lambda *a, **k: _out(
        _LLMSignpost(key="breadth", status="Watch",
                     evidence=[_LLMEvidence(quote="only 7 names", source_index=0)]),
        _LLMSignpost(key="yield_curve", status="Triggered",
                     evidence=[_LLMEvidence(quote="inverted", source_index=0)]),
        _LLMSignpost(key="not_a_signpost", status="Triggered"),
    ))
    report = run_macro_analyst([_item()])
    assert [s.key for s in report.signposts] == [k for k, _n, _t in BEAR_SIGNPOSTS]
    assert report.total == len(BEAR_SIGNPOSTS)
    # Everything the model didn't grade comes back Clear + unevidenced, never omitted.
    ungraded = [s for s in report.signposts if s.key not in {"breadth", "yield_curve"}]
    assert all(s.status == "Clear" and not s.evidenced for s in ungraded)


def test_ungrounded_alarm_is_downgraded_not_reported(monkeypatch):
    monkeypatch.setattr(macro_mod, "converse_structured", lambda *a, **k: _out(
        # Cites an excerpt that does not exist → the alarm has no source.
        _LLMSignpost(key="credit_spreads", status="Triggered", rationale="spreads blowing out",
                     evidence=[_LLMEvidence(quote="invented", source_index=99)]),
        # No evidence at all.
        _LLMSignpost(key="consumer", status="Watch", rationale="feels weak"),
        # Properly grounded → survives.
        _LLMSignpost(key="yield_curve", status="Triggered", rationale="inverted 14 months",
                     evidence=[_LLMEvidence(quote="inverted", source_index=0)]),
    ))
    report = run_macro_analyst([_item(url="real-url")])
    by_key = {s.key: s for s in report.signposts}

    for key in ("credit_spreads", "consumer"):
        assert by_key[key].status == "Clear"
        assert by_key[key].evidenced is False
        assert by_key[key].rationale == "Not evidenced in the current corpus."
        assert by_key[key].evidence == []

    assert by_key["yield_curve"].status == "Triggered"
    assert by_key["yield_curve"].evidenced is True
    assert by_key["yield_curve"].evidence[0].source_url == "real-url"
    assert report.triggered == 1 and report.watch == 0


def test_unknown_status_falls_back_to_clear(monkeypatch):
    monkeypatch.setattr(macro_mod, "converse_structured", lambda *a, **k: _out(
        _LLMSignpost(key="policy", status="ON FIRE",
                     evidence=[_LLMEvidence(quote="QT continues", source_index=0)]),
        # Casing from the model is normalised rather than rejected.
        _LLMSignpost(key="growth", status="triggered",
                     evidence=[_LLMEvidence(quote="ISM 46", source_index=0)]),
    ))
    report = run_macro_analyst([_item()])
    by_key = {s.key: s for s in report.signposts}
    assert by_key["policy"].status == "Clear"
    assert by_key["growth"].status == "Triggered"


def test_composite_score_and_label_bands(monkeypatch):
    def graded(n_triggered: int, n_watch: int):
        keys = [k for k, _n, _t in BEAR_SIGNPOSTS]
        rows = [
            _LLMSignpost(key=k, status="Triggered",
                         evidence=[_LLMEvidence(quote="q", source_index=0)])
            for k in keys[:n_triggered]
        ] + [
            _LLMSignpost(key=k, status="Watch",
                         evidence=[_LLMEvidence(quote="q", source_index=0)])
            for k in keys[n_triggered:n_triggered + n_watch]
        ]
        return _out(*rows)

    # 10 signposts: 6 triggered → 0.60 → elevated.
    monkeypatch.setattr(macro_mod, "converse_structured", lambda *a, **k: graded(6, 0))
    hot = run_macro_analyst([_item()])
    assert hot.triggered == 6 and hot.risk_score == 0.6
    assert hot.label == "LATE CYCLE · ELEVATED"

    # 2 triggered + 2 watch → (2 + 1) / 10 = 0.30 → watch.
    monkeypatch.setattr(macro_mod, "converse_structured", lambda *a, **k: graded(2, 2))
    mid = run_macro_analyst([_item()])
    assert mid.risk_score == 0.3 and mid.label == "MID CYCLE · WATCH"

    # Nothing lit → contained.
    monkeypatch.setattr(macro_mod, "converse_structured", lambda *a, **k: graded(0, 0))
    calm = run_macro_analyst([_item()])
    assert calm.risk_score == 0.0 and calm.label == "CYCLE RISK CONTAINED"


def test_reasoning_failure_returns_a_complete_unevidenced_tracker(monkeypatch):
    def boom(*_a, **_k):
        raise ReasoningError("timeout", kind="timeout")

    monkeypatch.setattr(macro_mod, "converse_structured", boom)
    report = run_macro_analyst([_item()])
    assert len(report.signposts) == len(BEAR_SIGNPOSTS)
    assert all(s.status == "Clear" and not s.evidenced for s in report.signposts)
    assert report.risk_score == 0.0
    assert "unavailable" in report.summary


def test_empty_macro_corpus_skips_the_llm():
    # No monkeypatch → a real LLM call would fail; an empty corpus must short-circuit.
    report = run_macro_analyst([])
    assert len(report.signposts) == len(BEAR_SIGNPOSTS)
    assert all(not s.evidenced for s in report.signposts)
    assert "ungraded, not clear" in report.summary


def test_checklist_prompt_lists_every_signpost():
    text = macro_mod.checklist_prompt()
    for key, name, _trigger in BEAR_SIGNPOSTS:
        assert key in text and name in text


def _capture_system(monkeypatch, out: _MacroOutput) -> list[str]:
    """Record the system prompt each mocked reasoning call is handed."""
    seen: list[str] = []

    def fake(_schema, system, _user, *a, **k):
        seen.append(system)
        return out

    monkeypatch.setattr(macro_mod, "converse_structured", fake)
    return seen


def test_checklist_reaches_the_model_even_if_the_prompt_drops_the_placeholder(monkeypatch):
    # An Agent Console edit that loses `{signposts}` fills to a no-op, so without the
    # safety net the desk would be asked to grade a checklist it was never shown.
    monkeypatch.setattr(
        macro_mod, "get_prompt",
        lambda _key, **_v: "You are the Macro Analyst. Grade the fixed checklist.",
    )
    seen = _capture_system(monkeypatch, _out(summary="s"))
    run_macro_analyst([_item()])

    assert len(seen) == 1
    for key, name, _trigger in BEAR_SIGNPOSTS:
        assert key in seen[0] and name in seen[0]


def test_a_prompt_that_keeps_the_placeholder_is_not_appended_to(monkeypatch):
    seen = _capture_system(monkeypatch, _out(summary="s"))
    run_macro_analyst([_item()])

    assert len(seen) == 1
    # The checklist is present exactly once — the fill worked, so nothing was re-appended.
    assert seen[0].count(macro_mod.checklist_prompt()) == 1


def test_display_names_and_cosmetic_variants_resolve_to_the_right_row(monkeypatch):
    # Same rows, spelled the way a re-worded prompt tends to get them back.
    monkeypatch.setattr(macro_mod, "converse_structured", lambda *a, **k: _out(
        _LLMSignpost(key="Labour Market", status="Triggered",
                     evidence=[_LLMEvidence(quote="layoffs broadening", source_index=0)]),
        _LLMSignpost(key="Yield-Curve", status="Watch",
                     evidence=[_LLMEvidence(quote="inverted", source_index=0)]),
        _LLMSignpost(key="CREDIT_SPREADS", status="Triggered",
                     evidence=[_LLMEvidence(quote="spreads widening", source_index=0)]),
    ))
    report = run_macro_analyst([_item()])
    by_key = {s.key: s for s in report.signposts}

    assert by_key["unemployment"].status == "Triggered"
    assert by_key["yield_curve"].status == "Watch"
    assert by_key["credit_spreads"].status == "Triggered"
    assert report.triggered == 2 and report.watch == 1


def test_an_invented_row_name_still_matches_nothing_and_is_logged(monkeypatch, caplog):
    monkeypatch.setattr(macro_mod, "converse_structured", lambda *a, **k: _out(
        _LLMSignpost(key="AI Capex Digestion", status="Triggered",
                     evidence=[_LLMEvidence(quote="capex rolling over", source_index=0)]),
    ))
    with caplog.at_level("WARNING"):
        report = run_macro_analyst([_item()])

    assert all(s.status == "Clear" and not s.evidenced for s in report.signposts)
    assert all(s.rationale == "Not returned by the analyst." for s in report.signposts)
    assert "AI Capex Digestion" in caplog.text


# --- Second pass: backfilling the rows the corpus left ungraded ------------------------


def _hit(url="https://fred.example/2s10s", text="the 2s10s spread re-steepened to +18bp in May"):
    """A web result the second pass would fetch for a gap."""
    return SourceItem(source_type=SourceType.WEB, title="curve watch", url=url, text=text)


def _graded(report, key):
    return {s.key: s for s in report.signposts}[key]


@pytest.fixture
def backfill_on(monkeypatch):
    """Small, deterministic caps so a test's expectations are about behaviour, not budget."""
    monkeypatch.setattr(settings, "macro_backfill_enabled", True)
    monkeypatch.setattr(settings, "macro_backfill_max_gaps", 6)
    monkeypatch.setattr(settings, "macro_backfill_results_per_gap", 2)
    monkeypatch.setattr(settings, "macro_backfill_max_items", 12)


def _searches(monkeypatch, *hits, error: Exception | None = None) -> list[str]:
    """Record every query the second pass runs; answer each with `hits` (or raise)."""
    seen: list[str] = []

    def fake(query, max_results=None, emit=None, **kwargs):
        seen.append(query)
        if error is not None:
            raise error
        return list(hits)

    monkeypatch.setattr(macro_mod.exa_source, "search", fake)
    return seen


def _pass_one(monkeypatch, *signposts: _LLMSignpost):
    """A first-pass report: `signposts` are graded, everything else is left ungraded."""
    monkeypatch.setattr(macro_mod, "converse_structured", lambda *a, **k: _out(
        *signposts, summary="Pass one summary."
    ))
    return run_macro_analyst([_item()])


def test_second_pass_grades_a_gap_from_fetched_material(monkeypatch, backfill_on):
    report = _pass_one(monkeypatch, _LLMSignpost(
        key="unemployment", status="Watch", rationale="layoffs broadening",
        evidence=[_LLMEvidence(quote="layoffs", source_index=0)],
    ))
    assert not _graded(report, "yield_curve").evidenced

    queries = _searches(monkeypatch, _hit())
    monkeypatch.setattr(macro_mod, "converse_structured", lambda *a, **k: _out(
        _LLMSignpost(key="yield_curve", status="Triggered", rationale="re-steepening",
                     evidence=[_LLMEvidence(quote="re-steepened to +18bp", source_index=0)]),
        summary="ignored",
    ))
    merged, fetched = macro_mod.backfill_signposts(report, [_item()])

    # One query per gap, built from the checklist entry itself.
    assert len(queries) == settings.macro_backfill_max_gaps
    assert any(q.startswith("Yield Curve latest data:") for q in queries)

    row = _graded(merged, "yield_curve")
    assert row.status == "Triggered" and row.evidenced and row.backfilled
    assert row.evidence[0].source_url == "https://fred.example/2s10s"
    # The tracker is re-tallied over the merged rows, and the fetched doc is handed back
    # for the run's source manifest.
    assert merged.triggered == 1 and merged.watch == 1
    assert merged.risk_score == pytest.approx(1.5 / len(BEAR_SIGNPOSTS))
    assert [it.source_url for it in fetched] == ["https://fred.example/2s10s"]
    assert fetched[0].stream is Stream.MACRO
    # Pass one's summary survives; the addendum is ours, not the model's.
    assert merged.summary.startswith("Pass one summary.")
    assert "Second pass: 1 signpost(s) graded from 1 externally fetched source(s)." in merged.summary


def test_a_row_graded_in_the_first_pass_is_never_reopened(monkeypatch, backfill_on):
    report = _pass_one(monkeypatch, _LLMSignpost(
        key="yield_curve", status="Watch", rationale="inverted",
        evidence=[_LLMEvidence(quote="inverted", source_index=0)],
    ))
    queries = _searches(monkeypatch, _hit())
    # The second pass answers for a row it was not asked about.
    monkeypatch.setattr(macro_mod, "converse_structured", lambda *a, **k: _out(
        _LLMSignpost(key="yield_curve", status="Triggered", rationale="louder",
                     evidence=[_LLMEvidence(quote="re-steepened", source_index=0)]),
        summary="ignored",
    ))
    merged, _fetched = macro_mod.backfill_signposts(report, [])

    assert all(not q.startswith("Yield Curve") for q in queries)
    row = _graded(merged, "yield_curve")
    assert row.status == "Watch" and row.rationale == "inverted" and not row.backfilled


def test_an_ungrounded_second_pass_alarm_leaves_the_first_pass_row_alone(monkeypatch, backfill_on):
    report = _pass_one(monkeypatch)
    before = _graded(report, "yield_curve")
    _searches(monkeypatch, _hit())
    monkeypatch.setattr(macro_mod, "converse_structured", lambda *a, **k: _out(
        # Cites an excerpt that does not exist → nothing survives grounding.
        _LLMSignpost(key="yield_curve", status="Triggered", rationale="invented",
                     evidence=[_LLMEvidence(quote="made up", source_index=42)]),
        summary="ignored",
    ))
    merged, _fetched = macro_mod.backfill_signposts(report, [])

    row = _graded(merged, "yield_curve")
    assert row.status == "Clear" and not row.evidenced and not row.backfilled
    # The gap keeps pass one's row verbatim, rather than being overwritten by a second
    # empty one — an alarm the fetched material cannot back is not an alarm.
    assert row is before
    assert merged.risk_score == 0.0
    assert "Second pass" not in merged.summary


def test_no_exa_key_leaves_the_tracker_untouched_and_skips_the_llm(monkeypatch, backfill_on):
    report = _pass_one(monkeypatch)
    _searches(monkeypatch, error=SourceUnavailable("EXA_API_KEY not set"))

    def boom(*_a, **_k):
        raise AssertionError("the second pass must not reason with nothing to reason over")

    monkeypatch.setattr(macro_mod, "converse_structured", boom)
    merged, fetched = macro_mod.backfill_signposts(report, [])
    assert merged is report and fetched == []


def test_an_empty_hit_is_dropped_rather_than_cited(monkeypatch, backfill_on):
    report = _pass_one(monkeypatch)
    _searches(monkeypatch, _hit(text="   "))
    monkeypatch.setattr(macro_mod, "converse_structured",
                        lambda *a, **k: pytest.fail("nothing usable was fetched"))
    merged, fetched = macro_mod.backfill_signposts(report, [])
    assert merged is report and fetched == []


def test_a_hit_already_in_the_corpus_is_not_fetched_twice(monkeypatch, backfill_on):
    report = _pass_one(monkeypatch)
    _searches(monkeypatch, _hit(url="already-known"))
    monkeypatch.setattr(macro_mod, "converse_structured",
                        lambda *a, **k: pytest.fail("every hit was already in the corpus"))
    merged, fetched = macro_mod.backfill_signposts(report, [_item(url="already-known")])
    assert merged is report and fetched == []


def test_the_fetch_is_capped_by_gaps_and_by_items(monkeypatch, backfill_on):
    monkeypatch.setattr(settings, "macro_backfill_max_gaps", 3)
    monkeypatch.setattr(settings, "macro_backfill_max_items", 4)
    report = _pass_one(monkeypatch)   # every row is a gap
    queries: list[str] = []

    def fake(query, max_results=None, emit=None, **kwargs):
        queries.append(query)
        return [_hit(url=f"{len(queries)}-{n}") for n in range(3)]

    monkeypatch.setattr(macro_mod.exa_source, "search", fake)
    monkeypatch.setattr(macro_mod, "converse_structured",
                        lambda *a, **k: _out(summary="ignored"))
    _merged, fetched = macro_mod.backfill_signposts(report, [])

    assert len(queries) == 3                       # gaps capped, in checklist order
    assert queries[0].startswith("Yield Curve")
    assert len(fetched) == 4                       # 3 gaps x 3 hits, capped at 4 items


def test_reasoning_failure_returns_the_first_pass_report_and_the_documents_read(
    monkeypatch, backfill_on
):
    report = _pass_one(monkeypatch)
    _searches(monkeypatch, _hit())

    def boom(*_a, **_k):
        raise ReasoningError("timeout", kind="timeout")

    monkeypatch.setattr(macro_mod, "converse_structured", boom)
    merged, fetched = macro_mod.backfill_signposts(report, [])
    # Read but uncited: the manifest still records what the pass looked at.
    assert merged is report and len(fetched) == 1


def test_the_second_pass_can_be_switched_off(monkeypatch, backfill_on):
    monkeypatch.setattr(settings, "macro_backfill_enabled", False)
    report = _pass_one(monkeypatch)
    queries = _searches(monkeypatch, _hit())
    merged, fetched = macro_mod.backfill_signposts(report, [])
    assert queries == [] and merged is report and fetched == []


def test_the_backfill_prompt_carries_only_the_ungraded_rows(monkeypatch, backfill_on):
    report = _pass_one(monkeypatch, _LLMSignpost(
        key="yield_curve", status="Watch",
        evidence=[_LLMEvidence(quote="inverted", source_index=0)],
    ))
    _searches(monkeypatch, _hit())
    seen = _capture_system(monkeypatch, _out(summary="ignored"))
    macro_mod.backfill_signposts(report, [])

    assert len(seen) == 1
    # The row pass one settled is off the table; the gaps it is asked about are on it.
    assert "yield_curve" not in seen[0]
    assert "credit_spreads" in seen[0] and "Credit Spreads" in seen[0]
