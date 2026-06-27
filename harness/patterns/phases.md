# Implementation Phases

Agents are built phase by phase, derived from the user's requirements — not a fixed ladder. **Phase 1 is the wow version — a complete, impressive first release, not a thin demo.** Later phases enhance and harden. The agentic stack runs from day one and is upgraded in a dedicated phase. Production concerns trail.

## Core Principle

**Wow first, then enhance, then harden.**

Phase 1 is a complete working product the user would be proud to show someone. Every requirement from intake is either working or explicitly deferred with a clear reason — not silently missing. The user tests Phase 1 and thinks "this is it" not "this is a placeholder". Subsequent phases add secondary features, upgrade the agentic architecture, and complete the system.

The spec-writer derives the phase breakdown from `spec/roadmap.md` — count and names come from requirements, not a fixed ladder.

## Phase Structure

Four roles are always present; the middle phases are derived from requirements:

---

### Phase 1 — The Wow Version

Phase 1 is a **complete, working product** — not a prototype, not a thin demo. Every primary requirement from intake works end-to-end. The user opens it for the first time and is genuinely impressed.

- **No half-done primary requirements.** Everything the user said they needed at intake either works in Phase 1, or is explicitly deferred with a labelled stub and a written reason. A requirement that's "partially there" is a failing gate.
- **The agentic stack is wired from day one.** Graph framework, state type, core nodes, and assembly are set up in Phase 1. The agent loop runs end-to-end. Never defer the agentic skeleton to a later phase.
- **The UI is polished enough to show someone.** Real data, real responses, real layout — not a "functional skeleton". Stubs for secondary features are clearly labelled, but nothing on the primary path looks broken or placeholder.
- All calls hit the real LLM/API (keys from `.env`) — no fake data on any tested path.
- **Gate (all must pass):**
  1. `pyproject.toml` declares the DB driver in `[project.dependencies]` (e.g. `psycopg2-binary` for PostgreSQL) — never dev-only
  2. `uv run alembic upgrade head` succeeds against the configured database — run and confirmed, not assumed
  3. Every primary requirement from intake works end-to-end against the real LLM/API; tests pass
  4. **Agentic stack gate:** graph compiles, state flows through nodes, agent runs end-to-end — confirmed by the Phase 1 test
  5. Working tree is clean and committed
  6. Phase test-handoff published; the human has tested and approved (see Human Testing Gate)

---

### Phases 2–N — Enhancement Phases *(spec-writer derives these)*

Each phase adds secondary features, remaining integrations, or capabilities that were intentionally deferred from Phase 1. The spec-writer **names these phases after what they add**, not after generic concerns.

- Phase 1 delivered the wow version; these phases make it more capable, more complete, or more robust.
- All external calls hit the real provider using keys from `.env`; tests assert on real responses.
- **Gate:** The phase's increment works end-to-end against the real LLM/API; tests pass; working tree clean; human approved.

---

### Phase N+1 — Agentic Stack Upgrade + Resilience

After user requirements are covered, upgrade the agentic architecture and harden external calls.

- **Upgrade the agentic stack** per `spec/agent.md`: wire in the patterns it calls for beyond the base ReAct loop — planning, reflection, multi-agent coordination, memory, or whatever the spec requires. Phase 1 laid the skeleton; this phase promotes it to the production-grade architecture.
- Add error handling to all external calls: try/except, retries, timeouts. Agent continues (degraded, not crashed) on non-critical failures.
- **Gate (all must pass):**
  1. Every pattern listed in `spec/agent.md` beyond the base loop is wired and exercised by a real test
  2. Agent handles all documented failure modes without crashing

---

### Phase N+2 — Complete Agentic System

All spec-required agent patterns are active and the system runs fully end-to-end.

- Every capability in `spec/roadmap.md` is real — no stubs on any active path.
- Complete any remaining integrations; system runs against all real services.
- **Gate (all must pass):**
  1. All integrations are real; agent runs fully end-to-end against the real LLM/API
  2. Every capability in the spec is implemented and tested with real data
  3. `spec/agent.md` graph matches the running code — drift audit passes on the agentic surfaces

---

### Trailing Phases *(only if the spec requires them)*

These phases exist only when the spec explicitly calls for them — never as defaults:

- **API / CLI Surface** — only if `spec/api.md` calls for an external API or CLI
- **UI Polish** — only if `spec/ui.md` calls for further UI work beyond Phase 1
- **Observability + Logging** — if the spec calls for structured logging or metrics beyond basic operation
- **Polish + Hand-off** — final drift audit; README verified end-to-end from a clean clone; user accepts hand-off

