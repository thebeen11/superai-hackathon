# AGENTS.md

This file provides guidance to coding agents when working with code in this repository.
Claude Code (claude.ai/code) reads it via the root `CLAUDE.md`, which imports this file.

## What this is

**Hedge Fund AI Agent Council** ("WTAF Fund") — a 5-tier multi-agent research pipeline that turns
research topics and subscribed YouTube channels into source-anchored investment insight, plus a
Next.js dashboard on top of it.

`docs/PROJECT_GUIDANCE.md` is the product/architecture spec and is the authority: code comments
cite it by section (`§6`, `§7.3`, `§12.6`, "Req 13"). Read the cited section before changing
behaviour those comments describe. `docs/BUILD_PLAN.md` covers scope decisions.
`docs/SESSION_HANDOFF.md` is gitignored, local-only, and **stale** (it describes an AWS/Bedrock
era; the stack is now GCP/Vertex) — don't trust it over the code.

## Before you plan or write code

Do both of these first. They are cheap, and they carry context that is not in the source tree:

1. **Search project memory (mem0).** Past decisions, rejected approaches, and the user's stated
   preferences live here, not in git history. Search before proposing a design, when an error
   smells familiar, or when the user references earlier work. Always scope the query with
   `user_id: thebeen` and `app_id: thebeen11-superai-hackathon`, and run 2-4 parallel searches
   filtered by category (`architecture_decisions`, `anti_patterns`, `coding_conventions`,
   `user_preferences`, `dependency_decisions`). Empty results are normal — proceed. Write new
   decisions back the same way, so they outlive the session.

2. **Query the knowledge graph (graphify).** `graphify-out/graph.json` is already built for this
   repo, so any "how does X work / what calls Y / trace the flow through Z" question goes through
   `graphify query "<question>"` *before* you start grepping — it resolves cross-file
   relationships faster than a search sweep and surfaces connections you would not think to ask
   about. `graphify path "A" "B"` and `graphify explain "<node>"` answer narrower questions;
   `graphify-out/GRAPH_REPORT.md` is the plain-language overview.

   `graphify-out/` is gitignored and local-only. If it is missing, build it with `/graphify`; after
   large changes run `/graphify . --update` so the graph stops answering from stale code.

Neither replaces reading the code you are about to change. They tell you *where* to read and
*what was already decided*.

## Commands

### Backend (`backend/`, Python 3.11+, uv)

```bash
uv sync                                        # install deps into .venv
cp .env.local.example .env.local               # then fill in GCP_PROJECT, DATABASE_URL, EXA_API_KEY…
gcloud auth application-default login          # Vertex auth is ADC, not an API key
docker compose up -d                           # local Postgres on :5433 (user/pass/db = council)
uv run python -m scripts.init_db               # create the schema
uv run uvicorn app.main:app --reload           # :8000 — /docs (Swagger), /redoc, /health

uv run pytest                                  # all tests; LLM + DB are mocked, no network needed
uv run pytest tests/test_council.py            # one file
uv run pytest tests/test_council.py::test_name # one test
uv run pytest -k watchlist                     # by name

uv run python -m scripts.run_discovery "AI memory chip demand"   # Discovery from the CLI
uv run python scripts/dump_openapi.py                            # regenerate backend/openapi.json
./deploy.sh deploy                             # Cloud Run redeploy (see caveat below)
```

`backend/INSTRUCTIONS.md` has the full end-to-end curl walkthrough and a long troubleshooting
section — read it before debugging Vertex 403/404s or Cloud SQL failures.

### Frontend (`frontend/`, Next.js 16 + React 19, **pnpm only**)

```bash
pnpm install
pnpm dev        # :3000  (note: dev runs --webpack, build runs --turbopack)
pnpm build
pnpm lint
pnpm gen:api    # regenerate the typed client from ../backend/openapi.json
```

There is no frontend test runner.

## The API contract pipeline

The frontend never introspects a running backend. The chain is:

```
backend routes → uv run python scripts/dump_openapi.py → backend/openapi.json (committed)
              → frontend: pnpm gen:api → frontend/src/lib/api/generated/** (committed)
```

**Changing any backend route/model means running both steps and committing both outputs.**
`generate_unique_id_function=_operation_id` in `app/main.py` makes the operationId the route
*function name*, so renaming a FastAPI handler renames the generated TS SDK function
(`list_items` → `listItems`).

## Backend architecture

Tiers map one-to-one onto packages under `backend/app/`:

| Tier | Package | Role |
| --- | --- | --- |
| 1 — Wilfred | `discovery/` | Fan out a topic to Exa (web) + YouTube; `youtube_channel.py`/`youtube_ingest.py`/`supadata.py` are the *standing* channel-subscription source |
| 2 — Timo | `dataeng/` | Per item: `redact → entities → labels → themes → guardrail → persist` |
| 3 — Andie ×3 | `council/analyst.py` | Three sector desks, disjoint sectors, ≤20 stocks each |
| 4 — Freddy ×2 | `council/debate.py` | Bull vs Bear, 6 alternating rounds |
| 5 — Winston | `council/chairman.py` | Fan-in: verdict, indicators, ACE, briefing, predictions |
| bypass | `council/macro.py` | `[MACRO]` items skip the analysts and go straight to Winston |
| weekly | `council/thematic.py` | Thematic Analysis: Winston's baskets, on their own weekly clock |

`council/orchestrator.py` is the DAG entry point (`run_council`) and the only place that
assembles a `CouncilReport` + source manifest. The pipeline is strictly ordered — no partial runs.

