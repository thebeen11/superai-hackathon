# Build Plan — Hedge Fund AI Agent Council

> The actionable, digestible companion to [`PROJECT_GUIDANCE.md`](./PROJECT_GUIDANCE.md).
> That doc says **what** and **why**; this doc says **in what order** and **how to
> not drown** during the hackathon.

---

## TL;DR — the mental model

It's a small hedge fund with **5 departments**. Data flows up; at Layer 2 it splits
into **MACRO** (→ dashboard) and **MICRO** (→ stock picks).

```text
SOURCES → [1] Discovery → [2] Data Eng ─┬─ MICRO → [3] Analysts → [4] Managers ─┐
                                        │                                       │
                                        └─ MACRO ───────────────────────────────┤
                                                                                ▼
                                                                        [5] Chairman → UI
```

| # | Department | Agents | Job |
|---|-----------|--------|-----|
| 1 | Discovery | Wilfred-YT / -Web | Given a topic, find & fetch sources — Exa (web) + YouTube transcripts |
| 2 | Data Eng | Timo | Clean, label (MACRO/MICRO/INDUSTRY), assign themes |
| 3 | Analysts | Andie ×3 pods (20 cos each) | Write per-company highlights from MICRO data |
| 4 | Managers | Freddy ×2–3 | Build baskets + holding periods, run LLM debate |
| 5 | Chairman | Freddy | Judge debates, build final portfolio, fill MACRO dashboard |

**Output rule (Option A):** conviction + holding period + evidence. **No price targets.**

**Hosting:** backend = **AWS only** (Bedrock, Step Functions, Fargate, Aurora,
OpenSearch Serverless, S3). Frontend = **Vercel** + **Vercel AI Gateway**.

---

## AWS architecture at a glance

```text
                         ┌──────────────── VERCEL ────────────────┐
                         │  Next.js + Tailwind + Tremor            │
                         │  Vercel AI Gateway (chat, follow-ups)   │
                         └───────────────────┬─────────────────────┘
                                             │ HTTPS
                         ┌───────────────────┴─────────────────────┐
                         │  Amazon API Gateway + Lambda  (AWS)      │
                         └───────────────────┬─────────────────────┘
                                             │
   EventBridge Scheduler ──▶ Step Functions / Lambda + ECS Fargate (the 5 layers)
                                             │
   ┌──────────────┬─────────────────┬────────┴────────┬──────────────────┐
   ▼              ▼                 ▼                 ▼                  ▼
 Amazon S3   Aurora Serverless   OpenSearch        Amazon Bedrock     Amazon
 (raw +      v2 (Postgres:       Serverless        (Claude / Nova /   Transcribe
 cleaned)    relational data)    (vectors) +       Llama + Titan      (audio →
                                 Knowledge Bases    embeddings)        text)
                                                    + debate models
   SQS (job queue) · EventBridge (events) · Secrets Manager (Barron's cookies)
   External: Polygon.io / yfinance (market data)
```

**One-line rule of thumb:** anything that *thinks* → **Bedrock**; anything *stored* →
**S3 / Aurora / OpenSearch**; anything *scheduled or event-driven* → **EventBridge
(+ SQS + Step Functions)**; anything the *user clicks* → **API Gateway**; anything
*conversational in the UI* → **Vercel AI Gateway**.

---

## Agent framework — DECISION

**Locked:** **plain Python + the Bedrock `converse` API (boto3)** for all reasoning
layers, with **LangGraph used *only* for the debate → chairman loop** if/when that
loop needs explicit state and a stop condition. **No general agent framework.**

Why:
- Most of the pipeline is a **deterministic flow** (fan-out, clean, score, synthesize),
  not open-ended agent autonomy — plain functions + loops are faster and easier to debug
  under hackathon time pressure.
- Bedrock `converse` gives a single, AWS-native call for every model (Claude, Nova,
  Llama); **Pydantic** enforces structured JSON output.
- The one genuinely agentic part — the **bull-vs-bear debate** — is where a state graph
  earns its keep (explicit rounds + a guaranteed termination), so LangGraph is scoped to
  *just that* via `langchain-aws`.

Conventions per layer:
- **Reasoning layers** (Analyst, Manager, Chairman) → a shared `bedrock.converse()`
  wrapper + a Pydantic schema per output.
