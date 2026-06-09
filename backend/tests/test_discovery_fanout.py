"""Task 3 — fan-out / merge / dedupe / skip-with-reason tests. Requirements 3-6."""
from __future__ import annotations

import pytest

from app.discovery import agent
from app.discovery.agent import _dedupe, _safe_call, discover
from app.discovery.exa_source import SourceUnavailable
from app.models import SourceItem, SourceType


def _item(url: str, text: str = "some signal") -> SourceItem:
    return SourceItem(source_type=SourceType.WEB, title="t", url=url, text=text)


# --- dedupe (Req 4.2, 4.3, 4.1 order) ---

def test_dedupe_keeps_first_seen_and_preserves_order():
    items = [_item("a"), _item("b"), _item("a"), _item("c")]
    out = _dedupe(items)
    assert [i.url for i in out] == ["a", "b", "c"]


def test_dedupe_is_case_sensitive_exact_match():
    out = _dedupe([_item("http://X"), _item("http://x")])
    assert len(out) == 2  # different by case → both kept


# --- _safe_call (Req 5.1, 5.2) ---

def test_safe_call_converts_source_unavailable_to_reason():
    def boom(q, m):
        raise SourceUnavailable("KEY not set")
    items, error = _safe_call(boom, "q", None)
    assert items == []
    assert "KEY not set" in error


def test_safe_call_converts_arbitrary_exception_to_reason():
    def boom(q, m):
        raise RuntimeError("network down")
    items, error = _safe_call(boom, "q", None)
    assert items == []
    assert "network down" in error


# --- discover end-to-end with both branches skipped (Req 5.6) ---

def test_both_branches_skipped_returns_empty_items_and_two_skips(monkeypatch):
    def unavailable(q, m):
        raise SourceUnavailable("no key")
    monkeypatch.setattr(agent.exa_source, "search", unavailable)
    monkeypatch.setattr(agent.youtube_source, "search", unavailable)

    result = discover("AI memory demand")
    assert result.items == []
    assert len(result.skipped) == 2
    assert {s.source_type for s in result.skipped} == {SourceType.WEB, SourceType.YOUTUBE}


def test_discover_merges_items_from_both_branches(monkeypatch):
    monkeypatch.setattr(agent.exa_source, "search", lambda q, m: [_item("web1")])
    monkeypatch.setattr(
        agent.youtube_source,
        "search",
        lambda q, m: [SourceItem(source_type=SourceType.YOUTUBE, title="v",
                                 url="yt1", text="signal")],
    )
    result = discover("topic")
    assert {i.url for i in result.items} == {"web1", "yt1"}
    assert result.count == 2
    assert result.skipped == []


# --- validation (Req 3.6, query empty) ---

def test_empty_query_raises():
    with pytest.raises(ValueError):
        discover("   ")


@pytest.mark.parametrize("bad", [0, 51, -1, 100])
def test_max_results_out_of_range_raises(bad):
    with pytest.raises(ValueError):
        discover("topic", max_results=bad)