**Thematic Analysis is not part of that DAG.** `council/thematic.py` is one LLM call that reads
the corpus directly and borrows the newest council snapshot for context; each execution is
persisted whole and dated as a `ThematicRun` (`thematic_runs`), which is what makes past weeks
readable — unlike `council_snapshots`, where only the newest row is ever served. Its cadence is
the `thematic-weekly` Cloud Scheduler job in `deploy.sh` (Mondays 03:00 UTC → `POST
/api/thematic/run`); a theme built from one day of headlines is noise, which is why it does not
ride the nightly crawl. Every basket carries a `timeframe` — `Short Term` (1M) / `Medium Term`
(1Q) / `Long Term` (1Y), a closed set normalised server-side. `CouncilReport.baskets` survives as
a deprecated field so snapshots written before the split still parse.

Cross-cutting pieces that new code must go through rather than around:

- **`llm/vertex.py` is the only module that talks to an LLM.** Structured JSON output validated
  against a Pydantic schema, with retries. Auth is ADC. Gemini 3.x is served only on the `global`
  endpoint — a regional `VERTEX_LOCATION` 404s on every call.
- **Prompts are never inline string literals.** Every system instruction is a `PromptSpec` in
  `prompts/registry.py` (task/"skill" layer) or `prompts/identity.py` (soul / rules / mental
  models / personality layers), fetched with `get_prompt(key, **placeholders)`. Runtime overrides
  are persisted by `prompts/store.py` and edited from the Agent Console via
  `GET/PUT/DELETE /api/prompts`. Adding a reasoning step means adding a spec, not a constant.
- **The Macro Analyst runs twice.** Pass 1 grades the fixed checklist against the `[MACRO]`
  corpus; `macro.backfill_signposts` then searches the web (one deterministic Exa query per
  still-ungraded row) and re-grades *only* those rows. Backfill documents are run-scoped —
  grounded, cited, and recorded in the snapshot's source manifest, but never written to
  `cleaned_items`, so material fetched to answer one row of one run does not join the corpus
  the desks and themes read. A row can only move up from unevidenced; one pass 1 grounded is
  never re-opened, and `Signpost.backfilled` says which rows came from outside the corpus.
- **Provenance guardrails.** `dataeng/guardrail.py` rejects items lacking a `source_url` or whose
  cleaned text isn't grounded in the source; `council/grounding.py` renders the corpus as a
  *numbered* excerpt list and maps the model's integer `source_index` back to a real URL, so a
  fabricated citation simply fails to resolve. Dropping an item is intended behaviour, not a bug.
- **Progress streaming.** Pipelines stay plain synchronous functions that take an `emit` callback
  (`events.py`, default `noop_emit`, so CLI/tests are unaffected). `sse.py` runs such a function on
  a background thread and streams `progress`/`result`/`error`/`done` SSE events; `jobs.py` is an
  in-process job registry so a client that reloads mid-run can reattach via
  `/api/jobs/{id}/stream`. The registry is **process-local** — a multi-worker deploy would need
  shared storage. Most endpoints exist in both a blocking JSON and a `/stream` variant.
- **Config layering** (`config.py`): optional `.env`, then `.env.{APP_ENV}` (`local` by default),
  and OS env outranks both — which is how Cloud Run injects prod secrets with no `.env.prod`
  shipped. Missing source API keys cause a graceful *skip with a recorded reason*, never a crash.

Persistence is SQLAlchemy over Postgres (`db/tables.py`, `db/repository.py`); `cleaned_items`
upserts are idempotent by `source_url`. Other tables: `council_snapshots`, `thematic_runs`,
`predictions`, `prompt_overrides`, `watchlist_overrides`,
`youtube_channels`/`_videos`/`_matches`.

## Frontend architecture

- `src/app/**` are thin route shells; all real UI lives in `src/components/wtaf/**` ("WTAF" is the
  fund's brand prefix, not a framework). Design tokens are CSS custom properties in
  `src/app/globals.css`; accent mapping in `components/wtaf/accents.ts`.
- **Mock vs live is decided by `NEXT_PUBLIC_API_URL`.** Unset → `USE_MOCK` (`lib/api/client.ts`)
  and endpoints resolve to `lib/mock-data.ts` for offline UI work. Set → real calls, and a failure
  surfaces as an error screen. Critically, the live snapshot is built on top of `emptyLiveData`
  in `lib/api/adapter.ts`, **not** the mock — an empty database must render honest empty states
  rather than fabricated numbers. Preserve that when adding cards.
- `lib/api/wtaf.ts` is the single endpoint layer; `lib/api/adapter.ts` maps backend `CleanedItem` /
  `CouncilReport` / `ThematicRun` shapes onto the dashboard's view models; `lib/api/sse.ts` consumes
  the backend streams. `providers/wtaf-provider.tsx` owns the snapshot plus in-flight discovery
  state, stashing the job id in `sessionStorage` so a reload reconnects to the running job.
- **Not everything belongs in the snapshot.** A resource on its own cadence fetches itself in the
  component that shows it, rather than making every dashboard load pay for it —
  `command-center/themes-card.tsx` (weekly thematic runs) and `pages/sources-youtube.tsx` are the
  two precedents.
- `frontend/AGENTS.md` (which `frontend/CLAUDE.md` just points at): this Next.js version has
  breaking changes vs training data — consult `node_modules/next/dist/docs/` before writing
  Next-specific code.

## Gotchas

- **`./deploy.sh deploy` for routine redeploys, never `all`/`provision`.** Provisioning burns the
  per-minute Cloud SQL Admin API quota and the free-trial instance flow auto-suspends after 30
  days with no recovery path. See `backend/INSTRUCTIONS.md` §8.
- **pnpm only** in `frontend/` (a stray `package-lock.json` exists; don't feed it).
- Commit only when asked. Never `rm -rf` a directory the user's shell may be sitting in.
