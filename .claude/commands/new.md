---
description: Bootstrap a new agent from an idea — spec + a proven v1, code and spec reconciled.
argument-hint: "<app idea>"
---

# /new — bootstrap

1. **Question** the idea in plan mode (`AskUserQuestion`): the one user-visible capability, its acceptance
   check, the runtime model + key, what's out of scope. Restate as a short brief and get approval.
2. **Scaffold** the smallest runnable agent (reuse the `agent/` patterns); pin current library versions.
3. **Implement** the one capability in code + a real test bound to the acceptance check.
4. **Prove** — `make gate` exits 0 (boots, two-turn run, judge; a wrong answer fails).
5. **Reconcile + review** — write `spec/capabilities/*.md` (EARS + `[@eval]` + `targets:`) from the code so
   `make analyze` passes; the `reviewer` subagent, then you. From here, evolve with `/change`.
