# Data Model

---

## Storage Technology

SQLite via SQLAlchemy 2.0 + Alembic (`AGENT_DATABASE_URL=sqlite:///./data/agent.db`), extending the existing skeleton's `src/db/models.py`. This is the genuine production database for this local-first, single-user tool — not a placeholder for a "real" database elsewhere. Uploaded file **bytes** are never stored in SQLite — only their disk path and extracted schema metadata are. Raw file bytes live under `data/uploads/<session_id>/<dataset_id>/<original_filename>` on local disk.

## Entities

### Entity: Session

Represents one upload-and-ask session. A session has exactly one active dataset at a time (re-uploading creates a new `Dataset` row under the same session) and accumulates an ordered thread of `Query` turns that give the agent conversation memory within that session.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | Text (UUID), PK | yes | Session identifier, generated on `POST /sessions` |
| created_at | Timestamp (tz-aware) | yes | Session creation time |
| last_active_at | Timestamp (tz-aware) | yes | Updated whenever a dataset is uploaded or a query is submitted |

### Entity: Dataset

The profiled, uploaded spreadsheet. Created once per upload; a session may accumulate more than one `Dataset` row over time (e.g. the user re-uploads a corrected file), but only one is "current" for new queries at any moment (the one referenced by the most recent `Query`, or explicitly by `dataset_id` on `POST /sessions/{id}/queries`). No multi-file joins are ever performed across `Dataset` rows.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | Text (UUID), PK | yes | Dataset identifier |
| session_id | Text, FK → sessions.id | yes | Owning session |
| original_filename | Text | yes | The filename as uploaded |
| storage_path | Text | yes | Local disk path: `data/uploads/<session_id>/<dataset_id>/<original_filename>` |
| file_type | Text | yes | `"csv"` or `"xlsx"` |
| row_count | Integer | yes | Total row count of the full dataset (never a sample count) |
| column_count | Integer | yes | Number of columns |
| schema_json | Text (JSON) | yes | Serialized `DatasetSchema`: list of `{name, dtype, null_count, min, max, distinct_sample}` per column (`distinct_sample` populated only for low-cardinality columns; otherwise `null`) — this JSON is the **only** dataset information ever sent to the LLM |
| uploaded_at | Timestamp (tz-aware) | yes | Upload time |

### Entity: Query

One question-and-answer turn. This is both the conversation-memory unit (via `turn_index` ordering within a session) and the permanent audit-log record the brief requires — every field a user or auditor would need to reconstruct what happened lives here.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | Text (UUID), PK | yes | Query identifier |
| session_id | Text, FK → sessions.id | yes | Owning session |
| dataset_id | Text, FK → datasets.id | yes | The dataset this question was asked against |
| turn_index | Integer | yes | 0-based order of this turn within the session |
| question | Text | yes | The user's natural-language question, verbatim |
| status | Text | yes | `"pending"` \| `"generating_code"` \| `"running_analysis"` \| `"completed"` \| `"failed"` \| `"needs_clarification"` (Phase 2) \| `"unanswerable"` (Phase 2) |
| generated_code | Text | no | The exact Python/pandas code Gemini generated (null until `generate_code` completes; this is what the "show code" panel displays) |
| retry_count | Integer | yes, default 0 | 0 or 1 — whether the one allowed execution retry was used |
| answer_text | Text | no | The plain-language answer sentence(s), including the key computed number(s) |
| result_table_json | Text (JSON) | no | Capped-row (≤ 50) summary table, JSON array of row objects — the cap is a display-layer limit only; the underlying computation always runs over the full dataset (see `spec/capabilities/ask-question.md`) |
| chart_spec_json | Text (JSON) | no | Phase 2. Plotly figure JSON (`fig.to_json()`), null if the question didn't produce a chart |
| suggested_followups_json | Text (JSON) | no | Phase 2. List of 2-3 suggested follow-up question strings |
| prompt_tokens | Integer | no | From the Gemini response |
| completion_tokens | Integer | no | From the Gemini response |
| total_tokens | Integer | no | From the Gemini response |
| error_message | Text | no | Human-readable failure reason (`status="failed"`), or the clarifying question / unanswerable explanation (`status` = `"needs_clarification"` / `"unanswerable"`, Phase 2) |
| created_at | Timestamp (tz-aware) | yes | Query submission time |
| completed_at | Timestamp (tz-aware) | no | Set when the graph reaches `finalize` or `handle_error` |

### Relationships

- `Session` 1 — many `Dataset` (one session can have more than one uploaded file over time, but never more than one active at once; no cross-`Dataset` joins).
- `Session` 1 — many `Query` (the ordered `turn_index` sequence is the conversation history).
- `Dataset` 1 — many `Query` (all queries against that particular uploaded file).

## Data Lifecycle

- **Created:** a `Session` row on `POST /sessions`; a `Dataset` row on successful upload+profile; a `Query` row (status `"pending"`) the instant a question is submitted, before any LLM call.
- **Updated:** a `Query` row is updated in place as it progresses through `"generating_code"` → `"running_analysis"` → its terminal status — this is what the frontend's status polling observes.
- **Deleted:** nothing is automatically deleted in any phase. There is no retention policy, no TTL, and no "past exports" browser (explicitly out of scope, see `spec/roadmap.md`). Uploaded file bytes under `data/uploads/` and all DB rows persist indefinitely as the permanent local audit trail; housekeeping (manual deletion of `data/`) is the user's own responsibility, not a built feature.
- **Nothing persists across separate sessions/days beyond this DB audit log** — a new session never reloads a prior session's `conversation_history`, `Dataset`, or `Query` rows into its working context.

> **Assumed:** the 50-row cap on `result_table_json` is not specified in the brief; it's a reasonable default for an on-screen summary table. It never limits the underlying computation, and the Phase 2 export capability streams the full, uncapped result.

## Sensitive Data

- Uploaded spreadsheets may contain personal or sensitive data (financial records, personal information, etc.). `schema_json` deliberately excludes raw values except for `min`/`max`/`null_count` (aggregate, non-identifying) and `distinct_sample` (only for low-cardinality columns — e.g. a "status" or "category" column, never a column like a name or ID that would be high-cardinality and could leak individual values).
- `storage_path` points at local disk only; there is no cloud sync, no external storage, and no network transmission of file bytes anywhere in the system.
- No authentication/PII-access-control layer exists or is needed — this is a genuinely single-user local tool (see Out of Scope in `spec/roadmap.md`).
