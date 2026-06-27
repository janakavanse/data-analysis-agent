# API

---

## API Style

REST (FastAPI), single origin. Responses use the skeleton's envelope `{ "data": {...}, "error": null }`. The frontend slice builds against this contract.

## Endpoints / Commands

### `POST /runs`

**Purpose:** Submit one plain-English question; the agent generates SQL, runs it locally against DuckDB, and returns the structured analysis payload.

**Request:**
```json
{
  "input_text": "What were total sales by region?"
}
```
> `input_text` is the NL question (required). `dataset_id` is NOT part of the Phase-1 request (the seeded `sales` table is implicit). From Phase 2/3 the active dataset is selected server-side via the dataset endpoints, so the request shape stays unchanged.

**Response (success):** The structured analysis is JSON-serialized into the existing `output_text` field (string). The UI parses it.
```json
{
  "data": {
    "run_id": "uuid",
    "status": "completed",
    "output_text": "{\"sql\":\"SELECT region, SUM(amount) AS total_sales FROM sales GROUP BY region\",\"columns\":[\"region\",\"total_sales\"],\"rows\":[[\"North\",1200.0],[\"South\",980.5]],\"chart_spec\":{\"chart_type\":\"bar\",\"x\":\"region\",\"y\":[\"total_sales\"]},\"error\":null}",
    "error": null
  },
  "error": null
}
```

The decoded `output_text` payload shape (the contract the UI relies on):
```json
{
  "sql": "string — the single read-only SELECT that was executed",
  "columns": ["string", "..."],
  "rows": [["cell", "..."], "..."],
  "chart_spec": { "chart_type": "bar|line|pie|scatter|table", "x": "colname", "y": ["colname", "..."] },
  "error": "string or null"
}
```

**Response (failure):** `status = "failed"`, top-level `error` carries the message, and `output_text` still contains the JSON payload with `error` set and empty `columns`/`rows` (UI renders a consistent shape):
```json
{
  "data": {
    "run_id": "uuid",
    "status": "failed",
    "output_text": "{\"sql\":\"...\",\"columns\":[],\"rows\":[],\"chart_spec\":null,\"error\":\"The model did not return valid SQL.\"}",
    "error": "The model did not return valid SQL."
  },
  "error": null
}
```

**Error cases:**
| Status | Condition |
|--------|-----------|
| 200 (status="failed") | LLM failure, non-SELECT rejected by guard, DuckDB query error — graceful, payload carries `error` |
| 404 | `GET /runs/{id}` for an unknown run |
| 500 | Run row missing after creation (skeleton invariant) |

### `GET /runs/{run_id}`

**Purpose:** Fetch a prior run. Same `data` shape as `POST /runs` (with `output_text` JSON payload).

### `GET /health`

**Purpose:** Liveness (existing skeleton endpoint). Returns `{ "data": { "status": "ok" }, "error": null }`.

### Phase 2/3 endpoints (not in Phase 1)

| Endpoint | Phase | Purpose |
|----------|-------|---------|
| `POST /datasets` (multipart CSV) | 2 | Upload a CSV → ingest into DuckDB → becomes active dataset |
| `GET /datasets` | 3 | List loaded datasets |
| `POST /datasets/{id}/activate` | 3 | Set the active dataset |
| `DELETE /datasets/{id}` | 3 | Drop a dataset |

> Phase 2/3 contracts are specified in their phase blocks in `spec/roadmap.md`; expand this section when those phases are built.

## Authentication

None — local single-user app on `localhost`. No auth layer in v1.
