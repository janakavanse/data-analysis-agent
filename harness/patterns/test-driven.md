
# Test-Driven Development

How tests are written in this repo. This expands the Testing section of `engineering-practices.md` into a concrete discipline. It applies to every phase and every fix.

---

## The Loop

**Red → Green → Refactor.** For every behaviour:

1. **Red** — write a failing test that describes the behaviour you want. Run it; watch it fail for the *right reason* (assertion failure, not import error).
2. **Green** — write the minimum code to make it pass. No more.
3. **Refactor** — clean up code *and* test, with the green bar as your safety net. Re-run.

If you wrote code before its test, you skipped Red. Delete the test you wrote afterward, or treat it as a characterization test and label it as such — don't pretend it was TDD.

---

## Test-First Is Not Negotiable for New Behaviour

- A new capability starts with a test that fails because the capability doesn't exist yet.
- A bug fix starts with a **regression test that reproduces the bug** — it must fail on the current code, then pass after the fix. A fix with no failing-first test is unverified; you cannot prove it fixed anything.
- `/zero-shot-fix` follows this: reproduce → red test → fix → green → verify the rest of the suite still passes.

---

## What a Good Test Asserts

- **Behaviour, not implementation.** Assert what the function returns or what side-effect occurred — never which internal helpers were called. Tests that mirror the code break on every refactor.
- **One concept per test, named as a sentence** stating precondition and outcome — so a failure tells you exactly what broke: `test_validate_rejects_negative_threshold`, not `test_validation`.
- **Arrange / Act / Assert**, visibly separated. Setup at top, one action, then assertions — never interleaved.

---

## Determinism Is a Hard Requirement

A flaky test is worse than no test — it trains everyone to ignore red.

- **No wall clock.** Inject time (a `clock` parameter, a frozen-time fixture). Never assert against `now()`.
- **No randomness.** Seed it, or pass the value in. A test that fails 1-in-50 runs is a defect.
- **Determinism at the unit level.** Pure unit tests inject time/seeds and may stub the provider boundary. Integration and E2E tests DO call the real LLM/API (keys from `.env`); for those, assert on response shape/invariants (status, key fields, structure) and tolerate non-deterministic prose rather than exact strings.
- **No shared mutable state between tests.** Each test sets up and tears down its own world. Order-dependence is a bug.

---

## If a Stub Is Used, Don't Mock

For pure-unit isolation, prefer a thin real implementation (in-memory queue, fake repository, stub LLM provider) over a framework mock. Integration and E2E tests use the **real provider**, not a stub.

- Stubs **compose** and survive refactors; mocks encode call sequences and break on them.
- IF a stub LLM provider is used (unit tests or optional offline dev), it should produce **distinct, node-tagged output** (see `rules/ai-agents.md` rule 8) so it is credible and node cross-contamination is caught.
- Use the production DB driver in integration tests (PostgreSQL via `conftest.py` setup/teardown) — **never** SQLite-as-a-substitute (`rules/ai-agents.md` rule 5).

---

## Stateful Capabilities Need a Second Interaction

A capability that **carries state** — persistent sessions, conversation history, memory, caches, anything that "remembers" or survives a reload/restart — has a bug class the first call can never expose: detached ORM rows, stale or unscoped caches, history-load crashes, session-scoping errors. These fire on the **second** interaction, or after the process restarts — not the first.

So a single happy-path test of a stateful capability is **not coverage of that capability**. For every stateful capability:

- **Multi-interaction test** — drive ≥2 operations in the *same* session/context and assert the later one succeeds AND sees the earlier state (ask → ask-again; create → read → update → read). The bug that shipped past a green Phase-1 gate (history loaded after its DB session closed → `DetachedInstanceError` on the 2nd question) was invisible to every single-turn test; one two-turn test would have caught it.
- **State-survival test** — reload the page / restart the process, then assert prior state is still present and usable.

Derive what to test from the phase's **capabilities**, not its endpoints: if the spec claims "persistent sessions" or "remembers across…", the absence of a multi-interaction + survival test is a coverage hole, regardless of line coverage.

---

## Analytical Capabilities Need Correctness Gates

A pipeline that runs and returns a non-empty response is **not** a passing gate for any analytical or data-driven capability. The gate must verify the answer is **correct**, not just present.

For every capability that answers questions about data or produces computed results:

- **Run a known question against a fixture dataset with a pre-computed correct answer.** The gate asserts the response contains that answer (or is numerically close to it). A wrong answer is **BLOCKED** at the same severity as a crash — silent wrongness is worse than a visible crash.
- **The fixture must make the correct answer unambiguous.** Design the dataset so the right answer is exactly one value (e.g. a specific team name, a specific number) that cannot be accidentally produced by a wrong computation on the same data.
- **Assert answer content, not pipeline success.** `assert response["result"]` is not a correctness test. `assert "FC Barcelona" in response["result"]` is.

```python
# Example correctness gate for a data analysis agent
def test_top_scorer_answer(client, fixture_csv):
    # fixture_csv: 10 rows, player "Alice" has highest goals (7)
    response = client.post("/analyse", json={
        "file": fixture_csv,
        "question": "Who scored the most goals?"
    })
    assert response.status_code == 200
    assert "Alice" in response.json()["result"]  # CORRECT answer, not just non-empty
```

