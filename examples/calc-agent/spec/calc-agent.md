# calc-agent

**Purpose** — A tiny Gemini ReAct agent that answers a natural-language math question by calling a safe `calculator` tool.

## Capability

English math question → the model calls the `calculator` tool with an arithmetic expression → the tool's numeric result is fed back → the model returns a text answer containing the number.

## `calculator` tool contract

`calculator(expression: str) -> str`

Parses `expression` with `ast.parse(mode="eval")` and evaluates it via a hand-written AST walker.

- **Supported nodes:** numeric constants (`int`/`float`), binary ops `+ - * / ** %`, unary `+`/`-`, and parentheses (grouping, implicit in the AST).
- **Result formatting:** a `float` whose value is integral is coerced to `int`; the result is returned as a `str` (e.g. `4 / 2` → `"2"`, `17 * 23 + 5` → `"396"`).
- **Safety property:** only the node types above are evaluated. Any other node — names/variables, function calls, attribute access, etc. — raises `ValueError("unsupported expression: ...")`. So input like `x + 1` or `__import__('os').system('echo hi')` is rejected before any evaluation; `eval`/`exec` are never used.

## Agent loop

`ask(question, *, client=None, max_steps=5)` runs a hand-rolled tool-calling loop (no agent framework):

- **Client:** uses the injected `client` if given; otherwise constructs `genai.Client(api_key=os.environ["GEMINI_API_KEY"])`. The injection point is what lets the loop be tested keyless with a fake client.
- **Model:** `MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")`, called via `client.models.generate_content`.
- **Tool:** exactly one declared tool, `calculator`, with a single required string parameter `expression`.
- **Per step (up to `max_steps`):** send the running `contents` to the model; append the model's reply. Collect any `function_call` parts.
  - If there are **no** function calls, return `resp.text` stripped — this is the finish condition.
  - Otherwise call `calculator(**fc.args)` for each call and append each result as a function-response part, then loop.
- **Tool-error handling (graceful degradation):** each tool call is wrapped in `try/except Exception`. On failure the result fed back to the model is the string `f"error: {e}"` rather than raising. The loop never crashes on a bad tool call; the model sees the error as the tool's response and decides what to do next (typically explaining the problem in natural language). So a div-by-zero (`ZeroDivisionError`) or an unsupported expression (`ValueError`) becomes `"error: ..."` in the conversation, not an exception out of `ask`.
- **Exhaustion:** if `max_steps` is reached with no text answer, returns the literal string `"(ran out of steps)"`.

## Interfaces

- **Function:** `ask(question: str, *, client=None, max_steps: int = 5) -> str`. `client` is an optional injected stand-in for `genai.Client` (any object exposing `models.generate_content(model, contents, config)`); when omitted, a real client is built and a `GEMINI_API_KEY` is required.
- **CLI:** `python agent.py "<question>"` — joins all argv into the question; with no args it defaults to `"what is 17 * 23 plus 5?"`. Prints the answer.
- **Config (`.env`, via `python-dotenv`):**
  - `GEMINI_API_KEY` — required only when no `client` is injected; read as `os.environ["GEMINI_API_KEY"]` inside `ask` (raises `KeyError` if unset).
  - `GEMINI_MODEL` — optional; defaults to `gemini-2.5-flash`.

## Acceptance check

`ask("what is 17 * 23 plus 5?")` returns an answer containing `396` (real Gemini call; test skipped when `GEMINI_API_KEY` is unset).

The remaining tests run **keyless**:

- **Tool correctness:** `396`, `1024`, `14`; and rejection of unsafe input (`x + 1`, `__import__(...)`) with `ValueError`.
- **Loop mechanics (injected fake client):** a `_FakeClient` scripts successive `generate_content` responses (repeating the last once exhausted).
  - *Tool-error recovery:* the model calls `calculator("1/0")`, the `"error: ..."` is fed back, and on the next step it returns a text answer — asserting the loop does not crash.
  - *Step exhaustion:* a model that always calls the tool returns `"(ran out of steps)"` at `max_steps`.

---

**Notes / flags:**
1. `GEMINI_MODEL` is read once at import time into module-level `MODEL`, while `GEMINI_API_KEY` is read at call time inside `ask` — so the model env var is honored differently (set it before import) than the API key.
2. Non-integer results still surface as raw Python text (`1/3` → `"0.3333..."`); there is no rounding. Tool *exceptions* (div-by-zero, unsupported expressions) no longer propagate out of `ask` — they are caught in the loop and returned to the model as `"error: ..."`. Note that `calculator` called directly (outside the loop) still raises.
