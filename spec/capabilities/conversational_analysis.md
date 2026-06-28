# Capability: Conversational Analysis (Answer + Show the Work)

## What It Does
Answers a plain-English question about the uploaded dataset by having the LLM write pandas code (given only schema + a tiny sample + prior chat context), executing that code locally over the real DataFrame, and returning a natural-language answer together with the exact code it ran and the computed numbers/table behind it.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| session_id | string (uuid) | UI (from upload) | yes |
| question | string (plain English) | chat input box | yes |
| prior turns | list of `{role, content}` | persisted message history for the session (see [data.md](../data.md)) | auto |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| answer | string (plain English) | chat transcript |
| code | string (the pandas snippet the LLM produced) | shown in the collapsible "show the work" panel |
| result_table | structured result (columns + rows, or a scalar) | rendered as a table/value under the code |
| message rows | persisted user + assistant messages | DB (see [data.md](../data.md) `Message`) |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini (via `LLMClient`) | Generate a pandas snippet from schema + sample + question + prior turns | Surface a readable error in the chat ("Could not analyze that — try rephrasing"); persist nothing as a successful answer |
| Local pandas exec | Run the generated snippet over the in-memory DataFrame in a restricted sandbox | One automatic repair attempt (feed the traceback back to the LLM for a corrected snippet); if it still fails, return the readable error above |

## Business Rules
- **Answer + show the work, always.** Every successful answer MUST include the executed code string AND the computed result (table or scalar). An answer with no work shown is a failure of this capability.
- **Privacy is absolute.** The LLM is given ONLY: the schema (column names + dtypes), the N-row sample, the question, and prior chat turns. The full dataset is NEVER sent. Computed results (small aggregates/tables) may be passed back to the LLM to phrase the answer, but raw row-level data beyond the sample is not.
- The generated code runs locally in a restricted sandbox: a fixed set of allowed names (`df`, `pd`), restricted builtins, no file/network/`import`/`__` access, and a wall-clock timeout. The result is read from a designated variable.
- **Follow-ups build on context.** Prior turns (question + answer summaries) for the session are threaded into the prompt so "what about just the West region?" resolves against the previous turn. Conversation memory is in scope for Phase 1.
- Messy data is handled inside the generated code with sensible defaults (e.g. coercing types, dropping `NaN` for an average); the user is not asked cleaning questions.

## Success Criteria
- [ ] Asking "what is the average of column X" over a known CSV returns the correct number AND a non-empty `code` string AND a `result_table`/scalar matching the number.
- [ ] The computed answer matches a direct pandas computation on the full file (not on the 5-row sample) — verified with a fixture large enough that the sample-only answer differs observably from the full-data answer.
- [ ] A follow-up question that omits a column/filter named only in the prior turn is answered correctly using prior context.
- [ ] A question that yields a first-attempt code error is silently repaired once and still returns a correct answer; a genuinely unanswerable question returns a readable error, not a crash.
- [ ] Generated code attempting `import os`, file access, or `__import__` is blocked by the sandbox and never executes.
