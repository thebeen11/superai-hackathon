"""Label assignment skill (Req 10). Exactly one MACRO/MICRO + exactly one industry."""
from __future__ import annotations

from pydantic import BaseModel

from ..llm import converse_structured
from ..models import Stream
from ..taxonomy import SECTORS, UNCLASSIFIED

_SYSTEM = (
    "Classify the financial text. Decide:\n"
    "1. stream: 'MACRO' if it is mainly about the economy/policy/markets at large, "
    "'MICRO' if it is mainly about specific companies.\n"
    f"2. industry: the single most prominent sector from this list: {SECTORS}. "
    "If none clearly applies, use 'Unclassified'."
)


class LabelOutput(BaseModel):
    stream: Stream
    industry: str


def assign_labels(text: str) -> LabelOutput:
    """Return exactly one MACRO/MICRO stream + one industry label (Req 10)."""
    out = converse_structured(LabelOutput, _SYSTEM, text)
    # Guard the industry to the allowed set; fall back to Unclassified (Req 10.4).
    if out.industry not in SECTORS:
        out.industry = UNCLASSIFIED
    return out
