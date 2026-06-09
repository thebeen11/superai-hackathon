# Project Raijin — Hedge Fund AI Agent Council

> **Project guidance** distilled from the planning conversation. This is the single
> source of truth for what we're building, why, and how the pieces fit together.
> Hand the relevant sections to engineers building the orchestrator and workers.

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

**End outcome:**
1. A dashboard monitoring financial-health indicators.
2. Portfolio **themes** of recommendations (e.g. AI data-centre buildout, banking,
   space, advanced materials) + the individual stocks under each theme.
3. **Backtest** validation: "if you invested $10,000 in this theme, how much would
   you have made over 3 / 6 / 12 months?"

---

## 2. The Agent Council (4 Agents)

A pipeline of four asynchronous agents. The user is the **"Commander"** — they set
parameters and read outputs; the agents do the work in the background.

| Agent | Role | One-liner |
|-------|------|-----------|
| **Wilfred** | Data Analyst / Scout | Discover & ingest raw data (YouTube, web, RSS, SEC) |
| **Timo** | Data Engineer / Purifier | Clean, normalize, chunk & embed transcripts |
| **Andie** | Hedge Fund Analyst / Brain | Score indicators, track signals, derive predictions |
| **Freddy** | Hedge Fund Manager / Allocator | Synthesize, build themes, backtest, report |

### Pipeline

```text
[ Data Sources: YouTube, Web, RSS, SEC ]
      │
      ▼
( WILFRED / Ingestion Worker )
  - Downloads audio via yt-dlp; transcribes via Whisper (fallback to CC).
  - Scrapes SEC filings & paywalled articles.
      │
      ▼
[ Raw Transcript DB ]
      │
      ▼
( TIMO / Pipeline Worker )
  - SponsorBlock removes ads/intros.
  - Entity resolution (slang → tickers).
  - Chunks text & generates embeddings.
      │
      ▼
[ Vector DB (Pinecone) + Relational DB (Postgres) ]
      │
      ▼
( ANDIE / Analytics Worker ) ← listens to user's Signal Rubrics
  - RAG retrieval, indicator scoring, prediction logging, n-order reasoning.
      │
      ▼
( FREDDY / Synthesis Worker )
  - ACE Index composite, thematic portfolios, Python backtests.
      │
      ▼
[ FRONTEND DASHBOARD (Next.js / React) ]
```

### Triggering model
- **Wilfred & Timo** → Cron jobs (time-based, continuous background).
- **Andie** → Event-driven (fires when Timo writes a new clean transcript).
- **Freddy** → User action (login / backtest request) **and** Cron (weekly Friday thesis).

---

## 3. Agent Specifications

These map to `.md` system-prompt / config files per agent. Personality matters — it
shapes the system prompt.

### 3.1 Wilfred — The Tireless Hunter (`/agents/wilfred_scout.md`)
**Persona:** Relentless, hyper-organized data-acquisition scout. Does NOT analyze —
only fetches, transcribes, and routes pristine raw data into the pipeline.

**Tools:** `youtube-transcript-api`, `yt-dlp` + `OpenAI Whisper API`,
`Playwright` (headless, paywall auth), `SEC_EDGAR_API`, `RSS_Feed_Parser`.

**Skills:**
- `skill_top_down_macro_scan` — poll macro channels/feeds every 60 min; emit webhook
  to Timo with `[URL, Source, Publish_Date, Raw_Text/Audio]`.
- `skill_bottom_up_watchlist_monitor` — per-ticker Google News + SEC Edgar queries.
- `skill_paywall_bypass_and_auth` — inject session cookies from a secure vault to
  scrape subscriber-only articles.

### 3.2 Timo — The Obsessive Cleaner (`/agents/timo_purifier.md`)
**Persona:** Ruthless data engineer. Despises noise/fluff. Bad data = losing trades.

