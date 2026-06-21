# Spec-Driven Development

The spec is written before the code. No exceptions.

## Why

When code is written without a spec, parts of the system make inconsistent
assumptions, testing becomes guesswork, every AI session re-derives requirements, and
scope creeps silently. When the spec comes first, every session reads the same
requirements, tests derive from the spec, and "does this match the spec?" is a
concrete, answerable question the analyst can audit.

## What goes where

- **`spec/product/`** — WHAT the system does: behavior, users, data, APIs, UI.
- **`spec/engineering/`** — HOW this build is done: chosen stack, code style.
- **Not in the spec** — line-by-line implementation (that's `src/`), temporary
  workarounds, or session notes (those go in `logs/sessions/`).

## When requirements change

1. Update the spec first (designer), with engineer feasibility and qa review.
2. Then update `src/`.
3. The analyst confirms `logs/` reconciles with the amended spec.

Never change code first and "update the spec later" — later never comes.

## Spec vs. implementation conflicts

If the spec says X and the code does Y, the code is wrong — fix it. Exception: if the
spec itself is wrong, amend the spec (designer + qa) first, then fix the code. The
analyst may *propose* spec amendments when outcome diverges from goal; humans and qa
approve them. The analyst never silently edits the goal.
