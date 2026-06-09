"""No-orphan-data hallucination guardrail (Req 13).

Enforces that a Cleaned_Item is traceable to its source before persistence:
- non-empty source_url,
- video items keep valid (>= 0) timestamp_start segments,
- the cleaned text must be grounded in the original source text (anti-fabrication).
"""
from __future__ import annotations

import re

from ..models import CleanedItem, SourceItem, SourceType, TranscriptSegment


class OrphanDataError(ValueError):
    """Raised when an item/claim cannot be traced to its source (Req 13.3, 13.4)."""


def enforce(cleaned: CleanedItem, origin: SourceItem) -> CleanedItem:
    """Validate provenance; drop ungrounded segments. Raise if the item is an orphan."""
    if not (cleaned.source_url or "").strip():
        raise OrphanDataError("missing source_url")

    if cleaned.source_url != origin.url:
        raise OrphanDataError("source_url does not match originating item")

    # Video claims must carry a valid, source-grounded timestamp_start (Req 13.2, 13.4).
    if cleaned.source_type == SourceType.YOUTUBE:
        origin_texts = {s.text.strip() for s in origin.segments}
        grounded: list[TranscriptSegment] = []
        for seg in cleaned.segments:
            if seg.start < 0:
                continue  # invalid timestamp (Req 13.3)
            if seg.text.strip() in origin_texts:  # grounded in source (Req 13.4)
                grounded.append(seg)
        cleaned.segments = grounded

    # Anti-fabrication: cleaned text must be derived from the source, not invented.
    # We approximate "grounded" by requiring meaningful overlap with the source text.
    if not _is_grounded(cleaned.clean_text, origin.text):
        raise OrphanDataError("cleaned text not found in source (possible fabrication)")

    return cleaned


def _shingles(text: str, n: int = 3) -> list[tuple[str, ...]]:
    """Normalized n-grams: lowercased, punctuation-stripped, whitespace-collapsed."""
    cleaned = re.sub(r"[^a-z0-9 ]", " ", text.lower())
    words = re.sub(r"\s+", " ", cleaned).split()
    return [tuple(words[i : i + n]) for i in range(len(words) - n + 1)]


def _is_grounded(clean_text: str, source_text: str) -> bool:
    """Grounding check: most cleaned-text 3-grams must appear in the source.

    Redaction only *removes* text, so faithful cleaned output shares almost all its
    3-grams with the source (only those straddling a removed span break). Fabricated
    or summarized text introduces many novel 3-grams. 3-grams + punctuation-stripping
    tolerate span removal and minor normalization, avoiding false "fabrication" flags.
    """
    cleaned = _shingles(clean_text)
    if not cleaned:
        return False
    source = set(_shingles(source_text))
    hits = sum(1 for sh in cleaned if sh in source)
    return hits / len(cleaned) >= 0.7
