# Capability: Analyze Question

## What It Does
Takes a plain-English question about the active dataset, runs the plan-then-execute agent graph (plan → generate pandas code → execute locally on the full data → synthesize answer), and streams back a plain-English answer with the key numbers, a summary table, the executed code, and the per-question token/cost figures.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| dataset_id | string (uuid) | active dataset in the UI | yes |
| question | string | chat input | yes |
| conversation history | list of prior turns | `messages` for this dataset's thread (see [conversation_memory](conversation_memory.md)) | yes (may be empty on first turn) |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| answer | string (plain English, streamed) | streamed to UI + `messages.answer` |
| plan | string (numbered steps) | UI (plan panel) + `messages.plan` |
| generated_code | string (pandas) | UI (collapsible) + `messages.generated_code` |
| key_numbers | JSON (label → value) | UI numbers strip + `messages.key_numbers_json` |
| result_table | JSON (rows/columns of the computed result) | UI summary table + `messages.result_table_json` |
| prompt_tokens, completion_tokens, cost_usd | int/int/float | UI tokens+cost + `messages` columns |
| status, error | string | `messages.status` / `messages.error` |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| LLM (Gemini) | plan, generate-code, synthesize — **schema + sample rows only**, never full data | Record a failed run, persist it, and stream the error to the user |
| Local pandas sandbox | Execute generated code against the full dataframe | On exception: one self-correction retry with the error fed back; if it still fails, surface the **actual exception + the code** and persist a failed message |

## Business Rules
- Only the **schema + up to `AGENT_SAMPLE_ROWS` sample rows** are ever sent to Gemini. The full dataset is loaded and computed locally. (Privacy boundary — see [architecture](../architecture.md).)
- The agent **plans before executing** — a numbered multi-step plan is produced and persisted, then carried out (plan-execute pattern, see [agent.md](../agent.md)).
- Generated code runs in a restricted local executor (no network, no filesystem writes, allowlisted imports) with a wall-clock timeout `AGENT_EXEC_TIMEOUT_S` (default 30 s).
- On execution failure, at most **one** light self-correction retry is attempted; transparency wins over silent retry loops — the real error and the offending code are always shown.
- Token usage and a computed `cost_usd` (from `AGENT_PRICE_PER_1K_INPUT` / `AGENT_PRICE_PER_1K_OUTPUT`) are captured for every question and persisted.
- Every question/answer is persisted as a `messages` row (full audit trail) regardless of success or failure.

## Success Criteria
- [ ] Asking an aggregation question (e.g. "what's the average of column X by category Y") streams a plain-English answer whose numbers match a direct pandas computation on the full file.
- [ ] The persisted `messages` row contains the plan, the generated code, the key numbers, the result table, tokens, and cost.
- [ ] A question that yields code raising an exception returns a failed message showing the real exception text and the code, after at most one retry — the server does not 500.
- [ ] With the Gemini key present, a real call is made and `prompt_tokens`/`completion_tokens` are non-zero on the persisted row.
- [ ] On a dataset large enough that a 20-row sample and the full file give different answers, the streamed answer matches the **full-file** computation (sample ≠ full).
