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
    _LLMStock,
    analyze_desk,
    route_to_desks,
)
from app.council import grounding
from app.council.grounding import LLMEvidence as _LLMEvidence
from app.council.chairman import (
    _ChairmanOutput,
    _LLMAce,
    _LLMBriefing,
    _LLMIndicator,
    _LLMPrediction,
    run_chairman,
)
from app.models import (
    BearSignpostReport,
    BriefingItem,
    CleanedItem,
    CouncilReport,
    Evidence,
    MacroIndicator,
    SectorNote,
    Signpost,
    SourceRef,
    SourceType,
    StockTake,
    Stream,
    ThemeRead,
    TranscriptSegment,
)


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
    assert record.round == 6 and record.rounds == 6
    assert [t.who for t in record.transcript] == ["bull", "bear"] * 3
    assert [t.round for t in record.transcript] == [f"R{i}" for i in range(1, 7)]
    # Bull and Bear alternate on two different model ids across all six rounds.
    assert used_models[0::2] == [used_models[0]] * 3
    assert used_models[1::2] == [used_models[1]] * 3
    assert used_models[0] != used_models[1]


# --- Tier 4b: the single-ticker chamber --------------------------------------


def _ticker_debate_env(monkeypatch, items, *, verdict="hold half", evidence=None, snapshot=None):
    """Wire the ticker chamber up to fakes and return the list of saved runs."""
    from app.council import ticker_debate as td

    saved: list = []
    monkeypatch.setattr(td, "list_cleaned_items", lambda **k: items)
    monkeypatch.setattr(td, "get_latest_council_snapshot", lambda: snapshot)
    monkeypatch.setattr(td, "save_ticker_debate_run", lambda r: (saved.append(r), r)[1])

    def fake_rounds(schema, system, user, *, model_id=None, **k):
        if "Bull" in system:
            return schema(stance="long", argument="buy it")
        return schema(stance="short", rebuttal="sell it")

    monkeypatch.setattr(debate_mod, "converse_structured", fake_rounds)
    monkeypatch.setattr(
        td, "converse_structured",
        lambda schema, system, user, **k: schema(verdict=verdict, evidence=evidence or []),
    )
    return td, saved


def test_ticker_debate_argues_only_its_own_corpus(monkeypatch):
    """The whole point of the single-emiten chamber: it reads the ticker's items, not all."""
    seen: dict = {}
    td, saved = _ticker_debate_env(monkeypatch, [])
    monkeypatch.setattr(td, "list_cleaned_items",
                        lambda **k: (seen.update(k), [_item(url="a", text="micron demand")])[1])

    run = td.run_ticker_debate("mu")

    assert seen["ticker"] == "$MU"           # bare input canonicalised for the entity filter
    assert run.ticker == "$MU"
    assert run.source_count == 1
    assert saved == [run]                    # persisted whole, exactly once


def test_ticker_debate_closes_with_a_winston_verdict(monkeypatch):
    td, _ = _ticker_debate_env(monkeypatch, [_item(url="a")], verdict="half position")

    run = td.run_ticker_debate("$NVDA")
    record = run.debate

    # Six alternating Freddy rounds, then Winston — the same shape the council-wide
    # chamber produces, so the card and the transcript modal need no special case.
    assert [t.who for t in record.transcript] == ["bull", "bear"] * 3 + ["winston"]
    assert record.transcript[-1].round == "Verdict"
    assert record.verdict == "half position"
    assert record.topic == "$NVDA · Bull vs Bear"


