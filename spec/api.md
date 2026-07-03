# API

---

## API Style

REST (FastAPI), JSON envelope on every response — `{"data": ..., "error": null}` on success, or a `4xx/5xx` with `{"detail": {"code": ..., "message": ...}}` on a request-level error (per the existing `src/api/_common.py` `ok()`/`api_error()` helpers). Status **polling** (not WebSockets/SSE) is the mechanism for the live "generating code… / running analysis…" indicator — the frontend calls `GET /queries/{id}` on an interval (~750ms) until `status` reaches a terminal value.

> **Assumed:** the brief left the polling-vs-SSE choice to the spec-writer, and explicitly said simple status-field polling is acceptable given latency doesn't matter. The ~750ms interval is a reasonable default, not specified in the brief — it can be tuned client-side with no API change.

## Endpoints / Commands

### `POST /sessions`

**Purpose:** create a new session at the start of an upload-and-ask visit.

**Request:** empty body.

**Response:**
```json
{
  "data": { "session_id": "uuid", "created_at": "iso8601" },
  "error": null
}
```

**Error cases:**
| Status | Condition |
|--------|-----------|
| 500 | Database write failure |

---

### `POST /sessions/{session_id}/datasets`

**Purpose:** upload a CSV/XLSX file, profile it locally with pandas, and store the schema. *(Phase 1)*

**Request:** `multipart/form-data`, field `file` (`.csv` or `.xlsx`).

**Response:**
```json
{
  "data": {
    "dataset_id": "uuid",
    "original_filename": "expenses.csv",
    "file_type": "csv",
    "row_count": 12034,
    "column_count": 8,
    "schema": [
      {"name": "amount", "dtype": "float64", "null_count": 0, "min": 0.0, "max": 4302.5, "distinct_sample": null},
      {"name": "category", "dtype": "object", "null_count": 3, "min": null, "max": null, "distinct_sample": ["food", "travel", "rent"]}
    ]
  },
  "error": null
}
```

**Error cases:**
| Status | Condition |
|--------|-----------|
| 400 | Missing file, unsupported file type (not `.csv`/`.xlsx`), or the file fails to parse (corrupt/empty) |
| 404 | `session_id` not found |
| 500 | Disk write failure, or an unexpected profiling error |

---

### `GET /sessions/{session_id}/datasets/{dataset_id}`

**Purpose:** re-fetch a dataset's profile summary (e.g. on page reload within the same session). *(Phase 1)*

**Response:** same shape as the `POST` response's `data` object.

**Error cases:**
| Status | Condition |
|--------|-----------|
| 404 | `session_id` or `dataset_id` not found |

---

### `POST /sessions/{session_id}/queries`

**Purpose:** ask a natural-language question about the session's dataset. Creates a `Query` row and starts the LangGraph pipeline in the background; returns immediately so the frontend can begin polling. *(Phase 1)*

**Request:**
```json
{ "dataset_id": "uuid", "question": "what is the average amount by category?" }
```

**Response:**
```json
{
  "data": { "query_id": "uuid", "status": "pending", "turn_index": 0 },
  "error": null
}
```

**Error cases:**
| Status | Condition |
|--------|-----------|
| 400 | Empty question, or `dataset_id` does not belong to `session_id` |
| 404 | `session_id` or `dataset_id` not found |
| 409 | The session already has a non-terminal query in flight (`status` in `pending`/`generating_code`/`running_analysis`) — one query per session at a time, per `spec/roadmap.md` → Key Constraints; the response names the in-flight `query_id` so the client can resume polling it instead |

---

### `GET /queries/{query_id}`

**Purpose:** poll for a query's live status and, once terminal, its full result. This is the endpoint the frontend polls to drive the status indicator and render the answer card. *(Phase 1; response gains chart/followups fields in Phase 2)*

**Response (in progress):**
```json
{
  "data": { "query_id": "uuid", "status": "running_analysis", "question": "...", "turn_index": 0 },
  "error": null
}
```

**Response (completed):**
```json
{
  "data": {
    "query_id": "uuid",
    "status": "completed",
    "question": "what is the average amount by category?",
    "answer_text": "The average amount is $84.21 for food, $212.50 for travel, and $1,450.00 for rent.",
    "result_table": [{"category": "food", "avg_amount": 84.21}, {"category": "travel", "avg_amount": 212.50}],
    "generated_code": "result = df.groupby('category')['amount'].mean()\n...",
    "retry_count": 0,
    "token_usage": {"prompt_tokens": 412, "completion_tokens": 96, "total_tokens": 508, "thinking_tokens": 0},
    "chart_spec": null,
    "suggested_followups": ["What is the median amount by category?", "Which category has the most transactions?"],
    "error": null,
    "created_at": "iso8601",
    "completed_at": "iso8601"
  },
  "error": null
}
```

**Response (failed):**
```json
{
  "data": {
    "query_id": "uuid",
    "status": "failed",
    "question": "...",
    "answer_text": null,
    "error": "Column 'revenu' does not exist. Did you mean 'revenue'? The generated code failed twice; please rephrase your question.",
    "retry_count": 1,
    "token_usage": {"prompt_tokens": 780, "completion_tokens": 140, "total_tokens": 920, "thinking_tokens": 0}
  },
  "error": null
}
```

**Error cases:**
| Status | Condition |
|--------|-----------|
| 404 | `query_id` not found |

---

### `GET /sessions/{session_id}/queries`

**Purpose:** fetch the ordered conversation thread for a session (e.g. on page reload within the same session, or to render the full Q&A history). *(Phase 1)*

**Response:**
```json
{
  "data": [
    { "query_id": "uuid", "turn_index": 0, "question": "...", "status": "completed", "answer_text": "..." }
  ],
  "error": null
}
```

**Error cases:**
| Status | Condition |
|--------|-----------|
| 404 | `session_id` not found |

---

### `POST /queries/{query_id}/export`

**Purpose:** export a cleaned/filtered version of the data produced by a completed query, as a downloadable file. Re-executes that query's already-audited `generated_code` (via the same sandbox) against the dataset file to regenerate the full result dataframe, then streams it — no new LLM call, no persisted "past exports" library (ephemeral, this-request-only). *(Phase 2)*

**Request:**
```json
{ "format": "csv" }
```
`format` is `"csv"` or `"xlsx"`.

> **Assumed:** the request shape for choosing an export format is not specified in the brief; a single `format` field defaulting to `"csv"` is the minimal reasonable design.

**Response:** binary file stream (`Content-Disposition: attachment; filename="export.csv"`), not a JSON envelope.

**Error cases:**
| Status | Condition |
|--------|-----------|
| 400 | `query_id`'s status is not `"completed"`, or its generated code produced no dataframe-shaped result to export |
| 404 | `query_id` not found |
| 500 | Re-execution failure (the dataset file changed/moved since the original run) |

---

### `GET /health`

**Purpose:** existing skeleton health check, unchanged.

## Authentication

None. This is a genuinely single-user, local-only tool (see `spec/roadmap.md` → Out of Scope) — no auth layer is built in any phase.
