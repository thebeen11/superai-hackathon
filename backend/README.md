# Backend — Hedge Fund AI Agent Council

Python API for the council. Built layer by layer; **Discovery** is first.

## Tech Stack

- **Language:** Python 3.11+
- **Framework:** FastAPI
- **Package manager:** uv

## Setup

```bash
uv sync                 # install deps into .venv from pyproject.toml
cp .env.example .env     # then fill in your API keys
```

## Environment Variables

See `.env.example`. Discovery **skips a source gracefully** if its key is missing,
so you can run with one, both, or neither key set.

- `EXA_API_KEY` — Exa web search + crawl
- `YOUTUBE_API_KEY` — YouTube Data API v3 (video search)

## Running

```bash
# API
uv run uvicorn app.main:app --reload     # http://localhost:8000  (docs at /docs)

# Discovery agent, straight from the CLI
uv run python -m scripts.run_discovery "AI memory chip demand"
```

## Project Structure

```
backend/
├── pyproject.toml          # deps (uv)
├── .env.example
├── app/
│   ├── config.py           # env-backed settings (Exa/YouTube/Bedrock/DB)
│   ├── models.py           # shared Pydantic shapes
│   ├── taxonomy.py         # market themes, sectors, alias maps
│   ├── main.py             # FastAPI app
│   ├── llm/
│   │   └── bedrock.py      # shared converse() wrapper + schema + retries
│   ├── discovery/          # LAYER 1 — Discovery agent
│   │   ├── agent.py        #   fan-out + merge + skip-with-reason
│   │   ├── refine.py       #   LLM query refinement / clarification
│   │   ├── exa_source.py   #   web branch (Exa)
│   │   └── youtube_source.py  # video branch (YouTube + transcripts)
│   ├── dataeng/            # LAYER 2 — Data Engineering (Timo)
│   │   ├── redact.py · entities.py · labels.py · themes.py
│   │   ├── guardrail.py    #   no-orphan-data enforcement
│   │   └── pipeline.py     #   per-item orchestration
│   └── db/                 # SQLAlchemy session, tables, repository
├── scripts/
│   ├── run_discovery.py    # CLI to try Discovery
│   └── init_db.py          # create the Postgres schema
└── tests/                  # pytest unit/integration tests
```

## What works today

- **Discovery (Layer 1):** a topic query is refined/clarified by the LLM, then fans out
  to Exa (web) + YouTube (transcripts) in parallel, merges + dedupes by URL, and records
  a reason for any branch/video it skips.
- **Data Engineering (Layer 2):** per item — redact noise, resolve entities, label
  MACRO/MICRO + industry, assign market themes, enforce the no-orphan-data guardrail,
  and upsert into Postgres (idempotent by source_url).
- **API:** `POST /discover`, `POST /discover/clarify`, `POST /dataeng/process`,
  `GET /items` (read persisted rows, filter by stream/theme/ticker), `GET /discover`,
  `GET /health`.

## Tests

```bash
uv run pytest        # unit + wrapper/guardrail/pipeline tests (no network/DB needed)
```

> DB-backed checks (repository upsert idempotency, full end-to-end) require a live
> Postgres (`DATABASE_URL` + `uv run python -m scripts.init_db`).
