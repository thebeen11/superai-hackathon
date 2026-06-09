# Testing Instructions — Discovery + Data Engineering Backend

This is the Layer 1 (Discovery) + Layer 2 (Data Engineering) backend of the Hedge Fund
AI Agent Council. It turns a research topic into clean, labelled, source-anchored rows in
Postgres, using Amazon Bedrock (Claude Opus) for reasoning.

---

## 1. Prerequisites

- **uv** (Python package manager) — https://docs.astral.sh/uv/
- **AWS credentials** in `creds.txt` at the repo root (temporary STS creds; they expire).
- Access to the shared **RDS Postgres** (already provisioned) — connection string is in
  `backend/.env`.

> All commands below are run from the `backend/` directory unless stated otherwise.

---

## 2. One-time setup

```bash
uv sync                 # install dependencies
```

`backend/.env` should already exist with the Bedrock model, AWS region, and the RDS
`DATABASE_URL`. If it doesn't, copy the example and ask the team for the DB password:

```bash
cp .env.example .env
```

You also need an `EXA_API_KEY` in `.env` for live web discovery (ask the team). Without
it, the web branch is skipped gracefully but you'll get no results.

---

## 3. Run the server

The app needs AWS credentials in its environment for Bedrock, so source `creds.txt` first:

```
uv run uvicorn app.main:app --reload'
```

- Server: **http://localhost:8000**
- Interactive API docs (try endpoints in the browser): **http://localhost:8000/docs**

Quick health check (in another terminal):

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

---

## 4. The API test flow

### Path A — One-shot (simplest)

`POST /discover` → `POST /dataeng/process` → `GET /items`

**Step 1 — Discover** (Opus refines the query, then fans out to Exa + YouTube):

```bash
curl -s -X POST http://localhost:8000/discover \
  -H 'Content-Type: application/json' \
  -d '{"query":"meta company","mode":"auto_proceed","max_results":5}'
```

Returns a `DiscoveryResult` `{query, original_query, items[], skipped[]}`.

**Step 2 — Process** (clean → label → theme → guardrail → persist to Postgres):

```bash
curl -s -X POST http://localhost:8000/discover \
  -H 'Content-Type: application/json' \
  -d '{"query":"meta company","mode":"auto_proceed","max_results":5}' \
| curl -s -X POST http://localhost:8000/dataeng/process \
  -H 'Content-Type: application/json' --data-binary @-
```

Returns a `DataEngReport` `{persisted, failed, failures[]}`.

**Step 3 — Read back** the stored rows:

```bash
curl -s 'http://localhost:8000/items?stream=MICRO&limit=10'
```

### Path B — Interactive (human-in-the-loop)

`POST /discover` (interactive) → `Clarify` → `POST /discover/clarify` → process → items

**Step 1 — Discover with a vague query:**

```bash
curl -s -X POST http://localhost:8000/discover \
  -H 'Content-Type: application/json' \
  -d '{"query":"meta","mode":"interactive","max_results":5}'
```

If ambiguous, returns a `Clarify` payload `{original_query, questions[], round}` instead
of results (no fan-out yet).

**Step 2 — Answer with a sharper query** (increment `round` each time):

```bash
curl -s -X POST http://localhost:8000/discover/clarify \
  -H 'Content-Type: application/json' \
  -d '{"clarified_query":"Meta Platforms (META) stock outlook","round":1,"mode":"interactive","max_results":5}'
```

Returns a `DiscoveryResult`. (Clarification is capped at 2 rounds, after that it proceeds
automatically.)

**Step 3 — Process** the clarified result into Postgres (pipe `/discover/clarify` straight
into `/dataeng/process`):

```bash
curl -s -X POST http://localhost:8000/discover/clarify \
  -H 'Content-Type: application/json' \
  -d '{"clarified_query":"Meta Platforms (META) stock outlook","round":1,"mode":"interactive","max_results":5}' \
| curl -s -X POST http://localhost:8000/dataeng/process \
  -H 'Content-Type: application/json' --data-binary @-
```

Returns a `DataEngReport` `{persisted, failed, failures[]}`.

**Step 4 — Read back** the stored rows:

```bash
curl -s 'http://localhost:8000/items?ticker=$META&limit=10'
```

---

## 5. Streaming (SSE) flow — watch it live

Every endpoint above has a **`/stream` variant** that emits Server-Sent Events so you can
watch each stage happen in real time (refinement → per-source fan-out → per-item
clean/label/theme/persist). Same flow, same results, just streamed.

Use `curl -N` (the `-N` disables buffering so events appear as they happen). Each frame is
`event: <name>` + `data: <json>`; the stream ends with `event: done`. The `progress`
events are behind-the-scenes status; the final `result` event carries the payload.

### Path B over SSE

**Step 1 — interactive discover** (streams refinement, returns clarifying questions):

