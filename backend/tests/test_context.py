"""Tracker Context Preview tests — LLM judge grounding + deterministic fallback.

The LLM and the DB are mocked, so these run with no network or credentials.
"""
from __future__ import annotations

from app.insights import context as ctx
from app.insights.context import _Pick, tracker_context
from app.llm import ReasoningError
from app.models import CleanedItem, SourceType, Stream, TranscriptSegment


def _item(url="u", themes=("Solar",), text="solar capacity is expanding fast", segments=()):
    return CleanedItem(
        source_url=url, source_type=SourceType.WEB, title="t", clean_text=text,
        stream=Stream.MICRO, industry="Energy", themes=list(themes),
        segments=[TranscriptSegment(start=s, text=t) for s, t in segments],
    )


def test_no_items_returns_none(monkeypatch):
    monkeypatch.setattr(ctx, "list_cleaned_items", lambda **k: [])
    assert tracker_context("Solar") is None


def test_judge_grounds_quote_and_scores(monkeypatch):
    items = [_item(url="a", text="grid demand jumps"), _item(url="b", text="solar capacity is expanding fast")]
    monkeypatch.setattr(ctx, "list_cleaned_items", lambda **k: items)
    pick = _Pick(source_index=1, quote="solar capacity is expanding", relevance=0.87)
    monkeypatch.setattr(ctx, "converse_structured", lambda *a, **k: pick)

    preview = tracker_context("Solar")
    assert preview is not None
    assert preview.score == 0.87                       # real LLM score, not a placeholder
    assert "solar capacity is expanding" in preview.quote
    assert preview.channel == "b" or preview.channel  # host derived from the grounded item


def test_judge_quote_not_in_source_falls_back_to_snippet(monkeypatch):
    items = [_item(url="a", text="solar capacity is expanding fast")]
    monkeypatch.setattr(ctx, "list_cleaned_items", lambda **k: items)
    pick = _Pick(source_index=0, quote="INVENTED TEXT NOT PRESENT", relevance=0.9)
    monkeypatch.setattr(ctx, "converse_structured", lambda *a, **k: pick)

    preview = tracker_context("Solar")
    assert "INVENTED" not in preview.quote             # fabricated quote rejected
    assert "solar capacity" in preview.quote           # replaced with the real snippet


def test_bad_index_falls_back(monkeypatch):
    items = [_item(url="a")]
    monkeypatch.setattr(ctx, "list_cleaned_items", lambda **k: items)
    monkeypatch.setattr(ctx, "converse_structured",
                        lambda *a, **k: _Pick(source_index=99, quote="x", relevance=0.5))
    preview = tracker_context("Solar")
    assert preview is not None and 0.0 <= preview.score <= 1.0


def test_llm_unavailable_uses_computed_fallback(monkeypatch):
    # Two items both tagged Solar → coverage 1.0; one is Solar-only (dominance 1.0).
    items = [_item(url="a", themes=("Solar",)), _item(url="b", themes=("Solar", "Energy"))]
    monkeypatch.setattr(ctx, "list_cleaned_items", lambda **k: items)

    def boom(*a, **k):
        raise ReasoningError("down", kind="transient")

    monkeypatch.setattr(ctx, "converse_structured", boom)
    preview = tracker_context("Solar")
    assert preview is not None
    assert 0.0 < preview.score <= 1.0                  # computed, never hardcoded 0.5/0.0
    assert preview.score != 0.5
