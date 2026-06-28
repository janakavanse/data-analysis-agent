# API

---

## API Style

REST (FastAPI), single origin on `:8001`. The UI is served from the same origin at `/app`. All success responses use the baseline `ok(...)` envelope (`{"data": {...}}`); errors use `api_error(...)` (`{"detail": {"code", "message"}}`).

## Endpoints / Commands

### `POST /datasets`

**Purpose:** Upload a CSV, load it locally, create a session + dataset, return privacy-safe metadata. (See [dataset_upload](capabilities/dataset_upload.md).)

**Request:** `multipart/form-data` with a single `file` field (CSV in Phase 1).

**Response:**
```json
{
  "data": {
    "session_id": "uuid",
    "filename": "sales.csv",
    "row_count": 1043,
    "schema": [{ "name": "region", "dtype": "object" }, { "name": "amount", "dtype": "float64" }],
    "sample_rows": [{ "region": "West", "amount": 12.5 }]
  }
}
```

**Error cases:**
| Status | Condition |
|--------|-----------|
| 400 | File missing, not a CSV, or unreadable by pandas |
| 500 | Internal error saving/loading |

### `POST /sessions/{session_id}/ask`

**Purpose:** Ask a plain-English question; run the analysis loop; return the answer WITH the work shown. (See [conversational_analysis](capabilities/conversational_analysis.md).)

**Request:**
```json
{ "question": "What is the average amount by region?" }
```

**Response:**
```json
{
  "data": {
    "answer": "The West region has the highest average amount at 18.40 …",
    "code": "result = df.groupby('region')['amount'].mean()",
    "result_table": {
      "kind": "table",
      "columns": ["region", "amount"],
      "rows": [["West", 18.40], ["East", 11.20]]
    },
    "status": "completed"
  }
}
```

**Error cases:**
| Status | Condition |
|--------|-----------|
| 404 | Unknown `session_id` |
| 400 | Empty question |
| 200 + `status:"failed"` | LLM/exec failed after one repair — `answer` carries a readable message, `code`/`result_table` may be null |

### `GET /sessions/{session_id}`

**Purpose:** Load the session: dataset header + full ordered transcript for replay. (See [session_history](capabilities/session_history.md).)

**Response:**
```json
{
  "data": {
    "session_id": "uuid",
    "dataset": { "filename": "sales.csv", "row_count": 1043, "schema": [] },
    "messages": [
      { "role": "user", "content": "What is the average amount by region?", "created_at": "…" },
      { "role": "assistant", "content": "The West region …", "code": "result = …", "result_table": {}, "created_at": "…" }
    ]
  }
}
```

**Error cases:**
| Status | Condition |
|--------|-----------|
| 404 | Unknown `session_id` |

> The baseline `POST /runs` and `GET /runs/{id}` endpoints are removed/replaced by the above. The transform endpoints do not survive Phase 1.

## Authentication

None. Single-user local tool bound to `localhost`. No auth in v1.
