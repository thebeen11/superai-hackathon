# Hedge Fund AI Agent Council

> **Project guidance** distilled from the planning conversation. This is the single
> source of truth for **what** we're building and **why**. For the actionable build
> order and milestones, see [`BUILD_PLAN.md`](./BUILD_PLAN.md).

---

## 1. Problem Statement

The user has very little time but wants to make informed US-equity investment
decisions from a large volume of financial news videos (YouTube), podcasts, and
articles. We need a system that **"reads" and "analyzes" transcripts on their
behalf** and surfaces only the financial/economic/investment signal they care about.

Two research approaches must be supported:

- **Top-Down** — scan headlines / macro sources for anything new.
- **Bottom-Up** — run through a Stock Watchlist and find news per individual stock.

**Scope (v1):** US public equities only.

### Output philosophy — Option A (Sentiment & Timing, not Price Triggers)

This system is a **research and conviction engine**, not a trade-signal engine.
It tells the user *what* to look at, *how strong the conviction is*, and *over what
time horizon* — it does **not** emit precise entry/exit prices, stop-losses, or
take-profit targets. Recommendations are expressed as:

- **Conviction** (e.g. High / Medium / Low, or a composite score),
- **Holding period / timing window** (short / medium / long term),
- **Evidence** (source quotes + timestamps).

> Every recommendation is research, **not financial advice**, and must be auditable
> back to a source quote at a timestamp.

**End outcome:**

