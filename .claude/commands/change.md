---
description: Evolve the agent — one intent into a change where code and spec end reconciled.
argument-hint: "<what to change>"
---

# /change — the loop

1. **Question** the intent in plan mode (`AskUserQuestion`) until it's a crisp 3-line brief (what ·
   acceptance check · out-of-scope); approve before editing.
2. **Implement in code** (`agent/` + `tests/`) — the smallest real change + a test for each new criterion.
3. **Prove** — `make gate` exits 0. Never report a pass you didn't see.
4. **Reconcile the spec** — update `spec/capabilities/*.md` (or run the `spec-projector` subagent) so it
   matches the code; `make analyze` must pass (the pre-commit hook also enforces this).
5. **Review** — the `reviewer` subagent, then you. One intent, one reconciled change.
