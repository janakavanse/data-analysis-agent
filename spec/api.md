# API

## API Style

REST (JSON). All endpoints are served by FastAPI at `http://localhost:8001`. The browser client calls these from the Next.js static export at `/app`.

All responses are wrapped in the existing `ok()` helper:
```json
{ "status": "ok", "data": { ... } }
```
All error responses use the existing `api_error()` helper:
```json
{ "status": "error", "error": { "code": "...", "message": "..." } }
```

## Authentication

None. Sessions are anonymous. No API keys, no login.

---

## Endpoints

### `GET /health`

**Purpose:** Health check. Returns 200 when the server is running.

**Response:**
```json
{ "status": "ok", "data": { "healthy": true } }
```

---

### `POST /sessions`

**Purpose:** Create a new analyst session. The browser calls this on page load.

**Request:** Empty body (no fields required).

**Response:**
```json
{
  "status": "ok",
  "data": {
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "created_at": "2026-06-26T12:00:00Z"
  }
}
```

**Error cases:**

| Status | Code | Condition |
|--------|------|-----------|
| 500 | `DB_ERROR` | Could not write to SQLite |

---

### `POST /sessions/{session_id}/datasets`

**Purpose:** Upload a CSV file into a session. Reads the file with pandas, extracts metadata, stores the file on disk, and persists a dataset record.

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file upload | yes | The CSV file |

**Response:**
```json
{
  "status": "ok",
  "data": {
    "dataset_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "filename": "sales_2024.csv",
    "row_count": 1200,
    "column_names": ["Month", "Region", "Revenue"],
    "created_at": "2026-06-26T12:01:00Z"
  }
}
```

**Error cases:**

| Status | Code | Condition |
|--------|------|-----------|
| 404 | `SESSION_NOT_FOUND` | `session_id` does not exist in `sessions` table |
| 413 | `FILE_TOO_LARGE` | File exceeds 50 MB |
| 422 | `INVALID_FILE_TYPE` | Uploaded file is not a `.csv` (checked by extension and attempted pandas parse) |
| 500 | `UPLOAD_FAILED` | Filesystem write or DB insert failed |

---

### `GET /sessions/{session_id}/datasets`

**Purpose:** List all datasets uploaded in a session.

**Response:**
```json
{
  "status": "ok",
  "data": {
    "datasets": [
      {
        "dataset_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
        "filename": "sales_2024.csv",
        "row_count": 1200,
        "column_names": ["Month", "Region", "Revenue"],
        "created_at": "2026-06-26T12:01:00Z"
      }
    ]
  }
}
```

**Error cases:**

| Status | Code | Condition |
|--------|------|-----------|
| 404 | `SESSION_NOT_FOUND` | `session_id` does not exist |

---

### `POST /sessions/{session_id}/queries`

**Purpose:** Run a natural-language query against one or more uploaded datasets. Invokes the LangGraph analyst graph and returns the answer.

**Request (Phase 1–2):**
```json
{
  "question": "What is the average revenue by region?",
  "dataset_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7"
}
```

**Request (Phase 3, multi-file):**
```json
{
  "question": "Join orders to customers on customer_id and show the top 5 by revenue.",
  "dataset_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "dataset_ids": [
    "7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "3fa85f64-5717-4562-b3fc-2c963f66afa6"
  ]
}
```

> When `dataset_ids` is provided (Phase 3), it takes precedence over `dataset_id` for the graph. `dataset_id` remains present in the request for backward compatibility and is used to populate `RunRow.dataset_id` (first element of the list).

**Response (Phase 1):**
```json
{
  "status": "ok",
  "data": {
    "run_id": "a3bb189e-8bf9-3888-9912-ace4e6543002",
    "status": "completed",
    "answer_text": "The average revenue by region is: North $52,400, South $38,200, West $61,700.",
    "table_data": [
      { "Region": "North", "Avg Revenue": 52400 },
      { "Region": "South", "Avg Revenue": 38200 },
      { "Region": "West", "Avg Revenue": 61700 }
    ],
    "chart_b64": null
  }
}
```

**Response (Phase 2, with chart):**
```json
{
  "status": "ok",
  "data": {
    "run_id": "a3bb189e-8bf9-3888-9912-ace4e6543002",
    "status": "completed",
    "answer_text": "Here is a bar chart of revenue by region.",
    "table_data": [ ... ],
    "chart_b64": "iVBORw0KGgoAAAANSUhEUgAA..."
  }
}
```

**Response (on failure):**
```json
{
  "status": "error",
  "error": {
    "code": "QUERY_FAILED",
    "message": "Gemini API error: 429 Resource exhausted"
  }
}
```

**Error cases:**

| Status | Code | Condition |
|--------|------|-----------|
| 404 | `SESSION_NOT_FOUND` | `session_id` does not exist |
| 404 | `DATASET_NOT_FOUND` | `dataset_id` does not exist or does not belong to `session_id` |
| 422 | `EMPTY_QUESTION` | `question` is empty or whitespace only |
| 422 | `QUERY_FAILED` | LangGraph graph returned `status == "failed"` (LLM error, file read error, etc.) |
| 500 | `INTERNAL_ERROR` | Unexpected exception outside the graph |

---

### `GET /runs/{run_id}` (existing, kept for compatibility)

**Purpose:** Retrieve a past run by ID. Returns the same fields as the query response.

**Response:** Same shape as `POST /sessions/{session_id}/queries` response `data` object.

**Error cases:**

| Status | Code | Condition |
|--------|------|-----------|
| 404 | `NOT_FOUND` | Run ID does not exist |