1. A **Financial/Economic Indicator Dashboard** (fed by the MACRO data stream).
2. **Thematic portfolios** of stock recommendations (e.g. "Memory Chips for the AI
   Buildout: Micron, SK Hynix, SanDisk") each with an **estimated holding period**.
3. **Backtest** validation: "if you invested $10,000 in this theme, how much would
   you have made over 3 / 6 / 12 months?" (buy-and-hold, no price triggers).

---

## 2. The Agent Council — a 5-Layer Hedge Fund Org

Think of the system as a small hedge fund with five departments. Data flows **up**
the hierarchy, and at Layer 2 it **forks** into two streams: **MACRO** (feeds the
dashboard) and **MICRO** (feeds stock picks).

```text
                         DATA SOURCES
              YouTube  ·  Google Search  ·  Barron's
                              │
        ┌─────────────────────┴─────────────────────┐
        │  LAYER 1 — DISCOVERY  (3 Data Analysts)    │
        │  Wilfred-YT · Wilfred-Web · Wilfred-Auth   │
        │  + chats with HUMAN for new sources        │
        │  + editable cron / sync schedule           │
        └─────────────────────┬─────────────────────┘
                              │  raw transcripts
        ┌─────────────────────┴─────────────────────┐
        │  LAYER 2 — DATA ENGINEERING  (Timo)        │
        │  clean · label MACRO/MICRO/INDUSTRY        │
        │  scan watchlist → assign THEMES            │
        └──────────┬───────────────────┬────────────┘
          MICRO    │                   │   MACRO
        ┌──────────┴──────────┐        │
        │ LAYER 3 — ANALYSTS  │        │
        │ 3 pods × 20 cos = 60│        │
        │ write highlights    │        │
        └──────────┬──────────┘        │
                   │ 60 reports        │
        ┌──────────┴──────────┐        │
        │ LAYER 4 — MANAGERS  │        │
        │ 2–3 managers        │        │
        │ thematic baskets +  │        │
        │ holding period      │        │
        │ LLM DEBATE × 3 rounds│       │
        └──────────┬──────────┘        │
                   │ verdict requests  │
        ┌──────────┴───────────────────┴────────────┐
        │  LAYER 5 — CHAIRMAN                         │
        │  judge debates · build final portfolio     │
        │  populate MACRO dashboard                  │
        └─────────────────────┬──────────────────────┘
                              │
                       FRONTEND DASHBOARD
```

### Mapping to the original personas

| Layer | Department | Persona(s) | Count |
| ----- | ---------- | ---------- | ----- |
| 1 | Discovery / Data Analyst | **Wilfred** (YT, Web, Auth) | 3 agents |
| 2 | Data Engineering | **Timo** | 1 agent |
| 3 | Investment Analyst | **Andie** (pods: TMT, HardAssets, Core) | 3 pods × 20 cos |
| 4 | Investment Manager | **Freddy** (managers) | 2–3 agents |
| 5 | Investment Chairman | **Freddy** (chairman) | 1 agent |

### The two data streams

Layer 2 forks every cleaned transcript by label:

- **MICRO stream** → company-specific signal → Analysts → Managers → Chairman →
  **stock recommendations** (thematic baskets + holding periods).
- **MACRO stream** → economy-wide signal → **skips the analysts** → straight to the
  Chairman → **Financial/Economic Indicator Dashboard**.

_Example:_ a Fed-policy transcript flows up the MACRO side and lands on the dashboard;
an Nvidia-earnings transcript flows up the MICRO side and influences a stock pick.

### Triggering model

- **Layer 1 (Discovery) & Layer 2 (Data Eng)** → Cron jobs (time-based, continuous).
- **Layer 3 (Analysts)** → Event-driven (fires when Timo writes a new clean transcript).
- **Layer 4 (Managers) & Layer 5 (Chairman)** → User action (login / backtest request)
  **and** Cron (weekly Friday thesis).

---

## 3. Layer Specifications

These map to `.md` system-prompt / config files per agent. Personality matters — it
shapes the system prompt.

### 3.1 Layer 1 — Discovery (Wilfred ×3) — The Tireless Hunters

**Persona:** Relentless, hyper-organized data-acquisition scouts. They do NOT analyze
— only fetch, transcribe, and route pristine raw data into the pipeline.

**Three specialized agents, one per channel:**

| Agent | Channel | Primary tools |
| ----- | ------- | ------------- |
| **Wilfred-YT** | YouTube | `youtube-transcript-api`, `yt-dlp` + **Amazon Transcribe** (CC fallback) |
| **Wilfred-Web** | Google Search / News | Exa search API, `RSS_Feed_Parser` |
| **Wilfred-Auth** | Barron's (paywalled) | `Playwright` headless + **AWS Secrets Manager** cookie vault (mock API for v1) |

**Shared responsibilities:**

- `skill_top_down_macro_scan` — poll macro channels/feeds on schedule; emit webhook
  to Timo with `[URL, Source, Publish_Date, Raw_Text/Audio]`.
- `skill_bottom_up_watchlist_monitor` — per-ticker queries (Google News + SEC Edgar).
- **Human-in-the-loop source chat** — a conversational surface where the HUMAN can
  add/remove YouTube channels, articles, and feeds to track. Wilfred validates new
  sources and fetches metadata.
- **Sync schedule UI** — display and edit each agent's cron / sync schedule and view
  queued ingestion tasks.

### 3.2 Layer 2 — Data Engineering (Timo) — The Obsessive Cleaner

**Persona:** Ruthless data engineer. Despises noise/fluff. Bad data = losing trades.

**Tools:** `SponsorBlock_API`, **Amazon Comprehend** (or spaCy + `FinBERT_NER` on Fargate),
`LangChain RecursiveCharacterTextSplitter` (~1000-token chunks, 200 overlap),
**Amazon Bedrock Titan Text Embeddings v2**, **Amazon OpenSearch Serverless** (vector),
**Amazon S3** for cleaned-file object storage.

**Skills:**

- `skill_noise_redaction` — drop ad reads / filler ("use promo code", "smash like").
- `skill_entity_resolution` — `["Zuck","Meta","FB"] → $META`;
  `["Powell","J-Pow","The Fed","FOMC"] → Federal_Reserve`.
- `skill_label_assignment` — tag every transcript (and chunk) with:
  - **MACRO** vs **MICRO** (which stream it feeds), and
  - **INDUSTRY** (sector tag, see §10).
- `skill_theme_assignment` — regularly scan the stock watchlist and assign **Themes**,
  routing each to the Analyst pod that specializes in that theme.
- `skill_vector_embedding_pipeline` — chunk, embed, write with metadata
  `{channel, date, timestamp_start, tickers_mentioned[], labels[], theme}`.

### 3.3 Layer 3 — Investment Analysts (Andie ×3 pods) — The Skeptical Brains

**Persona:** Skeptical, objective, deeply analytical. Derives 2nd/3rd-order outcomes.
Strictly follows the Commander's rubrics. Requires evidence for every claim.

**Structure:** 3 pods, each covering **20 companies (60 total)**:

| Pod | Focus | Example coverage |
| --- | ----- | ---------------- |
| **Andie-TMT** | Tech / Media / Telecom | 20 tech names |
| **Andie-HardAssets** | Industrials / Materials / Energy | 20 industrial names |
| **Andie-Core** | Financials / Macro-sensitive | 20 financial names |

**Tools:** LLM orchestrator via **Amazon Bedrock** (Claude Sonnet), `JSON_Schema_Enforcer`,
**Bedrock Knowledge Bases** query engine.

**Skills:**

- Receive **cleaned MICRO transcripts** from Timo (event-driven).
- `skill_rubric_indicator_scoring` — score each chunk against user indicators. Output:
  `{Indicator, Score (-1..1), Reasoning, Source_Timestamp}`.
- `skill_investment_highlights` — write per-company **investment highlights & notes**
  for the Managers (the "60 reports").
- `skill_prediction_ledger_extraction` — log forward-looking statements to
  `predictions_db` with `PENDING` status + `resolve_by_date`.
- `skill_n_order_thinking` — `If X → Y impacted → Action Z` decision trees.

### 3.4 Layer 4 — Investment Managers (Freddy ×2–3) — The Debating Allocators

**Persona:** Decisive, risk-aware, focused on actionable alpha. No waffling — speaks
in strategies, timelines, and conviction.

**Skills:**

- **Synthesize at scale** — ingest **all 60 analyst reports at once** (MICRO data).
- `skill_portfolio_theme_generator` — group correlated stocks into a basket with
  Strategy, Risk, and an **estimated holding period** (short/med/long). _Example:_
  "Memory Chips for AI Buildout → Micron, SK Hynix, SanDisk; hold 6–12 months."
- `skill_llm_debate_stress_test` — for each proposed basket, run a **bull-vs-bear
  debate using 2 different Bedrock models for 3 rounds** (e.g. Claude Sonnet vs
  Amazon Nova Pro / Llama 3), then forward the debate transcript to the Chairman for
  verdict.
- `skill_backtest_execution` — pull historical closes, simulate $10k buy-and-hold.
  Output: `{total_return_pct, max_drawdown, equity_curve_array}`.

### 3.5 Layer 5 — Investment Chairman (Freddy) — The Final Judge

**Persona:** The CIO. Decisive arbiter. Owns the final book.

**Skills:**

- `skill_debate_verdict` — judge every Manager debate; issue a per-stock verdict:
  `APPROVE / REJECT / RESIZE`, with reasoning.
- `skill_portfolio_construction` — assemble approved stocks into the **final portfolio**
  presented to the HUMAN (conviction + holding period + evidence, per Option A).
- `skill_macro_dashboard_population` — receive the **MACRO data stream** and populate
  the **Financial/Economic Indicator Dashboard**.
- `skill_ace_index_calculator` — compute the normalized ACE composite (see §5).
- `skill_weekly_thesis_synthesis` — Friday 4pm: aggregate findings, top-10 quotes,
  ACE Index, pending predictions → one "Weekly Investment Thesis".

### The debate mechanism (concrete)

1. A Manager proposes a basket — e.g. *"Memory chips for AI buildout: Micron, SK Hynix,
   SanDisk; holding period 6–12 months."*
2. **Two different Bedrock models** (e.g. Claude Sonnet vs Amazon Nova Pro) argue
   **bull vs bear** for **3 rounds**.
3. The debate transcript goes to the **Chairman**, who issues a per-stock verdict
   (`APPROVE / REJECT / RESIZE`).
4. Approved stocks are assembled into the final portfolio shown to the HUMAN.

> Per Option A, every output is **conviction + holding period + timing window** —
> never a price target.

---

## 4. Core Features

### 4.1 Semantic Keyword & Concept Tracker

- Track the **meaning** of a phrase (e.g. "AI bubble collapse" also matches
  "tech valuations are unsustainable"), not literal string matching.
- Channel-level only (no single-transcript tracking — isolated datapoints are
  meaningless). Filter / weight by channel.
- Graph: **mentions over time**, with per-channel breakdown and a **Context Preview**
  (the exact sentence/paragraph + jump-to-timestamp link).
- **Max 15 trackers.** At 16, warn user; deleting archives historical vector data.
- Start mode: **track forward-only** OR **run historically** across past transcripts.

### 4.2 Signal / Indicator Generator (Rubric Engine)

User defines indicators + rubrics; the Analyst pods grade every transcript.

Example indicators: Macroeconomic Outlook, Inflation Trajectory, Interest Rate Policy,
Market Sentiment, Sector Trends, Geopolitical Risk.

- Output per indicator: Positive/Neutral/Negative OR High/Med/Low OR %Score.
- **Must include evidence** (quotes/facts + source timestamp).

### 4.3 Insight Generator

- **Predictions** — insights resolvable True/False after a time window. Track accuracy
  → **Prediction Ledger** leaderboard ranking which channels/analysts are most accurate
  (Brier-score style).
- **Top 10 Quotes** of the week.
- **Weekly Investment Thesis** — coherent market outlook synthesized from all content.
- **Thematic Ideas** (broad) + **Stock-Specific Ideas**, each with Strategy / Risk /
  **Holding Period**, plus AI follow-up questions critiquing assumptions and
  2nd/3rd-order effects.

---

## 5. Composite Signal — ACE Index

**AI Capital Environment Index.** High ACE = favorable macro + dovish policy + bullish
AI capex.

```python
class CompositeSignalGenerator:
    def calculate_ace_index(self, ai_sentiment, rate_expectations, inflation_drag):
        """
        Weights dynamically adjustable by the Chairman based on macro regime.
        Default: AI Sentiment 40%, Rates 30%, Inflation 30%.
        Returns float in [-1.0 (capital starved) .. +1.0 (capital abundant)].
        """
        return (ai_sentiment * 0.4) + (rate_expectations * 0.3) + (inflation_drag * 0.3)
```

- `rate_expectations`: +1 = dovish (cuts), -1 = hawkish.
- `inflation_drag`: +1 = disinflation tailwind, -1 = high inflation drag.
- Plot ACE Index overlaid on AI indices (`$SMH`, `$QQQ`, `$ARKK`) to validate alpha.

---

## 6. Data Staleness & Freshness

Time-relevance of data is a first-class concern across the whole system.

- Every transcript carries `published_at` **and** `ingested_at`.
- Every recommendation shows a **freshness badge**:
  🟢 fresh (< 24h) · 🟡 aging (1–7d) · 🔴 stale (> 7d).
- The **Chairman down-weights stale evidence** when constructing the final portfolio.
- A live **sync status** indicator shows pipeline activity
  ("Wilfred-YT processing 3 videos… Andie-TMT analyzing 5 transcripts…").

---

## 7. User Flows

### Flow 1 — Cold Start (configuration)

1. **Source & Agent Management:** add YouTube channel / video / web / RSS / Barron's
   via the **source chat** → Wilfred validates, fetches metadata, queues ingestion.
2. **Watchlist (Bottom-Up):** import US tickers → Timo maps to entity-resolution dict
   and assigns Themes.
3. **Schedule:** review/edit each agent's cron schedule.

### Flow 2 — Create a Signal/Tracker

- Fork: **Concept/Keyword Tracker** (phrase + target channels + historical/forward
  toggle) **or** **Custom Indicator Rubric** (name + rubric definition).

### Flow 3 — Daily Consumption Loop (< 5 min)

1. **Command Center:** Chairman's 3-bullet daily briefing + watchlist alerts +
   freshness badges.
2. Tracker graphs (max 15) → hover a spike → click → **Context Preview** modal →
   "Go to Source" opens YouTube at exact `HH:MM:SS`.

### Flow 4 — Insight & Backtesting

1. **Investment Thesis page:** final portfolio themes (strategy, stocks, risk,
   holding period) + the debate verdicts behind them.
2. **Backtest Sandbox:** "$10k invested N months ago" → historical prices → equity
   curve vs S&P 500 with ROI & max drawdown (buy-and-hold).

---

## 8. UI / Page Map

1. **Command Center (Dashboard)** — 60-second daily briefing, top macro shifts,
   thematic portfolios, watchlist alerts, sync/freshness status.
2. **Signal & Tracker Terminal** — keyword/semantic graphs + indicator heatmap.
3. **Thematic Portfolio & Backtesting Sandbox** — themes, debate verdicts, run-backtest,
   What-If scenario analysis ("what if inflation prints 3.5% tomorrow?").
4. **Source & Agent Management** — source chat, toggle data sources, edit cron
   schedules, Prediction Ledger leaderboard.
5. **Financial Indicator Dashboard** — MACRO indicators, watchlist, key events
   (past & upcoming).

---

## 9. Tech Stack

**Hosting split:** the entire **backend runs on AWS**; the **frontend runs on Vercel**
and uses the **Vercel AI Gateway** for its interactive AI features. No third-party
backend SaaS (no Pinecone / Supabase / OpenAI / Celery-Redis) — everything server-side
is an AWS managed service.

### 9.1 Backend — AWS only

| Concern | AWS choice | Notes |
| ------- | ---------- | ----- |
| Agent orchestration | **AWS Step Functions** (state graph) + **Lambda**; **Bedrock AgentCore** optional | Explicit state machine prevents infinite agent loops |
| Reasoning LLM | **Amazon Bedrock** — Claude Sonnet (Analysts, Managers, Chairman) | Single API, IAM-governed |
| Debate models | **Amazon Bedrock** — 2 distinct model families, e.g. **Claude Sonnet vs Amazon Nova Pro / Llama 3** | No OpenAI needed; bull-vs-bear stress test |
| Cheap bulk LLM | **Amazon Bedrock** — **Amazon Nova Micro/Lite** or **Llama 3 8B** | Timo's high-volume cleaning |
| Transcription | **Amazon Transcribe** | Replaces Whisper; CC fallback still applies |
| Embeddings | **Amazon Bedrock Titan Text Embeddings v2** | Replaces OpenAI embeddings |
| RAG | **Amazon Bedrock Knowledge Bases** | Managed chunk → embed → retrieve |
| Entity resolution / NER | **Amazon Comprehend** or spaCy/FinBERT on **Fargate** | Slang → ticker mapping |
| Relational DB | **Amazon Aurora Serverless v2 (PostgreSQL)** | users, keywords, predictions, reports |
| Vector DB | **Amazon OpenSearch Serverless (vector engine)** or **Aurora `pgvector`** | Transcript embeddings; backs Knowledge Bases |
| Object store | **Amazon S3** | Raw + cleaned transcript files |
| Async / long jobs | **ECS Fargate** tasks via **Amazon SQS** | Long-video processing |
| Event bus | **Amazon EventBridge** | Event-driven analyst triggers |
| Scheduling (cron) | **Amazon EventBridge Scheduler** | Discovery & Data-Eng cron, Friday thesis |
| API layer | **Amazon API Gateway** + **Lambda** (or ALB + Fargate) | Serves the Vercel frontend |
| Secrets / cookie vault | **AWS Secrets Manager** | Barron's session cookies (mock in v1) |
| Cache (optional) | **Amazon ElastiCache (Redis)** | If a fast shared cache is needed |
| Market data | **Polygon.io / yfinance** (external API) | Called from Lambda/Fargate |

### 9.2 Frontend — Vercel + AI Gateway

| Concern | Choice | Notes |
| ------- | ------ | ----- |
| Hosting | **Vercel** | Next.js + TailwindCSS + Tremor.so (financial charts) |
| Interactive AI | **Vercel AI SDK** over the **Vercel AI Gateway** | Unified multi-model access, observability, fallbacks, budgets |
| Use cases | Source chat, follow-up Q&A, What-If scenarios | User-facing conversational features |

> The AI Gateway powers **user-facing** AI (chat, follow-ups). The heavy multi-agent
> pipeline (Discovery → Chairman) runs **server-side on Bedrock**.

> This repo: `backend/` (Python on AWS) + `frontend/` (Next.js + TypeScript on Vercel).

---

## 10. Engineering Constraints & Guardrails

1. **Option A only:** no price-level entry/exit triggers — conviction + holding period
   + evidence only.
2. **15-tracker limit:** 16th create → warning modal; delete archives the tracker's
   historical vector search data.
3. **Stale-data handling:** freshness badges everywhere; Chairman down-weights stale
   evidence; live sync status (see §6).
4. **Hallucination guardrails:** every Quote/Score MUST carry `source_url` +
   `timestamp_start`. **No orphan data** — the user must always be able to audit AI logic.
5. **Channel-level tracking only** — never track isolated single transcripts.
6. **Not financial advice:** all outputs are research; surface this framing in the UI.

---

## 11. Reference — Sectors of Interest

Technology · Consumer Discretionary · Healthcare · Industrials · Financials ·
Communication Services · Consumer Staples · Energy · Real Estate · Utilities ·
Basic Materials.
