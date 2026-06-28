# Capability: Session History

## What It Does
Persists and replays the chat transcript for a dataset session so the conversation (questions, answers, and the work shown) survives a page reload and so follow-up questions have prior context to build on.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| session_id | string (uuid) | UI | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| messages | ordered list of `{role, content, code, result_table, created_at}` | UI transcript on load |
| dataset meta | `{filename, schema, row_count}` | UI header for the session |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| SQLite (via SQLAlchemy) | Read session + ordered messages | Return 404 if the session does not exist |

## Business Rules
- Each assistant message persists not just the answer text but the `code` and `result_table` so "show the work" is replayable after reload.
- Messages are ordered by `created_at` ascending and scoped strictly to one `session_id`.
- This capability is the persistence substrate that [conversational_analysis](conversational_analysis.md) reads prior turns from; the two share the `Message` table.

## Success Criteria
- [ ] After asking two questions, GET of the session returns both user messages and both assistant messages in order, each assistant message carrying its `code` and `result_table`.
- [ ] Reloading the page (re-fetching by `session_id`) reproduces the full transcript including collapsed work.
- [ ] GET of an unknown `session_id` returns 404.
