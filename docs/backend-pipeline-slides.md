# Backend Pipeline — Presentation Deck

> Speaker notes: the backend is a 4-stage agent pipeline. Each stage mixes
> deterministic **processing** with LLM-powered **agentic reasoning**. Every
> LLM call goes through one Bedrock gateway with schema validation + retries.

---

## Slide 1 — The Big Picture

**A hedge-fund "AI council" pipeline**

```
Topic Query
   │
   ▼
[1] Discovery        → find & normalize sources
   │
   ▼
[2] Data Engineering → clean, label, persist
   │
   ▼
[3-5] The Council    → analyze, debate, rule
   │
   ▼
Persisted Snapshot   → baskets, briefing, predictions
```

- User picks the **topic**. The agents pick the **sources, labels, and verdict**.
- Each stage is fault-isolated — a failure downstream never breaks what came before.

---

## Slide 2 — Layer 1: Discovery

**Goal: turn one topic query into a clean set of source items.**

Agentic step
- **Query Refinement** (1 LLM call): classify CLEAR vs AMBIGUOUS, rewrite into a
  search-optimized query, ask clarifying questions if genuinely ambiguous.

Processing steps
- **Parallel fan-out** to source branches (web via Exa, video via YouTube).
- **Fault isolation**: an unavailable source is recorded as "skipped", not fatal.
- **Normalize** every hit into a uniform `SourceItem`.
- **Deduplicate** by URL.

> Output: `DiscoveryResult` (items + skipped sources + query audit trail)

---

## Slide 3 — Layer 2: Data Engineering

**Goal: clean, label, and persist each item. Items are independent —
one failure never halts the batch.**

Per item, in order:

```
redact → resolve entities → label → theme → guardrail → persist
```

Agentic steps (LLM)
- **Redact** — strip ads/filler, keep all financial signal.
- **Resolve Entities** — slang/aliases → canonical tickers (dictionary first, then LLM).
- **Label** — exactly one MACRO/MICRO stream + one industry.
- **Theme** — tag against a fixed market-theme taxonomy.

Processing steps
- **Guardrail** — anti-hallucination: cleaned text must be grounded in the source.
- **Persist** — idempotent upsert keyed on URL (one row per source).

> Output: `DataEngReport` (persisted / failed counts + per-item failures)

---

## Slide 4 — The Council: A Strict Agent DAG

**Tiers 3 → 4 → 5 run over the persisted corpus. Each tier waits on the previous.**

```
        MICRO items                         MACRO items
            │                                    │
            ▼                                    │
[3] Andie desks (fan-out, parallel)             │  (macro bypass)
            │                                    │
            ▼                                    │
[4] Freddy debate (Bull vs Bear)                │
            │                                    │
            └──────────────┬─────────────────────┘
                           ▼
              [5] Winston, the Chairman (fan-in)
                           │
                           ▼
                    Council Snapshot
```

> MACRO items skip the analysts and route straight to the Chairman.

---

## Slide 5 — Tier 3: Andie (Sector Analysts)

**Three desks, each covering disjoint sectors, run in parallel.**

- **TMT** · **Physical** · **Capital** — each capped at 20 stocks to keep the model focused.
- Each desk reads only MICRO items for its sectors.
- Produces a desk note: summary, catalyst highlights, and per-stock take.
- Each stock gets a **conviction** (-1.0 bearish → +1.0 bullish), horizon, and rationale.

No-orphan guardrail
- Every conviction must cite a **real source quote** mapped back to a given item.
- Ungrounded stock takes are dropped.

---

## Slide 6 — Tier 4: Freddy (Bull vs Bear Debate)

**Two adversarial personas argue for 3 rounds so the model can't rubber-stamp itself.**

```
R1  Bull proposes the trade
R2  Bear attacks the thesis
R3  Bull defends or adjusts
```

- Bull and Bear run on **different model families** (Claude Opus vs Amazon Nova Pro)
  to curb collusion.
- Full transcript is logged and handed up to the Chairman.

---

## Slide 7 — Tier 5: Winston (The Chairman)

**Reads the debate transcript + macro items, then issues the final ruling.**

One LLM call produces:
- **Verdict** — weighs the bull thesis against the bear's risks.
- **Baskets** — thematic stock baskets with risk, horizon, conviction, hold period
  (conviction + timing only, never price targets).
- **Indicators** — macro signals (e.g. Inflation, Rate Policy) scored -1.0…+1.0.
- **ACE composite** — AI Capital Environment index (weighted sentiment + rates + inflation).
- **Briefing** — 3-4 daily one-liners.
- **Predictions** — resolvable claims with a resolve date.

> Output: `CouncilReport`, persisted as the latest snapshot.

---

## Slide 8 — Cross-Cutting Infrastructure

**One LLM gateway** (`llm/bedrock.py`)
- Single Bedrock `converse` call per reasoning step.
- Output constrained to JSON, validated against a Pydantic schema.
- Retries with exponential backoff; distinguishes schema vs transient failures.

**Real-time progress** (`events.py` + `sse.py`)
- Every stage emits progress events.
- Streamed live to the UI via Server-Sent Events.
- Reconnectable jobs let a reloaded client rejoin a run mid-flight.

---

## Slide 9 — Summary: Processing vs Agentic

| Stage | Agentic (LLM reasoning) | Deterministic processing |
|-------|-------------------------|--------------------------|
| Discovery | Query refinement | Parallel fan-out, dedupe, normalize |
| Data Engineering | Redact, entities, labels, themes | Guardrail, idempotent persist |
| Tier 3 — Andie | Per-desk sector analysis | Routing, source grounding |
| Tier 4 — Freddy | Bull/Bear debate | Round orchestration, transcript |
| Tier 5 — Winston | Verdict, baskets, indicators | Clamping, snapshot persistence |

**Takeaway:** agents do the judgment; deterministic code guarantees provenance,
isolation, and storage.
```
