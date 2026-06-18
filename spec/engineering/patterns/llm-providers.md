# Pattern: LLM Provider Selection & Stubs

**Canonical home for the provider/stub rules.** Any project with an LLM dependency follows these.
Model identifiers themselves live in `spec/engineering/tech-stack.md` § Models — not here.

---

## 1. `provider=auto` by default

Resolve to the real provider when the API key env var is set, otherwise to the stub. **Setting the key
is the only step the user should need** — never require flipping a second flag on top of the key.
Encapsulate this in a `resolved_llm_provider` property on `Settings` (real when key set, stub
otherwise).

## 2. Stub outputs branch on explicit node tags, not prose

Each pipeline node injects a unique tag (`<node:plan>`, `<node:draft>`, `<node:title>`, …) into its
prompt, and the stub matches on those tags. Matching on words that also appear in the prompt body
cross-contaminates — e.g. a draft prompt containing "expand this outline" must not trigger the stub's
"outline" branch and emit bullets where a draft belongs.

## 3. Stub outputs are shaped like the real thing

Whatever the real node would produce, the stub produces in the same shape — prose nodes return
paragraphs/headings, not a bare bullet list; a data node returns a plausible table, etc. Offline demos
must be believable, because every page is clearly labelled as stub mode (rule 4) and users still judge
the shape.

## 4. The UI shows a visible stub-mode banner

Every rendered page shows a banner when the resolved provider is `stub`. Inject `llm_provider` into
every template context. Silent stubs that look like real output are a bug — users will report "it
didn't work."

## 5. Tolerate dirty `.env` values

`pydantic-settings` does **not** strip inline comments. A `.env` line like
`APP_LLM_PROVIDER=stub   # stub | gemini` arrives as the literal string `"stub   # stub | gemini"`.
Strip inline `#` comments and surrounding whitespace yourself before comparing enum-like env values
(`provider`, `mode`, …) — do it in the `resolved_*` property, never trust the raw field.

---

## Testing stub mode — `setenv("KEY", "")`, not `delenv`

To simulate "no API key set" in a test, set the var to an empty string; do not delete it:

```python
# CORRECT — empty string overrides the .env placeholder
monkeypatch.setenv("APP_ANTHROPIC_API_KEY", "")

# WRONG — pydantic-settings falls back to the .env file value ("your-key-here" → truthy → real provider)
monkeypatch.delenv("APP_ANTHROPIC_API_KEY", raising=False)
```

**Why:** `pydantic-settings` reads from both the process environment and the `.env` file. `delenv`
removes the key from the process environment, but pydantic-settings then falls back to the `.env`
file, whose placeholder (`your-api-key-here`) is a non-empty string — so `resolved_llm_provider`
returns the real provider and the test fails unexpectedly. An empty string overrides the file value
and is correctly treated as stub mode.
