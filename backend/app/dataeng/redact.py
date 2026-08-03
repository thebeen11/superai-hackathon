"""Noise redaction skill (Req 8). Removes ad reads/filler, preserves signal.

Uses the LLM to strip promotional/filler passages while keeping every passage that
carries financial/investment signal. For video items, surviving transcript segments
keep their timestamp_start so claims stay anchored (Req 8.3).
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from ..llm import converse_structured
from ..models import SourceItem, TranscriptSegment
from ..prompts import get_prompt


def _collapse(text: str) -> str:
    """Whitespace-collapsed text, for comparing a segment against reflowed output."""
    return re.sub(r"\s+", " ", text).strip()


class _RedactOutput(BaseModel):
    clean_text: str = Field(default="")


class RedactionResult(BaseModel):
    clean_text: str
    segments: list[TranscriptSegment]
    is_all_noise: bool


def redact(item: SourceItem) -> RedactionResult:
    """Return cleaned text + surviving segments. `is_all_noise` if nothing remained."""
    out = converse_structured(_RedactOutput, get_prompt("dataeng.redact"), item.text)
    clean = (out.clean_text or "").strip()

    if not clean:
        return RedactionResult(clean_text="", segments=[], is_all_noise=True)

    # Keep only segments whose text still appears in the cleaned output (Req 8.3),
    # preserving each segment's timestamp_start anchor.
    #
    # Compared with whitespace collapsed on both sides. Captions carry hard line breaks
    # mid-sentence ("...this weekend.\nStrikes unfold.") and the model reflows them onto one
    # line, so a literal `in` test fails for every segment of a real transcript — silently
    # stripping every timestamp from the item while still reporting success. This is the same
    # tolerance `guardrail._is_grounded` already applies: the exact word sequence is still
    # required, only the whitespace between words is forgiven.
    collapsed_clean = _collapse(clean)
    surviving = [
        s for s in item.segments if _collapse(s.text) and _collapse(s.text) in collapsed_clean
    ]
    return RedactionResult(clean_text=clean, segments=surviving, is_all_noise=False)
