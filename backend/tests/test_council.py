"""Council (Tiers 3–5) tests — Andie routing/grounding, Freddy debate, Winston, DAG.

The LLM and the DB are mocked, so these run with no network or credentials, exactly
like the Layer-2 tests.
"""
from __future__ import annotations

from app.council import analyst as analyst_mod
from app.council import chairman as chairman_mod
from app.council import debate as debate_mod
from app.council import orchestrator as orch
from app.council.analyst import (
    MAX_STOCKS_PER_DESK,
    _AnalystOutput,
    _LLMEvidence,
    _LLMStock,
    analyze_desk,
    route_to_desks,
)
from app.council.chairman import _ChairmanOutput, _LLMAce, _LLMBasket, run_chairman
from app.models import CleanedItem, SourceType, Stream


def _item(url="u", industry="Technology", stream=Stream.MICRO, text="nvidia demand strong",
          tickers=("$NVDA",)):
    from app.models import ResolvedEntity
    return CleanedItem(
        source_url=url, source_type=SourceType.WEB, title="t", clean_text=text,
        stream=stream, industry=industry,
        entities=[ResolvedEntity(canonical=tk) for tk in tickers],
    )


# --- Tier 3: Andie desk routing ---------------------------------------------

def test_route_to_desks_groups_by_sector():
    items = [
        _item(url="a", industry="Technology"),
        _item(url="b", industry="Energy"),
        _item(url="c", industry="Financials"),
        _item(url="d", industry="Unclassified"),  # dropped (no desk)
    ]
    buckets = route_to_desks(items)
    assert [it.source_url for it in buckets["TMT"]] == ["a"]
    assert [it.source_url for it in buckets["Physical"]] == ["b"]
    assert [it.source_url for it in buckets["Capital"]] == ["c"]


def test_analyze_desk_grounds_evidence_and_drops_orphans(monkeypatch):
    items = [_item(url="real-url")]
    out = _AnalystOutput(
        summary="s",
        highlights=["h"],
        stocks=[
            _LLMStock(ticker="NVDA", conviction=2.0, horizon="6M",
                      evidence=[_LLMEvidence(quote="demand strong", source_index=0)]),
            _LLMStock(ticker="FAKE", conviction=0.5, horizon="6M",
                      evidence=[_LLMEvidence(quote="invented", source_index=99)]),  # bad index
        ],
    )
    monkeypatch.setattr(analyst_mod, "converse_structured", lambda *a, **k: out)
    note = analyze_desk("TMT", items)
    assert len(note.stocks) == 1                       # orphan dropped (no-orphan guardrail)
    assert note.stocks[0].ticker == "$NVDA"            # normalized to $-prefix
    assert note.stocks[0].conviction == 1.0            # clamped to [-1, 1]
    assert note.stocks[0].evidence[0].source_url == "real-url"


def test_analyze_desk_empty_items_skips_llm():
    # No monkeypatch → if it called the LLM it would error; empty desk must short-circuit.
    note = analyze_desk("TMT", [])
    assert note.desk == "TMT" and note.stocks == []


def test_analyst_caps_stocks_per_desk(monkeypatch):
    items = [_item(url="real-url")]
    out = _AnalystOutput(stocks=[
        _LLMStock(ticker=f"T{i}", conviction=0.5, horizon="6M",
                  evidence=[_LLMEvidence(quote="q", source_index=0)])
        for i in range(MAX_STOCKS_PER_DESK + 5)
    ])
    monkeypatch.setattr(analyst_mod, "converse_structured", lambda *a, **k: out)
    note = analyze_desk("TMT", items)
    assert len(note.stocks) == MAX_STOCKS_PER_DESK


# --- Tier 4: Freddy debate ---------------------------------------------------

def test_debate_uses_two_model_families(monkeypatch):
    used_models: list[str] = []

    def fake(schema, system, user, *, model_id=None, **k):
        used_models.append(model_id)
        if "Bull" in system:
            return schema(stance="long", argument="buy")
        return schema(stance="short", rebuttal="sell")

    monkeypatch.setattr(debate_mod, "converse_structured", fake)
    from app.models import SectorNote, StockTake
    notes = [SectorNote(desk="TMT", summary="s", stocks=[
        StockTake(ticker="$NVDA", conviction=0.8, horizon="6M")])]
    record = debate_mod.run_debate(notes)
    assert record.round == 3
    assert [t.who for t in record.transcript] == ["bull", "bear", "bull"]
    # Bull and Bear ran on different model ids (R1 bull, R2 bear, R3 bull).
    assert used_models[0] != used_models[1]
    assert used_models[0] == used_models[2]


# --- Tier 5: Winston ---------------------------------------------------------

def test_chairman_builds_dashboard(monkeypatch):
    out = _ChairmanOutput(
        verdict="half position in MU",
        baskets=[_LLMBasket(name="AI Buildout", stocks=["nvda"], conviction=1.5)],  # clamp
        ace=_LLMAce(value=0.34, label="CAPITAL ABUNDANT"),
    )
    monkeypatch.setattr(chairman_mod, "converse_structured", lambda *a, **k: out)
    verdict = run_chairman([], None, [])
    assert verdict.verdict == "half position in MU"
    assert verdict.baskets[0].conviction == 1.0       # clamped to [0, 1]
    assert verdict.baskets[0].stocks == ["NVDA"]      # upper-cased
    assert verdict.ace.value == 0.34


# --- DAG orchestration -------------------------------------------------------

def test_run_council_empty_corpus_saves_empty_snapshot(monkeypatch):
    saved = {}
    monkeypatch.setattr(orch, "list_cleaned_items", lambda **k: [])
    monkeypatch.setattr(orch, "save_council_snapshot", lambda r: saved.update(report=r))
    report = orch.run_council()
    assert report.source_count == 0
    assert saved["report"].source_count == 0


def test_run_council_runs_full_dag(monkeypatch):
    from app.models import (
        BriefingItem, DebateRecord, DebateSideMeta, SectorNote, ThemeBasket,
    )
    from app.council.chairman import ChairmanVerdict

    calls: list[str] = []
    monkeypatch.setattr(orch, "list_cleaned_items",
                        lambda **k: [_item(stream=Stream.MICRO), _item(url="m", stream=Stream.MACRO)])
    monkeypatch.setattr(orch, "save_council_snapshot", lambda r: calls.append("saved"))

    def fake_analysts(micro, emit=None):
        calls.append("analysts")
        assert all(i.stream == Stream.MICRO for i in micro)  # macro bypass: no MACRO here
        return [SectorNote(desk="TMT")]

    def fake_debate(notes, emit=None):
        calls.append("debate")
        return DebateRecord(bull=DebateSideMeta(name="b", model="m"),
                            bear=DebateSideMeta(name="r", model="n"))

    def fake_chairman(notes, debate, macro, emit=None):
        calls.append("chairman")
        assert all(i.stream == Stream.MACRO for i in macro)  # macro bypass routes MACRO here
        return ChairmanVerdict(verdict="ruling", baskets=[ThemeBasket(name="x")],
                               briefing=[BriefingItem(tone="up", text="y")])

    monkeypatch.setattr(orch, "run_analysts", fake_analysts)
    monkeypatch.setattr(orch, "run_debate", fake_debate)
    monkeypatch.setattr(orch, "run_chairman", fake_chairman)

    report = orch.run_council()
    assert calls == ["analysts", "debate", "chairman", "saved"]  # strict DAG order
    assert report.debate.verdict == "ruling"
    assert report.debate.transcript[-1].who == "winston"         # verdict stitched in
    assert report.baskets[0].name == "x"
    assert report.source_count == 2
