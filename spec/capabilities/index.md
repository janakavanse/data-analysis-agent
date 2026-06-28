# Capabilities Index

> One file per capability. Each describes exactly one discrete thing DataChat can do. The chosen stack/graph lives in [`architecture.md`](../architecture.md) and [`agent.md`](../agent.md), not here.

---

## Active Capabilities (v1 — Phase 1)

These four are real and end-to-end on the Phase 1 tested path.

| Capability | File | Delivered in |
|-----------|------|--------------|
| Profile Dataset | [profile_dataset.md](profile_dataset.md) | Phase 1 |
| Analyze Question (plan → code → execute locally → answer) | [analyze_question.md](analyze_question.md) | Phase 1 |
| Conversation Memory (per-dataset thread) | [conversation_memory.md](conversation_memory.md) | Phase 1 |
| Run History (audit trail) | [run_history.md](run_history.md) | Phase 1 |

## Deferred Capabilities (later phases — shown in Phase 1 only as clearly-labelled NON-FUNCTIONAL stubs)

These are intentionally **not** in Phase 1. They appear in the UI as labelled stubs so the owner sees the vision; a stub must never read as a bug. Each maps to a later phase in [`roadmap.md`](../roadmap.md).

| Deferred capability | Phase |
|---------------------|-------|
| Interactive charts / dashboards | Phase 2 — Charts & Richer Output |
| Follow-up question suggestions (2–3 after each answer) | Phase 2 — Charts & Richer Output |
| Persistent multi-dataset library (sidebar list across days) | Phase 3 — Dataset Library & Persistent Threads |
| Save derived/cleaned datasets back to the library as new items | Phase 3 — Dataset Library & Persistent Threads |
| Excel `.xlsx` + multi-sheet workbook support | Phase 4 — Excel & Multi-file Joins |
| Multiple-file join / compare | Phase 4 — Excel & Multi-file Joins |
| Running daily cost total | Phase 5 — Daily Cost Total & Confirm-Before-Heavy-Work |
| Confirm-before-heavy/expensive-work clarification gate | Phase 5 — Daily Cost Total & Confirm-Before-Heavy-Work |

## How to Add a New Capability

Run `/zero-shot-build [description]` on the existing spec. The spec-writer creates `<name>.md` here (no number prefix), updates this index, flags dependencies, and self-reviews fit against the architecture and data model.
