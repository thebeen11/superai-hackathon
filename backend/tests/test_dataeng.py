"""Task 10 — Data Engineering guardrail + pipeline tests. Requirements 7, 11, 13."""
from __future__ import annotations

import pytest

from app.dataeng import pipeline
from app.dataeng.guardrail import OrphanDataError, enforce
from app.dataeng.themes import assign_themes
from app.dataeng import themes as themes_mod
from app.models import (
    CleanedItem,
    DiscoveryResult,
    ResolvedEntity,
    SourceItem,
    SourceType,
    Stream,
    TranscriptSegment,
)


def _cleaned(url="u", text="micron sees strong memory demand", stype=SourceType.WEB,
            segments=None):
    return CleanedItem(
        source_url=url, source_type=stype, title="t", clean_text=text,
        stream=Stream.MICRO, industry="Technology", segments=segments or [],
    )


def _origin(url="u", text="micron sees strong memory demand", stype=SourceType.WEB,
           segments=None):
    return SourceItem(source_type=stype, title="t", url=url, text=text,
                      segments=segments or [])


# --- guardrail (Req 13) ---

def test_guardrail_rejects_empty_source_url():
    cleaned = _cleaned(url="")
    with pytest.raises(OrphanDataError):
        enforce(cleaned, _origin(url="u"))


def test_guardrail_rejects_url_mismatch():
    with pytest.raises(OrphanDataError):
        enforce(_cleaned(url="a"), _origin(url="b"))


def test_guardrail_rejects_fabricated_text():
    cleaned = _cleaned(text="the fed will cut rates to zero next week guaranteed")
    with pytest.raises(OrphanDataError):
        enforce(cleaned, _origin(text="micron sees strong memory demand this quarter"))


def test_guardrail_drops_ungrounded_and_negative_segments():
    origin = _origin(
        stype=SourceType.YOUTUBE,
        text="nvidia demand is strong and accelerating into next year",
        segments=[TranscriptSegment(start=10.0, text="nvidia demand is strong")],
    )
    cleaned = _cleaned(
        url="u", stype=SourceType.YOUTUBE,
        text="nvidia demand is strong and accelerating into next year",
        segments=[
            TranscriptSegment(start=10.0, text="nvidia demand is strong"),  # grounded
            TranscriptSegment(start=-1.0, text="nvidia demand is strong"),  # bad ts
            TranscriptSegment(start=5.0, text="totally invented quote"),    # ungrounded
        ],
    )
    out = enforce(cleaned, origin)
    assert len(out.segments) == 1
    assert out.segments[0].start == 10.0


# --- themes (Req 11) ---

def test_assign_themes_filters_to_taxonomy_and_dedupes(monkeypatch):
    class _Out:
        themes = ["Technology", "Technology", "Made Up Theme", "Solar"]
    monkeypatch.setattr(themes_mod, "converse_structured", lambda *a, **k: _Out())
    out = assign_themes("some text")
    assert out == ["Technology", "Solar"]  # de-duped, invented theme dropped


# --- pipeline isolation (Req 7) ---

def test_pipeline_empty_input_persists_nothing():
    report = pipeline.process_discovery_result(DiscoveryResult(query="q"))
    assert report.persisted == 0 and report.failed == 0


def test_pipeline_isolates_per_item_failures(monkeypatch):
    # First item builds fine and persists; second raises during skill processing.
    good = _origin(url="good")
    bad = _origin(url="bad")

    def fake_build(item):
        if item.url == "bad":
            raise RuntimeError("skill blew up")
        return _cleaned(url=item.url)

    monkeypatch.setattr(pipeline, "_build_cleaned_item", fake_build)
    monkeypatch.setattr(pipeline, "upsert_cleaned_item", lambda item: None)

    report = pipeline.process_discovery_result(
        DiscoveryResult(query="q", items=[good, bad])
    )
    assert report.persisted == 1
    assert report.failed == 1
    assert report.failures[0].source_url == "bad"
