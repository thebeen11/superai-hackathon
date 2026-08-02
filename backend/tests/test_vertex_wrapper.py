"""Task 10 — Gemini/Vertex wrapper retry behaviour (stubbed client). Requirements 12.3-12.5."""
from __future__ import annotations

import pytest
from google.genai import errors as genai_errors
from pydantic import BaseModel

from app.llm import ReasoningError, vertex


class _Schema(BaseModel):
    value: int


class _FakeClient:
    """Returns a queued sequence of replies / exceptions on each generate_content() call.

    `self.models = self` so `client.models.generate_content(...)` resolves here, matching
    the google-genai client surface the wrapper calls.
    """

    def __init__(self, scripted):
        self._scripted = list(scripted)
        self.calls = 0
        self.models = self

    def generate_content(self, **kwargs):
        self.calls += 1
        item = self._scripted.pop(0)
        if isinstance(item, Exception):
            raise item
        return type("_Resp", (), {"text": item})()


def _server_error():  # 5xx → transient
    return genai_errors.ServerError(503, {"error": {"code": 503, "message": "unavailable"}})


def _throttle():  # 429 → transient
    return genai_errors.ClientError(429, {"error": {"code": 429, "message": "rate limited"}})


def _denied():  # 403 → non-retryable
    return genai_errors.ClientError(403, {"error": {"code": 403, "message": "permission denied"}})


def _patch_client(monkeypatch, client):
    monkeypatch.setattr(vertex, "_client", lambda: client)
    # no real sleeping during tests
    monkeypatch.setattr(vertex.time, "sleep", lambda *_: None)


def test_valid_first_try(monkeypatch):
    client = _FakeClient(['{"value": 7}'])
    _patch_client(monkeypatch, client)
    out = vertex.converse_structured(_Schema, "sys", "user", max_retries=3)
    assert out.value == 7
    assert client.calls == 1


def test_retries_then_succeeds_on_bad_json(monkeypatch):
    client = _FakeClient(["not json", '{"value": 5}'])
    _patch_client(monkeypatch, client)
    out = vertex.converse_structured(_Schema, "sys", "user", max_retries=3)
    assert out.value == 5
    assert client.calls == 2


def test_retries_on_throttling_then_succeeds(monkeypatch):
    client = _FakeClient([_throttle(), '{"value": 9}'])
    _patch_client(monkeypatch, client)
    out = vertex.converse_structured(_Schema, "sys", "user", max_retries=3)
    assert out.value == 9
    assert client.calls == 2


def test_retries_on_server_error_then_succeeds(monkeypatch):
    client = _FakeClient([_server_error(), '{"value": 8}'])
    _patch_client(monkeypatch, client)
    out = vertex.converse_structured(_Schema, "sys", "user", max_retries=3)
    assert out.value == 8
    assert client.calls == 2


def test_exhaustion_raises_schema_validation(monkeypatch):
    client = _FakeClient(["nope"] * 4)
    _patch_client(monkeypatch, client)
    with pytest.raises(ReasoningError) as ei:
        vertex.converse_structured(_Schema, "sys", "user", max_retries=3)
    assert ei.value.kind == "schema_validation"
    assert client.calls == 4  # 1 + 3 retries


def test_exhaustion_raises_transient(monkeypatch):
    client = _FakeClient([_server_error()] * 4)
    _patch_client(monkeypatch, client)
    with pytest.raises(ReasoningError) as ei:
        vertex.converse_structured(_Schema, "sys", "user", max_retries=3)
    assert ei.value.kind == "transient"


def test_non_retryable_error_surfaces_immediately(monkeypatch):
    client = _FakeClient([_denied(), '{"value": 1}'])
    _patch_client(monkeypatch, client)
    with pytest.raises(genai_errors.ClientError):
        vertex.converse_structured(_Schema, "sys", "user", max_retries=3)
    assert client.calls == 1  # not retried


def test_default_model_comes_from_settings(monkeypatch):
    """When model_id is omitted, the wrapper passes settings.gemini_model to the client."""
    seen: dict = {}

    class _Capture(_FakeClient):
        def generate_content(self, **kwargs):
            seen.update(kwargs)
            return super().generate_content(**kwargs)

    client = _Capture(['{"value": 1}'])
    _patch_client(monkeypatch, client)
    monkeypatch.setattr(vertex.settings, "gemini_model", "gemini-3.1-pro-preview")
    vertex.converse_structured(_Schema, "sys", "user", max_retries=0)
    assert seen["model"] == "gemini-3.1-pro-preview"
    assert seen["config"]["response_mime_type"] == "application/json"
