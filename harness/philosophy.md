# Philosophy

Zer0 is a **coding-agent harness**: a disciplined method for building software with
AI agents, where human intent and machine action stay continuously reconciled. The
method is agent-agnostic; this repo is its Claude Code reference implementation.

## The name

Zero is the starting point and the empty ground — zero-shot from intent to a working
system, and the openness from which any build takes form. A build begins from zero
each time: nothing is assumed that the spec did not state.

## Four layers, one feedback loop

Three top-level folders are *sources of truth* about the system from different
angles; the fourth observes them and adjusts.

| Layer      | Holds           | The question it answers                   | Mind      |
|------------|-----------------|-------------------------------------------|-----------|
| `spec/`    | the **goal**    | what should this system be?               | intention |
| `src/`     | the **action**  | what is it, in code?                      | doing     |
| `logs/`    | the **outcome** | what does it actually do?                 | result    |
| `harness/` | **mindfulness** | is the outcome the goal? if not, adjust.  | awareness |

`spec`, `src`, `logs` are nouns — artifacts. `harness` is a verb — the practice of
checking goal against action against outcome and correcting the drift between them.

## The loop

```
spec (goal) ──▶ src (action) ──▶ logs (outcome)
   ▲                                   │
   └──────────── harness ◀─────────────┘
        observe drift, adjust goal or action
```

A build is not "done" when the code runs. It is done when the outcome in `logs/`
matches the goal in `spec/` and the harness can show they reconcile. When they
diverge, the harness decides which is wrong — the action (fix `src/`) or the goal
(amend `spec/`) — and closes the gap. The analyst owns this observation; the manager
owns the adjustment. (See `method/reconcile.md`.)

## Principles

1. **Humans author intent.** The spec and prompts are written by people. The designer
   assists — interviews, challenges, fills gaps you approve — but never invents your
   goals. Requirements are gathered for as long as it takes, to the line level, until
   they are complete and feasible.
2. **Generate only what is needed.** No gold-plating, no speculative abstractions, no
   files that exist "just in case."
3. **Spec before code.** No change to `src/` without a backing change in `spec/`.
4. **Outcome is evidence, not opinion.** "It should work" is not a result; claims are
   backed by `logs/` and tests that were actually run.
5. **The loop must close.** Every unit of work ends reconciled: spec ↔ src ↔ logs
   agree, the tree is clean, the change is pushed.

## Lineage

- **Specification-driven development** — the spec is the contract; code conforms.
- **Closed-loop control / OODA** — reconcile is a control loop over goal, action,
  outcome.
- **Claude Code operating practices** — sub-agents for context isolation, skills as
  invokable workflows, hooks for mechanically-enforced discipline, a lean `CLAUDE.md`.
