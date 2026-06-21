# Testing & Gates

## Test before claiming done

A unit of work is not done until its tests pass. Write tests as you implement. Run the
full suite before marking a phase complete. Show the output.

## Gate law

Each phase ends at a gate. A phase is complete only when ALL hold:

1. All code for the phase is committed and pushed.
2. The phase's gate test passes — actually run, output shown.
3. The working tree is clean.
4. The session report in `logs/sessions/` reflects completion.
5. qa has signed off (the `qa-gate` workflow, or a manual checklist).

Never mark a phase complete if any gate is red. Never start the next phase first.

## Honest tests

- Test against the **production** data store and drivers, not a convenient substitute.
  Tests that only pass on a different engine do not count as passing.
- The skeleton (first) phase must run fully offline — no real API key, no network.
  Stubs stand in for external calls; stubbed mode is visibly labelled in any UI so a
  viewer never mistakes a stub for real output.
- A golden-path smoke test walks the primary user journey end-to-end and asserts
  response **content**, not just status codes.

The concrete gate commands per stack live in `spec/engineering/tech-stack.md`.
