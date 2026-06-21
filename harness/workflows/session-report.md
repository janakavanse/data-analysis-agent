# workflow: session-report

Every working session has a report in `logs/sessions/`. It is part of the outcome
record and must exist before any code is written.

## Path

`logs/sessions/YYYY-MM-DD-HHMMSS-<branch>.md`

## Required sections

- **Goal** — what this session is trying to accomplish.
- **Phase** — where in the lifecycle / which build phase.
- **Decisions** — choices made and why (link spec sections).
- **Steps** — logged as you work, not reconstructed at the end.
- **Prompt log** — each user message and a one-line summary of the response.
- **Gate results** — each gate test run and its outcome.
- **Open / next** — what remains.

Update it in real time. A missing session report is a build failure
(`../rules/non-negotiables.md`).
