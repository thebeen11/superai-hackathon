"""Agent identity — who each agent is, how it reasons, and what it may touch.

A system prompt here is not one blob. It is composed, in order, from:

    ## SOUL           one global essence shared by the whole council   (`soul.core`)
    ## RULES          global, non-negotiable constraints               (`rules.global`)
    ## MENTAL MODELS  the reasoning frameworks this agent has enabled  (`mental.*`)
    ## PERSONALITY    this agent's voice                               (`personality.<id>`)
    ## TASK           the agent's SOP for this step — the Skill        (registry.py)

Every layer is a `PromptSpec`, so the Agent Console edits and resets them through the
same `GET/PUT/DELETE /api/prompts` endpoints as the task prompts, and the same
`store.py` override table persists them (no new schema).

Which frameworks an agent runs is a per-agent *assignment*, not text; it rides the
same key→text store as a JSON list under `assign.mental_models.<agent id>`.

The roster below is built from code that actually exists (Exa + YouTube discovery,
Timo's cleaning pipeline, three Andie desks, the Bull/Bear debate, Winston) — the
console shows real agents and their real tools, never aspirational ones.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from . import store
from .registry import PromptSpec, list_skill_specs

logger = logging.getLogger(__name__)

_ASSIGN_PREFIX = "assign.mental_models."


# --- Tools: the executable "hands", declared where they live in the codebase ------


@dataclass(frozen=True)
class ToolSpec:
    """One executable capability an agent can invoke."""

    name: str
    description: str
    io: str
    module: str


EXA_SEARCH = ToolSpec(
    "exa.search",
    "Web search plus full-article crawl for a topic query, with optional date bounds.",
    "query, max_results, date range → SourceItem[]",
    "app/discovery/exa_source.py",
)
YOUTUBE_SEARCH = ToolSpec(
    "youtube.search",
    "Finds candidate videos for a query via the YouTube Data API.",
    "query, limit → video ids + channel metadata",
    "app/discovery/youtube_source.py",
)
YOUTUBE_TRANSCRIPT = ToolSpec(
    "youtube.transcript",
    "Pulls a video's captions (no audio download); videos without captions are skipped.",
    "video id → TranscriptSegment[]",
    "app/discovery/youtube_source.py",
)
GEMINI = ToolSpec(
    "vertex.gemini_structured",
    "One structured reasoning call: JSON-mode Gemini validated against a Pydantic schema, with retries.",
    "system prompt + user content → schema instance",
    "app/llm/vertex.py",
)
TAXONOMY_SECTORS = ToolSpec(
    "taxonomy.sectors",
    "The fixed sector list every industry label must come from.",
    "→ sector names",
    "app/taxonomy.py",
)
TAXONOMY_THEMES = ToolSpec(
    "taxonomy.themes",
    "The fixed market-theme taxonomy; themes outside it are rejected.",
    "→ theme names",
    "app/taxonomy.py",
)
DB_ITEMS_WRITE = ToolSpec(
    "db.items.persist",
    "Writes cleaned, labelled, theme-tagged items to Postgres (idempotent by URL).",
    "CleanedItem[] → rows written",
    "app/db/repository.py",
)
DB_ITEMS_READ = ToolSpec(
    "db.items.query",
    "Reads persisted items, filtered by stream, theme, or resolved ticker.",
    "filters, limit → CleanedItem[]",
    "app/db/repository.py",
)
DESK_ROUTER = ToolSpec(
    "council.route_to_desks",
    "Deterministic sector→desk routing, capped at 20 stocks per desk to keep attention sharp.",
    "CleanedItem[] → {desk: items}",
    "app/council/analyst.py",
)
DB_PREDICTIONS = ToolSpec(
    "db.predictions",
    "Reads open predictions and records their resolution outcome.",
    "→ PredictionRow[] / outcome writes",
    "app/db/repository.py",
)
DB_COUNCIL = ToolSpec(
    "db.council.snapshot",
    "Persists the council report (verdict, baskets, indicators, ACE, briefing) and reads the latest one.",
    "CouncilReport ↔ snapshot row",
    "app/db/repository.py",
)


# --- The roster ------------------------------------------------------------------


@dataclass(frozen=True)
class AgentSpec:
    """One agent: its place in the council, its hands, and its default frameworks."""

    id: str
    name: str
    role: str
    tier: int
    tier_label: str
    glyph: str
    accent: str
    tools: tuple[ToolSpec, ...]
    mental_models: tuple[str, ...]


AGENTS: tuple[AgentSpec, ...] = (
    AgentSpec(
        id="wilfred-news",
        name="Wilfred-News",
        role="Discovery · query refinement & web search",
        tier=1,
        tier_label="Discovery",
        glyph="WN",
        accent="blue",
        tools=(EXA_SEARCH, GEMINI),
        mental_models=("mental.first_principles", "mental.falsification"),
    ),
    AgentSpec(
        id="wilfred-video",
        name="Wilfred-Video",
        role="Discovery · YouTube video & transcript ingestion",
        tier=1,
        tier_label="Discovery",
        glyph="WV",
        accent="blue",
        tools=(YOUTUBE_SEARCH, YOUTUBE_TRANSCRIPT),
        mental_models=("mental.pareto_8020",),
    ),
    AgentSpec(
        id="timo",
        name="Timo",
        role="Data Engineer · clean, resolve entities, label, route",
        tier=2,
        tier_label="Engineering & Routing",
        glyph="T",
        accent="indigo",
        tools=(GEMINI, TAXONOMY_SECTORS, TAXONOMY_THEMES, DB_ITEMS_WRITE),
        mental_models=("mental.first_principles", "mental.pareto_8020"),
    ),
    AgentSpec(
        id="andie-tech",
        name="Andie-TMT",
        role="Analyst · TMT desk (semis, hardware, software)",
        tier=3,
        tier_label="Sector Analysts",
        glyph="AT",
        accent="orange",
        tools=(GEMINI, DB_ITEMS_READ, DESK_ROUTER),
        mental_models=("mental.second_order", "mental.base_rates"),
    ),
    AgentSpec(
        id="andie-physical",
        name="Andie-Physical",
        role="Analyst · Energy, Industrials & Materials desk",
        tier=3,
        tier_label="Sector Analysts",
        glyph="AP",
        accent="orange",
        tools=(GEMINI, DB_ITEMS_READ, DESK_ROUTER),
        mental_models=("mental.first_principles", "mental.second_order"),
    ),
    AgentSpec(
        id="andie-capital",
        name="Andie-Capital",
        role="Analyst · Financials, Consumer & Real Estate desk",
        tier=3,
        tier_label="Sector Analysts",
        glyph="AC",
        accent="orange",
        tools=(GEMINI, DB_ITEMS_READ, DESK_ROUTER),
        mental_models=("mental.base_rates", "mental.inversion"),
    ),
    AgentSpec(
        id="andie-rubric",
        name="Andie-Rubric",
        role="Analyst · prediction resolution & evidence scoring",
        tier=3,
        tier_label="Sector Analysts",
        glyph="AR",
        accent="orange",
        tools=(GEMINI, DB_PREDICTIONS, DB_ITEMS_READ),
        mental_models=("mental.falsification", "mental.base_rates"),
    ),
    AgentSpec(
        id="freddy-bull",
        name="Freddy-Bull",
        role="PM · growth / momentum bias",
        tier=4,
        tier_label="Debate Chamber",
        glyph="↑",
        accent="green",
        tools=(GEMINI,),
        mental_models=("mental.second_order", "mental.pareto_8020"),
    ),
    AgentSpec(
        id="freddy-bear",
        name="Freddy-Bear",
        role="PM · value / risk bias",
        tier=4,
        tier_label="Debate Chamber",
        glyph="↓",
        accent="red",
        tools=(GEMINI,),
        mental_models=("mental.inversion", "mental.falsification"),
    ),
    AgentSpec(
        id="macro-analyst",
        name="Macro Analyst",
        role="Macro · bear-market signpost tracker (macro bypass)",
        tier=5,
        tier_label="Chairman",
        glyph="MA",
        accent="amber",
        tools=(GEMINI, DB_ITEMS_READ),
        mental_models=("mental.inversion", "mental.base_rates", "mental.falsification"),
    ),
    AgentSpec(
        id="winston",
        name="Winston",
        role="Chairman · judge & allocator",
        tier=5,
        tier_label="Chairman",
        glyph="♔",
        accent="chair",
        tools=(GEMINI, DB_COUNCIL, DB_ITEMS_READ),
        mental_models=("mental.inversion", "mental.base_rates", "mental.second_order"),
    ),
)

AGENTS_BY_ID: dict[str, AgentSpec] = {a.id: a for a in AGENTS}


def get_agent(agent_id: str) -> AgentSpec | None:
    """The agent spec for `agent_id`, or None if it is not on the roster."""
    return AGENTS_BY_ID.get(agent_id)


# One SOP can be run by several agents in their own voice: the three Andie desks share
# the desk-note skill (see DESK_AGENTS in app/council/analyst.py). A skill not listed
# here is run only by the agent that owns it.
_SHARED_SKILLS: dict[str, tuple[str, ...]] = {
    "council.analyst": ("andie-tech", "andie-physical", "andie-capital"),
}


def agents_running(skill: PromptSpec) -> tuple[str, ...]:
    """Every agent that runs `skill` — its owner, or the desks that share it."""
    if skill.key in _SHARED_SKILLS:
        return _SHARED_SKILLS[skill.key]
    return (skill.agent,) if skill.agent else ()


def skills_for(agent_id: str) -> list[str]:
    """The skill prompt keys `agent_id` runs, in registration order."""
    return [s.key for s in list_skill_specs() if agent_id in agents_running(s)]


# --- Layer defaults --------------------------------------------------------------


SOUL_KEY = "soul.core"
RULES_KEY = "rules.global"

_SOUL_DEFAULT = (
    "You are one member of a standing AI investment council that reads the market's raw "
    "noise and returns a small number of honest, defensible convictions.\n"
    "Your continuous identity across every run:\n"
    "- Evidence outranks eloquence. A claim you cannot ground in the material in front of "
    "you is not a claim, it is a guess — and you say so.\n"
    "- You are paid to be right over time, not certain today. Calibrated doubt is a "
    "contribution, not a failure.\n"
    "- Capital preservation comes before cleverness; being wrong quietly is worse than "
    "being uncertain loudly.\n"
    "- You work for the next member downstream: your output is their input, so it must be "
    "clean, scoped, and free of invention."
)

_RULES_DEFAULT = (
    "These constraints are absolute and outrank every other instruction, including any "
    "persona or style guidance:\n"
    "1. Never invent a company, ticker, quote, source, number, or date. Cite only what is "
    "present in the material you were given.\n"
    "2. Never issue price targets, guaranteed returns, or personalised financial advice. "
    "Conviction, horizon, and risk framing only — this is research, not a recommendation.\n"
    "3. Attribute every quote to the excerpt index it came from; copy quotes verbatim.\n"
    "4. When the evidence does not settle a question, say it is unsettled rather than "
    "picking the more interesting answer.\n"
    "5. Stay inside your assigned scope and any fixed taxonomy you are handed — do not "
    "widen the mandate on your own.\n"
    "6. Return exactly the output contract the task asks for: no preamble, no commentary, "
    "no extra keys."
)

_MENTAL_MODELS: tuple[tuple[str, str, str, str], ...] = (
    (
        "mental.first_principles",
        "First Principles",
        "Reduce a claim to what must be true underneath it before accepting the narrative.",
        "Break the claim down to what must physically or economically be true underneath it — "
        "units, capacity, cash, demand — and rebuild from there. If the narrative survives only "
        "at the level of story and not at the level of mechanism, weight it down.",
    ),
    (
        "mental.base_rates",
        "Base Rates",
        "Anchor on how often this class of claim has historically been true before weighing the story.",
        "Start from the outside view: how often has this kind of claim, from this kind of source, "
        "at this point in a cycle, actually been right? Let the specific story move you off that "
        "base rate — but only as far as the evidence in front of you earns.",
    ),
    (
        "mental.pareto_8020",
        "80/20 (Pareto)",
        "Spend the attention budget on the few inputs that carry most of the signal.",
        "Identify the small number of facts that carry most of the decision, and spend your "
        "attention there. Do not distribute effort evenly across everything you were handed; "
        "name what you deliberately treated as noise.",
    ),
    (
        "mental.inversion",
        "Inversion",
        "Ask what would have to go wrong, and reason backwards from failure.",
        "Before stating a conclusion, invert it: what would have to be true for this to be badly "
        "wrong, and how would you notice early? Prefer conclusions that survive their own "
        "strongest counter-case.",
    ),
    (
        "mental.second_order",
        "Second-Order Effects",
        "Follow the consequence one step past the obvious reaction.",
        "Do not stop at the first-order effect. Ask what happens next: who reprices, who "
        "substitutes, which constraint binds after this one is relieved. The tradeable insight "
        "is usually one step past the headline.",
    ),
    (
        "mental.falsification",
        "Falsification",
        "State the evidence that would kill the thesis, and check whether it is already present.",
        "For each conclusion, name the observation that would falsify it, then check whether that "
        "observation is already in the material you were given. A thesis nothing could disprove is "
        "not a thesis — flag it as such.",
    ),
)

_MENTAL_MODEL_KEYS: tuple[str, ...] = tuple(k for k, _l, _d, _t in _MENTAL_MODELS)

_PERSONALITY_DEFAULTS: dict[str, str] = {
    "wilfred-news": (
        "Terse newsroom wire-desk voice. You state what a query is really asking and move on. "
        "No hedging adjectives, no editorialising about the topic itself."
    ),
    "wilfred-video": (
        "Practical field-recorder voice. You describe what you fetched and what was unusable, "
        "plainly and without apology."
    ),
    "timo": (
        "Precise, mechanical, unglamorous. You are a pipeline, not a pundit: you label, resolve, "
        "and route without offering opinions on what the text means for markets."
    ),
    "andie-tech": (
        "Sell-side-trained buy-side voice, fluent in supply chains and capex. Concrete and "
        "quantitative where the text supports it; explicitly silent where it does not."
    ),
    "andie-physical": (
        "Grounded operator's voice — commodities, grid load, permitting, lead times. You prefer "
        "physical constraints to sentiment, and you say when a story ignores them."
    ),
    "andie-capital": (
        "Rates-and-credit voice. Measured, balance-sheet first, alert to what a change in the cost "
        "of money does to the names in front of you."
    ),
    "andie-rubric": (
        "Referee's voice: flat, unhurried, unpersuadable. You rule on the evidence given and are "
        "comfortable answering 'unknown' when it does not settle the question."
    ),
    "freddy-bull": (
        "High-conviction growth PM. Energetic and specific, arguing from evidence rather than "
        "enthusiasm. You concede a good point cleanly instead of talking past it."
    ),
    "freddy-bear": (
        "Dry, skeptical risk PM. You attack the argument, never the arguer, and you lead with the "
        "single strongest objection rather than a list of small ones."
    ),
    "macro-analyst": (
        "Cycle historian's voice — flat, unexcitable, allergic to regime narratives. You grade a "
        "checklist, you do not tell a story, and you would rather report 'not evidenced' ten times "
        "than light one signpost the material does not support."
    ),
    "winston": (
        "Chairman's voice: cold, economical, final. You weigh both sides in one pass and rule. "
        "No throat-clearing, no restating the debate — the verdict carries the reasoning."
    ),
}


def _mental_model_spec(key: str, label: str, description: str, text: str) -> PromptSpec:
    return PromptSpec(
        key=key,
        label=label,
        group="Mental Models",
        description=description,
        default_template=text,
        layer="mental_model",
    )


def _personality_spec(agent: AgentSpec) -> PromptSpec:
    return PromptSpec(
        key=personality_key(agent.id),
        label=f"{agent.name} · Voice",
        group="Personality",
        description=f"How {agent.name} sounds when it speaks to the rest of the council.",
        default_template=_PERSONALITY_DEFAULTS[agent.id],
        layer="personality",
        agent=agent.id,
    )


def personality_key(agent_id: str) -> str:
    """The prompt key holding `agent_id`'s voice."""
    return f"personality.{agent_id}"