def test_ticker_debate_uses_the_desks_standing_call_as_context(monkeypatch):
    """The desks already formed a view on this name; the chamber must not ignore it."""
    from app.models import CouncilReport, SectorNote, StockTake

    snapshot = CouncilReport(sector_notes=[SectorNote(
        desk="TMT", summary="chips",
        stocks=[StockTake(ticker="$NVDA", conviction=0.7, horizon="6M", rationale="demand"),
                StockTake(ticker="$AAPL", conviction=-0.1, horizon="3M")],
    )])
    briefs: list[str] = []
    td, _ = _ticker_debate_env(monkeypatch, [_item(url="a")], snapshot=snapshot)
    monkeypatch.setattr(
        debate_mod, "converse_structured",
        lambda schema, system, user, **k: (
            briefs.append(user),
            schema(stance="s", argument="a") if "Bull" in system else schema(stance="s", rebuttal="r"),
        )[1],
    )

    td.run_ticker_debate("NVDA")

    assert "Desk TMT: conviction +0.70 (6M) — demand" in briefs[0]
    assert "$AAPL" not in briefs[0]          # one name only; no drift into the desk's others


def test_ticker_debate_with_no_matching_sources_persists_an_empty_run(monkeypatch):
    """A ticker nothing mentions must read as 'ran, found nothing', not as a 500."""
    td, saved = _ticker_debate_env(monkeypatch, [])

    run = td.run_ticker_debate("ZZZZ")

    assert saved == [run]                    # the empty run is still recorded, and dated
    assert run.ticker == "$ZZZZ"
    assert run.source_count == 0
    assert run.debate.transcript == [] and run.debate.verdict == ""


def test_ticker_verdict_citing_a_bogus_index_is_shown_unsourced(monkeypatch):
    """An index the model invented must not become a URL (no-orphan guardrail §12.6)."""
    td, _ = _ticker_debate_env(
        monkeypatch, [_item(url="real")],
        evidence=[_LLMEvidence(quote="q", source_index=0),
                  _LLMEvidence(quote="made up", source_index=99)],
    )

    run = td.run_ticker_debate("NVDA")

    assert [e.source_url for e in run.verdict_evidence] == ["real"]
    assert run.debate.verdict            # the ruling survives, just partly un-anchored
    assert run.sources[0].cited_by == ["Winston"]


def test_ticker_debate_survives_a_failed_verdict(monkeypatch):
    """The transcript is already paid for; losing it because the ruling failed is worse."""
    from app.council import ticker_debate as td_mod
    from app.llm import ReasoningError

    td, saved = _ticker_debate_env(monkeypatch, [_item(url="a")])

    def boom(*_a, **_k):
        raise ReasoningError("no", kind="schema_validation")

    monkeypatch.setattr(td_mod, "converse_structured", boom)

    run = td.run_ticker_debate("NVDA")

    assert len(run.debate.transcript) == 6      # six Freddy rounds kept
    assert run.debate.verdict == ""
    assert saved == [run]


# --- Tier 5: Winston ---------------------------------------------------------

def test_chairman_builds_dashboard(monkeypatch):
    out = _ChairmanOutput(
        verdict="half position in MU",
        indicators=[_LLMIndicator(name="Rates", score=1.5, band="Positive")],  # clamp
        ace=_LLMAce(value=0.34, label="CAPITAL ABUNDANT"),
    )
    monkeypatch.setattr(chairman_mod, "converse_structured", lambda *a, **k: out)
    verdict = run_chairman([], None, [])
    assert verdict.verdict == "half position in MU"
    assert verdict.indicators[0].score == 1.0         # clamped to [-1, 1]
    assert verdict.ace.value == 0.34
    # Thematic baskets moved to their own weekly run; the Chairman no longer emits them.
    assert not hasattr(verdict, "baskets")


def test_chairman_grounds_every_claim_kind(monkeypatch):
    """Winston's indicators/briefing/predictions all resolve to real URLs."""
    macro = [_item(url="macro-url", stream=Stream.MACRO, text="the fed is on hold")]
    out = _ChairmanOutput(
        indicators=[_LLMIndicator(name="Rates", score=0.3, band="Positive", rationale="steady",
                                  evidence=[_LLMEvidence(quote="on hold", source_index=0)])],
        briefing=[_LLMBriefing(tone="up", text="Fed steady",
                               evidence=[_LLMEvidence(quote="on hold", source_index=0)])],
        predictions=[_LLMPrediction(claim="no cut", resolve="01 SEP",
                                    evidence=[_LLMEvidence(quote="on hold", source_index=0)])],
    )
    monkeypatch.setattr(chairman_mod, "converse_structured", lambda *a, **k: out)
    v = run_chairman([], None, macro)
    for claim in (v.indicators[0], v.briefing[0], v.predictions[0]):
        assert [e.source_url for e in claim.evidence] == ["macro-url"]
    assert v.indicators[0].rationale == "steady"


