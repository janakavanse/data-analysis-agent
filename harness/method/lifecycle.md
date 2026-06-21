# Lifecycle

A Zer0 build moves through four movements. Roles are always-on; this is the order in
which their work crests.

```
INTAKE ──▶ BUILD ──▶ RECONCILE ──▶ SHIP
(designer)  (engineer)  (analyst)    (manager)
   ▲___________________________________|
        the loop re-opens on any drift
```

## 1. Intake — get the goal right (designer-led)

The designer turns the user's prompts into a complete spec. This takes as many
questions as it takes — to the line level. For every line of the spec the user either
writes it or answers a question that produces it. No placeholders survive.

- The engineer reviews each draft for feasibility and flags anything infeasible or
  expensive back to the designer to rescope.
- qa reads the spec for testability and end-user fit.

**Gate to build (all required):**
1. The spec-completeness checklist passes — no `<!-- FILL IN -->`, no TODOs, every
   product file present.
2. designer signs off: requirements captured.
3. engineer signs off: feasible within the chosen stack.
4. qa signs off: testable and serves the end-user's goals.

No code is written before this gate clears. This is the only human-approval gate;
after it, the build proceeds autonomously, gated by tests.

## 2. Build — make the action (engineer-led)

Work is sliced into phases **by end-user value** (qa, as user representative, drives
the ordering): the highest-value working slice first, each phase running end-to-end
before the next.

The designer derives the actual phases from the spec — there is no fixed phase list.
Each phase ends at a gate (see `../rules/testing.md`): its test passes, the tree is
clean, the commit is pushed, qa signs off.

## 3. Reconcile — check outcome against goal (analyst-led)

The analyst is always observing `logs/` — runtime behavior, traces, test results, and
the user's own prompts and frustrations. At each gate (and whenever a signal warrants)
it asks: does the outcome match the goal? Divergence is written to `logs/analysis/`
and fed back to the team; when the goal itself is wrong, the analyst proposes a spec
amendment for qa/human approval. (See `reconcile.md`.)

## 4. Ship — close it out (manager-led)

The manager finalizes the PR (it was opened before the first commit), confirms the
loop is closed, and hands off. Deploy is a later phase (Render by default; see
`../workflows/deploy.md`).
