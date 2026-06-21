# Zer0 — the harness

**Zer0** is a coding-agent harness: a disciplined, agent-agnostic method for
building software with AI, where human intent and machine action stay continuously
reconciled. This repository is Zer0's Claude Code reference implementation.

The name is the starting point — zero-shot from intent to a working system, and the
empty ground from which a build takes form. Everything here exists to keep one loop
closed: *goal → action → outcome → and back.*

## The four layers

| Folder     | Holds           | Question                     | Owner role   |
|------------|-----------------|------------------------------|--------------|
| `spec/`    | the **goal**    | what should it be?           | designer     |
| `src/`     | the **action**  | what is it?                  | engineer     |
| `logs/`    | the **outcome** | what does it do?             | analyst      |
| `harness/` | **mindfulness** | does outcome = goal? adjust. | manager + qa |

`harness/` is the only agent-agnostic layer and the source of truth for *method*.
`.claude/` is a thin adapter that binds this method to Claude Code; another runtime
could bind the same `harness/` differently. See `philosophy.md` for the full model.

## The team (always-on roles)

Each role carries a standing responsibility, not a one-shot task. The **manager is
the main Claude session**; the rest are delegated sub-agents.

- **manager** — coordinates the team and keeps the loop closing. (`roles/manager.md`)
- **designer** — turns your prompts into requirements; writes the spec; UX. (`roles/designer.md`)
- **engineer** — feasibility feedback, then builds to the approved spec. (`roles/engineer.md`)
- **qa** — reviews spec & code, owns standards and the end-user's goals. (`roles/qa.md`)
- **analyst** — always observing logs, traces, tests, and your prompts; feeds reality back. (`roles/analyst.md`)

## Mechanisms (Claude Code adapter)

| Concept     | Canonical (source of truth) | Adapter in `.claude/`              |
|-------------|-----------------------------|------------------------------------|
| Rules       | `harness/rules/`            | `.claude/rules/` auto-load shim    |
| Method      | `harness/method/`           | referenced by `CLAUDE.md`          |
| Roles       | `harness/roles/`            | `.claude/agents/` (thin pointers)  |
| Workflows   | `harness/workflows/`        | `.claude/skills/` (`build`, `fix`, `deploy`) |
| Enforcement | `harness/rules/`            | `.claude/hooks/` (push-after-commit) |

## How a build runs

1. **Intake** — the designer interviews you for as long as it takes, to the line
   level, until the spec is complete (no placeholders) and the engineer confirms
   it's feasible. Nothing is built before designer + engineer + qa sign off.
2. **Build** — work is sliced into phases by end-user value; each phase runs
   end-to-end and passes its gate before the next.
3. **Reconcile** — the analyst checks outcome (`logs/`) against goal (`spec/`) and
   feeds back; the team adjusts the action or the goal until they agree.
4. **Ship / Deploy** — open a PR; deploy is a later phase (Render by default).

See `workflows/build.md`.

## References

Zer0 builds on existing ideas; it does not invent new ones:

- **Specification-driven development** — the spec is the contract.
- **Closed-loop control / OODA** (observe–orient–decide–act) — `reconcile` is a
  control loop over goal, action, outcome.
- **Claude Code operating practices** — sub-agents for context isolation, skills as
  invokable workflows, hooks for mechanically-enforced discipline, lean `CLAUDE.md`.

> Pointers to the coding-agent-harness literature are collected here and expanded
> as the field publishes.