def test_chairman_keeps_claims_whose_citation_does_not_resolve(monkeypatch):
    """Unlike a desk's stock take, an ungrounded chairman claim survives un-anchored.

    A conviction with no source is worthless, but a briefing line still carries meaning —
    so it is kept and shown as unsourced rather than silently deleted.
    """
    macro = [_item(url="macro-url", stream=Stream.MACRO)]
    out = _ChairmanOutput(
        indicators=[_LLMIndicator(name="Rates", score=0.3,
                                  evidence=[_LLMEvidence(quote="fake", source_index=99)])],
        briefing=[_LLMBriefing(tone="up", text="Fed steady",
                               evidence=[_LLMEvidence(quote="fake", source_index=99)])],
    )
    monkeypatch.setattr(chairman_mod, "converse_structured", lambda *a, **k: out)
    v = run_chairman([], None, macro)
    assert len(v.indicators) == 1 and v.indicators[0].evidence == []
    assert len(v.briefing) == 1 and v.briefing[0].evidence == []


def test_citable_corpus_includes_desk_cited_micro_sources():
    """Winston rules on the debate, so he must be able to cite the desks' own sources."""
    macro = [_item(url="macro-url", stream=Stream.MACRO)]
    micro = [_item(url="micro-cited"), _item(url="micro-unused")]
    notes = [SectorNote(desk="TMT", stocks=[
        StockTake(ticker="$NVDA", conviction=0.5, horizon="6M",
                  evidence=[Evidence(quote="q", source_url="micro-cited")]),
    ])]
    corpus = chairman_mod.citable_corpus(macro, notes, micro)
    assert [it.source_url for it in corpus] == ["macro-url", "micro-cited"]


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
        BearSignpostReport, BriefingItem, DebateRecord, DebateSideMeta, SectorNote,
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

    def fake_macro(macro, emit=None):
        calls.append("macro")
        assert all(i.stream == Stream.MACRO for i in macro)  # macro bypass routes MACRO here
        return BearSignpostReport(total=10, triggered=2, label="MID CYCLE · WATCH")

    def fake_chairman(notes, debate, macro, emit=None, macro_report=None, micro_items=None):
        calls.append("chairman")
        assert all(i.stream == Stream.MACRO for i in macro)  # macro bypass routes MACRO here
        assert macro_report is not None and macro_report.triggered == 2  # tracker handed up
        # Winston needs the desks' micro sources too, or he could never cite anything.
        assert micro_items is not None and all(i.stream == Stream.MICRO for i in micro_items)
        return ChairmanVerdict(verdict="ruling", briefing=[BriefingItem(tone="up", text="y")])

    monkeypatch.setattr(orch, "run_analysts", fake_analysts)
    monkeypatch.setattr(orch, "run_debate", fake_debate)
    def fake_backfill(report, corpus, emit=None):
        calls.append("backfill")
        # The second pass is stubbed here so this test stays about the DAG; its own
        # behaviour is covered in tests/test_macro.py.
        return report, []

    def fake_theme_reads(items, notes=None, emit=None):
        calls.append("themes")
        # Themes are tagged on MICRO items, so unlike the Chairman this call sees the
        # whole corpus, not the macro bypass slice.
        assert {i.stream for i in items} == {Stream.MICRO, Stream.MACRO}
        return [ThemeRead(theme="Technology", stance="Bullish", rationale="r", evidenced=True)]

    monkeypatch.setattr(orch, "run_macro_analyst", fake_macro)
    monkeypatch.setattr(orch, "backfill_signposts", fake_backfill)
    monkeypatch.setattr(orch, "run_chairman", fake_chairman)
    monkeypatch.setattr(orch, "run_theme_reads", fake_theme_reads)

    report = orch.run_council()
    # Strict DAG order — the second pass sits between the desk and the Chairman, so
    # Winston rules on a tracker that has already been backfilled.
    assert calls == ["analysts", "debate", "macro", "backfill", "chairman", "themes", "saved"]
    assert report.theme_reads[0].stance == "Bullish"
    assert report.macro.triggered == 2                           # tracker persisted
    assert report.debate.verdict == "ruling"
    assert report.debate.transcript[-1].who == "winston"         # verdict stitched in
    assert report.briefing[0].text == "y"
    assert not report.baskets      # thematic baskets are a separate weekly run now
    assert report.source_count == 2


