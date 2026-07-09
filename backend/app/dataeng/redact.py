"""Noise redaction skill (Req 8). Removes ad reads/filler, preserves signal.

Uses the LLM to strip promotional/filler passages while keeping every passage that
carries financial/investment signal. For video items, surviving transcript segments
keep their timestamp_start so claims stay anchored (Req 8.3).
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..llm import converse_structured
from ..models import SourceItem, TranscriptSegment
from ..prompts import get_prompt


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
    surviving = [s for s in item.segments if s.text.strip() and s.text.strip() in clean]
    return RedactionResult(clean_text=clean, segments=surviving, is_all_noise=False)
