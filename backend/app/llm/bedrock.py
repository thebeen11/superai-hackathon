"""Shared Amazon Bedrock `converse` wrapper with schema enforcement + retries.

Used by every reasoning step in the backend (the Discovery query-refinement skill
and all Data Engineering skills). It is the single place that talks to an LLM.

Design (Requirements 12):
- One call per reasoning step via the Bedrock `converse` API (boto3).
- The reply is constrained to JSON and validated against a caller-supplied Pydantic
  schema.
- Retries up to `max_retries` additional attempts on BOTH:
    * Pydantic `ValidationError` (model returned malformed / invalid JSON), and
    * transient Bedrock errors (throttling / timeouts),
  with exponential backoff.
- On exhaustion raises `BedrockReasoningError(kind=...)` so callers can surface a
  reason distinguishing a schema-validation failure from a transient service error.
"""
from __future__ import annotations

import enum
import json
import logging
import re
import time
import types
import typing
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from ..config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# botocore error codes treated as transient / retryable.
_TRANSIENT_CODES = {
    "ThrottlingException",
    "TooManyRequestsException",
    "ModelTimeoutException",
    "ServiceUnavailableException",
    "InternalServerException",
}


class BedrockReasoningError(Exception):
    """Raised when a Bedrock reasoning call cannot produce valid output.

    `kind` is "schema_validation" or "transient" so callers can record a precise,
    human-readable failure reason (Req 12.5).
    """

    def __init__(self, message: str, *, kind: str) -> None:
        super().__init__(message)
        self.kind = kind


def _client():
    # Imported lazily so the app boots without AWS configured.
    import boto3

    return boto3.client("bedrock-runtime", region_name=settings.aws_region)


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
    """Call Bedrock `converse`, parse the JSON reply, validate it against `schema`.

    Returns a validated instance of `schema`. Raises BedrockReasoningError after the
    retry budget is exhausted.
    """
    from botocore.exceptions import ClientError

    model = model_id or settings.bedrock_model_id
    retries = settings.bedrock_max_retries if max_retries is None else max_retries

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
            response = _client().converse(
                modelId=model,
                system=[{"text": system_with_schema}],
                messages=[{"role": "user", "content": [{"text": user_content}]}],
                inferenceConfig={"temperature": 0.0},
            )
            reply = response["output"]["message"]["content"][0]["text"]
            return schema.model_validate(_extract_json(reply))

        except ClientError as exc:  # transient vs fatal AWS errors
            code = exc.response.get("Error", {}).get("Code", "")
            if code in _TRANSIENT_CODES:
                last_error, last_kind = exc, "transient"
                logger.warning("Bedrock transient error %s (attempt %d)", code, attempt + 1)
            else:
                raise  # non-retryable (auth, access, bad model id) — surface immediately
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            last_error, last_kind = exc, "schema_validation"
            logger.warning("Bedrock output failed validation (attempt %d): %s", attempt + 1, exc)

        if attempt < retries:
            time.sleep(2 ** attempt)  # exponential backoff: 1s, 2s, 4s...

    raise BedrockReasoningError(
        f"Bedrock reasoning failed after {retries + 1} attempts ({last_kind}): {last_error}",
        kind=last_kind,
    )
