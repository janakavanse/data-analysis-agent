# Opinionated Boilerplate — Build Plan (locked)

> A complete rewrite, branched from `main`. Decisions locked with the owner across the intake. Lean by
> design; the harness has a mechanical line budget. Field rationale: [`sdd-deck.md`](sdd-deck.md).

## 1. What it is
An **opinionated boilerplate + a Claude-Code-native harness**. You clone a real, tested, *architecturally
complete* agentic-AI agent (the `code`), described by a lean `spec`, and the `harness` both **bootstraps a new
agent from a prompt** and **evolves the shipped one** — keeping spec and code reconciled, proven by the gate.
Ships as a **public, MIT, GitHub "template" repo.**

## 2. Three parts
| Part | Is | Source of truth |
|---|---|---|
| **`harness/`** | the CC-native machine that converts prompts → spec + code, and reconciles them | agent-agnostic; the harness logic |
| **`spec/`** | the human-readable description (lean: `product.md` + `capabilities/*.md`) | a **projection of the code** |
| **`code`** (`agent/` + `ui/` + `tests/`) | the real, tested agent | **truth** (code wins on conflict) |

> On-disk the `code` keeps the proven layout (`agent/`, `ui/`, `tests/` at root) so `python -m agent` and the
> gate work unchanged. *(Micro-fork: wrap them under `code/` instead — costs an import refactor. Default: root.)*

## 3. Locked decisions
- **Truth model:** code is truth; spec mechanically reconciles to it (`/analyze` coverage; hook-enforced).
- **Stack:** Python + **LangGraph** + FastAPI + **Next.js**; local DB **SQLite** (DuckDB when a capability is data-analysis). **Provider-agnostic** via `init_chat_model` — chosen at build, no baked default.
- **Example agent:** **generic, domain-neutral, but architecturally complete** — **one** real capability that exercises the full stack.
- **Agentic layers — live in the reference:** ReAct loop · tools (in-proc `@tool`; MCP for external OAuth) · short-term memory · observability · SSE streaming · `force_finalize`/worst-case `max_iterations`/graceful degradation · **retrieval/RAG** · **long-term memory** · **guardrails (AST-safe-eval) + HITL**. **Multi-agent = documented scaffold** (not wired live).
- **Gate (the moat):** all 8 checks **+ `/analyze` reconciliation**. Boot + two-turn same-session + **judge-stable** outcome (multi-sample N=5, margin) + UI E2E + traces + trajectory (tool spans, a guardrail that *fires*). `make gate` exit-0 = done. Inner loop deterministic (FakeModel); full judge at the merge gate.
- **Spec:** lean — `product.md` + `capabilities/*.md`, **EARS + `[@eval]` + `targets:`**.
- **UI:** Next.js primary journey (ask → stream → trace) **+ a proper metrics dashboard** (traces, cost, tokens, latency — a real UI, not the bare server-rendered page). Ports 8001 / 3001.
- **Ops:** **no CI** (local `make gate`); deploy to **Render** (portable Dockerfile / `langgraph.json`); **hard leanness ceiling** on `harness/` + `.claude/`, hook-enforced; MIT, public, template repo.

## 4. The harness (CC-native, grounded in CC internals)
Each dev-cycle phase on the primitive built for it:
- **Intake** → main loop + **plan mode** + `AskUserQuestion` (question intent before any edit).
- **Spec · Plan · Review · QA** → **subagents** (isolated context; return summaries). **Implement → the conductor (main loop).**
- **Knowledge** (agentic patterns, gate, stack) → **skills, lazy-loaded**; **`CLAUDE.md` stays tiny**.
- **Enforce** (secrets · reconciliation/`/analyze` · leanness budget · branch) → **hooks** (block on exit-2).
- **Workflows** → skills: `build` (bootstrap), `change` (evolve), `new-capability`, `deploy`.
- **Absorbed SDD, condensed:** EARS (Kiro) → bound to a test by `[@eval]` (ours) + to code by `targets:` (Tessl) → one deterministic `/analyze` coverage check (Spec Kit) → a change = a short brief approved in plan-mode (OpenSpec delta-intent, minus the tree). No constitution.
- **OPEN (think through):** the **subagent roster granularity** (4 / 6 / 8 / 3). Resolved in Phase 4.

## 5. Phased implementation (each ends GREEN + real-execution-anchored; revert the brick if red)
1. **Recover & prove the moat.** Bring the real tested agent + 8-check gate from **`d6def4a`** (data-analysis build) onto this branch; strip to a single generic capability; pin current libs; prove **`make gate` exits 0** incl. an **injected wrong-answer that FAILS**. Add the **leanness hook**. *Exit: real gate green in the new tree.*
2. **Genericize → architecturally complete.** Replace the data domain with a generic capability; wire the advanced layers **live** (retrieval, long-term memory, guardrails + HITL); SSE streaming; provider-agnostic accessor; multi-agent **scaffold**. *Exit: gate green incl. trajectory + a guardrail that fires.*
3. **Spec + reconciliation.** Lean `spec/` (EARS + `[@eval]` + `targets:`); the spec-writer subagent **projects spec from code**; the `/analyze` coverage check + reconciliation hook. *Exit: `/analyze` green; break a binding → fails.*
4. **The CC-native harness.** Skills (`build`/`change`/`new-capability`/`deploy`); subagents (**roster decided here**); hooks (secrets/reconcile/leanness/branch); plan-mode intake; tiny `CLAUDE.md`. *Exit: dry-run `/change` adds a capability reconciled + gated; harness under the line budget.*
5. **UI: the metrics dashboard.** Next.js primary journey + a **proper observability/cost dashboard** (real charts: runs, success, cost, tokens, latency, drill-down). *Exit: UI E2E green; dashboard shows real metrics.*
6. **Deploy (Render) + ship.** Portable artifact + a Render deploy path; README clone→run in ~5 min; template-ize; MIT. *Exit: deploys to Render; a fresh reader groks the repo in ~30 min.*

## 6. Validation
The gate is the bar (boot + judge; a 200-with-wrong-answer fails). The harness self-checks by **simulating its workflows** (a `/change` dry-run on a scripted intent) **+ one real keyed gate run** per merge. Inner loop deterministic (FakeModel); never a live single-sample judge.

## 7. Micro-defaults (flag any to change)
- `code` at root (`agent/`/`ui/`/`tests/`), not under `code/`. · Provider chosen at build (no default). · DuckDB only for a data capability. · No constitution / no plan-before-code artifact (you cut both). · Roster granularity = **open**, decided in Phase 4.
