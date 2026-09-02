"""Shared citation plumbing — the no-orphan guardrail in one place (§12.6).

Every reasoning agent that has to cite works the same way: render the corpus as a
*numbered* excerpt list carrying the real URL, ask the model for an integer
`source_index` alongside each quote, then map that index back to a real source here.
An index the model invented simply doesn't resolve, so the claim behind it can be
dropped or de-anchored — the model never gets to write a URL itself.

`best_offset` is the reason a video citation is worth clicking: it finds the transcript
segment the quote actually came from rather than assuming the top of the video, so the
UI can deep-link to the right second.
"""
from __future__ import annotations

import re
from typing import Callable, Iterable, Mapping, Protocol

from pydantic import BaseModel

from ..models import CleanedItem, Evidence, SourceRef

SNIPPET = 600  # chars of clean_text shown per excerpt, to bound the prompt

# Words too common to say anything about which segment a quote came from.
_STOPWORDS = frozenset(
    "a an and are as at be been but by for from has have in is it its of on or that "
    "the this to was were will with we you they he she i not no so if then than".split()
)
_WORD = re.compile(r"[a-z0-9$%.]+")


class LLMEvidence(BaseModel):
    """The citation shape every agent's output schema embeds.

    `source_index` points into the list rendered by `digest()`. It is the model's only
    way to reference a source — it never sees a URL slot it could fill in itself.
    """

    quote: str
    source_index: int


class _HasEvidence(Protocol):
    quote: str
    source_index: int


def digest(
    items: list[CleanedItem],
    *,
    snippet: int = SNIPPET,
    extra: Callable[[CleanedItem], str] | None = None,
) -> str:
    """Render the numbered excerpt list agents cite back into.

    `extra` appends per-item fields to the header line (the analyst desks add the
    resolved tickers, so a stock take can be attributed without re-reading the body).
    """
    lines: list[str] = []
    for i, it in enumerate(items):
        text = it.clean_text[:snippet].replace("\n", " ")
        head = f"[{i}] title={it.title!r}"
        if extra:
            suffix = extra(it)
            if suffix:
                head = f"{head} {suffix}"
        lines.append(f"{head} url={it.source_url}\n    {text}")
    return "\n".join(lines)


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOPWORDS and len(w) > 1}


def best_offset(item: CleanedItem, quote: str) -> float | None:
    """Seconds into the video where `quote` was said, or None for articles.

    Scores each transcript segment by how much of the quote's vocabulary it contains.
    Falls back to the first segment when nothing overlaps — an anchor at the top of the
    video still beats no anchor at all, and the alternative (dropping the citation) would
    throw away a quote the guardrail already verified against the source text.
    """
    if not item.segments:
        return None
    wanted = _tokens(quote)
    if not wanted:
        return item.segments[0].start

    best, best_score = None, 0.0
    for seg in item.segments:
        overlap = len(wanted & _tokens(seg.text))
        if not overlap:
            continue
        score = overlap / len(wanted)
        if score > best_score:
            best, best_score = seg, score
    return best.start if best is not None else item.segments[0].start


def ground(refs: Iterable[_HasEvidence], items: list[CleanedItem]) -> list[Evidence]:
    """Resolve cited indices to real sources; silently drop the ones that don't exist.

    Callers decide what an empty result means: the analyst desks drop the stock take
    entirely (a conviction with no source is worthless), while the Chairman keeps the
    claim and renders it de-anchored.
    """
    grounded: list[Evidence] = []
    for ref in refs:
        if 0 <= ref.source_index < len(items):
            src = items[ref.source_index]
            grounded.append(
                Evidence(
                    quote=ref.quote,
                    source_url=src.source_url,
                    timestamp_start=best_offset(src, ref.quote),
                )
            )
    return grounded


def source_manifest(
    items: list[CleanedItem], cited: Mapping[str, Iterable[str]]
) -> list[SourceRef]:
    """One row per document a run read, tagged with the agents that quoted it.

    This is the audit trail the UI's Sources page renders (§12.6). It is recorded on the
    saved run rather than recomputed from the live corpus, so a stored run still reports
    what it was actually based on after the corpus moves on. Documents nobody cited are
    kept — "read but not used" is a fact worth showing, not one to hide.

    `cited` maps a source URL to the agents that quoted it; build it with `attribute`.
    """
    return [
        SourceRef(
            url=it.source_url,
            title=it.title,
            source_type=it.source_type,
            stream=it.stream,
            author=it.author,
            published_at=it.published_at,
            themes=list(it.themes),
            cited_by=sorted(cited.get(it.source_url, ())),
        )
        for it in items
    ]


def attribute(cited: dict[str, set[str]], agent: str, evidence: Iterable[Evidence]) -> None:
    """Record that `agent` quoted every source in `evidence`, into a `source_manifest` map."""
    for ev in evidence:
        cited.setdefault(ev.source_url, set()).add(agent)
