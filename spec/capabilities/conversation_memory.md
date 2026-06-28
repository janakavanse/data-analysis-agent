# Capability: Conversation Memory

## What It Does
Maintains a persistent per-dataset conversation thread so follow-up questions ("now break that down by region") are answered with the context of prior turns, and the thread can be reopened across days.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| dataset_id | string (uuid) | active dataset | yes |
| new question + produced answer | turn | output of [analyze_question](analyze_question.md) | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| thread history | ordered list of prior turns for the dataset | loaded into the analysis run and sent (trimmed) to the planning/answer prompts |
| persisted turn | `messages` row linked to `dataset_id` | DB (audit trail + thread) |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| SQLite (`messages`) | Insert each turn; read prior turns for a dataset ordered by `created_at` | DB error → `api_error(...)`; analysis still completes statelessly for that turn |

## Business Rules
- Each dataset owns exactly one conversation thread; messages are linked by `dataset_id` (no separate thread table needed in Phase 1).
- The plan and synthesize prompts receive a **trimmed window** of the last `AGENT_HISTORY_TURNS` turns (default 8), oldest-trimmed-first, to stay within token budget — only question + answer text of prior turns, never re-sending full data.
- History is persisted, so reopening a dataset reloads its full thread from the DB (not just in-memory session state).
- Loading a dataset returns its message history so the chat panel renders prior turns.

## Success Criteria
- [ ] After asking Q1, asking a pronoun/follow-up Q2 ("break that down by …") produces an answer consistent with Q1's result (the model received Q1 in context).
- [ ] Reopening the same `dataset_id` returns the prior `messages` ordered oldest-first, and the chat panel renders them.
- [ ] The trimmed window never exceeds `AGENT_HISTORY_TURNS` turns in the prompt sent to Gemini.
