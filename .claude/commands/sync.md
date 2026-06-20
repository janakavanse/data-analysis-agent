---
description: Reconcile the spec from the current code (code is truth).
---

# /sync — reconcile

Bring the spec back in line with the code. Hand the current diff to the **spec-projector** subagent: it
rewrites the affected `spec/capabilities/*.md` to describe what the code does **now** (EARS + `[@eval]` +
`targets:`), then `make analyze` must pass. Show a short summary of what changed and stop for review.
Use after a code change that skipped step 4 of `/change`, or whenever spec and code may have drifted.
