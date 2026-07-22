"""Editable prompt catalogue + runtime overrides (the Agent Console backend)."""
from .identity import AgentSpec, ToolSpec, get_agent
from .registry import (
    PromptSpec,
    get_prompt,
    get_spec,
    list_prompt_specs,
    list_skill_specs,
)

__all__ = [
    "AgentSpec",
    "PromptSpec",
    "ToolSpec",
    "get_agent",
    "get_prompt",
    "get_spec",
    "list_prompt_specs",
    "list_skill_specs",
]
