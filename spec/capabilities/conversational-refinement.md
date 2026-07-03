# Capability: Conversation Memory, Clarification & Follow-Up Suggestions

## What It Does

Makes the Q&A thread feel like a real conversation rather than a series of disconnected lookups: the agent remembers prior turns in the same session (Phase 1), asks before guessing when a question is ambiguous or references data that doesn't exist (Phase 2), and proactively suggests 2-3 relevant next questions after each answer (Phase 2).

## Inputs

| Input | Type | Source | Required |
|-------|------|--------|----------|
| Prior Q&A pairs (last 5) | list of `{question, answer_text}` | `Query` rows in the same session (`spec/data.md`) | no (empty on turn 0) |
| Current question | string | `POST /sessions/{id}/queries` | yes |
| `DatasetSchema` | JSON | `Dataset` row | yes |
| Gemini's structured decision (Phase 2) | `{status, message}` parsed from the single `generate_code` call | `generate_code` node | yes, Phase 2 |

## Outputs

| Output | Type | Destination |
|--------|------|-------------|
| Context-aware answer (Phase 1) | text | Same `answer_text` field described in `ask-question.md` |
| Clarifying question or unanswerable explanation (Phase 2) | text | `Query.error_message`, `status="needs_clarification"`/`"unanswerable"` |
| Suggested follow-up questions (Phase 2) | list of ≤ 3 strings | `Query.suggested_followups_json` |

## External Calls

| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini API | Phase 2: the **same single** `generate_code` call additionally classifies the question and, on success, proposes follow-ups — no extra LLM call is added for this capability | Same failure path as `ask-question.md`'s `generate_code` node |

## Business Rules

- **Phase 1 — conversation memory is real, not deferred.** Every `generate_code` prompt includes the last 5 prior `(question, answer_text)` pairs from the same session, as plain text. This is what lets a follow-up question be interpreted correctly on the very first phase.
- **Phase 2 — clarification before analysis.** If the question is ambiguous (e.g. it references "that column" without a clear referent, or is otherwise underspecified given the schema), the single `generate_code` call returns `status="needs_clarification"` with a specific clarifying question in `message` — the graph routes straight to `finalize` **without ever attempting execution**. No code is run, no wrong answer is guessed.
- **Phase 2 — unanswerable detection.** If the question references a column that doesn't exist in `DatasetSchema`, or is unrelated to the dataset entirely, the same call returns `status="unanswerable"` with a plain explanation in `message` — again, no code is executed and no substitute answer is guessed.
- **Phase 2 — follow-up suggestions cost no extra LLM call.** `followups` (2-3 short question strings) is part of the same structured JSON response that produced `code` — never a second round-trip to Gemini.
- A clarifying answer from the user is just the next normal question in the thread (a new `Query` turn) — there is no separate "answer the clarification" endpoint; conversation memory (this capability, Phase 1) is what lets that next turn be interpreted in context of the clarifying question that was asked.
- Follow-up suggestions and the clarification message are always grounded in the actual `DatasetSchema` — the prompt that produces them has the same schema-only privacy boundary as code generation (see `spec/architecture.md`).

## Success Criteria

- [ ] Turn 2 of a session, phrased as a follow-up to turn 1 (e.g. "and by month?" after "what's the total revenue?"), produces a correct answer that reflects turn 1's context — verified with a real two-turn integration test (not a single-call test; see `harness/patterns/test-driven.md` → "Stateful Capabilities Need a Second Interaction").
- [ ] A deliberately ambiguous question against a real fixture dataset returns `status="needs_clarification"` with a non-empty, specific clarifying question, and `generated_code` is null (no code was ever run).
- [ ] A question referencing a column name absent from the fixture's schema returns `status="unanswerable"` with an explanation naming the issue, and `generated_code` is null.
- [ ] A successfully completed query returns 2-3 non-empty `suggested_followups`, each a distinct, plausible next question about the same dataset (not a generic placeholder like "Ask another question").
- [ ] Clicking a suggested follow-up chip in the UI populates and submits that exact question as the next turn.
