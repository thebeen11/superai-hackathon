"""Task 2.4 — Query Refinement unit tests (Bedrock mocked). Requirements 2.1-2.9, 1.x."""
from __future__ import annotations

import pytest

from app.discovery import refine as refine_mod
from app.discovery.refine import QueryValidationError, refine_query, validate_query
from app.llm import BedrockReasoningError
from app.models import (
    Clarify,
    ClarificationMode,
    Proceed,
    QueryClassification,
    RefineLLMOutput,
)


def _stub_llm(monkeypatch, *, classification, refined="refined topic", questions=None):
    def fake(schema, system, user_content, **kwargs):
        return RefineLLMOutput(
            classification=classification,
            refined_query=refined,
            clarifying_questions=questions or [],
        )
    monkeypatch.setattr(refine_mod, "converse_structured", fake)


def _raise_llm(monkeypatch, kind="transient"):
    def fake(*a, **k):
        raise BedrockReasoningError("boom", kind=kind)
    monkeypatch.setattr(refine_mod, "converse_structured", fake)


# --- validation (Req 1.1, 1.2, 1.4) ---

def test_empty_query_rejected():
    with pytest.raises(QueryValidationError):
        validate_query("   ")


def test_overlong_query_rejected():
    with pytest.raises(QueryValidationError):
        validate_query("x" * 501)


def test_query_trimmed():
    assert validate_query("  hello  ") == "hello"


# --- clear path (Req 2.2, 2.3) ---

def test_clear_query_proceeds_with_refined(monkeypatch):
    _stub_llm(monkeypatch, classification=QueryClassification.CLEAR, refined="AI memory demand")
    out = refine_query("ai memory", ClarificationMode.INTERACTIVE)
    assert isinstance(out, Proceed)
    assert out.refined_query == "AI memory demand"
    assert out.original_query == "ai memory"      # original preserved (Req 2.3)
    assert out.proceeded_without_clarification is False


# --- ambiguous × interactive (Req 2.5) ---

def test_ambiguous_interactive_returns_clarify(monkeypatch):
    _stub_llm(monkeypatch, classification=QueryClassification.AMBIGUOUS,
              questions=["Which sector?"])
    out = refine_query("stuff", ClarificationMode.INTERACTIVE)
    assert isinstance(out, Clarify)
    assert out.questions == ["Which sector?"]
    assert out.round == 0


# --- ambiguous × auto-proceed (Req 2.6) ---

def test_ambiguous_auto_proceed(monkeypatch):
    _stub_llm(monkeypatch, classification=QueryClassification.AMBIGUOUS, refined="best effort")
    out = refine_query("stuff", ClarificationMode.AUTO_PROCEED)
    assert isinstance(out, Proceed)
    assert out.proceeded_without_clarification is True
    assert out.refined_query == "best effort"


# --- round cap (Req 2.8) ---

def test_round_cap_proceeds_without_calling_llm(monkeypatch):
    # If the LLM were called it would explode; the cap must short-circuit first.
    _raise_llm(monkeypatch)
    out = refine_query("anything", ClarificationMode.INTERACTIVE, round=2)
    assert isinstance(out, Proceed)
    assert out.proceeded_without_clarification is True


# --- LLM failure fallback (Req 2.9) ---

def test_llm_failure_falls_back_to_original(monkeypatch):
    _raise_llm(monkeypatch, kind="schema_validation")
    out = refine_query("original topic", ClarificationMode.INTERACTIVE)
    assert isinstance(out, Proceed)
    assert out.refinement_failed is True
    assert out.refined_query == "original topic"
