# Tech Stack

> **Boilerplate status:** The FILL-IN sections are completed by the tech-designer sub-agent after the
> product spec is approved. The user may override any choice; a stated preference is always binding
> (see `.claude/agents/tech-designer.md`). The **Permanent Rules** at the bottom apply to all projects.

---

## Default Stack (when the user states no preference)

- **Backend / agent:** Python 3.12+ — agent logic, data processing, API server.
- **Frontend:** Node.js 20+ (TypeScript / Next.js). **The frontend is always Node.js, never Python.**
  There is no Python frontend option; any UI/web surface is Node.js regardless of the backend.
- **Database:** SQLite — zero-ops, file-based, ships with Python. Upgrade to PostgreSQL only when
  multi-user concurrency or full-text search requires it (then it's a migration-only change with
  SQLAlchemy 2.0).
- **Dependency management:** `uv` + `pyproject.toml` (Python); `pnpm` or `npm` (Node.js).

This is the stack the intake question (`agent-builder` Q2) recommends first.

## Models (source of truth — every other file links here)

Always use a current, verified model name — never a guessed or deprecated one. The name must be
configurable via an env var (e.g. `APP_LLM_MODEL`) so it changes without a code deploy. A 404
`NOT_FOUND` from an LLM API almost always means a wrong/deprecated model name — check the name first.
Verify against the provider's current docs / `ListModels` before hardcoding.

| Provider | Default | Cheap / fast | Hard reasoning | Notes |
|----------|---------|--------------|----------------|-------|
| **Anthropic** (default) | `claude-sonnet-4-6` | `claude-haiku-4-5-20251001` | `claude-opus-4-8` | `claude-fable-5` also available |
| Google Gemini | `gemini-2.5-flash` | `gemini-2.5-flash` | `gemini-2.5-pro` | older `1.5`/`2.0-flash` unavailable to new users |
| OpenAI | `gpt-4o-mini` | `gpt-4o-mini` | `gpt-4o` | |

---

## To fill in (tech-designer)

### Language & Runtime
<!-- FILL IN: e.g. Python 3.12 backend; Node.js 20 frontend. Default stack above unless overridden. -->
**Why:** <!-- reason -->

### Agent Framework
<!-- FILL IN: LangGraph (conditional routing / checkpointing) · simple loop · none -->
**Why:** <!-- reason -->

### LLM Provider & Model
<!-- FILL IN: provider + a specific model from the Models table above -->
**Why:** <!-- reason -->

### Backend Framework
<!-- FILL IN: FastAPI (Python, recommended) · Express · none -->

### Database & ORM
<!-- FILL IN: SQLite (default) / PostgreSQL / none — see § Database & Tests for the binding rules.
     ORM: SQLAlchemy 2.0 (works with both SQLite and PostgreSQL). -->

### Frontend
<!-- FILL IN: Node.js only — Next.js 15 + React, Vite + React, etc. Never Python. -->

### Key Libraries
<!-- FILL IN: HTTP client, LLM client, ORM, testing, logging, integration-specific libs. -->

| Library | Version | Purpose |
|---------|---------|---------|
| | | |

### What to Avoid
<!-- FILL IN: libraries/patterns explicitly off-limits and why. -->

---

## Permanent Rules (all projects)

### Database & Tests (canonical home)

- **Driver in main dependencies.** The DB driver (e.g. `psycopg2-binary` for PostgreSQL) goes in
  `[project.dependencies]`, never a dev-only group. Alembic migrations run at deploy/setup time, not
  just in tests — a dev-only driver makes `alembic upgrade head` fail wherever dev deps aren't installed.
- **Tests use the same driver as production.** If production is PostgreSQL, tests run against
  PostgreSQL — tests that only pass on SQLite are not a passing gate. If production is SQLite (the
  default stack), SQLite tests are correct.
- **Test DB is set up automatically** via `conftest.py` (`Base.metadata.create_all` against the test DB
  URL, dropped after). No manual steps. The URL comes from an env var (`TEST_DATABASE_URL`, or a
  `_test` database via `DATABASE_URL`), provided by a gitignored `.env.test` or a CI variable, and the
  README documents it.
- The Phase 2 gate must pass with **no LLM API key set** — the DB URL is set, the LLM is stubbed
  (`patterns/llm-providers.md`).

### Default Dev Port — 8001

All generated projects use **port 8001** (not 8000, which is commonly occupied by other local
services). `__main__.py` hard-codes `port=8001` unless an env var overrides it; the README references
`http://localhost:8001`; `.env.example` includes `PORT=8001` if configurable.
