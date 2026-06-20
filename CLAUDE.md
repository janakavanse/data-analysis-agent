# Claude Code — entry point

A lean, Claude-Code-native **harness** that builds and evolves an agentic-AI agent and keeps its **spec and
code always in sync**. Code is truth; the spec is a projection reconciled to it. The harness is the point —
the `agent/` is just the example it builds and proves.

## The loop
`intent → question it (plan mode) → implement in CODE → reconcile SPEC → prove (make gate) → review`

## Commands
- `/new "<idea>"` — bootstrap a new agent: spec → a proven v1.
- `/change "<intent>"` — evolve the agent; code + spec end reconciled.
- `/sync` — reconcile the spec from the current code (code → spec).

## What's here
- `agent/` — the real, tested agent (truth) · `spec/capabilities/` — its EARS criteria (a projection of the code)
- `make gate` — the proof: boots, runs two turns, judges the answer (a 200 with a wrong answer FAILS)
- `make analyze` — the reconciliation check: every criterion bound to a test, every `targets:` glob real
- `.claude/agents/` — `spec-projector` (code→spec) · `reviewer` (diff review) · `.githooks/` — secret + reconciliation guards

**Done = `make gate` exits 0.** **Spec and code must always reconcile (`make analyze`)** — the pre-commit hook enforces it.
