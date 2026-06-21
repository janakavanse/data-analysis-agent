# workflow: fix

Diagnose and fix a defect, keeping the loop closed. Invoked by the `fix` skill.

## Steps

1. **Reproduce.** Capture the actual behavior from `logs/` or a failing test. No fix
   begins without a reproduction — outcome is evidence.
2. **Locate (analyst + engineer).** The analyst points at the divergence in `logs/`;
   the engineer traces it to `src/`.
3. **Classify the drift** (`../method/reconcile.md`):
   - code ≠ spec or code ≠ logs → a bug; fix `src/`.
   - logs ≠ spec because the goal was wrong → the designer amends `spec/` first (with
     qa), then the engineer implements.
4. **Write a failing test** that captures the defect, then make it pass.
5. **qa signs off**; the analyst confirms the outcome now matches the goal.
6. **Commit + push** (`fix: …`). Update the session report.

Never patch the symptom in `src/` while leaving `spec/` and `logs/` in disagreement —
the loop must close.
