# Gotchas — encoded institutional memory

Hard-won fixes from real builds. Each one was a live failure that cost rework. **Read the
section for your stack before Iteration 0** — the point of this file is that a build never
re-derives a trap that a previous build already paid for.

Each entry is **Trap → Fix**. When a build hits a *new* trap, add it here (one entry, same
shape) before closing the build — that is how the harness stays smarter than any single run.
See also [working-with-llms.md](../patterns/working-with-llms.md) for the LLM-specific depth.

---

## Python packaging & `uv`

- **Hatchling can't find `src/`.** A build with `src/`-layout fails to install with
  "Unable to determine which files to ship."
  → Add to `pyproject.toml`:
  ```toml
  [tool.hatch.build.targets.wheel]
  packages = ["src"]
  ```

- **FastAPI form / file upload 500s with "python-multipart not installed."**
  → Add `python-multipart` to `dependencies` whenever the app accepts uploads or form posts.

- **`uv run` ignores dev deps.** Test/lint tools in `[project.optional-dependencies].dev`
  aren't installed by a bare `uv sync`.
  → Run tests with `uv run --extra dev pytest`, or `uv sync --extra dev` first.

## Config & environment

- **pydantic-settings crashes on unknown env vars.** Extra keys in `.env` raise a
  `ValidationError`.
  → Set `model_config = SettingsConfigDict(..., extra="ignore")`.

- **Inline `#` comments leak into env values.** `PROVIDER=stub  # default` is read by
  pydantic-settings as the literal string `"stub  # default"`, not `"stub"`.
  → Strip in a resolver property: `value.split("#")[0].strip()`. Never trust the raw value.

- **Port 8000 collides** with other local servers and proxies.
  → Default dev port is **8001** for every recipe. Keep it configurable via env.

- **Secrets logged by accident.** Use `pydantic.SecretStr` for every key; record only a
  boolean ("present: yes/no") in the session report — never the value. See
  [secret-hygiene.md](secret-hygiene.md).

## Databases — PostgreSQL / Alembic

- **SQLite tests are a lie.** A test suite that passes on `sqlite+aiosqlite` proves nothing
  about PostgreSQL migrations, JSON columns, or async drivers. This is a
  [non-negotiable](non-negotiables.md): **test against the production driver.**
  → Use a real Postgres in `tests/` (a container or a disposable local DB), not SQLite.
  The recipe's unit `conftest.py` must not silently swap engines.

- **Alembic Phase-1 sequence.** A missing `alembic/script.py.mako` makes
  `revision --autogenerate` fail cryptically.
  → Ship `script.py.mako`; the Phase-1 gate is `revision` → `upgrade head` → `current`,
  run and confirmed (not assumed).

## Databases — DuckDB (analytics / local-first)

- **DuckDB is not a Postgres recipe with the URL swapped.** Using the Postgres recipe for a
  DuckDB project means rewriting `db/`, dropping Alembic, and editing `pyproject.toml` — it
  burned ~30% of one Iteration 0. **Use the `python-fastapi-duckdb` recipe instead.**

- **DuckDB views are connection-scoped.** `CREATE VIEW` lives only for the current
  connection. After a server restart the view is gone even though the file and the
  `datasets` table row remain — queries fail with "table or view not found."
  → Persist view metadata in a table and **re-create views at startup** (in the FastAPI
  `lifespan`). The DuckDB recipe ships this.

- **`os.makedirs(dirname(path))` crashes on a bare filename.** If the DB path is
  `"analyst.duckdb"` (no directory), `os.path.dirname` returns `""` and `makedirs("")`
  raises `FileNotFoundError`.
  → Guard: `if dirname: os.makedirs(dirname, exist_ok=True)`.

- **Excel ingest leaks temp files.** Converting `.xlsx` via an adjacent temp CSV
  accumulates files on disk that the view still references.
  → Use `tempfile.mkdtemp()` or convert to Parquet in memory.

## LLM providers (Gemini)

- **`google-generativeai` is deprecated.** It raises a `FutureWarning` and is unmaintained.
  → Use **`google-genai`** (`from google import genai`). The API differs:
  ```python
  client = genai.Client(api_key=key)
  resp = client.models.generate_content(model=..., contents=..., config=...)
  ```

- **Gemini wraps JSON in ```` ```json ```` fences** even when the system prompt says
  "JSON only."
  → Strip the opening/closing fence lines in `complete()` before `json.loads`. The recipe
  `GeminiClient` does this.

- **Model names go stale.** `gemini-1.5-flash` / `gemini-2.0-flash` were deprecated or
  unavailable to new keys.
  → Default to **`gemini-2.5-flash`**, and keep the model name in config, never hardcoded
  in call sites. See [working-with-llms.md](../patterns/working-with-llms.md).

- **The offline gate must never call a real model.** A green stub run that secretly hit the
  network burns keys and lies about being offline.
  → Default `…_LLM_PROVIDER=stub`; add a hard `ALLOW_MODEL_REQUESTS=False` guard in test
  `conftest.py` so CI *cannot* make a live call.

## Frontend (Next.js)

- **Markdown renders as raw pipes.** Dropping a GFM table string into `<pre>` shows literal
  `|` and `---`.
  → Render with `react-markdown` (with `table`/`th`/`td` component overrides), not `<pre>`.

- **`react-plotly.js` breaks SSR.** It needs `window`.
  → `dynamic(() => import('react-plotly.js'), { ssr: false })`.

- **Hardcoded `session_id: 'default'`** makes every browser tab share one conversation.
  → Generate a per-tab id once: `crypto.randomUUID()` in a `useRef`/`useState` initialiser,
  with a `Math.random` fallback for non-secure contexts.

- **`NEXT_PUBLIC_API_URL`** is the only env var the browser can read for the backend URL —
  fall back to `http://localhost:8001` for local dev; never hardcode a deployed URL.

## Layout, docs & delivery

- **Repo root *is* the project.** No `app/` subdirectory nesting. All application code lives
  in `src/`; tests in `tests/` at the root. See [layout.md](../layout.md).

- **The README is written in Iteration 0, not deferred.** A repo whose README never gets
  updated leaves a cloner unable to run it — a [non-negotiable](non-negotiables.md) "docs
  must be true" violation. Iteration 0's deliverable includes a working quickstart.

- **Non-coders need copy-paste commands.** "Create a `.env` with `KEY=…`" assumes too much.
  → Provide the exact command, what success looks like, and what to do on failure. The
  executor creates `.env` from `.env.example` and prints a one-line "edit this, replace
  `your-key-here`" instruction.

- **`git add -A` sweeps in stray files.** A stray `data/` or `.venv` gets committed.
  → Stage specific paths only. See [git-and-delivery.md](git-and-delivery.md).
