# Code Style

> **Boilerplate status:** The tech-designer fills in the language-specific FILL-IN sections. The
> Universal Rules and Framework Gotchas below apply to all projects.

---

## Universal Rules

1. **Types at boundaries** — every function crossing a module boundary uses typed inputs and outputs
   (Pydantic, TypeScript interfaces, Go structs) — never raw dicts or `any`.
2. **One responsibility per file** — if a file does two things, split it.
3. **No comments explaining WHAT** — names carry that; comment only non-obvious WHY.
4. **No dead code** — remove unused imports/functions/variables immediately; don't comment them out.
5. **Fail loudly at startup** — validate required config/env at startup, not silently at runtime.
6. **No hardcoding** — values that could change (URLs, limits, credentials) live in config or env vars.

## To fill in (tech-designer)

- **Naming conventions** — <!-- per language -->
- **File organization** — <!-- by layer / feature / type -->
- **Error handling pattern** — <!-- how errors are represented and propagated -->
- **Logging pattern** — <!-- structured vs. unstructured; always-included fields -->
- **Testing conventions** — <!-- unit-test location, naming, runner -->
- **What NOT to do** — <!-- anti-patterns specific to this stack -->

---

## See also (don't restate these here)

- **ReAct loop, AST safe-executor, reasoning trace** → [`patterns/react-agent.md`](patterns/react-agent.md).
- **LLM provider selection, stubs, stub-mode banner, dirty-`.env` tolerance** →
  [`patterns/llm-providers.md`](patterns/llm-providers.md).
- **DB driver / test environment** → [`tech-stack.md`](tech-stack.md) § Database & Tests.

---

## Framework Gotchas (Python / FastAPI — keep current)

### Starlette ≥ 1.0 `TemplateResponse` signature

```python
# CORRECT (Starlette ≥ 1.0)
return templates.TemplateResponse(request, "page.html", {"foo": bar})
# WRONG (pre-1.0) — fails with TypeError: unhashable type: 'dict'
return templates.TemplateResponse("page.html", {"request": request, "foo": bar})
```

A small helper keeps call sites tidy:

```python
def render(request: Request, name: str, **ctx):
    return templates.TemplateResponse(request, name, ctx)
```

### Pydantic-settings — always set `extra="ignore"`

`pydantic-settings` reads the **entire** `.env` and validates every key against the model. If `.env`
contains variables the model doesn't declare (`TEST_DATABASE_URL`, `EDITOR`, CI vars), Pydantic raises
`ValidationError: Extra inputs are not permitted`. Set `extra="ignore"` in `model_config` for any
project whose `.env` carries variables owned by other tools.

### Pipeline errors — render an error template, never raise `HTTPException`

When an LLM pipeline node fails, the error propagates back via the pipeline state's `error` field. Don't
re-raise it as `HTTPException` (that returns a bare JSON body to the browser) — render a readable error
page instead:

```python
if state["error"]:
    log.error("analyze.pipeline_error", error=state["error"])
    return render(request, "error.html", detail=state["error"])
```

`error.html` must always exist and link back to the start page. Every web route that runs the pipeline
follows this pattern.

### Async test footguns

- Replace an async `init_db()` with an **async** noop, not a sync lambda:
  `async def _noop(): ...` then `monkeypatch.setattr("<pkg>.graph.runner.init_db", _noop)`. A sync lambda
  breaks `await`.
- Use `tmp_path` (a file DB), not `:memory:`, for integration tests — `:memory:` has shared-state issues
  across the engine/connection boundary.