**Tools:** `SponsorBlock_API`, `spaCy` + `FinBERT_NER`,
`LangChain RecursiveCharacterTextSplitter` (~1000-token chunks, 200 overlap),
`OpenAI text-embedding-3-small`, `Pinecone` / `Milvus`.

**Skills:**
- `skill_noise_redaction` — drop ad reads / filler ("use promo code", "smash like").
- `skill_entity_resolution` — `["Zuck","Meta","FB","Facebook"] → $META`;
  `["Powell","J-Pow","The Fed","FOMC"] → Federal_Reserve`.
- `skill_vector_embedding_pipeline` — chunk, embed, write to Pinecone with metadata
  `{channel, date, timestamp_start, tickers_mentioned[]}`.

### 3.3 Andie — The Skeptical Brain (`/agents/andie_analyst.md`)
**Persona:** Skeptical, objective, deeply analytical. Derives 2nd/3rd-order outcomes.
Strictly follows the Commander's rubrics. Requires evidence for every claim.

**Tools:** LLM orchestrator (Claude Sonnet / GPT-4o), `JSON_Schema_Enforcer`,
`Vector_DB_Query_Engine`.

**Skills:**
- `skill_semantic_keyword_tracker` — semantic (not literal) match for tracked phrases;
  count, filter by channel, output time-series JSON.
- `skill_rubric_indicator_scoring` — score chunk vs user indicator. Output:
  `{Indicator, Score (-1..1), Reasoning, Source_Timestamp}`.
- `skill_prediction_ledger_extraction` — log forward-looking statements to
  `predictions_db` with `PENDING` status + `resolve_by_date`.
- `skill_n_order_thinking` — `If X → Y impacted → Action Z required` decision trees.

### 3.4 Freddy — The Cold Allocator (`/agents/freddy_manager.md`)
**Persona:** Decisive, risk-aware, focused on actionable alpha. No waffling — speaks
in strategies, timelines, and quantitative backtests.

**Tools:** `Zipline` / `Backtrader`, `Polygon.io` / `YFinance`, `Pandas`+`NumPy`,
`Markdown_Reporting_Engine`.

**Skills:**
- `skill_ace_index_calculator` — compute normalized ACE composite (see §5).
- `skill_portfolio_theme_generator` — group 3–5 correlated stocks into a basket with
  Strategy, Risk, Timeline (short/med/long).
- `skill_backtest_execution` — pull historical closes, simulate $10k entry. Output:
  `{total_return_pct, max_drawdown, equity_curve_array}`.
- `skill_weekly_thesis_synthesis` — Friday 4pm: aggregate findings, top-10 quotes,
  ACE Index, pending predictions → one "Weekly Investment Thesis".

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
User defines indicators + rubrics; Andie grades every transcript.

Example indicators: Macroeconomic Outlook, Inflation Trajectory, Interest Rate Policy,
Market Sentiment, Sector Trends, Geopolitical Risk.

- Output format per indicator: Positive/Neutral/Negative OR High/Med/Low OR %Score.
- **Must include evidence** (quotes/facts + source timestamp).

### 4.3 Insight Generator
- **Predictions** — special insights resolvable True/False after a time window
  (timing matters; user marks or auto-resolves). Track accuracy → **Prediction Ledger**
  leaderboard ranking which channels/analysts are most accurate (Brier-score style).
- **Top 10 Quotes** of the week.
- **Weekly Investment Thesis** — coherent market outlook synthesized from all content.
- **Thematic Ideas** (broad) + **Stock-Specific Ideas**, each with Strategy / Risk /
  Timeline, plus AI follow-up questions critiquing assumptions and 2nd/3rd-order effects.

---

## 5. Composite Signal — ACE Index

**AI Capital Environment Index.** High ACE = favorable macro + dovish policy + bullish
AI capex.

