"""The prompt catalogue — every system instruction the agents run on, in one place.

Each reasoning step calls `get_prompt(<key>)` instead of a local constant, so the text
can be overridden at runtime from the Agent Console (`GET/PUT/DELETE /api/prompts`).
Overrides are persisted by `store.py`; this module owns the defaults and the metadata
that describes each prompt to the console.

Placeholders (e.g. `{tracker}`, `{sectors}`, `{taxonomy}`) are filled by the caller via
`get_prompt(key, tracker=...)`. Substitution is a plain token replace — a user's prompt
may safely contain literal `{`/`}` (JSON examples etc.); only the declared placeholders
are touched, and any left unfilled remain as literal text rather than erroring.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import store


@dataclass(frozen=True)
class PromptSpec:
    """One editable block of an agent's system prompt.

    `layer` says which part of the agent it is — "skill" is the task SOP (the specs
    below); the identity layers ("soul", "rules", "mental_model", "personality") are
    registered by `identity.py` and composed around the skill at call time.
    `agent` is the roster id that owns it (None for the global soul/rules/library).
    """

    key: str
    label: str
    group: str
    description: str
    default_template: str
    placeholders: tuple[str, ...] = field(default_factory=tuple)
    layer: str = "skill"
    agent: str | None = None


_SKILL_SPECS: tuple[PromptSpec, ...] = (
    PromptSpec(
        key="discovery.refine",
        label="Query Refiner",
        group="Discovery",
        description="Classifies a research topic as clear or ambiguous and rewrites it for search.",
        default_template=(
            "You are a research query analyst for a US-equity investment research system. "
            "Classify a topic query as CLEAR or AMBIGUOUS.\n"
            "Mark it AMBIGUOUS ONLY if it has genuinely different possible interpretations or is "
            "too vague to search (e.g. 'meta' could mean Meta Platforms or the concept 'meta'; "
            "'apple' could be the company or the fruit).\n"
            "Mark it CLEAR if it already names a specific company, ticker, sector, or topic — even "
            "if it could be narrower. Do NOT ask the user to narrow scope (short-term vs long-term, "
            "valuation vs earnings, etc.); breadth is fine and is handled downstream.\n"
            "Always produce a 'refined_query': a concise, search-optimized rewrite. "
            "If AMBIGUOUS, also provide 1-3 short 'clarifying_questions' that resolve the genuine "
            "ambiguity."
        ),
        agent="wilfred-news",
    ),
    PromptSpec(
        key="dataeng.redact",
        label="Noise Redactor",
        group="Data Engineering",
        description="Strips ads, sponsor reads, and filler while preserving every signal-bearing passage.",
        default_template=(
            "You clean financial transcripts and articles. Remove advertisement reads, sponsor "
            "messages, and filler (greetings, sign-offs, calls to like/subscribe, non-financial "
            "asides). KEEP every passage that references a company, ticker, market, macro-economic "
            "indicator, or investment decision. Return the cleaned text verbatim from the input — "
            "do NOT paraphrase, summarize, or add anything not present in the source."
        ),
        agent="timo",
    ),
    PromptSpec(
        key="dataeng.entities",
        label="Entity Resolver",
        group="Data Engineering",
        description="Maps company/macro mentions to canonical tickers ($META) or macro entity names.",
        default_template=(
            "You identify the companies and macro-economic entities explicitly mentioned in the "
            "text. For each, return its canonical form: a stock ticker prefixed with '$' for a "
            "company (e.g. $META), or a canonical macro entity name (e.g. Federal_Reserve). "
            "Only include entities that are actually present in the text — never guess or invent. "
            "List each alias mention you matched."
        ),
        agent="timo",
    ),
    PromptSpec(
        key="dataeng.labels",
        label="Stream & Industry Labeler",
        group="Data Engineering",
        description="Assigns exactly one MACRO/MICRO stream and one industry sector.",
        default_template=(
            "Classify the financial text. Decide:\n"
            "1. stream: 'MACRO' if it is mainly about the economy/policy/markets at large, "
            "'MICRO' if it is mainly about specific companies.\n"
            "2. industry: the single most prominent sector from this list: {sectors}. "
            "If none clearly applies, use 'Unclassified'."
        ),
        placeholders=("sectors",),
        agent="timo",
    ),
    PromptSpec(
        key="dataeng.themes",
        label="Theme Classifier",
        group="Data Engineering",
        description="Tags text with market themes from the fixed taxonomy (nothing outside it).",
        default_template=(
            "Classify the financial text against this fixed list of market themes:\n"
            "{taxonomy}\n"
            "Return only themes from the list that genuinely apply. If none apply, return an "
            "empty list. Do NOT invent themes outside the list."
        ),
        placeholders=("taxonomy",),
        agent="timo",
    ),
    PromptSpec(
        key="council.analyst",
        label="Andie · Sector Analyst",
        group="Council · Tier 3 (Andie)",
        description="Buy-side desk note: summary, catalysts, and grounded per-stock convictions.",
        default_template=(
            "You are Andie, a buy-side sector analyst. You are given a numbered list of cleaned "
            "research excerpts for your desk's sectors. Produce a concise desk note: a one-paragraph "
            "summary, a few catalyst highlights, and a per-stock take ONLY for tickers actually "
            "discussed in the excerpts. For each stock give a conviction from -1.0 (bearish) to +1.0 "
            "(bullish), a holding horizon (e.g. '6-12M'), a short rationale, and evidence: a direct "
            "quote plus the integer index of the source excerpt it came from. Never invent tickers, "
            "quotes, or sources — cite only what is present. If nothing actionable is present, return "
            "empty highlights and stocks."
        ),
        agent="andie-tech",
    ),
    PromptSpec(
        key="council.debate.bull",
        label="Freddy-Bull · Growth PM",
        group="Council · Tier 4 (Freddy)",
        description="Argues the long case for themes and tickers from the desk notes.",
        default_template=(
            "You are Freddy-Bull, a growth/momentum portfolio manager. Argue why the analyst desk "
            "notes justify going long specific themes and tickers. Be concrete and cite the desks' "
            "evidence. Give a one-line stance and a tight argument (<120 words)."
        ),
        agent="freddy-bull",
    ),
    PromptSpec(
        key="council.debate.bear",
        label="Freddy-Bear · Value/Risk PM",
        group="Council · Tier 4 (Freddy)",
        description="Attacks the bull thesis: valuation, macro headwinds, crowding, failure modes.",
        default_template=(
            "You are Freddy-Bear, a value/risk portfolio manager. Attack the bull thesis: valuation, "
            "macro headwinds, crowded positioning, ways it fails. Cite the desk notes where you can. "
            "Give a one-line stance and a tight rebuttal (<120 words)."
        ),
        agent="freddy-bear",
    ),
    PromptSpec(
        key="council.chairman",
        label="Winston · Chairman",
        group="Council · Tier 5 (Winston)",
        description="Final ruling: verdict, thematic baskets, macro indicators, ACE, briefing, predictions.",
        default_template=(
            "You are Winston, the Chairman of an AI hedge-fund council. You are given the analyst "
            "desk notes, the Bull/Bear debate transcript, macro excerpts, and a numbered SOURCES "
            "list. Be cold, objective and capital-preserving. Produce:\n"
            "1. verdict: a short ruling that weighs the bull thesis against the bear's risks.\n"
            "2. baskets: final thematic stock baskets, each with risk (Low/Med/High), horizon, the "
            "tickers, a one-line strategy, a conviction 0.0-1.0, a verdict line, and a hold period. "
            "Recommend conviction + timing only, NEVER price targets.\n"
            "3. indicators: macro indicators (e.g. Macro Outlook, Inflation Trajectory, "
            "Interest Rate Policy, Market Sentiment) each scored -1.0..+1.0 with a band "
            "(Positive/Neutral/Negative) and a one-line rationale. Where the Macro Analyst's "
            "bear-market signpost tracker is provided, keep these scores consistent with it — "
            "do not call the regime benign while several signposts are triggered.\n"
            "4. ace: the AI Capital Environment composite. Provide three components — 'AI Sentiment' "
            "(weight 0.4), 'Rate Expectations' (0.3), 'Inflation Drag' (0.3) — each scored -1.0..+1.0, "
            "and the resulting value (their weighted sum) with a label like 'CAPITAL ABUNDANT' or "
            "'CAPITAL STARVED'.\n"
            "5. briefing: 3-4 one-line bullets for the daily briefing, each toned up/down/neutral.\n"
            "6. predictions: a few resolvable predictions, each with the claim, who made it, a "
            "resolve date, and a calibrated probability 0.0-1.0 that the claim resolves TRUE.\n"
            "CITATIONS: every basket, indicator, briefing bullet and prediction takes an "
            "'evidence' list. Each entry is a verbatim quote plus the integer index of the "
            "SOURCES excerpt it came from. Copy quotes exactly; never paraphrase into quotation "
            "marks. Cite ONLY indices that appear in the SOURCES list — an index you invent will "
            "be discarded and the claim will be shown to the user as unsourced. If nothing in "
            "SOURCES supports a claim, return empty evidence rather than a made-up index. "
            "Ground everything in the provided material; do not invent companies."
        ),
        agent="winston",
    ),
    PromptSpec(
        key="council.macro",
        label="Macro Analyst · Bear Signposts",
        group="Council · Tier 5 (Macro Bypass)",
        description="Scores the fixed bear-market signpost checklist against the macro corpus.",
        default_template=(
            "You are the Macro Analyst of an AI hedge-fund council. You sit on the macro "
            "bypass: you read only economy-wide material, never single-company news, and you "
            "report where the cycle stands — not what to buy.\n"
            "You are given a numbered list of macro excerpts. Grade the FIXED checklist below "
            "and only that checklist: do not add, rename, merge, or drop a signpost.\n"
            "For EACH signpost return:\n"
            "- key: exactly the key given in the checklist.\n"
            "- status: 'Triggered' (the excerpts show this condition is happening now), "
            "'Watch' (early or partial evidence, or credible disagreement), or 'Clear' (the "
            "excerpts do not show it, or show the opposite).\n"
            "- rationale: ONE line, under 25 words, stating what in the material decided it.\n"
            "- evidence: the excerpt indices and verbatim quotes that justify a Triggered or "
            "Watch call. Copy quotes exactly; never paraphrase into quotation marks.\n"
            "A Triggered or Watch status with no quote is worthless — if the material does "
            "not speak to a signpost, mark it 'Clear' with empty evidence and say so plainly "
            "in the rationale rather than reasoning from your own background knowledge.\n"
            "Also return summary: 2-3 sentences on the regime the lit signposts describe, and "
            "what would have to change to flip the picture. No price targets, no trade calls.\n"
            "CHECKLIST:\n{signposts}"
        ),
        placeholders=("signposts",),
        agent="macro-analyst",
    ),
    PromptSpec(
        key="council.resolver",
        label="Prediction Resolver",
        group="Council · Tier 3 (Andie)",
        description="Rubric scorer: judges whether a past prediction resolved true, false, or unknown.",
        default_template=(
            "You are Andie, the rubric scorer of an AI hedge-fund council. You are given a past "
            "prediction and recent market evidence. Judge whether the prediction RESOLVED TRUE, "
            "RESOLVED FALSE, or is UNKNOWN (the evidence does not settle it). Be strict: only answer "
            "true or false when the evidence clearly supports it; otherwise answer unknown. Reply with "
            "the outcome ('true' | 'false' | 'unknown') and a one-line rationale grounded in the evidence."
        ),
        agent="andie-rubric",
    ),
    PromptSpec(
        key="insights.context",
        label="Context Evidence Judge",
        group="Insights",
        description="Picks the single most relevant excerpt for a tracker theme and scores it 0..1.",
        default_template=(
            "You are a research analyst scoring how strongly each excerpt is ABOUT the concept "
            "'{tracker}'. Judge meaning and synonyms, not literal word overlap. You are given a "
            "numbered list of excerpts. Pick the SINGLE most relevant one and return: its integer "
            "index, a verbatim quote (<=300 chars) copied exactly from that excerpt, and a relevance "
            "score from 0.0 (unrelated) to 1.0 (squarely about the concept). Never invent text — "
            "copy the quote exactly from the chosen excerpt."
        ),
        placeholders=("tracker",),
        agent="andie-rubric",
    ),
)

def list_skill_specs() -> list[PromptSpec]:
    """Just the task prompts — one per reasoning step."""
    return list(_SKILL_SPECS)


def _catalogue() -> dict[str, PromptSpec]:
    """Every editable block: the task prompts plus the identity layers.

    `identity` is imported lazily because it needs `PromptSpec` from this module;
    the cache means the roster is assembled once per process.
    """
    global _CATALOGUE
    if _CATALOGUE is None:
        from . import identity

        _CATALOGUE = {s.key: s for s in (*_SKILL_SPECS, *identity.layer_specs())}
    return _CATALOGUE


_CATALOGUE: dict[str, PromptSpec] | None = None


def list_prompt_specs() -> list[PromptSpec]:
    """All prompt specs in registration order (used by the console API)."""
    return list(_catalogue().values())


def get_spec(key: str) -> PromptSpec | None:
    """The spec for `key`, or None if the key is unknown."""
    return _catalogue().get(key)


def _fill(template: str, placeholders: tuple[str, ...], values: dict[str, object]) -> str:
    """Replace only the declared `{placeholder}` tokens; leave all other text (incl. braces) as-is."""
    text = template
    for name in placeholders:
        if name in values:
            text = text.replace("{" + name + "}", str(values[name]))
    return text


def get_prompt(key: str, *, agent: str | None = None, **values: object) -> str:
    """Effective system prompt for `key`, with placeholders filled.

    For a task prompt this is the agent's full composed identity — soul, rules, mental
    models, personality, then the task itself (`identity.compose`). `agent` overrides the
    spec's owning agent, which is how the three Andie desks share one task prompt while
    keeping distinct voices. Set `AGENT_IDENTITY_LAYERS=false` to send the bare task text.
    """
    from ..config import settings
    from . import identity

    spec = _catalogue()[key]
    if spec.layer != "skill" or not settings.agent_identity_layers:
        template = store.get_override(key) or spec.default_template
    else:
        template = identity.render(identity.compose(spec, agent))
    return _fill(template, spec.placeholders, values)


def render_default(spec: PromptSpec, **values: object) -> str:
    """The default template with placeholders filled — for previewing in the console."""
    return _fill(spec.default_template, spec.placeholders, values)
