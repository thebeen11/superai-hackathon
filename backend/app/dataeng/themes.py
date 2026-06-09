"""Theme assignment skill (Req 11). Classify against the Market_Theme_Taxonomy.

The LLM may only choose themes from the configured taxonomy; anything outside it is
discarded, and assigned themes are de-duplicated. No watchlist in this layer.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..llm import converse_structured
from ..taxonomy import MARKET_THEME_TAXONOMY

_SYSTEM = (
    "Classify the financial text against this fixed list of market themes:\n"
    f"{MARKET_THEME_TAXONOMY}\n"
    "Return only themes from the list that genuinely apply. If none apply, return an "
    "empty list. Do NOT invent themes outside the list."
)


class _ThemeOutput(BaseModel):
    themes: list[str] = Field(default_factory=list)


def assign_themes(text: str) -> list[str]:
    """Return the applicable taxonomy themes, de-duplicated, order preserved (Req 11)."""
    out = converse_structured(_ThemeOutput, _SYSTEM, text)
    allowed = set(MARKET_THEME_TAXONOMY)
    seen: set[str] = set()
    result: list[str] = []
    for theme in out.themes:
        if theme in allowed and theme not in seen:  # only taxonomy themes (Req 11.4)
            seen.add(theme)
            result.append(theme)
    return result
