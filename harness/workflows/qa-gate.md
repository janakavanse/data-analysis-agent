# workflow: qa-gate

qa's sign-off on a phase. Nothing passes to the next phase without it.

## Checklist

- [ ] Code for the phase matches the spec slice (no more, no less).
- [ ] The phase's gate test exists, was **run**, and passed — output shown.
- [ ] Tests run against the production data store, not a substitute.
- [ ] If there's a UI/HTTP surface: the golden-path smoke test asserts content, not
      just status codes; stubbed mode is visibly labelled.
- [ ] The working tree is clean; the commit is pushed.
- [ ] The session report reflects the phase.
- [ ] The analyst has reconciled outcome vs goal for this phase.

If every box is checked, qa signs off. If any box is red, the phase is not done — back
to the engineer.