---

## Human Testing Gate

The build is autonomous WITHIN a phase, with a human testing gate BETWEEN phases — at EVERY phase boundary.

After a phase passes its automated gate and is committed, the build publishes a **test-handoff** and STOPS:
- The handoff gives exact run commands, what to click/look at, the expected result, and what is a labelled stub vs. real.
- Only the root session presents it and asks the human.
- The next phase starts ONLY after the human approves.
- On a reported issue → qa-auditor diagnoses and routes → the right generator (frontend and/or backend) fixes → re-gate → re-present.

## Parallel Slices Within a Phase

- spec-writer carves each phase into INDEPENDENT SLICES (the parallel units) with explicit dependencies; default to independence so slices build concurrently.
- agent-builder fans out a generator per slice — multiple code-generator invocations in a SINGLE message so they run concurrently (disjoint paths: frontend writes the frontend surface, backend writes `src/` — never the same file). Then fans out qa-auditor per slice concurrently and aggregates verdicts.
- Serialize ONLY across a true declared dependency. On a BLOCKED slice, loop only that slice's generator; other slices are unaffected. For headless/CLI builds, only backend generators run.

## Phase Gates

A phase is complete when ALL of the following are true:
1. All code for the phase is committed and pushed
2. All tests for the phase pass
3. Working tree is clean
4. Phase test-handoff published; (build) human tested and approved
5. qa-auditor sub-agent (or manual QA checklist) has signed off
6. For Phase 1 specifically: `alembic upgrade head` has been run against the real DB and succeeded
7. **README updated** — every command, env var, setup step, route, or capability this phase added is reflected in `README.md`, and every README command in scope has been run and confirmed to work from the stated directory. A stale README is a BLOCKER.

**Never mark a phase complete if any gate is red.**

**Never claim a phase passes based on tests alone if those tests use a different DB driver than production.** SQLite tests passing does not mean PostgreSQL migrations work.

**Never claim Phase 2+ passes on stubbed providers** — the gate runs against the real LLM/API with keys from `.env`.

## Phase Tracking

The current phase is recorded in git commit messages (`phase-N: [description]`). To see phase history, run `git log --oneline | grep "phase-"`.

## Adapting the Phases

The spec-writer derives the phases from `spec/roadmap.md`. What is fixed:

- **Phase 1 is always the Wow Version** — a complete working product, not a thin demo; every primary requirement from intake works or is explicitly deferred
- **The agentic stack is always wired in Phase 1** — graph, state, nodes, assembly; never deferred
- **There is always an Agentic Stack Upgrade phase** and a **Complete Agentic System phase** — in that order, after the enhancement phases
- **Trailing phases are only added when the spec explicitly requires them**

What varies (derived from requirements):
- How many enhancement phases (2–N) — count comes from `spec/roadmap.md`
- Names of enhancement phases — named after what they add (e.g. "Export + Sharing", "Advanced Filters", "Scheduled Reports"), not generic concerns

---

## Language-Specific Gate Commands

The spec-writer sets the exact gate command per phase in `spec/roadmap.md` (## Phases of Development), honoring the test rules in `harness/patterns/tech-stack.md`.

| Language | Phase 1 gate | Phase 2+ gate |
|----------|-------------|-------------|
| Python | `uv run alembic upgrade head` + `uv run pytest` | `uv run pytest` (PostgreSQL, automated via conftest) |
| TypeScript (Bun) | migration tool + `bun test tests/unit/` | `bun test tests/integration/` |
| TypeScript (Node) | migration tool + `npx vitest run tests/unit/` | `npx vitest run tests/integration/` |
| Go | `migrate up` + `go test ./internal/...` | `go test ./...` |

Phase 2+ gates run with **real LLM/API keys loaded from `.env`** regardless of language; both the DB URL and the provider key(s) must be set.

## TypeScript/Bun Integration Test Pattern

```typescript
// tests/integration/pipeline.test.ts
import { describe, it, expect, beforeEach } from "bun:test";

// Use the production DB driver via conftest-style setup/teardown — never SQLite-as-a-substitute
// Call the real LLM/API using keys from .env

describe("pipeline", () => {
  it("runs end-to-end against the real provider", async () => {
    // call runner against the real provider
    // assert DB record created with correct status
  });
});
```
