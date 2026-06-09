"""Entity resolution skill (Req 9). Maps slang/aliases to canonical tickers/entities.

A built-in alias map (taxonomy.py) handles the common cases cheaply; the LLM resolves
the rest. Resolved entities are de-duplicated by canonical name. Unrecognized tokens are
never mapped (Req 9.5).
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..llm import converse_structured
from ..models import ResolvedEntity
from ..taxonomy import COMPANY_ALIASES, MACRO_ALIASES

_SYSTEM = (
    "You identify the companies and macro-economic entities explicitly mentioned in the "
    "text. For each, return its canonical form: a stock ticker prefixed with '$' for a "
    "company (e.g. $META), or a canonical macro entity name (e.g. Federal_Reserve). "
    "Only include entities that are actually present in the text — never guess or invent. "
    "List each alias mention you matched."
)


class _LLMEntity(BaseModel):
    canonical: str
    mentions: list[str] = Field(default_factory=list)


class _EntityOutput(BaseModel):
    entities: list[_LLMEntity] = Field(default_factory=list)


def _builtin_matches(text: str) -> dict[str, set[str]]:
    """Cheap dictionary pass: canonical -> set of matched alias surface forms."""
    lowered = text.lower()
    found: dict[str, set[str]] = {}
    for alias, canonical in {**COMPANY_ALIASES, **MACRO_ALIASES}.items():
        if alias in lowered:
            found.setdefault(canonical, set()).add(alias)
    return found


def resolve_entities(text: str) -> list[ResolvedEntity]:
    """Resolve entities via the built-in map + LLM, de-duplicated by canonical."""
    merged: dict[str, set[str]] = _builtin_matches(text)

    out = converse_structured(_EntityOutput, _SYSTEM, text)
    for e in out.entities:
        canonical = (e.canonical or "").strip()
        if not canonical:
            continue
        merged.setdefault(canonical, set()).update(m.strip() for m in e.mentions if m.strip())

    return [
        ResolvedEntity(canonical=c, mentions=sorted(m)) for c, m in sorted(merged.items())
    ]
