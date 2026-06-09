# Implementation Plan

## Overview

Layer 1 (Discovery) fan-out already exists in `backend/app/discovery/`. These tasks
formalize/extend it (query refinement) and build Layer 2 (Data Engineering) end to end.
Discovery fan-out/merge/dedupe stays plain Python; refinement and all Data Eng skills use
the shared Bedrock `converse` wrapper. No LangGraph.

## Task Dependency Graph

```text
1 (deps + Bedrock wrapper)
├── 2 (query refinement) ──► 4 (wire refinement into discovery)
├── 3 (formalize fan-out tests)  [independent of 1]
├── 5 (DB foundation)
│   └── 6 (DE models + taxonomy)
│       └── 7 (DE skills) ──► 8 (pipeline) ──► 9 (API) ──► 10 (integration tests)
└── (1 also unblocks 7, since skills use the Bedrock wrapper)
```

Critical path: 1 → 5 → 6 → 7 → 8 → 9 → 10. Tasks 2/4 and 3 can proceed in parallel
with the Layer 2 chain.

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1", "3"], "dependsOn": [] },
    { "wave": 2, "tasks": ["2", "5"], "dependsOn": ["1"] },
    { "wave": 3, "tasks": ["4", "6"], "dependsOn": ["2", "5"] },
    { "wave": 4, "tasks": ["7"], "dependsOn": ["1", "6"] },
    { "wave": 5, "tasks": ["8"], "dependsOn": ["7"] },
    { "wave": 6, "tasks": ["9"], "dependsOn": ["8"] },
    { "wave": 7, "tasks": ["10"], "dependsOn": ["9"] }
  ]
}
```

## Tasks

- [x] 1. Add dependencies and shared LLM foundation
  - Add `boto3`, `sqlalchemy`, `psycopg[binary]`, `alembic` via `uv add`; re-export `requirements.txt`.
  - Add `bedrock_model_id` (default Claude Sonnet), AWS region, and `database_url` to `app/config.py`.
  - Implement `app/llm/bedrock.py` `converse_structured(schema, system, user_content, *, model_id=None, max_retries=3)`: call Bedrock `converse`, parse JSON, validate against the Pydantic schema, retry on `ValidationError` and transient/throttling errors with backoff, raise `BedrockReasoningError(kind)` on exhaustion.
  - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 16.2, 16.3_

- [x] 2. Query Refinement & Clarification (Discovery)
- [x] 2.1 Refinement models and skill
  - Add `RefineLLMOutput`, `Proceed`, `Clarify`, `ClarificationMode`, `QueryClassification` to `app/models.py` (or `app/llm/schemas.py`).
  - Implement `app/discovery/refine.py` `refine_query(query, mode, round=0)` using `converse_structured`: classify clear/ambiguous, rewrite clear queries, preserve the original query, return `Clarify` (interactive) or best-effort `Proceed` (auto-proceed); fall back to the original query on LLM failure.
  - _Requirements: 2.1, 2.2, 2.3, 2.6, 2.9_
- [x] 2.2 Query intake validation
  - Validate the topic query: trim, reject empty/whitespace, reject >500 chars; validate `max_results ∈ [1,50]`.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 3.5, 3.6_
- [x] 2.3 Clarification round control
  - Track clarification rounds; cap at the configured max (default 2); on cap reached, proceed to fan-out with the most recent query.
  - _Requirements: 2.4, 2.5, 2.7, 2.8_
- [x] 2.4 Unit tests for refinement (Bedrock mocked)
  - Cover clear/ambiguous × interactive/auto-proceed, original-query preservation, round cap, and LLM-failure fallback.
  - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6, 2.7, 2.8, 2.9_

- [x] 3. Formalize Discovery fan-out with tests (existing code)
  - Add unit tests for `_dedupe` (first-seen by exact URL, order preserved) and merge order.
  - Add unit tests for `_safe_call` converting `SourceUnavailable` and arbitrary exceptions into `SkippedSource`; assert both-branches-skipped returns empty items + 2 skipped without raising.
  - Assert empty/whitespace-text results are excluded; every retained item has a non-empty `source_url`; `retrieved_at` is set.
  - _Requirements: 3.1, 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.4, 5.5, 5.6, 6.1, 6.4, 6.5, 6.6_

- [x] 4. Wire refinement into the discovery flow
  - Have the discovery entrypoint run `refine_query` before fan-out and pass the refined query to `discover(...)`.
  - Carry the original+refined query pair into `DiscoveryResult` for audit.
  - _Requirements: 2.2, 2.3, 2.6, 2.9_

- [x] 5. Database foundation (Postgres)
- [x] 5.1 SQLAlchemy session + cleaned_items table
  - Implement `app/db/session.py` (engine/session from `database_url`) and `app/db/tables.py` with the `cleaned_items` table (source_url UNIQUE, stream, industry, entities JSONB, themes JSONB, segments JSONB, published_at nullable, ingested_at) + indexes.
  - Add an Alembic migration creating the table and indexes.
  - _Requirements: 14.1, 14.2, 14.3, 14.4, 15.2, 15.3_
- [x] 5.2 Repository with idempotent upsert
  - Implement `app/db/repository.py` `upsert_cleaned_item(item)` using `INSERT ... ON CONFLICT (source_url) DO UPDATE`; on write failure roll back and raise so the pipeline records the failure.
  - _Requirements: 15.1, 15.5, 15.6_

- [x] 6. Data Engineering models and taxonomy
  - Add `Stream`, `ResolvedEntity`, `CleanedItem`, `ProcessingFailure`, `DataEngReport` to `app/models.py`.
  - Add `app/taxonomy.py`: the `Market_Theme_Taxonomy` list (Healthcare, Technology, Solar, Oil & Gas, Financials, ...), the project sector list, and the built-in alias→ticker / macro-alias map.
  - _Requirements: 7.5, 9.1, 9.2, 10.2, 11.1, 11.4_

- [x] 7. Data Engineering skills (Bedrock-backed)
- [x] 7.1 Noise redaction (`dataeng/redact.py`)
  - Remove ad reads/filler, preserve signal, keep each surviving passage tied to its `TranscriptSegment.start`; if the item is all noise, exclude with a reason.
  - _Requirements: 8.1, 8.2, 8.3, 8.4_
- [x] 7.2 Entity resolution (`dataeng/entities.py`)
  - Resolve company aliases → tickers and macro aliases → entities via the built-in map + LLM; de-duplicate canonical set; empty set allowed; never map unrecognized tokens.
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_
- [x] 7.3 Label assignment (`dataeng/labels.py`)
  - Assign exactly one MACRO/MICRO and exactly one industry from the sector list; multi-sector → single most prominent; no match → `Unclassified`.
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_
- [x] 7.4 Theme assignment (`dataeng/themes.py`)
  - Classify the item against `Market_Theme_Taxonomy` via the LLM; assign only taxonomy themes, de-duplicated; no match → no theme, item retained.
  - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_
- [x] 7.5 No-orphan-data guardrail (`dataeng/guardrail.py`)
  - Drop any claim/item lacking `source_url`, any video claim lacking a valid `timestamp_start`, and any claim whose text is not present in the source; surface each drop with a reason.
  - _Requirements: 13.1, 13.2, 13.3, 13.4_

- [x] 8. Data Engineering pipeline (`dataeng/pipeline.py`)
  - Orchestrate per item: redact → entities → labels → themes → guardrail → upsert; build `CleanedItem` with provenance + staleness metadata (`published_at` ISO8601/nullable, `ingested_at` UTC).
  - Process items independently: isolate per-item failures, record `ProcessingFailure(source_url, reason)`, continue; empty input → processed count 0; return `DataEngReport(persisted, failed, failures)`.
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 14.1, 14.2, 14.3, 14.4, 15.1_

- [x] 9. API endpoints (`app/main.py`)
  - `POST /discover` {query, mode?, max_results?}: refine → fan-out; return `DiscoveryResult`, or a clarification payload when interactive + ambiguous.
  - `POST /discover/clarify` {original_query, clarified_query, round}: re-run refinement (round cap 2).
  - `POST /dataeng/process`: accept a `DiscoveryResult`, run the pipeline, return `DataEngReport`. Keep existing `GET /discover` for the CLI.
  - _Requirements: 1.1, 2.4, 2.5, 2.7, 7.1, 16.1_

- [x] 10. Integration tests and verification
  - Bedrock wrapper retry behaviour with a stubbed client (ValidationError→success; Throttling→success; exhaustion→error).
  - Repository: same `source_url` twice → one row (15.5); simulated write failure → rollback + failure recorded (15.6).
  - End-to-end against a disposable Postgres schema: `POST /discover` (auto_proceed) → `POST /dataeng/process` → rows present with source_url, stream, industry, ingested_at; tear down the schema after.
  - _Requirements: 7.2, 7.3, 12.3, 12.4, 12.5, 13.3, 13.4, 15.5, 15.6_

## Notes

- Discovery's fan-out/merge/dedupe (Task 3) is already implemented; that task only adds
  tests to lock the behaviour. All new reasoning (Tasks 2, 7) goes through the shared
  Bedrock wrapper from Task 1.
- `POST /dataeng/process` is a separate call from `/discover` (not auto-triggered).
- Themes come from the configured `Market_Theme_Taxonomy` in `taxonomy.py` — there is no
  watchlist in this layer.
- Default reasoning model is Claude Sonnet (`settings.bedrock_model_id`).
- After adding dependencies in Task 1, re-run `uv export` to keep `requirements.txt` in sync.