- **Non-reasoning plumbing** (Discovery fan-out/merge/dedupe, Data Eng plumbing) → plain
  Python, **no LLM framework** (Discovery's fan-out is already built this way: a
  `ThreadPoolExecutor` fan-out). Discovery additionally has **one** LLM-backed step — the
  query refinement/clarification skill — via `bedrock.converse()` + a Pydantic schema.
- **Debate loop** → LangGraph nodes (bull / bear / chairman) with a round cap.

> Supersedes the earlier "LangGraph / AutoGen" note. AutoGen and Bedrock AgentCore were
> considered and dropped as too heavy for the MVP.

---

## Hackathon MVP scope (build THIS first)

> The 5-department design above is the **north star**. For the hackathon we build a
> deliberately shrunk version that tells the **same story end-to-end** without the
> infrastructure that only matters at scale. Everything cut here is recoverable later.

### Agents — "1 prompt per role, looped"

An agent is **a system prompt + a model + tools**, not a deployed service. The "role"
lives in the prompt. So we ship **4 prompts total** and call them in loops:

| Role | Prompt file | How it runs in the MVP |
| ---- | ----------- | ---------------------- |
| Discovery | `data-analyst.md` | One agent that **fans out a single query** to Exa (web) + YouTube (transcripts) |
| Data Eng | `data-engineer.md` | One cleaner/labeller, called per transcript |
| Analyst | `investment-analyst.md` | One prompt, **looped over ~8 companies** (not 60 across 3 pods) |
| Manager | `investment-manager.md` | One prompt, builds 1–2 baskets from the ~8 reports |
| Chairman | `investment-chairman.md` | One prompt, runs once → verdict + final portfolio |

```python
# The "council of analysts" is a loop, not 60 services.
analyst_prompt = load_prompt("andie.md")
reports = [bedrock_call(analyst_prompt, transcripts_for(co)) for co in watchlist]  # ~8 cos
```

> Scale-up path: split `investment-analyst.md` into the 3 specialized pods and grow
> the watchlist back to 60. The UI and data flow already look like a council, so
> nothing visible changes.

### Scope cuts vs the north star

| Concern | North star | **Hackathon MVP** |
| ------- | ---------- | ----------------- |
| Vectors / RAG | OpenSearch + Titan embeddings + Knowledge Bases | **Plain Postgres** + LLM does semantic matching; FTS (`tsvector`) for literal filtering |
| Transcription | Amazon Transcribe + `yt-dlp` | **YouTube captions** via `youtube-transcript-api` (no audio, no Transcribe) |
| Data sources | YouTube + Exa + Barron's | **One topic query → fans out to Exa (web) + YouTube (transcripts)**; Barron's dropped |
| Input model | Paste specific URLs / channels | **Single research-topic query**; Discovery finds the sources itself |
| Orchestration | Step Functions + Fargate + SQS + EventBridge | **One FastAPI service + a "Run" button**; plain Python + Bedrock `converse` (LangGraph only for the debate) |
| Database | Aurora Serverless v2 | **RDS Postgres** (single small instance) |
| Compute | Lambda + Fargate | **AWS App Runner** (or 1 small EC2) |
| Companies | 60 (3 pods × 20) | **~8**, chosen to tell one clean thematic story |
| Debate | 2 models × 3 rounds, every basket | Keep as the **"wow" feature**: 2 Bedrock models, **1–2 rounds, top basket only** |
| Multi-user / auth | Yes | **Single user, no auth** |
| Deferred polish | — | Skip: 15-tracker limit, Prediction Ledger, What-If, freshness badges (just show a timestamp) |

### MVP demo flow (still complete)

One topic query → Discovery fans out to **Exa (web) + YouTube (transcripts)** → clean &
label → analyst writes highlights for ~8 companies → manager builds a basket with a
holding period → **two Bedrock models debate** → chairman picks the final portfolio →
dashboard renders it, and **every claim links to its source quote**.

> Keep `backend = AWS only`: the MVP still runs on **App Runner + RDS + Bedrock**
> (+ S3 optional). It just uses ~3 AWS services instead of ~10.

---

## Frontend — what the user sees

