# Data Model

> SQLite schema for DataChat. Storage tech and the privacy rationale live in [`architecture.md`](architecture.md); this file pins the tables, fields, and lifecycle.

---

## Storage Technology

- **SQLite** (single local file, default `data/agent.db`) via **SQLAlchemy 2.0** + **Alembic** migrations. SQLite is the **production** database here — DataChat is a single-owner local tool, so SQLite is the correct production driver, not a substitute. Tests run against SQLite too.
- **Uploaded files** live on local disk under `data/uploads/<dataset_id>.csv` (not in the DB) — the full data never leaves the machine and is too large for a row.
- All schema changes ship as Alembic revisions (the Phase 1 migration adds `datasets` and `messages`).

## Entities

### Entity: Dataset

A single uploaded tabular file plus its locally-computed profile. Owns one conversation thread.

| Field | Type | Required | Phase | Description |
|-------|------|----------|-------|-------------|
| id | TEXT (uuid) | yes | 1 | Primary key |
| name | TEXT | yes | 1 | Display name (derived from the original filename) |
| original_filename | TEXT | yes | 1 | The uploaded file's original name |
| file_path | TEXT | yes | 1 | On-disk path of the stored full file (`data/uploads/<id>.csv`) |
| profile_json | TEXT (JSON) | yes | 1 | Local profile: per-column dtype/range/missing counts, row count, N sample rows |
| source_kind | TEXT | yes | 1 | `csv` (Phase 1). `xlsx`/`derived` added later — defaults `csv` |
| sheet_name | TEXT | no | 4 | Multi-sheet workbook sheet (Excel phase) — null in Phase 1 |
| derived_from_id | TEXT (uuid) | no | 3 | If a saved derived dataset, the source dataset id — null in Phase 1 |
| created_at | TIMESTAMP(tz) | yes | 1 | Creation time |
| updated_at | TIMESTAMP(tz) | yes | 1 | Last update time |

> `sheet_name`, `derived_from_id`, `source_kind != 'csv'` are **later-phase** columns. They are added to the schema in the phase that uses them; Phase 1 ships only the Phase-1 columns to keep the migration minimal — OR, to avoid a second migration, Phase 1 MAY include the nullable later columns unused. **Decision:** Phase 1 migration includes `id, name, original_filename, file_path, profile_json, source_kind (default 'csv'), created_at, updated_at`. `sheet_name` and `derived_from_id` are added by the phase that needs them.

### Entity: Message (Run / Audit Trail)

One analysis run — a question and everything the agent produced for it. This is both the conversation thread (per dataset) and the immutable audit trail.

| Field | Type | Required | Phase | Description |
|-------|------|----------|-------|-------------|
| id | TEXT (uuid) | yes | 1 | Primary key |
| dataset_id | TEXT (uuid, FK → datasets.id) | yes | 1 | Thread linkage; scopes history |
| question | TEXT | yes | 1 | The plain-English question (one row = one turn: question + answer + run metadata; no separate `role` field) |
| plan | TEXT | no | 1 | The numbered plan the agent produced |
| generated_code | TEXT | no | 1 | The pandas code that was executed (or the offending code on failure) |
| answer | TEXT | no | 1 | The streamed plain-English answer |
| key_numbers_json | TEXT (JSON) | no | 1 | label → value of the headline aggregates |
| result_table_json | TEXT (JSON) | no | 1 | The computed summary table (rows/columns) |
| prompt_tokens | INTEGER | yes | 1 | Tokens sent to Gemini for this run (default 0) |
| completion_tokens | INTEGER | yes | 1 | Tokens returned for this run (default 0) |
| cost_usd | REAL | yes | 1 | Computed cost for this run (default 0.0) |
| status | TEXT | yes | 1 | `running` \| `completed` \| `failed` |
| error | TEXT | no | 1 | The real error/traceback when `status = failed` |
| chart_spec_json | TEXT (JSON) | no | 2 | Chart spec for richer output — null in Phase 1 |
| created_at | TIMESTAMP(tz) | yes | 1 | Run start time |
| completed_at | TIMESTAMP(tz) | no | 1 | Run completion time |

> `chart_spec_json` is added by Phase 2. All other columns ship in the Phase 1 migration.

### Relationships

- `Dataset 1 ──< Message` — a dataset has many messages (its conversation thread + audit trail), linked by `messages.dataset_id`. No separate `threads` table is needed in Phase 1: one dataset = one thread.
- `Dataset.derived_from_id → Dataset.id` (self-reference) — later-phase derived datasets point at their source. Originals are never mutated.

### Skeleton `runs` table

The skeleton ships a `runs` table for the `transform_text` slot. DataChat does not use it. **Decision:** the Phase 1 Alembic revision **drops `runs`** (or leaves it unused and unreferenced). Dropping is cleaner; either passes the gate as long as `datasets` + `messages` exist and `alembic upgrade head` succeeds.

## Data Lifecycle

- **Create:** a `datasets` row + on-disk file on upload (after successful local profiling). A `messages` row per question — written as `running`, updated to `completed`/`failed` when the graph ends.
- **Read:** datasets loaded by id; messages read per dataset (thread + history), ordered by `created_at`.
- **Update:** `datasets.updated_at` on touch; a `messages` row is updated exactly once (running → terminal). After that it is **immutable** — the audit trail is never edited.
- **Delete:** none in Phase 1 (the owner keeps their history). Dataset deletion (and its file + messages) is a later-phase library action.
- **Retention:** unbounded local retention; the owner owns the file. Nothing is time-boxed.

## Sensitive Data

- The dataset may contain the owner's private/PII data. It **stays local** — only schema + sample rows + profile reach Gemini (the privacy boundary in [`architecture.md`](architecture.md)). No auth is needed (single local owner); files and DB are protected by the OS filesystem.
- No secrets are persisted in the DB. The Gemini key lives only in `.env` (gitignored) and is confirmed by presence, never logged.
