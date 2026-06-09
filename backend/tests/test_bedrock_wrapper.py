"""Task 10 — Bedrock wrapper retry behaviour (stubbed client). Requirements 12.3-12.5."""
from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.llm import BedrockReasoningError, bedrock


class _Schema(BaseModel):
    value: int


class _FakeClient:
    """Returns a queued sequence of replies / exceptions on each converse() call."""

    def __init__(self, scripted):
        self._scripted = list(scripted)
        self.calls = 0

    def converse(self, **kwargs):
        self.calls += 1
        item = self._scripted.pop(0)
        if isinstance(item, Exception):
            raise item
        return {"output": {"message": {"content": [{"text": item}]}}}


def _throttle():
    from botocore.exceptions import ClientError
    return ClientError({"Error": {"Code": "ThrottlingException"}}, "Converse")


def _patch_client(monkeypatch, client):
    monkeypatch.setattr(bedrock, "_client", lambda: client)
    # no real sleeping during tests
    monkeypatch.setattr(bedrock.time, "sleep", lambda *_: None)


def test_valid_first_try(monkeypatch):
    client = _FakeClient(['{"value": 7}'])
    _patch_client(monkeypatch, client)
    out = bedrock.converse_structured(_Schema, "sys", "user", max_retries=3)
    assert out.value == 7
    assert client.calls == 1


def test_retries_then_succeeds_on_bad_json(monkeypatch):
    client = _FakeClient(["not json", '{"value": 5}'])
    _patch_client(monkeypatch, client)
    out = bedrock.converse_structured(_Schema, "sys", "user", max_retries=3)
    assert out.value == 5
    assert client.calls == 2


def test_retries_on_throttling_then_succeeds(monkeypatch):
    client = _FakeClient([_throttle(), '{"value": 9}'])
    _patch_client(monkeypatch, client)
    out = bedrock.converse_structured(_Schema, "sys", "user", max_retries=3)
    assert out.value == 9
    assert client.calls == 2


def test_exhaustion_raises_schema_validation(monkeypatch):
    client = _FakeClient(["nope"] * 4)
    _patch_client(monkeypatch, client)
    with pytest.raises(BedrockReasoningError) as ei:
        bedrock.converse_structured(_Schema, "sys", "user", max_retries=3)
    assert ei.value.kind == "schema_validation"
    assert client.calls == 4  # 1 + 3 retries


def test_exhaustion_raises_transient(monkeypatch):
    client = _FakeClient([_throttle()] * 4)
    _patch_client(monkeypatch, client)
    with pytest.raises(BedrockReasoningError) as ei:
        bedrock.converse_structured(_Schema, "sys", "user", max_retries=3)
    assert ei.value.kind == "transient"


def test_non_retryable_error_surfaces_immediately(monkeypatch):
    from botocore.exceptions import ClientError
    access_denied = ClientError({"Error": {"Code": "AccessDeniedException"}}, "Converse")
    client = _FakeClient([access_denied, '{"value": 1}'])
    _patch_client(monkeypatch, client)
    with pytest.raises(ClientError):
        bedrock.converse_structured(_Schema, "sys", "user", max_retries=3)
    assert client.calls == 1  # not retried