def test_backfilled_documents_reach_winston_and_the_manifest(monkeypatch):
    """The second pass's sources are run-scoped, so the DAG has to carry them by hand."""
    from app.models import (
        BearSignpostReport, DebateRecord, DebateSideMeta, SectorNote, Signpost,
    )
    from app.council.chairman import ChairmanVerdict

    external = _item(url="fetched-by-the-second-pass", stream=Stream.MACRO)
    monkeypatch.setattr(orch, "list_cleaned_items",
                        lambda **k: [_item(stream=Stream.MICRO), _item(url="m", stream=Stream.MACRO)])
    monkeypatch.setattr(orch, "save_council_snapshot", lambda r: None)
    monkeypatch.setattr(orch, "run_analysts", lambda micro, emit=None: [SectorNote(desk="TMT")])
    monkeypatch.setattr(orch, "run_debate", lambda notes, emit=None: DebateRecord(
        bull=DebateSideMeta(name="b", model="m"), bear=DebateSideMeta(name="r", model="n")))
    monkeypatch.setattr(orch, "run_macro_analyst",
                        lambda macro, emit=None: BearSignpostReport(total=10))
    monkeypatch.setattr(orch, "backfill_signposts", lambda report, corpus, emit=None: (
        BearSignpostReport(total=10, triggered=1, signposts=[
            Signpost(key="yield_curve", name="Yield Curve", status="Triggered",
                     backfilled=True,
                     evidence=[Evidence(quote="q", source_url=external.source_url)]),
        ]),
        [external],
    ))

    seen: dict = {}

    def fake_chairman(notes, debate, macro, emit=None, macro_report=None, micro_items=None):
        seen["macro_urls"] = [i.source_url for i in macro]
        return ChairmanVerdict(verdict="ruling")

    monkeypatch.setattr(orch, "run_chairman", fake_chairman)
    monkeypatch.setattr(orch, "run_theme_reads", lambda items, notes=None, emit=None: [])
    report = orch.run_council()

    # Winston can cite what the second pass fetched...
    assert seen["macro_urls"] == ["m", "fetched-by-the-second-pass"]
    # ...and the run's audit trail says the document was read, and by whom.
    manifest = {s.url: s.cited_by for s in report.sources}
    assert manifest["fetched-by-the-second-pass"] == ["Macro Analyst"]
    assert report.source_count == 3


# --- Source manifest (§12.6 audit trail) -------------------------------------

def test_manifest_lists_every_document_and_who_cited_it():
    items = [_item(url="cited-by-desk"), _item(url="cited-by-winston"), _item(url="unused")]
    report = CouncilReport(
        sector_notes=[SectorNote(desk="TMT", stocks=[
            StockTake(ticker="$NVDA", conviction=0.5, horizon="6M",
                      evidence=[Evidence(quote="q", source_url="cited-by-desk")]),
        ])],
        briefing=[BriefingItem(tone="up", text="y",
                               evidence=[Evidence(quote="q", source_url="cited-by-winston")])],
        macro=BearSignpostReport(signposts=[
            Signpost(key="breadth", name="Breadth", status="Triggered",
                     evidence=[Evidence(quote="q", source_url="cited-by-desk")]),
        ]),
    )
    manifest = {s.url: s.cited_by for s in orch._build_manifest(items, report)}
    assert manifest["cited-by-desk"] == ["Andie-TMT", "Macro Analyst"]
    assert manifest["cited-by-winston"] == ["Winston"]
    # Read but never quoted — still listed, so "we looked and it didn't matter" is visible.
    assert manifest["unused"] == []


