# API

---

## API Style

REST (FastAPI, `api:app` on port 8001). All responses use the skeleton envelope `{"data": ..., "error": null}` (see `src/api/_common.py`); errors raise `HTTPException` with `detail = {code, message}`. The frontend reads `data` / `detail.message`.

> The existing `/runs` endpoints from the skeleton are superseded by the dataset/ask endpoints below for the analysis path. `GET /health` is retained.

## Endpoints / Commands

### `POST /datasets`  (Phase 1)

**Purpose:** Upload a CSV; ingest it into a local DuckDB file; return the dataset summary.

**Request:** `multipart/form-data` with a `file` field (CSV; Excel added Phase 3).

**Response:**
```json
{
  "data": {
    "id": "uuid",
    "name": "sales.csv",
    "row_count": 12345,
    "schema": [{ "name": "revenue", "type": "BIGINT" }, { "name": "region", "type": "VARCHAR" }],
    "profile": null
  },
  "error": null
}
```
`profile` is `null` in Phase 1 (populated in Phase 2).

**Error cases:**
| Status | Condition |
|--------|-----------|
| 400 | Not a CSV / unparseable / empty file |
| 413 | File exceeds the ~100MB limit |
| 500 | Ingest/DuckDB failure |

### `POST /datasets/{id}/ask`  (Phase 1) — **the core contract both Phase-1 slices build to**

**Purpose:** Ask one plain-English question about a dataset; run the agent; return the answer with the exact SQL.

**Request:**
```json
{ "question": "What is the total revenue?" }
```

**Response (success):**
```json
{
  "data": {
    "run_id": "uuid",
    "dataset_id": "uuid",
    "status": "completed",
    "question": "What is the total revenue?",
    "answer": "Total revenue across all rows is 4,210,500.",
    "sql": "SELECT sum(revenue) AS total_revenue FROM data;",
    "result": [{ "total_revenue": 4210500 }],
    "flagged": false,
    "error": null,

    "chart": null,
    "summary_table": null,
    "followups": null,
    "tokens": null
  },
  "error": null
}
```

**Response contract notes (binding for both slices):**
- Phase 1 ALWAYS returns `answer`, `sql`, `result` on success. `chart`, `summary_table`, `followups`, `tokens` are present as `null` placeholders so the frontend can wire stub panels without a contract change — they are populated in Phases 2–3.
- `flagged: true` when the agent returns a best-guess (ambiguous question) rather than a confident answer — the UI shows a "best-guess" badge.
- On failure (`status: "failed"`): `answer`/`sql`/`result` may be `null` and `error` carries the reason. The agent NEVER returns a fabricated number — a failure is surfaced, not hidden.

**Error cases:**
| Status | Condition |
|--------|-----------|
| 400 | Empty question |
| 404 | Unknown dataset id |
| 500 | Unexpected internal error (Gemini/infra). SQL errors are retried internally and do not 500 unless retries are exhausted, which returns `200` with `status:"failed"`. |

### `GET /datasets/{id}/runs`  (Phase 3)

**Purpose:** List past runs (audit trail) for a dataset: question, SQL, result, tokens, timestamp.

### `POST /datasets/{id}/ask/stream`  (Phase 3)

**Purpose:** Server-Sent Events stream of agent steps (generate SQL → execute → answer) for live transparency.

### `GET /health`  (existing)

Liveness check; returns `{ "data": { "status": "ok" }, "error": null }`.

## Authentication

None — single-user, local-only. The app binds to localhost; there is no auth layer by design (`roadmap.md` out-of-scope).
