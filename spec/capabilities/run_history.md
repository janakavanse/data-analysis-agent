# Capability: Run History (Audit Trail)

## What It Does
Persists every analysis run (question, plan, generated code, result, key numbers, tokens, cost, status, error, timestamps) and exposes it for browsing, so the owner can audit and revisit how any past answer was produced.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| dataset_id | string (uuid) | active dataset | yes (to scope history) |
| message_id | string (uuid) | a history row | only for the detail view |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| history list | array of message summaries (question, status, cost, created_at) | `GET /api/datasets/{id}/messages` → UI history list |
| run detail | full message (plan, code, result table, key numbers, tokens, cost, error) | `GET /api/messages/{id}` → UI detail/expand |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| SQLite (`messages`) | Read rows for a dataset / a single row by id | `api_error("NOT_FOUND", ...)` for a missing id |

## Business Rules
- Every analysis run is written to `messages` exactly once, **including failed runs** (status `failed` with the error and the code that caused it).
- History is immutable — rows are never edited after the run completes; this is the audit trail.
- History is scoped per dataset and ordered by `created_at`.

## Success Criteria
- [ ] After N questions on a dataset, `GET /api/datasets/{id}/messages` returns N rows with question, status, cost, and timestamp.
- [ ] `GET /api/messages/{id}` returns the full plan, code, result table, key numbers, tokens, and cost for that run.
- [ ] A failed run appears in history with status `failed`, the real error, and the offending code.
