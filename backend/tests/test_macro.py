"""Macro Analyst — bear-market signpost tracker.

The LLM is mocked, so these run with no network or credentials, like the other
council tests.
"""
from __future__ import annotations

from app.council import macro as macro_mod
from app.council.grounding import LLMEvidence as _LLMEvidence
from app.council.macro import _LLMSignpost, _MacroOutput, run_macro_analyst
from app.llm import ReasoningError
from app.models import CleanedItem, SourceType, Stream
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
