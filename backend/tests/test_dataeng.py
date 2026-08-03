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


# --- redaction must not silently strip timestamps (regression) ---

def test_captions_survive_redaction_when_the_model_reflows_them(monkeypatch):
    """Captions carry hard line breaks mid-sentence; the model reflows them onto one line.

    A literal containment test fails for every segment of a real transcript, which strips
    every timestamp from the item while still reporting a successful ingest.
    """
    from app.dataeng import redact as redact_mod
    from app.models import SourceItem, SourceType, TranscriptSegment

    segments = [
        TranscriptSegment(start=2.13, text="Coming up on Bloomberg this weekend.\nStrikes unfold."),
        TranscriptSegment(start=6.0, text="President Trump reverses course\novernight."),
    ]
    item = SourceItem(
        source_type=SourceType.YOUTUBE, title="t",
        url="https://www.youtube.com/watch?v=v1",
        text=" ".join(s.text for s in segments), segments=segments,
    )
    reflowed = (
        "Coming up on Bloomberg this weekend. Strikes unfold. "
        "President Trump reverses course overnight."
    )
    monkeypatch.setattr(
        redact_mod, "converse_structured",
        lambda schema, system, user, **kw: schema(clean_text=reflowed),
    )
    monkeypatch.setattr(redact_mod, "get_prompt", lambda key, **v: "p")

    result = redact_mod.redact(item)

    assert [s.start for s in result.segments] == [2.13, 6.0]


def test_redaction_still_drops_segments_the_model_removed(monkeypatch):
    """Whitespace tolerance must not become 'keep everything'."""
    from app.dataeng import redact as redact_mod
    from app.models import SourceItem, SourceType, TranscriptSegment

    segments = [
        TranscriptSegment(start=1.0, text="real market commentary here"),
        TranscriptSegment(start=2.0, text="this episode is sponsored by a mattress company"),
    ]
    item = SourceItem(
        source_type=SourceType.YOUTUBE, title="t",
        url="https://www.youtube.com/watch?v=v1",
        text=" ".join(s.text for s in segments), segments=segments,
    )
    monkeypatch.setattr(
        redact_mod, "converse_structured",
        lambda schema, system, user, **kw: schema(clean_text="real market commentary here"),
    )
    monkeypatch.setattr(redact_mod, "get_prompt", lambda key, **v: "p")

    result = redact_mod.redact(item)

    assert [s.start for s in result.segments] == [1.0]   # the ad read is gone
