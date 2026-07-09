"""Label assignment skill (Req 10). Exactly one MACRO/MICRO + exactly one industry."""
from __future__ import annotations

from pydantic import BaseModel

from ..llm import converse_structured
from ..models import Stream
from ..prompts import get_prompt
from ..taxonomy import SECTORS, UNCLASSIFIED


class LabelOutput(BaseModel):
    stream: Stream
    industry: str


def assign_labels(text: str) -> LabelOutput:
    """Return exactly one MACRO/MICRO stream + one industry label (Req 10)."""
    out = converse_structured(LabelOutput, get_prompt("dataeng.labels", sectors=SECTORS), text)
    # Guard the industry to the allowed set; fall back to Unclassified (Req 10.4).
    if out.industry not in SECTORS:
        out.industry = UNCLASSIFIED
    return out