```python
class CompositeSignalGenerator:
    def calculate_ace_index(self, ai_sentiment, rate_expectations, inflation_drag):
        """
        Weights dynamically adjustable by Freddy based on macro regime.
        Default: AI Sentiment 40%, Rates 30%, Inflation 30%.
        Returns float in [-1.0 (capital starved) .. +1.0 (capital abundant)].
        """
        return (ai_sentiment * 0.4) + (rate_expectations * 0.3) + (inflation_drag * 0.3)
```

- `rate_expectations`: +1 = dovish (cuts), -1 = hawkish.
- `inflation_drag`: +1 = disinflation tailwind, -1 = high inflation drag.
- Plot ACE Index overlaid on AI indices (`$SMH`, `$QQQ`, `$ARKK`) to validate
  predictive alpha.

---

## 6. User Flows

### Flow 1 — Cold Start (configuration)
1. **Agent Management & Sources:** add YouTube channel / video / web / RSS →
   Wilfred validates, fetches metadata, queues ingestion.
2. **Watchlist (Bottom-Up):** import US tickers → Timo maps to entity-resolution dict.

### Flow 2 — Create a Signal/Tracker
- Fork: **Concept/Keyword Tracker** (phrase + target channels + historical/forward
  toggle) **or** **Custom Indicator Rubric** (name + rubric definition).

### Flow 3 — Daily Consumption Loop (< 5 min)
1. **Command Center:** Freddy's 3-bullet daily briefing + watchlist alerts.
2. Tracker graphs (max 15) → hover a spike → click → **Context Preview** modal →
   "Go to Source" opens YouTube at exact `HH:MM:SS`.

### Flow 4 — Insight & Backtesting
1. **Investment Thesis page:** generated portfolio themes (strategy, stocks, risk,
   timeline).
2. **Backtest Sandbox:** set "$10k invested N months ago" → Freddy pulls historical
   prices → renders equity curve vs S&P 500 with ROI & max drawdown.

---

## 7. UI / Page Map

1. **Command Center (Dashboard)** — 60-second daily briefing, top macro shifts,
   thematic portfolios, watchlist alerts.
2. **Signal & Tracker Terminal** — keyword/semantic graphs + indicator heatmap.
3. **Thematic Portfolio & Backtesting Sandbox** — themes, run-backtest, What-If
   scenario analysis ("what if inflation prints 3.5% tomorrow?").
4. **Source & Agent Management** — toggle data sources; Prediction Ledger leaderboard.
5. **Financial Indicator Dashboard** — macro indicators, watchlist, key events
   (past & upcoming).

---

## 8. Tech Stack

| Layer | Choice |
|-------|--------|
| Orchestration | LangGraph / Microsoft AutoGen (state graph, avoid infinite loops) |
| Reasoning LLM | Claude Sonnet / GPT-4o (Andie, Freddy) |
| Cheap bulk LLM | Llama-3 8B (Timo's high-volume cleaning) |
| Relational DB | Supabase / PostgreSQL (users, keywords, predictions) |
| Vector DB | Pinecone (transcript embeddings) |
| Frontend | Next.js + TailwindCSS + Tremor.so (financial charts) |
| Jobs/Compute | Celery + Redis or Inngest (async long-video processing) |
| Market data | Polygon.io / YFinance |

> This repo: `backend/` (Python) + `frontend/` (Next.js + TypeScript).

---

## 9. Engineering Constraints & Guardrails

1. **15-tracker limit:** 16th create → warning modal; delete archives the tracker's
   historical vector search data.
2. **Stale-data indicator:** show sync status ("Wilfred processing 3 videos… Andie
   analyzing 2 transcripts…") so the user knows if data is real-time.
3. **Hallucination guardrails:** every Quote/Score MUST carry `source_url` +
   `timestamp_start`. **No orphan data** — the user must always be able to audit AI logic.
4. **Channel-level tracking only** — never track isolated single transcripts.

---

## 10. Reference — Sectors of Interest

Technology · Consumer Discretionary · Healthcare · Industrials · Financials ·
Communication Services · Consumer Staples · Energy · Real Estate · Utilities ·
Basic Materials.
