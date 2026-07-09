"""Query Refinement & Clarification — the one LLM-backed step in Discovery (Req 2).

Before fan-out, classify the topic query as clear or ambiguous, rewrite a
clear-but-rough query for better source search, and either (interactive mode) return
clarifying questions, or (auto-proceed mode) proceed with a best-effort refined query.
Falls back to the original query if the LLM call fails.
"""
from __future__ import annotations

import logging

from ..config import settings
from ..llm import ReasoningError, converse_structured
from ..prompts import get_prompt
from ..models import (
    Clarify,
    ClarificationMode,
    Proceed,
    QueryClassification,
    RefineLLMOutput,
)

logger = logging.getLogger(__name__)

MAX_QUERY_LEN = 500
MAX_CLARIFICATION_ROUNDS = 2

class QueryValidationError(ValueError):
    """Raised when the submitted topic query is empty or too long (Req 1.2, 1.4)."""


def validate_query(query: str) -> str:
    """Trim and validate a topic query (Req 1.1, 1.2, 1.4)."""
    trimmed = query.strip()
    if not trimmed:
        raise QueryValidationError("query is empty")
    if len(trimmed) > MAX_QUERY_LEN:
        raise QueryValidationError(f"query exceeds maximum length of {MAX_QUERY_LEN} characters")
    return trimmed


def refine_query(
    query: str,
    mode: ClarificationMode = ClarificationMode.INTERACTIVE,
    round: int = 0,
) -> Proceed | Clarify:
    """Classify + rewrite a topic query, or request clarification.

    Returns `Proceed` (discovery can run with `refined_query`) or `Clarify`
    (interactive mode needs the Commander to disambiguate).
    """
    trimmed = validate_query(query)

    # Round cap: stop asking and proceed with the latest query (Req 2.8).
    if round >= MAX_CLARIFICATION_ROUNDS:
        logger.info("Clarification round cap reached; proceeding with %r", trimmed)
        return Proceed(original_query=trimmed, refined_query=trimmed,
                       proceeded_without_clarification=True)

    try:
        out = converse_structured(RefineLLMOutput, get_prompt("discovery.refine"), trimmed)
    except ReasoningError as exc:
        # Graceful fallback: proceed with the original query (Req 2.9).
        logger.warning("Query refinement failed (%s); using original query", exc.kind)
        return Proceed(original_query=trimmed, refined_query=trimmed, refinement_failed=True)

    refined = (out.refined_query or "").strip() or trimmed

    if out.classification == QueryClassification.CLEAR:
        return Proceed(original_query=trimmed, refined_query=refined)  # Req 2.2

    # Ambiguous:
    if mode == ClarificationMode.AUTO_PROCEED:
        # Best-effort refined query, no pause (Req 2.6).
        return Proceed(original_query=trimmed, refined_query=refined,
                       proceeded_without_clarification=True)

    # Interactive: pause and ask (Req 2.5).
    questions = out.clarifying_questions or ["Could you clarify the focus of your topic?"]
    return Clarify(original_query=trimmed, questions=questions, round=round)