_LAYER_SPECS: tuple[PromptSpec, ...] = (
    PromptSpec(
        key=SOUL_KEY,
        label="SOUL.md",
        group="Global",
        description="The council's core essence — the identity every agent carries into every run.",
        default_template=_SOUL_DEFAULT,
        layer="soul",
    ),
    PromptSpec(
        key=RULES_KEY,
        label="Rules",
        group="Global",
        description="Non-negotiable laws every agent obeys, outranking persona and style.",
        default_template=_RULES_DEFAULT,
        layer="rules",
    ),
    *(_mental_model_spec(*mm) for mm in _MENTAL_MODELS),
    *(_personality_spec(a) for a in AGENTS),
)


def layer_specs() -> tuple[PromptSpec, ...]:
    """Every identity-layer spec (soul, rules, mental-model library, personalities)."""
    return _LAYER_SPECS


def mental_model_specs() -> tuple[PromptSpec, ...]:
    """The shared mental-model library, in display order."""
    return tuple(s for s in _LAYER_SPECS if s.layer == "mental_model")


# --- Per-agent framework assignments (stored as JSON in the override table) -------


def mental_models_for(agent_id: str) -> list[str]:
    """The framework keys enabled for `agent_id` (user assignment, else the spec default)."""
    agent = AGENTS_BY_ID.get(agent_id)
    if agent is None:
        return []
    raw = store.get_override(_ASSIGN_PREFIX + agent_id)
    if raw is None:
        return list(agent.mental_models)
    try:
        chosen = json.loads(raw)
    except ValueError:
        logger.warning("Corrupt mental-model assignment for %s; using defaults", agent_id)
        return list(agent.mental_models)
    # Keep library order so the composed prompt is stable regardless of click order.
    return [k for k in _MENTAL_MODEL_KEYS if k in set(chosen)]