```bash
curl -N -X POST http://localhost:8000/discover/stream \
  -H 'Content-Type: application/json' \
  -d '{"query":"meta","mode":"interactive","max_results":3}'
```

**Step 2 — answer the clarification** (streams refinement + the Exa/YouTube fan-out):

```bash
curl -N -X POST http://localhost:8000/discover/clarify/stream \
  -H 'Content-Type: application/json' \
  -d '{"clarified_query":"Meta Platforms (META) stock outlook","round":1,"mode":"interactive","max_results":3}'
```

**Step 3 — process into Postgres** (streams per-item progress: redact → entities → labels
→ themes → persisted). Feed the clarified `DiscoveryResult` into the process stream:

```bash
curl -s -X POST http://localhost:8000/discover/clarify \
  -H 'Content-Type: application/json' \
  -d '{"clarified_query":"Meta Platforms (META) stock outlook","round":1,"mode":"interactive","max_results":3}' \
| curl -N -X POST http://localhost:8000/dataeng/process/stream \
  -H 'Content-Type: application/json' --data-binary @-
```

**Step 4 — read back, streamed:**

```bash
curl -N 'http://localhost:8000/items/stream?ticker=$META&limit=10'
```

> Tip: pipe through `grep -E '^event:|message'` to see just the status messages without
> the full payloads. In a browser, consume `GET` streams with `EventSource` and `POST`
> streams with `fetch` + `ReadableStream`.

---

## 6. Endpoint reference

| Method | Path | Purpose | Returns |
| ------ | ---- | ------- | ------- |
| GET | `/health` | liveness check | `{status}` |
| POST | `/discover` | refine query → fan out (Exa + YouTube) | `DiscoveryResult` or `Clarify` |
| POST | `/discover/clarify` | resume after clarifying questions | `DiscoveryResult` or `Clarify` |
| POST | `/dataeng/process` | clean + label + theme + persist | `DataEngReport` |
| GET | `/items` | read persisted rows (filters: `stream`, `theme`, `ticker`, `limit`) | `list[CleanedItem]` |
| GET | `/discover?query=` | plain fan-out, no LLM (quick test, no AWS needed) | `DiscoveryResult` |

**Streaming variants** (Server-Sent Events — see section 5): every endpoint above has a
`/stream` version with the same inputs — `POST /discover/stream`,
`POST /discover/clarify/stream`, `POST /dataeng/process/stream`, `GET /discover/stream`,
`GET /items/stream`. They emit `progress` events as work happens, then a final `result`
(or `error`) event, closed by `done`.

**Key request fields**
- `mode`: `"auto_proceed"` (skip clarification, one-shot) or `"interactive"` (ask when ambiguous). Default is interactive.
- `max_results`: 1–50 results per source.
- `/items` filters: `stream=MICRO|MACRO`, `theme=Solar` (etc.), `ticker=$META`.

---

## 7. Inspecting the database directly (DBeaver / psql)

The data lives in the shared **RDS Postgres** (see `DATABASE_URL` in `.env`):

- Host: `council-db.cdkao7bmhbkr.us-west-2.rds.amazonaws.com`
- Port: `5432`
- Database / User: `council`
- Password: ask the team (it's in `backend/.env`)

Table: `cleaned_items` (schema `public`).

---

## 8. Run the tests

```bash
uv run pytest        # 32 unit tests; no network or DB needed (Bedrock + DB are mocked)
```

---

## 9. Troubleshooting

- **DB connection times out** → the RDS security group only allows specific IPs and your
  IP may have rotated. Add your current IP (run from the **repo root**):
  ```bash
  bash -c 'set -a; source creds.txt; set +a; aws ec2 authorize-security-group-ingress \
    --region us-west-2 --group-id sg-019ccf119510b074f \
    --protocol tcp --port 5432 --cidr $(curl -s https://checkip.amazonaws.com)/32'
  ```
- **`ExpiredTokenException` from Bedrock** → `creds.txt` STS tokens expired. Get fresh
  credentials and replace `creds.txt`, then restart the server.
- **`EXA_API_KEY not set` in `skipped`** → add the Exa key to `backend/.env` and restart.
- **No results, both sources skipped** → expected if neither `EXA_API_KEY` nor
  `YOUTUBE_API_KEY` is set; the run still succeeds, just with empty `items`.
- **An item shows up in `failed` with "cleaned text not found in source"** → the
  anti-fabrication guardrail dropped it (the cleaned text wasn't grounded in the source).
  This is intended safety behaviour, not a crash.

---

## 10. What to look for when testing

A successful end-to-end run should show:
1. `POST /discover` returns real web sources with the query **refined** by Opus
   (`original_query` vs `query` differ).
2. `POST /dataeng/process` reports `persisted > 0`.
3. `GET /items` returns rows with sensible `stream` (MACRO/MICRO), `industry`, `themes`
   (e.g. Solar, Technology), and resolved `entities` (e.g. `$META`).
4. Every stored item has a `source_url` — nothing is "orphan" / unsourced.