The user is **"the Commander"**: they don't operate the agents, they read what the
council produced and steer it. Every screen surfaces signal **and lets you audit it** —
every number, quote, or pick links back to a source quote at a timestamp.

### MVP: 3 screens + 1 input (the demo critical path)

**Screen 1 — Command Center** (landing)
- Chairman's short briefing at the top.
- **Thematic portfolio cards** (e.g. "AI-Buildout Memory: Micron, SK Hynix, Nvidia"),
  each showing **conviction** (High/Med/Low) + **holding period** (short/med/long).
- A simple "last synced" timestamp (full freshness badges deferred).

**Screen 2 — Recommendation detail** (the money shot — proves it's not a black box)
- The analyst highlights for that company.
- The **bull-vs-bear debate** between the two Bedrock models, shown as two columns.
- The **Chairman's verdict** (`APPROVE / REJECT / RESIZE`) + reasoning.
- **Human override (HITL):** right beside the verdict, the user can **Approve / Reject /
  Resize** the Chairman's pick. The human is the final arbiter — their decision is what
  enters the portfolio, and it's recorded alongside the AI verdict for the audit trail.
- **Evidence quotes** with "Go to Source" links — web articles (Exa) deep-link to the
  page; videos (YouTube) jump to the exact `HH:MM:SS` timestamp.

**Screen 3 — Backtest Sandbox** (the visual close)
- Pick a theme, set "$10k, N months ago" → equity curve vs **S&P 500** with ROI +
  max drawdown.

**Topic input** (lightweight, replaces full Source & Agent Management)
- A single box for a **research topic** (e.g. "AI memory chip demand") + a **"Run council"**
  button. Discovery fans the query out to **Exa (web) + YouTube (transcripts)** — the
  user picks the *topic*, the agent picks the *sources*.
- A status line ticks through the layers (incl. the Exa/YouTube fan-out) so judges
  watch data flow live.

### MVP demo arc (as the user experiences it)

Type a **research topic** → hit **Run** → watch Discovery fan out to **Exa + YouTube**
and the status tick through the layers → land on the **Command Center** with fresh
portfolio cards → click one to read the **analyst notes, the debate, and the chairman's
verdict with source quotes** → **approve / reject / resize the pick yourself** → jump to
the **Backtest** to see what that (human-approved) theme would've returned. ~3 clicks.

### Full page map (north star — see `PROJECT_GUIDANCE.md` §8)

| Page | In MVP? |
| ---- | ------- |
| 1. Command Center (dashboard) | ✅ Screen 1 |
| 2. Signal & Tracker Terminal (keyword graphs + heatmap) | ⛔ deferred |
| 3. Thematic Portfolio & Backtest Sandbox | ✅ Screens 2 + 3 |
| 4. Source & Agent Management (source chat, cron editor, Prediction Ledger) | ⚠️ reduced to the topic input |
| 5. Financial Indicator Dashboard (MACRO stream) | ⛔ deferred |

---

## Decision Points (autonomy & reasoning)

The pipeline isn't just plumbing — at each layer an agent makes a **judgment call**.
These are the autonomous decisions to surface in the pitch and demo.

| Agent | Decision it makes | What drives it | Output |
| ----- | ----------------- | -------------- | ------ |
| **Discovery** | Which sources answer this topic, and are they new enough? | The query + Exa/YouTube results, publish date, dedupe against seen URLs | Fan out to Exa + YouTube; ingest or skip each hit |
| **Data Eng** | Is this MACRO or MICRO? Which INDUSTRY/theme? | Entities + topics in the transcript | Routing label → which analyst gets it |
| **Analyst** | How does this evidence score against each rubric? | User indicator + the quote, with required citation | `{indicator, score −1..1, reasoning, timestamp}` |
| **Analyst** | What are the 2nd/3rd-order effects? | n-order reasoning: `If X → Y impacted → action Z` | Investment highlights |
| **Manager** | Which stocks group into one coherent basket? | Correlation + shared thesis across the ~8 reports | Theme + holding period |
| **Manager (debate)** | Does the bull or bear case hold up? | 2 models argue across rounds | Debate transcript |
| **Chairman** | Approve / Reject / Resize each pick? | Debate outcome, conviction, **freshness-weighted** evidence | Verdict per stock |
| **Chairman** | Break ties / down-weight stale data | Round cap reached, or evidence past freshness threshold | Final (pre-human) portfolio |

**Reasoning patterns in play:** rubric-based scoring, n-order ("If X → Y → Z") thinking,
multi-model **debate** as a stress test, and an **evidence-or-discard** rule (no claim
survives without a source + timestamp).

> Pitch line: *"Every box in the pipeline is a decision, not a transform — the system
> reasons about relevance, routing, scoring, second-order effects, and conviction,
> and it has to cite its evidence to act on any of them."*

---

## Human-in-the-Loop

The user is the **final arbiter above the Chairman** — the AI proposes, the human disposes.

- **Approve / Reject / Resize a pick.** On the recommendation detail screen, after the
  debate and the Chairman's verdict, the user makes the final call. Their decision (not
  the Chairman's) is what enters the portfolio.
- **Auditability.** Both the AI verdict and the human override are stored together, so
  the trail always shows *what the AI recommended* vs *what the human decided*.
- **Topic control (MVP).** The user enters the **research topic**; Discovery decides
  which web + video sources to pull.
- **Scale-up:** editing rubrics, resolving predictions, and tuning ACE Index weights.

> Pitch line: *"The council does the research and argues it out, but you sign off on
> every position."* — covers the Human-in-the-Loop criterion directly.

---

## Failure Handling

How the system recovers from errors and unexpected states. Several of these reframe
guardrails we already designed as explicit recovery mechanisms.

| Failure mode | Recovery behaviour |
| ------------ | ------------------ |
| **Transcript fetch fails** (no captions / API error) | Retry once → skip the source and log a reason; the run continues with what it has |
| **LLM returns invalid JSON** | `JSON_Schema_Enforcer` rejects it → retry with a stricter prompt; after N retries, mark the item `FAILED` and surface it |
| **Hallucination / unsupported claim** | **No orphan data:** any quote/score lacking a `source_url` + `timestamp` is dropped before it reaches the user |
| **Debate doesn't converge** | Cap at the configured rounds; the **Chairman breaks the tie** and the human can still override |
| **No data for a company** | Skip with a logged "insufficient evidence" note rather than fabricating a view |
| **Stale evidence** | Chairman **down-weights** data past the freshness threshold; staleness shown in the UI |
| **Market-data (backtest) API down** | Show last cached curve or a clear "data unavailable" state — never a fake chart |

> Pitch line: *"Every claim is sourced or it's discarded, and the system degrades
> gracefully — it skips and logs rather than inventing."*

---

## Build order — vertical slice first

Do **not** build all 5 layers wide at once. Prove one thin path end-to-end, then widen.

### Milestone 0 — Scaffolding
- [x] Backend skeleton (`backend/`): **FastAPI**, managed with **uv** (`pyproject.toml`); env-backed config. _(Deploy target: App Runner; north star Lambda + API Gateway.)_
- [ ] **AWS foundation (MVP):** **RDS Postgres** + Bedrock model access enabled; S3 bucket optional.
      _(North star adds OpenSearch Serverless + Aurora Serverless v2.)_
- [ ] DB schema v1 (Postgres): `sources`, `transcripts`, `companies`, `analyst_reports`,
      `baskets`, `debates`, `portfolio`. _(No `chunks` table in the MVP — no embeddings.)_
- [ ] Frontend skeleton (`frontend/`) on **Vercel**: app shell + one page reading a mock API.
- [ ] Wire **Vercel AI Gateway** (AI SDK) with a "hello" chat call.
- [ ] Shared types / API contract between backend and frontend.

### Milestone 1 — The vertical slice (ONE path, end to end)
Goal: a single rendered recommendation that flows through every layer.
- [~] **Layer 1 — Discovery (in progress):** topic query fans out to **Exa (web)** + **YouTube transcripts** in parallel, merges + dedupes, skips-with-reason. Built behind `/discover` + a CLI. **TODO:** plug in API keys and validate against live results.
- [ ] **Layer 2:** Timo — clean + label MACRO/MICRO/INDUSTRY; store transcript/article rows in **Postgres** (no embedding).
- [ ] **Layer 3:** the analyst prompt — looped over **~8 companies** to produce highlights (**Bedrock** Claude).
- [ ] **Layer 4:** the manager prompt — produce one thematic basket + holding period.
- [ ] **Layer 5:** chairman — pass-through verdict + render one recommendation in UI.
- [ ] **Failure handling baseline:** retry-once-then-skip on fetch errors; enforce JSON schema on LLM output; drop any claim without a `source_url` + `timestamp`.
- [ ] **Demo check:** click recommendation → see evidence quote + jump-to-timestamp.

### Milestone 2 — Widen the intake
- [ ] Complete the **fan-out**: run Exa (web) and YouTube (transcripts) branches in parallel from the one query, then merge into the transcript pool.
- [ ] Grow the watchlist (MVP stays ~8; north star = 3 analyst pods × 20 = 60 companies).
- [ ] Topic input wired to the backend `/run` endpoint with live status.
- [ ] Watchlist import + Timo theme assignment.

### Milestone 3 — The debate mechanism
- [ ] Wire **2 distinct Bedrock models** (e.g. Claude Sonnet + Amazon Nova Pro / Llama 3) for **bull vs bear**.
- [ ] Run **1–2 rounds** on the top basket for the MVP (north star: 3 rounds, every basket); persist the debate transcript.
- [ ] Chairman `skill_debate_verdict` → per-stock `APPROVE / REJECT / RESIZE`.
- [ ] **Human override (HITL):** UI control to Approve / Reject / Resize the pick; store the human decision next to the AI verdict.
- [ ] Final portfolio assembled from **human-approved** stocks.

### Milestone 4 — Split the MACRO stream
- [ ] Route MACRO-labelled transcripts straight to the Chairman.
- [ ] Build **Financial/Economic Indicator Dashboard**.
- [ ] Implement **ACE Index** + overlay on `$SMH` / `$QQQ` / `$ARKK`.

### Milestone 5 — Polish & guardrails
- [ ] Cron / sync schedule editor UI.
- [ ] **Freshness badges** (🟢/🟡/🔴) + live sync status; Chairman down-weights stale data.
- [ ] Semantic keyword tracker (max 15) + Context Preview modal.
- [ ] Backtest Sandbox ($10k buy-and-hold vs S&P 500).
- [ ] Prediction Ledger leaderboard.
- [ ] "Not financial advice" framing across the UI.

---

## Triggering model (who runs when)

| Layer | Trigger | AWS mechanism |
|-------|---------|---------------|
| 1 Discovery | Cron (continuous) | EventBridge Scheduler → Fargate/Lambda |
| 2 Data Eng | Cron (continuous) | EventBridge Scheduler → Fargate (SQS queue) |
| 3 Analysts | Event-driven (new clean transcript) | EventBridge event → Lambda/Fargate |
| 4 Managers | User action + weekly cron | API Gateway + EventBridge Scheduler |
| 5 Chairman | User action (login/backtest) + Friday 4pm cron | API Gateway + EventBridge Scheduler |

---

## Definition of Done for the demo

A judge should be able to:
1. Open the **Command Center** and read a 3-bullet briefing.
2. See a **thematic portfolio** (e.g. memory chips) with conviction + holding period.
3. Click any pick → read the **debate verdict** and the **source quote at a timestamp**.
4. **Approve / reject / resize the pick** — the human override lands in the portfolio.
5. See the **MACRO dashboard** + **ACE Index**.
6. Run a **backtest** ($10k, N months) → equity curve vs S&P 500.
7. Trust it: every number traces to a source; failed items are skipped and logged, never faked.

---

## Open decisions (TODO before/with engineering)

- [ ] **MVP watchlist:** pick the ~8 companies that tell one clean thematic story (e.g. AI-buildout memory names).
- [ ] **Exact 60-company split** across the 3 analyst pods (TMT / HardAssets / Core) — scale-up only.
- [ ] Number of Managers in Layer 4 (2 vs 3) and how baskets are divided among them — scale-up only.
- [ ] Which 2 **Bedrock** models for the debate (e.g. Claude Sonnet vs Nova Pro vs Llama 3), and token/cost budget per debate.
- [ ] When (if ever) to reintroduce embeddings: stays **plain Postgres** until transcript volume makes retrieval necessary.
