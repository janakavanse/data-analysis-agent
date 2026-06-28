# API

> HTTP contract for DataChat. Single-origin FastAPI on `:8001`; the Next.js static export is served at `/app/` and calls these same-origin routes. Every JSON route returns the skeleton envelope `ok(data)` → `{"data": ..., "error": null}`, or raises `api_error(code, message, status)` → `{"detail": {"code", "message"}}`. No authentication — single local owner.

---

## API Style

REST + JSON, plus one **Server-Sent Events** streaming endpoint for the analysis answer. All routes are mounted under `/api` (the static frontend is at `/app/`, so `/api` avoids collision).

> **Assumed:** routes are namespaced under `/api/...`. The skeleton mounts `/runs` at root and the frontend at `/app`; DataChat moves its routes under `/api` to keep the surface clean alongside the static mount. The frontend calls same-origin `/api/...`.

## Endpoints / Commands

### `POST /api/datasets` — upload + profile (Phase 1, REAL)

**Purpose:** Upload a single CSV, store it locally, profile it with pandas (no LLM), return the dataset + profile.

**Request:** `multipart/form-data` with a `file` field (the CSV).

**Response:**
```json
{
  "data": {
    "dataset_id": "uuid",
    "name": "sales_2025.csv",
    "profile": {
      "row_count": 10234,
      "columns": [
        {"name": "region", "dtype": "object", "missing": 0, "distinct": 5, "sample_values": ["North", "South"]},
        {"name": "revenue", "dtype": "float64", "missing": 12, "min": 0.0, "max": 98213.5, "mean": 1423.7}
      ],
      "sample_rows": [ { "region": "North", "revenue": 1200.0 } ]
    }
  },
  "error": null
}
```

**Error cases:**
| Status | Code | Condition |
|--------|------|-----------|
| 400 | `MALFORMED_FILE` | pandas cannot parse the CSV (message carries the real parse error) |
| 400 | `UNSUPPORTED_TYPE` | non-CSV uploaded (Excel/multi-sheet — "coming in a later phase") |
| 413 | `FILE_TOO_LARGE` | exceeds `AGENT_MAX_UPLOAD_MB` |
| 500 | `UPLOAD_FAILED` | disk write failure |

### `POST /api/datasets/{dataset_id}/ask` — analyze (Phase 1, REAL, **streaming**)

**Purpose:** Ask a plain-English question; run the plan-execute agent and **stream** the answer back via SSE while persisting the full run.

**Request:**
```json
{ "question": "What is the average revenue by region?" }
```

**Response:** `text/event-stream`. Event sequence (each `event:`/`data:` JSON):
- `event: status` → `{"step": "planning"}` / `{"step": "generating_code"}` / `{"step": "executing"}` / `{"step": "synthesizing"}` — drives the step counter.
- `event: plan` → `{"plan": "1. ...\n2. ..."}`
- `event: code` → `{"code": "result = df.groupby('region')['revenue'].mean()"}`
- `event: token` → `{"text": "<next chunk of the streamed answer>"}` (repeated)
- `event: done` → `{"message_id": "uuid", "key_numbers": {...}, "result_table": {...}, "prompt_tokens": 812, "completion_tokens": 143, "cost_usd": 0.0007, "status": "completed"}`
- `event: error` → `{"message_id": "uuid", "error": "<real error/traceback>", "code": "<offending code>", "status": "failed"}` (the server does **not** 500; the failure rides the stream)

**Error cases (pre-stream):**
| Status | Code | Condition |
|--------|------|-----------|
| 404 | `NOT_FOUND` | unknown `dataset_id` |
| 400 | `EMPTY_QUESTION` | blank question |

### `GET /api/datasets/{dataset_id}` — load a dataset + its thread (Phase 1, REAL)

**Purpose:** Reopen a dataset: returns the profile and its conversation/history (so the chat panel rehydrates across days).

**Response:**
```json
{
  "data": {
    "dataset_id": "uuid",
    "name": "sales_2025.csv",
    "profile": { },
    "messages": [
      {"id": "uuid", "question": "...", "answer": "...", "status": "completed",
       "key_numbers": {}, "result_table": {}, "cost_usd": 0.0007, "created_at": "..."}
    ]
  },
  "error": null
}
```
| Status | Code | Condition |
|--------|------|-----------|
| 404 | `NOT_FOUND` | unknown `dataset_id` |

### `GET /api/datasets/{dataset_id}/messages` — run history list (Phase 1, REAL)

**Purpose:** Browse the audit trail for a dataset — summaries ordered by `created_at`.

**Response:** `{"data": [{"id", "question", "status", "cost_usd", "created_at"}], "error": null}`

### `GET /api/messages/{message_id}` — run detail (Phase 1, REAL)

**Purpose:** Full record of one run for the audit trail / re-inspection.

**Response:** `{"data": {"id", "dataset_id", "question", "plan", "generated_code", "answer", "key_numbers", "result_table", "prompt_tokens", "completion_tokens", "cost_usd", "status", "error", "created_at", "completed_at"}, "error": null}`
| Status | Code | Condition |
|--------|------|-----------|
| 404 | `NOT_FOUND` | unknown `message_id` |

### `GET /api/datasets` — library list (Phase 1: STUBBED, real from Phase 3)

**Purpose:** List all datasets (the persistent library sidebar).
**Phase 1 behaviour:** returns `{"data": [], "error": null}` (or only the single active dataset). The multi-dataset persistent library, derived-dataset saving, and cross-day reopening from the sidebar are **Phase 3**. The single active dataset is fully real in Phase 1 via the routes above; this list endpoint is the stub that becomes real in Phase 3. The UI labels the sidebar as a stub.

### `GET /health` — liveness (skeleton, kept)

Returns `{"data": {"status": "ok"}, "error": null}`.

## Deferred endpoints (later phases)

| Endpoint | Phase | Purpose |
|----------|-------|---------|
| `POST /api/datasets/{id}/derive` | 3 | Save a derived/cleaned dataset as a new library item |
| `DELETE /api/datasets/{id}` | 3 | Remove a dataset from the library (file + messages) |
| `GET /api/cost/today` | 5 | Running daily cost total |
| `POST /api/datasets/{id}/ask` `confirm` flag | 5 | Confirm-before-heavy-work gate |

## Authentication

None. DataChat is a single-owner local tool with no multi-tenant or remote access; the OS protects the local files and DB. (Documented as an explicit non-requirement so a generator never adds an auth layer.)
