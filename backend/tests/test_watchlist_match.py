"""Watchlist moment matching — the gate, the judge, and the anti-fabrication fallbacks.

The load-bearing property is the *gate*: a video that mentions nothing tracked must cost
zero LLM calls, because a channel poll runs over every new video whether or not it is
relevant.
"""
from __future__ import annotations

import pytest

from app.db.repository import WatchlistOverride
from app.insights import watchlist_match as wm
from app.llm import ReasoningError
from app.models import CleanedItem, ResolvedEntity, SourceType, Stream, TranscriptSegment


def _item(*, entities: list[str], segments: list[tuple[float, str]] | None = None) -> CleanedItem:
    # `is None` rather than `or`: an explicitly empty list means "no transcript".
    segs = (
        [
            (10.0, "the setup here is broadly constructive"),
            (25.5, "nvidia is power constrained, not demand constrained"),
            (40.0, "and that is the whole story for now"),
        ]
        if segments is None
        else segments
    )
    return CleanedItem(
        source_url="https://www.youtube.com/watch?v=vid1",
        source_type=SourceType.YOUTUBE,
        title="The bottleneck",
        clean_text=" ".join(t for _, t in segs),
        stream=Stream.MICRO,
        industry="Semiconductors",
        entities=[ResolvedEntity(canonical=e, mentions=[e]) for e in entities],
        segments=[TranscriptSegment(start=s, text=t) for s, t in segs],
        author="Silicon Signals",
    )


@pytest.fixture(autouse=True)
def _fine_chunks(monkeypatch):
    """Keep the fixture's short captions as separate chunks.

    Matching merges caption-sized segments into quotable chunks before judging; with the
    production 1000-char cap these three lines would collapse into one, which is correct
    behaviour but leaves nothing to index into. Merging itself is covered separately.
    """
    from app.config import settings
    monkeypatch.setattr(settings, "youtube_transcript_chunk_size", 45)


@pytest.fixture
def _no_overrides(monkeypatch):
    """Nothing paused or deleted — every resolved ticker is tracked by default."""
    monkeypatch.setattr(wm, "list_watchlist_overrides", lambda: [])


@pytest.fixture
def _judge(monkeypatch):
    """Record judge calls and return a scripted verdict."""
    calls: list[tuple[str, str]] = []
    box: dict = {"pick": wm._Pick(chunk_index=1, quote="nvidia is power constrained", relevance=0.9)}

    def fake(schema, system, user_content, **kw):
        calls.append((system, user_content))
        result = box["pick"]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(wm, "converse_structured", fake)
    monkeypatch.setattr(wm, "get_prompt", lambda key, **v: f"prompt:{key}")
    return calls, box


# --- stage 1: the free gate ---

def test_untracked_video_costs_no_llm_call(_no_overrides, _judge):
    calls, _ = _judge
    items = [_item(entities=["Federal_Reserve"])]   # macro entity, no "$" ticker
    assert wm.match_items_to_watchlist(items, channel_id="UCtest") == []
    assert calls == []


def test_paused_and_deleted_tickers_are_excluded(monkeypatch, _judge):
    monkeypatch.setattr(wm, "list_watchlist_overrides", lambda: [
        WatchlistOverride(ticker="NVDA", enabled=False, deleted=False),
        WatchlistOverride(ticker="MU", enabled=True, deleted=True),
    ])
    item = _item(entities=["$NVDA", "$MU", "$AAPL"])
    assert wm.matched_tickers(item) == ["$AAPL"]


def test_item_without_transcript_is_skipped(_no_overrides, _judge):
    calls, _ = _judge
    item = _item(entities=["$NVDA"], segments=[])
    assert wm.match_items_to_watchlist([item], channel_id="UCtest") == []
    assert calls == []


def test_duplicate_entities_are_matched_once(_no_overrides):
    item = _item(entities=["$NVDA", "$NVDA"])
    assert wm.matched_tickers(item) == ["$NVDA"]


# --- stage 2: the judge ---

def test_match_anchors_the_quote_to_a_real_timestamp(_no_overrides, _judge):
    matches = wm.match_items_to_watchlist([_item(entities=["$NVDA"])], channel_id="UCtest")
    assert len(matches) == 1
    m = matches[0]
    assert m.ticker == "$NVDA"
    assert m.quote == "nvidia is power constrained"
    # Resolved from the transcript by best_offset — the chunk the quote came from.
    assert m.timestamp_start == 25.5
    assert m.video_id == "vid1"
    assert m.channel_id == "UCtest"
    assert m.channel_name == "Silicon Signals"


def test_one_judge_call_per_matched_ticker(_no_overrides, _judge):
    calls, _ = _judge
    wm.match_items_to_watchlist([_item(entities=["$NVDA", "$AAPL"])], channel_id="UCtest")
    assert len(calls) == 2


