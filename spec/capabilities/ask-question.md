# Capability: Ask a Question and Get a Real Answer

## What It Does

Turns one natural-language question about the uploaded dataset into a real, plain-language answer with correct key numbers — computed by pandas code that Gemini generates from schema-only context and that runs locally against the full dataset, with exactly one automatic retry if the generated code fails to execute.

## Inputs

| Input | Type | Source | Required |
|-------|------|--------|----------|
| `question` | string | `POST /sessions/{id}/queries` body | yes |
| `dataset_id` | string (UUID) | `POST /sessions/{id}/queries` body | yes |
| `DatasetSchema` (`schema_json`) | JSON | `Dataset` row (see `upload-and-profile.md`) | yes |
| Prior Q&A pairs (last 5) | list of `{question, answer_text}` | `Query` rows in the same session, `turn_index`-ordered | no (empty on the first turn) |

## Outputs

| Output | Type | Destination |
|--------|------|-------------|
| `Query` row, fully populated (status, generated_code, answer_text, result_table_json, token usage, retry_count, timestamps) | DB record | SQLite `queries` table — the permanent audit trail |
| Live status updates (`generating_code` → `running_analysis` → terminal) | field on the `Query` row | Polled by the frontend via `GET /queries/{id}` |
| Plain-language answer + summary table + generated code + token usage | JSON | API response, rendered as the answer card |

## External Calls

| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini API (`generate_code` node) | Generate pandas code from the schema-only prompt (question + `DatasetSchema` + conversation history + optional prior-error text) | Fatal, not retried by the execution-retry mechanism — `status="failed"` with a clear error |
| Restricted-exec sandbox (`execute_code` node, local) | Run the generated code against the real, fully-loaded dataframe | Recoverable once: triggers exactly one retry (feeds the error back into a second `generate_code` call); a second failure is fatal — `status="failed"` |

## Business Rules

- **The generated code, and only the generated code, ever touches the actual data.** The LLM prompt contains `DatasetSchema` (column metadata) plus text — never a dataframe, never raw rows, never file bytes. This is structurally enforced (see `spec/architecture.md` → Privacy Boundary), not just a prompt instruction.
- **Exactly one automatic retry** on an execution failure — never zero, never more than one. A second execution failure surfaces a specific, human-readable error (e.g. naming the bad column if identifiable), never a raw Python traceback.
- **The full dataset is always used for computation** — the sandbox loads the entire file fresh for every attempt; there is no sampling, truncation, or "first N rows" shortcut anywhere in the computation path (only the **displayed** summary table is capped at 50 rows for the UI, after the full computation).
- The generated code's `answer` variable must be a complete natural-language sentence containing the computed number(s) — the system does not separately "explain" the result with a second LLM call; the code-gen call is the only LLM call per question (per the brief's single-call model).
- Conversation memory is real from Phase 1: a question is interpreted with the last 5 prior Q&A pairs from the same session as context, so a follow-up like "and last month?" can build on the prior turn.
- Token usage (prompt/completion/total) shown in the UI is the real value from the Gemini response for that query's `generate_code` call(s) — summed across both attempts if a retry occurred.
- **Phase 2 addition:** the summary table gains sortable columns and formatted numbers (currency/percentage/thousands-separators inferred from dtype) — a display-layer polish, not a change to the underlying computed data.
- **One query in flight per session at a time** — submitting a new question while a prior one for the same session hasn't reached a terminal status returns `409` (see `spec/api.md`, `spec/roadmap.md` → Key Constraints); the UI disables the input while a query is in flight so this is never user-visible as an error in normal use.

## Success Criteria

- [ ] Asking a question with a knowable, pre-computed correct answer against a fixture CSV of **≥ 5,000 rows** (large enough that a sampled/truncated implementation would produce a different, wrong number) returns an `answer_text` containing the correct value — not merely a non-empty response.
- [ ] The `generated_code` field on the resulting `Query` row is non-empty, is valid Python, and is visible in the UI's collapsible code panel.
- [ ] `token_usage` on the response reflects real `prompt_tokens`/`completion_tokens`/`total_tokens` from the Gemini API — never a hardcoded or zero value.
- [ ] A question engineered to fail on the first generated-code attempt (e.g. by referencing a column name with a common typo) is retried exactly once, and `retry_count == 1` on the final `Query` row; if the retry succeeds, `status="completed"`.
- [ ] A question that fails on both attempts results in `status="failed"` with a specific, human-readable `error_message` — never a raw stack trace reaching the API response or the UI.
- [ ] A second question in the same session that references the first question's answer (e.g. "and what about X" following an initial "what is the average of Y") produces an answer that is observably informed by the first turn's context — this is asserted with a real two-turn integration test, not a single-call test.
- [ ] No test, log line, or LangSmith trace for this capability ever contains a raw data row from the uploaded file — only schema metadata, questions, and generated code appear in prompts/logs.