# --- Citation timestamps -----------------------------------------------------

def test_best_offset_finds_the_segment_the_quote_came_from():
    """A video citation must open at the quote, not at 0:00."""
    item = CleanedItem(
        source_url="https://www.youtube.com/watch?v=abc", source_type=SourceType.YOUTUBE,
        title="t", clean_text="body", stream=Stream.MACRO, industry="Unclassified",
        segments=[
            TranscriptSegment(start=0.0, text="hello and welcome to the show"),
            TranscriptSegment(start=142.5, text="continuing claims have been creeping higher"),
            TranscriptSegment(start=300.0, text="that is all for today"),
        ],
    )
    assert grounding.best_offset(item, "continuing claims have been creeping higher") == 142.5
    # Nothing overlaps → anchor at the top rather than dropping a verified quote.
    assert grounding.best_offset(item, "zzz qqq") == 0.0
    # Articles have no transcript, so there is no offset to give.
    assert grounding.best_offset(_item(url="a"), "anything") is None


# --- Stored-snapshot compatibility -------------------------------------------
#
# A whole CouncilReport is persisted as JSON (db/tables.py: council_snapshots.report) and
# read back through these models, so narrowing a field's type retroactively invalidates
# every saved run. That failure surfaces as an empty dashboard rather than an error, so it
# is asserted here instead of being left to review.

def test_legacy_snapshot_with_string_indicator_evidence_still_loads():
    """`MacroIndicator.evidence` used to be free text; old snapshots must still parse."""
    legacy = {
        "indicators": [
            {"name": "Rate Policy", "score": 0.5, "band": "Positive",
             "evidence": "dovish FOMC commentary"},
        ],
        # Written before these fields existed at all.
        "briefing": [{"tone": "up", "text": "Fed steady"}],
        # Written before the baskets moved to their own weekly run — the field is kept on
        # CouncilReport precisely so rows like this one still parse.
        "baskets": [{"name": "AI Buildout"}],
        "predictions": [{"claim": "no cut", "by": "Macro Lens", "resolve": "01 SEP"}],
        "source_count": 12,
    }
    report = CouncilReport.model_validate(legacy)
    # The old free-text evidence was really a rationale — keep the words, drop the claim
    # to a citation it never had.
    assert report.indicators[0].rationale == "dovish FOMC commentary"
    assert report.indicators[0].evidence == []
    # The rest of the snapshot must survive, not just the migrated field.
    assert report.briefing[0].text == "Fed steady"
    assert report.baskets[0].name == "AI Buildout"
    assert report.predictions[0].claim == "no cut"
    assert report.source_count == 12


def test_legacy_migration_does_not_clobber_an_explicit_rationale():
    report = CouncilReport.model_validate({
        "indicators": [{"name": "x", "score": 0.0, "band": "Neutral",
                        "rationale": "real rationale", "evidence": "legacy text"}],
    })
    assert report.indicators[0].rationale == "real rationale"
    assert report.indicators[0].evidence == []


def test_current_snapshot_round_trips():
    """Serialize → deserialize, the check that would have caught the regression."""
    report = CouncilReport(
        indicators=[MacroIndicator(name="Rates", score=0.3, band="Positive",
                                   rationale="steady",
                                   evidence=[Evidence(quote="q", source_url="u",
                                                      timestamp_start=142.5)])],
        sources=[SourceRef(url="u", title="t", source_type=SourceType.WEB,
                           stream=Stream.MACRO, cited_by=["Winston"])],
        source_count=1,
    )
    again = CouncilReport.model_validate(report.model_dump(mode="json"))
    assert again.indicators[0].evidence[0].timestamp_start == 142.5
    assert again.indicators[0].rationale == "steady"
    assert again.sources[0].cited_by == ["Winston"]