---

## Data-Processing Capabilities Need Full-Data Gates

A capability that analyses, aggregates, or computes over a dataset has a silent failure mode: **sampling**. An implementation that sends only the first N rows to the LLM and asks it to describe them looks correct on a gate CSV of exactly N rows — because sample == full dataset. The bug is invisible until a real user uploads a file with N+1 rows.

For every capability that processes a dataset:

- **Gate test must exceed the maximum plausible sample size.** The test dataset must be large enough that a result computed from a sample is observably different from a result computed from the full set. If the implementation could truncate at N, the gate dataset must have significantly more than N items.
- **Assert the computed value, not a proxy.** Pick a dataset where the correct answer is exactly knowable and can only be produced from the full data — not a value that a partial view would also produce. Avoid test data where the full-data answer and the sample answer are the same.
- **The spec must name the approach.** "LLM describes a sample" is not "code execution on the full dataset". These two approaches pass different tests; record which one the spec requires so the gate can distinguish them.

---

## UI Smoke Tests — What They Must Actually Check

A UI smoke test is not "it returns 200". It is "a real user would see a real, working, styled page with real AI output". These are the two tests that must both pass:

### Test 1 — API-level smoke (TestClient)

Run via `TestClient` (or equivalent) — fast, no real server needed:

- Drive the **full primary user journey** from HTTP request to response. Not just `/health` — the actual user flow: submit input → agent runs → response rendered.
- Assert **response content**, not just status codes. Check that the response body contains real output (a key field, a non-empty result, a structure the LLM produced) — not just `{"status": "ok"}`.
- Assert **edge cases and error paths**: empty input, oversized input, malformed input — each returns a human-readable error, not a stack trace.
- For **stateful capabilities** (history, sessions, memory): drive ≥2 interactions in the same session and assert the second one sees the first (see Stateful Capabilities section above).

```python
# Example — assert content, not just status
response = client.post("/run", json={"input": "analyse this dataset"})
assert response.status_code == 200
data = response.json()
assert data["result"]          # non-empty
assert "error" not in data     # no silent error swallowed
assert len(data["result"]) > 20  # not a placeholder string
```

### Test 2 — Live-server smoke (real process + curl)

Start the app as the user would (`uv run python -m <pkg>`) and hit it with `curl` — this is the only test that catches import errors, missing env vars, startup crashes, and CSS/JS loading failures:

- `curl` both `/health` AND a real page that exercises the LLM/API path. Both must return 200 **and** show real AI content.
- **For any UI served statically:** verify the page is actually styled. A 200 that serves an unstyled page is a broken page. Check that the built CSS bundle contains real utility classes (`.flex`, `.bg-*`, `.rounded-*`) and no unexpanded `@tailwind` directives. Do not accept "I got a 200" as passing.
- **The single-origin path only:** test `pnpm build` → serve via backend → `http://localhost:<port>/app/` — NOT the `pnpm dev` port. These are different servers and bugs hide in the gap.

```bash
# Start the real app (not dev mode)
cd frontend && pnpm build
cd .. && uv run python -m myagent &
sleep 2

# Hit health + a real page
curl -sf http://localhost:8001/health | grep -q '"status":"ok"'
curl -sf http://localhost:8001/app/ | grep -q 'class="flex'  # styled, not barebones
```

### What "passing" means

| Check | Minimum bar | Failure signal |
|-------|-------------|----------------|
| Status code | 200 | 4xx/5xx or connection refused |
| Content | Non-empty AI output present | `{}`, `null`, placeholder text, or `"error":` field |
| Styling | CSS utility classes in the rendered page | Barebones HTML, `@tailwind` directives still present |
| State | 2nd interaction sees 1st (if stateful) | `DetachedInstanceError`, empty history, wrong session |
| Error paths | Human-readable message, no stack trace | 500 with Python traceback, unhandled exception |

---

## The Pyramid

| Level | Count | Speed | Scope |
|-------|-------|-------|-------|
| Unit | many | ms | one function/class, all deps stubbed |
| Integration | fewer | 100s of ms | real DB and real LLM/API boundary (keys from `.env`) |
| E2E / smoke | fewest | seconds | a real process, golden-path user journey |

Push assertions **down** the pyramid: if a unit test can catch it, don't wait for the smoke test. The golden-path UI smoke test runs against the **live provider** and asserts **real response content**, not just status codes — a 200 that renders a broken or unstyled page is a failing test.

---

## Coverage Is a Floor, Not a Goal

- Cover every branch of business logic and every documented error path.
- Don't chase 100% by testing trivial getters or framework glue — that's noise.
- A line covered by a test with no meaningful assertion is **not** covered. Coverage tools count execution, not verification; you count verification.

---

## Before You Claim Done

- Run the **full** suite, not just the test you touched. Show the output.
- "It should pass" is not a passing test (`rules/ai-agents.md` rule 2). Run it or say you couldn't.
- A phase is not complete until its gate suite is green against the production DB driver WITH real LLM/API keys from `.env`, including edge-case and E2E/UI tests.
