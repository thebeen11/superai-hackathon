"""Shared Gemini (Vertex AI) structured-reasoning wrapper with schema enforcement + retries.

Used by every reasoning step in the backend (the Discovery query-refinement skill
and all Data Engineering / Council skills). It is the single place that talks to an LLM.

Design (Requirements 12):
- One call per reasoning step via the Vertex AI `generate_content` API (google-genai).
- The reply is constrained to JSON (Gemini JSON mode) and validated against a
  caller-supplied Pydantic schema.
- Retries up to `max_retries` additional attempts on BOTH:
    * Pydantic `ValidationError` (model returned malformed / invalid JSON), and
    * transient Vertex errors (5xx / rate limits),
  with exponential backoff.
- On exhaustion raises `ReasoningError(kind=...)` so callers can surface a reason
  distinguishing a schema-validation failure from a transient service error.

Auth: the Vertex client uses Application Default Credentials (ADC). On Cloud Run the
service account is picked up automatically; locally run `gcloud auth application-default
login`. No API keys are stored.
"""
from __future__ import annotations

import enum
import json
import logging
import re
import threading
import time
import types
import typing
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from ..config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_client_singleton = None
_client_lock = threading.Lock()


class ReasoningError(Exception):
    """Raised when a reasoning call cannot produce valid output.

    `kind` is "schema_validation" or "transient" so callers can record a precise,
    human-readable failure reason (Req 12.5).
    """

    def __init__(self, message: str, *, kind: str) -> None:
        super().__init__(message)
        self.kind = kind


def _client():
    # Cache one client for the process. A fresh client per call hits a GC race: the
    # throwaway Client wrapper is finalized right after `.models` is read, which closes
    # the httpx client the live Models object still uses -> subsequent sends fail with
    # "Cannot send a request, as the client has been closed." A module-level reference
    # keeps the client alive, and reusing it avoids rebuilding the httpx pool / re-
    # resolving ADC on every reasoning step.
    global _client_singleton
    if _client_singleton is None:
        with _client_lock:
            if _client_singleton is None:
                # Imported lazily so the app boots without GCP configured.
                from google import genai

                # Vertex backend uses Application Default Credentials; project/location
                # come from settings (env). If `gcp_project` is unset, google-auth
                # resolves it from ADC.
                _client_singleton = genai.Client(
                    vertexai=True,
                    project=settings.gcp_project,
                    location=settings.vertex_location,
                )
    return _client_singleton


def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model reply (tolerates code fences)."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object found in model reply")
    return json.loads(candidate[start : end + 1])


def _example_value(annotation):
    """Build a placeholder value for a field annotation, for the prompt example."""
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin in (typing.Union, getattr(types, "UnionType", ())):
        non_none = [a for a in args if a is not type(None)]
        return _example_value(non_none[0]) if non_none else "string"
    if origin in (list, set, tuple):
        return [_example_value(args[0])] if args else ["string"]
    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        return next(iter(annotation)).value
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return {n: _example_value(f.annotation) for n, f in annotation.model_fields.items()}
    if annotation is bool:
        return False
    if annotation is int:
        return 0
    if annotation is float:
        return 0.0
    return "string"


def _example_object(schema: type[BaseModel]) -> str:
    """A concrete example JSON instance of `schema` to show the model the shape."""
    example = {n: _example_value(f.annotation) for n, f in schema.model_fields.items()}
    return json.dumps(example)


def converse_structured(
    schema: type[T],
    system: str,
    user_content: str,
    *,
    model_id: str | None = None,
    max_retries: int | None = None,
) -> T:
    """Call Gemini, parse the JSON reply, validate it against `schema`.

    Returns a validated instance of `schema`. Raises ReasoningError after the retry
    budget is exhausted.
    """
    from google.genai import errors as genai_errors

    model = model_id or settings.gemini_model
    retries = settings.gemini_max_retries if max_retries is None else max_retries

    # Show the model a concrete example instance (NOT the JSON Schema — some models
    # echo the schema back). It must fill in real values with the same keys.
    system_with_schema = (
        f"{system}\n\nReturn ONLY a single JSON object with exactly these keys, "
        f"filling in real values (do not return this example verbatim, no prose, "
        f"no code fences):\n{_example_object(schema)}"
    )

    last_error: Exception | None = None
    last_kind = "schema_validation"

    for attempt in range(retries + 1):
        try:
            client = _client()
            response = client.models.generate_content(
                model=model,
                contents=user_content,
                config={
                    "system_instruction": system_with_schema,
                    # No temperature: Gemini 3 is tuned for its default (1.0), and forcing
                    # it low risks looping / degraded reasoning on complex tasks. Schema
                    # conformance comes from JSON mode + Pydantic validation + the retry
                    # loop below, not from determinism.
                    "response_mime_type": "application/json",
                },
            )
            return schema.model_validate(_extract_json(response.text))

        except genai_errors.ServerError as exc:  # 5xx — transient
            last_error, last_kind = exc, "transient"
            logger.warning("Vertex transient error %s (attempt %d)", exc.code, attempt + 1)
        except genai_errors.ClientError as exc:  # 4xx — only rate limits are retryable
            if exc.code == 429:
                last_error, last_kind = exc, "transient"
                logger.warning("Vertex rate-limited (attempt %d)", attempt + 1)
            else:
                raise  # non-retryable (auth, permission, bad model id) — surface immediately
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            last_error, last_kind = exc, "schema_validation"
            logger.warning("Vertex output failed validation (attempt %d): %s", attempt + 1, exc)

        if attempt < retries:
            time.sleep(2 ** attempt)  # exponential backoff: 1s, 2s, 4s...

    raise ReasoningError(
        f"Gemini reasoning failed after {retries + 1} attempts ({last_kind}): {last_error}",
        kind=last_kind,
    )