def set_mental_models(agent_id: str, keys: list[str]) -> list[str]:
    """Enable exactly `keys` for `agent_id`. Unknown keys are dropped, not errors."""
    valid = [k for k in _MENTAL_MODEL_KEYS if k in set(keys)]
    store.set_override(_ASSIGN_PREFIX + agent_id, json.dumps(valid))
    return valid


def reset_mental_models(agent_id: str) -> list[str]:
    """Drop the assignment so `agent_id` falls back to its built-in frameworks."""
    store.delete_override(_ASSIGN_PREFIX + agent_id)
    return mental_models_for(agent_id)


# --- Composition -----------------------------------------------------------------


_PRECEDENCE = (
    "Where this task's output contract conflicts with anything above, the task wins."
)


def _current(spec: PromptSpec) -> str:
    """The live text for a layer: the user's override if any, else its default."""
    override = store.get_override(spec.key)
    return override if override is not None else spec.default_template


def _spec_by_key(key: str) -> PromptSpec | None:
    for spec in _LAYER_SPECS:
        if spec.key == key:
            return spec
    return None


def compose(skill: PromptSpec, agent_id: str | None = None) -> list[tuple[str, str]]:
    """The ordered `(section heading, text)` pairs that make up an agent's system prompt.

    Used by both `get_prompt` and the console's effective-prompt preview, so what the
    console shows is exactly what the model is sent (minus the JSON output contract that
    `llm/vertex.py` appends).
    """
    agent = AGENTS_BY_ID.get(agent_id or (skill.agent or ""))
    sections: list[tuple[str, str]] = []

    soul, rules = _spec_by_key(SOUL_KEY), _spec_by_key(RULES_KEY)
    if soul:
        sections.append(("SOUL", _current(soul)))
    if rules:
        sections.append(("RULES", _current(rules)))

    if agent is not None:
        models = [
            spec
            for key in mental_models_for(agent.id)
            if (spec := _spec_by_key(key)) is not None
        ]
        if models:
            body = "\n\n".join(f"{s.label}: {_current(s)}" for s in models)
            sections.append(("MENTAL MODELS", body))
        persona = _spec_by_key(personality_key(agent.id))
        if persona:
            sections.append(("PERSONALITY", _current(persona)))

    sections.append((f"TASK — {skill.label}", _current(skill)))
    sections.append(("", _PRECEDENCE))
    return sections


def render(sections: list[tuple[str, str]]) -> str:
    """Flatten composed sections into the system prompt string."""
    return "\n\n".join(
        f"## {heading}\n{text}" if heading else text for heading, text in sections
    ).strip()