def test_repository_serves_legacy_snapshot_and_degrades_on_unreadable(monkeypatch, caplog):
    """The read path itself, which is where the blank-dashboard regression actually landed."""
    import types
    from app.db import repository as repo

    def _session_returning(row):
        class _Res:
            def scalars(self):
                return types.SimpleNamespace(first=lambda: row)
        return types.SimpleNamespace(execute=lambda stmt: _Res(), close=lambda: None)

    legacy = types.SimpleNamespace(
        generated_at="2026-07-20T00:00:00Z",
        report={
            "indicators": [{"name": "Rate Policy", "score": 0.5, "band": "Positive",
                            "evidence": "dovish FOMC commentary"}],
            "debate": {"topic": "t", "round": 1, "rounds": 6,
                       "bull": {"name": "Freddy-Bull", "model": "m"},
                       "bear": {"name": "Freddy-Bear", "model": "n"},
                       "transcript": [{"who": "bull", "round": "R1", "label": "Bull", "text": "buy"}]},
            "source_count": 42,
        },
    )
    monkeypatch.setattr(repo, "get_session", lambda: _session_returning(legacy))
    snap = repo.get_latest_council_snapshot()
    # The whole report must come back, not just the migrated field — a 500 here blanked
    # debate, baskets, briefing and the ledger all at once.
    assert snap is not None
    assert len(snap.debate.transcript) == 1
    assert snap.indicators[0].rationale == "dovish FOMC commentary"
    assert snap.source_count == 42

    # A snapshot no migration can rescue degrades to "no snapshot" with a logged reason,
    # rather than a 500 the frontend turns into an identical, unexplained blank.
    junk = types.SimpleNamespace(
        generated_at="2026-07-21T00:00:00Z",
        report={"indicators": [{"name": "x", "score": "not-a-number", "band": "Positive"}]},
    )
    monkeypatch.setattr(repo, "get_session", lambda: _session_returning(junk))
    with caplog.at_level("ERROR"):
        assert repo.get_latest_council_snapshot() is None
    assert "does not match the current models" in caplog.text


def test_indicator_history_series_is_chronological_and_skips_junk(monkeypatch):
    """The trend the indicator cards chart: oldest first, unusable readings dropped."""
    import types
    from app.db import repository as repo

    # As the query returns them: newest first, (report, generated_at) pairs.
    rows = [
        ({"indicators": [{"name": "Rate Policy", "score": 0.5, "band": "Positive"},
                         {"name": "Growth", "score": -0.2, "band": "Negative"}]},
         "2026-09-03T03:00:00Z"),
        # A run where Winston did not score Growth — a gap in that line, not a zero.
        ({"indicators": [{"name": "Rate Policy", "score": 0.1, "band": "Neutral"}]},
         "2026-09-02T03:00:00Z"),
        # Unusable: a non-numeric score and a nameless row leave nothing to plot, and a
        # report whose *other* fields have drifted must still yield its scores.
        ({"indicators": [{"name": "Rate Policy", "score": "n/a"}, {"score": 0.4}],
          "debate": "shape drift elsewhere"},
         "2026-09-01T03:00:00Z"),
    ]
    monkeypatch.setattr(
        repo, "get_session",
        lambda: types.SimpleNamespace(execute=lambda stmt: types.SimpleNamespace(all=lambda: rows),
                                      close=lambda: None),
    )

    points = repo.get_indicator_history()
    assert [p.generated_at.day for p in points] == [2, 3]
    assert points[0].scores == {"Rate Policy": 0.1}
    assert points[1].scores == {"Rate Policy": 0.5, "Growth": -0.2}