def test_passing_mention_is_dropped_below_the_relevance_floor(_no_overrides, _judge):
    _, box = _judge
    box["pick"] = wm._Pick(chunk_index=1, quote="nvidia is power constrained", relevance=0.2)
    assert wm.match_items_to_watchlist([_item(entities=["$NVDA"])], channel_id="UCtest") == []


def test_relevance_is_clamped_to_one(_no_overrides, _judge):
    _, box = _judge
    box["pick"] = wm._Pick(chunk_index=1, quote="nvidia is power constrained", relevance=4.2)
    (match,) = wm.match_items_to_watchlist([_item(entities=["$NVDA"])], channel_id="UCtest")
    assert match.relevance == 1.0


# --- anti-fabrication ---

def test_invented_quote_falls_back_to_the_chunk_text(_no_overrides, _judge):
    _, box = _judge
    box["pick"] = wm._Pick(chunk_index=1, quote="nvidia will double next quarter", relevance=0.9)
    (match,) = wm.match_items_to_watchlist([_item(entities=["$NVDA"])], channel_id="UCtest")
    assert match.quote == "nvidia is power constrained, not demand constrained"


def test_out_of_range_index_falls_back_to_a_chunk_naming_the_ticker(_no_overrides, _judge):
    _, box = _judge
    box["pick"] = wm._Pick(chunk_index=99, quote="whatever", relevance=0.9)
    (match,) = wm.match_items_to_watchlist([_item(entities=["$NVDA"])], channel_id="UCtest")
    assert match.quote == "nvidia is power constrained, not demand constrained"


def test_llm_outage_degrades_to_a_deterministic_match(_no_overrides, _judge):
    _, box = _judge
    box["pick"] = ReasoningError("vertex down", kind="transient")
    (match,) = wm.match_items_to_watchlist([_item(entities=["$NVDA"])], channel_id="UCtest")
    assert match.relevance == 0.5
    assert "nvidia" in match.quote           # found by alias, not by the model
    assert match.timestamp_start == 25.5


def test_fallback_uses_the_first_chunk_when_no_alias_appears(_no_overrides, _judge):
    _, box = _judge
    box["pick"] = ReasoningError("vertex down", kind="transient")
    item = _item(entities=["$TSLA"], segments=[(3.0, "opening remarks"), (9.0, "closing remarks")])
    (match,) = wm.match_items_to_watchlist([item], channel_id="UCtest")
    # Both captions fit one chunk, which keeps the start of the first.
    assert match.quote == "opening remarks closing remarks"
    assert match.timestamp_start == 3.0


# --- prompt hints ---

def test_company_hint_lists_every_known_alias():
    assert wm._company_hint("$META") == "Facebook, Fb, Meta, Zuck"


def test_company_hint_falls_back_to_the_bare_symbol():
    assert wm._company_hint("$XYZ") == "XYZ"


# --- chunk assembly (merging at INGEST is what stripped every timestamp in prod) ---

def test_captions_are_merged_into_quotable_chunks(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "youtube_transcript_chunk_size", 40)
    item = _item(entities=["$NVDA"], segments=[
        (1.0, "aaaa"), (2.0, "bbbb"), (3.0, "cccc"),
    ])
    chunks = wm._chunks(item, "$NVDA")
    assert [(c.start, c.text) for c in chunks] == [(1.0, "aaaa bbbb cccc")]


def test_a_chunk_keeps_the_start_of_its_first_caption(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "youtube_transcript_chunk_size", 10)
    item = _item(entities=["$NVDA"], segments=[(5.0, "aaaa"), (6.0, "bbbb"), (99.0, "cccc")])
    chunks = wm._chunks(item, "$NVDA")
    assert [(c.start, c.text) for c in chunks] == [(5.0, "aaaa bbbb"), (99.0, "cccc")]


def test_chunks_naming_the_ticker_survive_the_prompt_budget(monkeypatch):
    """On a long broadcast the relevant minute is rarely in the first few chunks."""
    from app.config import settings
    monkeypatch.setattr(settings, "youtube_transcript_chunk_size", 10)
    monkeypatch.setattr(wm, "_MAX_CHUNKS", 2)
    segs = [(float(i), f"filler{i:02d}") for i in range(20)]
    segs.append((99.0, "nvidia beat"))
    item = _item(entities=["$NVDA"], segments=segs)

    chunks = wm._chunks(item, "$NVDA")

    assert len(chunks) == 2
    assert any("nvidia" in c.text for c in chunks)


def test_selected_chunks_stay_in_chronological_order(monkeypatch):
    """The judge reads the digest as a narrative; a shuffled transcript reads as a different one."""
    from app.config import settings
    monkeypatch.setattr(settings, "youtube_transcript_chunk_size", 10)
    monkeypatch.setattr(wm, "_MAX_CHUNKS", 3)
    item = _item(entities=["$NVDA"], segments=[
        (1.0, "aaaa"), (2.0, "bbbb"), (50.0, "nvidia up"),
    ])
    chunks = wm._chunks(item, "$NVDA")
    assert [c.start for c in chunks] == sorted(c.start for c in chunks)
