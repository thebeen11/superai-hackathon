"""Editable prompt catalogue + runtime overrides (the Agent Console backend)."""
from .registry import (
    PROMPTS,
    PromptSpec,
    get_prompt,
    get_spec,
    list_prompt_specs,
)

__all__ = [
    "PROMPTS",
    "PromptSpec",
    "get_prompt",
    "get_spec",
    "list_prompt_specs",
]
