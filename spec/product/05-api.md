# API

## API Style

Async **FastAPI** REST API + **Next.js** UI (the default trigger). Every route returns the standard
JSON envelope — `ok(data)` on success or `api_error(code, message, status)` on failure
([`../engineering/code-style.md`](../engineering/code-style.md) § Errors are JSON). Errors are never an
HTML page; the frontend renders them.

**Interaction model:** **multi-turn chat.** A conversation is bound to one dataset; each question is a
turn whose answer streams back over **Server-Sent Events (SSE)**.

Envelope shape:

```json
// success
{ "ok": true, "data": { /* ... */ } }
// error
{ "ok": false, "error": { "code": "CSV_PARSE_ERROR", "message": "..." } }
```

## Endpoints / Commands

### `POST /datasets`

**Purpose:** Create a named, empty dataset.

**Request:**
```json
{ "name": "string — dataset name, e.g. \"Q1 Sales\"" }
```

**Response:**
```json
{ "ok": true, "data": { "id": "uuid", "name": "string", "created_at": "datetime" } }
```

**Error cases:**
| Status | Condition |
|--------|-----------|
| 400 | missing/empty name (`VALIDATION_ERROR`) |
| 500 | DB error (`DB_ERROR`) |

---

### `POST /datasets/{dataset_id}/files`

**Purpose:** Upload one or more CSV files into a dataset; parse, infer schema, load into DuckDB.

**Request:** `multipart/form-data` with one or more `files` parts (CSV).

**Response:**
```json
{ "ok": true, "data": {
  "dataset_id": "uuid",
  "files": [
    { "id": "uuid", "filename": "sales_2024.csv", "row_count": 1200,
      "schema": [ { "name": "region", "type": "VARCHAR" }, { "name": "sales", "type": "DOUBLE" } ] }
  ]
} }
```

**Error cases:**
| Status | Condition |
|--------|-----------|
| 400 | non-CSV upload (`UNSUPPORTED_FORMAT`) or malformed CSV (`CSV_PARSE_ERROR`) |
| 404 | dataset not found (`NOT_FOUND`) |
| 500 | DB/DuckDB load error (`DB_ERROR`) |

---

### `GET /datasets`

**Purpose:** List datasets (id, name, file count) for the dataset picker.

**Response:**
```json
{ "ok": true, "data": { "datasets": [
  { "id": "uuid", "name": "Q1 Sales", "file_count": 2, "created_at": "datetime" }
] } }
```

**Error cases:** 500 (`DB_ERROR`).

---

### `GET /datasets/{dataset_id}`

**Purpose:** Get a dataset with its files and inferred schemas (shown before/while chatting).

**Response:**
```json
{ "ok": true, "data": {
  "id": "uuid", "name": "Q1 Sales",
  "files": [ { "id": "uuid", "filename": "sales_2024.csv", "row_count": 1200,
              "schema": [ { "name": "region", "type": "VARCHAR" } ] } ]
} }
```

**Error cases:** 404 (`NOT_FOUND`), 500 (`DB_ERROR`).

---

### `POST /conversations`

**Purpose:** Start a conversation bound to a dataset.

**Request:**
```json
{ "dataset_id": "uuid" }
```

**Response:**
```json
{ "ok": true, "data": { "id": "uuid", "dataset_id": "uuid", "created_at": "datetime" } }
```

**Error cases:** 404 (dataset `NOT_FOUND`), 500 (`DB_ERROR`).

---

### `POST /conversations/{conversation_id}/messages`  (SSE)

**Purpose:** Ask a question (first or follow-up) in a conversation. Runs the ReAct agent and **streams**
the live trace and final answer. This is the multi-turn NL-query entry point.

**Request:**
```json
{ "question": "string — e.g. \"total sales by region\"" }
```

**Response:** `text/event-stream`. Event payloads (each `data:` line is JSON):
| Event | Payload |
|-------|---------|
| `run_started` | `{ "run_id": "uuid" }` |
| `step` | `{ "description": "Grouping sales by region…", "is_error": false }` — one per `action_history` entry (the live trace; never raw SQL alone) |
| `answer` | `{ "text": "Total sales by region: …", "result_table": { "columns": [...], "rows": [[...]] } }` |
| `done` | `{ "run_id": "uuid", "status": "completed", "early_exit_reason": null }` |
| `error` | `{ "code": "LLM_UNAVAILABLE", "message": "…" }` (stream then closes) |

**Error cases (before the stream opens, as JSON envelope):**
| Status | Condition |
|--------|-----------|
| 400 | empty question (`VALIDATION_ERROR`) |
| 404 | conversation not found (`NOT_FOUND`) |
| 409 | dataset not loaded in DuckDB (e.g. after restart) — `DATASET_NOT_LOADED` |
| 500 | run failed fatally (`RUN_FAILED`) / LLM unavailable (`LLM_UNAVAILABLE`) |

---

### `GET /conversations/{conversation_id}/messages`

**Purpose:** Get the full conversation history (for reload / display).

**Response:**
```json
{ "ok": true, "data": { "conversation_id": "uuid", "messages": [
  { "id": "uuid", "role": "user", "content": "total sales by region", "created_at": "datetime" },
  { "id": "uuid", "role": "assistant", "content": "Total sales by region: …",
    "result_table": { "columns": ["region","total"], "rows": [["West", 4200]] },
    "trace": [ { "description": "Grouping sales by region…", "is_error": false } ],
    "created_at": "datetime" }
] } }
```

**Error cases:** 404 (`NOT_FOUND`), 500 (`DB_ERROR`).

## Authentication

First release runs as a **single-deployment, single-tenant** service — no per-user auth. (Auth, roles,
and quotas are deferred — [`01-vision.md`](01-vision.md) § Future Phases.) The `GEMINI_API_KEY` is a
server-side secret, never exposed to clients.
