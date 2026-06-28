# Data Model

---

## Storage Technology

SQLite (`sqlite:///./data/agent.db`) via SQLAlchemy 2.0, migrated with Alembic. Local-first, single-user — SQLite is the correct choice. The **raw dataset is never stored in the DB**: only schema, sample, and file-path metadata are persisted. The uploaded file itself lives on disk under `data/uploads/`.

## Entities

### Entity: Session

A conversation bound to one uploaded dataset.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | TEXT (uuid) | yes | Primary key |
| created_at | TIMESTAMP | yes | When the session/upload was created |
| updated_at | TIMESTAMP | yes | Last activity |

### Entity: Dataset

Privacy-safe metadata for the file attached to a session. **Stores schema + sample + file path, never the full rows.**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | TEXT (uuid) | yes | Primary key |
| session_id | TEXT | yes | FK → Session.id (one dataset per session) |
| filename | TEXT | yes | Original upload filename (display only) |
| file_path | TEXT | yes | Path under `data/uploads/` to the saved file (for lazy reload after restart) |
| file_type | TEXT | yes | `csv` in Phase 1; `xlsx`/`xls` from Phase 4 |
| row_count | INTEGER | yes | Number of rows in the loaded DataFrame |
| schema_json | TEXT (JSON) | yes | `[{name, dtype}, ...]` — column names + dtypes |
| sample_json | TEXT (JSON) | yes | First N rows (default 5) — the ONLY raw rows persisted; used only for prompting |
| created_at | TIMESTAMP | yes | Creation time |

### Entity: Message

One turn in the chat transcript. Assistant messages carry the work shown.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | TEXT (uuid) | yes | Primary key |
| session_id | TEXT | yes | FK → Session.id |
| role | TEXT | yes | `user` or `assistant` |
| content | TEXT | yes | Question (user) or answer text (assistant) |
| code | TEXT | no | Assistant only — the pandas snippet that was executed (show the work) |
| result_json | TEXT (JSON) | no | Assistant only — `{kind, columns?, rows?, value?}` computed result (show the work) |
| status | TEXT | no | Assistant only — `completed` or `failed` |
| created_at | TIMESTAMP | yes | Ordering key for the transcript |

> The existing baseline `RunRow` table is retained for the agent-run bookkeeping (`run_id`, status, error). It is orthogonal to the chat entities above and is not user-facing.

### Relationships

- `Session 1—1 Dataset` (a session has exactly one active dataset).
- `Session 1—N Message` (ordered by `created_at`).
- A new upload creates a new `Session` (and `Dataset`); it does not mutate an existing one.

## Data Lifecycle

- **Created:** `Session` + `Dataset` on upload; `Message` rows on each question (user) and answer (assistant).
- **Updated:** `Session.updated_at` on each new message. Datasets and messages are otherwise immutable.
- **Deleted:** No automatic deletion in v1 (single-user local tool). The uploaded file under `data/uploads/` persists for lazy reload. Manual cleanup of `data/` is the user's prerogative.

## Sensitive Data

- The uploaded dataset may contain the user's private/PII data. The HARD privacy guarantee: **the full dataset never leaves the machine and is never sent to the LLM** — only `schema_json`, `sample_json` (N rows), and computed aggregates are ever transmitted to Gemini.
- No secrets are stored in the DB. `AGENT_GEMINI_API_KEY` lives only in `.env`.
- `sample_json` (N rows) is the single place raw row-level data is persisted; it is small by design and is the same data the privacy model already allows the LLM to see.
