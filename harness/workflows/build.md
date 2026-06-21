# workflow: build

The end-to-end build, from a one-line idea to a working, reconciled system. Invoked by
the `build` skill. The manager runs this, delegating to the team.

## 1. Intake (designer, with engineer + qa)

1. Open a session report in `logs/sessions/` (see `session-report.md`). It must exist
   before anything else.
2. The designer interviews the user — as many rounds as needed, to the line level. For
   every spec line, the user writes it or answers a question that produces it.
3. The engineer reviews each draft for feasibility; the designer rescopes.
4. The architect/designer records the stack in `spec/engineering/tech-stack.md`
   (default lives in that file).
5. Run the spec-completeness checklist. Loop until it passes — no placeholders.

**Gate:** checklist passes AND designer + engineer + qa sign off. Only now is code
written. This is the single human-approval gate.

## 2. Plan (designer + qa)

Slice the work into phases by end-user value. The highest-value working slice is phase
1. Record the phases and their gate tests in the session report.

## 3. Implement (engineer, per phase)

For each phase:
1. Implement exactly what the phase's spec slice calls for.
2. Write and run the gate test (`../rules/testing.md`).
3. qa signs off (`qa-gate.md`).
4. Commit + push (`phase-N: …`). The analyst reconciles at the gate.
5. Never start the next phase until this one's gate is green.

## 4. Reconcile (analyst)

At each gate, the analyst checks outcome vs goal and writes `logs/analysis/`. Drift →
fix `src/` or propose a `spec/` amendment.

## 5. Ship (manager)

Finalize the PR (opened before the first commit). Summarize what was built, how to run
it, what's deferred. Deploy is a later phase (`deploy.md`).
