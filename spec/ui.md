# UI

---

## UI Type

Single-page web app (Next.js static export, served by FastAPI at `/app/`). One screen, chat-style: upload zone at the top, a scrolling Q&A thread below it, an input box pinned at the bottom.

## Views / Screens

### Screen: Upload & Session

**Purpose:** the entry point — start a session and give the agent a dataset to work with.

**Key elements:**
- File drop-zone / picker, accepting `.csv` and `.xlsx` only (real, Phase 1).
- **Empty state:** before any file is uploaded — explains "Upload a CSV or Excel file to start asking questions" (never a blank panel).
- **Loading state:** while the file uploads and is profiled — "Uploading and profiling your file…" with visible progress, not a frozen screen.
- **Dataset profile card (real, Phase 1):** once profiled — filename, row count, column count, and a compact column list (name + inferred type). This is the user's confirmation that the agent understood their file, before they ask anything.
- **Error state:** unsupported file type or a parse failure shows a specific, human message ("This file couldn't be read as a spreadsheet — check it's a valid CSV or XLSX") with a retry action — never a raw exception.

**Actions available:**
- Upload a file (real, Phase 1).
- Re-upload to replace the active dataset within the same session (real, Phase 1 — creates a new `Dataset` row per `spec/data.md`).

### Screen: Q&A Thread (the main surface)

**Purpose:** ask questions about the uploaded dataset and read the agent's answers, in order, within the same session.

**Key elements — per turn:**
- **User question bubble** (real, Phase 1): the question as submitted.
- **Status indicator while processing (real, Phase 1):** in place of the answer card, a sequential text line reflecting live polling of `GET /queries/{id}`: "Generating code…" then "Running analysis…" — never a bare spinner with no context. If the one automatic retry fires, this briefly shows "That didn't work — retrying with a corrected approach…" before returning to "Running analysis…".
- **Answer card (real, Phase 1), once `status="completed"`:**
  - Plain-language answer text with the key number(s), rendered prominently.
  - Basic summary table (real, Phase 1 — a plain `<table>`; Phase 2 adds sortable columns and number formatting as a polish pass, not new data).
  - **Chart area:** Phase 1 = a clearly-labelled **non-functional stub** — a greyed placeholder panel reading "Interactive chart — coming in Phase 2" (never mistaken for a bug: visibly styled as disabled, not broken). Phase 2 = a real interactive Plotly chart (`react-plotly.js`), rendered only when `chart_spec` is non-null for that query.
  - **Collapsed code panel (real, Phase 1):** "Show generated code ▾" toggle, collapsed by default; expands to show the exact `generated_code` in a monospace block.
  - **Token-usage badge (real, Phase 1):** e.g. "412 + 96 = 508 tokens", from the real Gemini response.
  - **Retry note (real, Phase 1):** if `retry_count == 1`, a small inline note: "Retried once after the first attempt failed."
  - **Follow-up suggestion chips row:** Phase 1 = a clearly-labelled **non-functional stub** — 2-3 greyed, non-clickable chip outlines reading "Suggested follow-ups — coming in Phase 2". Phase 2 = real, clickable chips (from `suggested_followups`) that populate and submit the next question.
  - **Export button:** Phase 1 = a disabled button, "Export cleaned data (coming in Phase 2)", with a tooltip explaining why. Phase 2 = real — triggers `POST /queries/{id}/export` and downloads the file.
- **Clarification bubble (Phase 2 only; does not exist as a UI element in Phase 1 since it cannot occur yet):** when `status="needs_clarification"` or `"unanswerable"`, render the agent's `error_message` as a distinct message-bubble style (not an error-red card) — for `needs_clarification`, prompt the user to answer in the same input box; for `unanswerable`, state plainly that the question can't be answered from this data and why.
- **Error state (real, Phase 1):** when `status="failed"`, render a red card with the human-readable `error_message` (never a stack trace) and a hint to rephrase the question.

**Actions available:**
- Ask a question (real, Phase 1) — text input + Send, disabled while a query for that session is in flight.
- Expand/collapse the generated-code panel (real, Phase 1).
- Click a follow-up chip (Phase 2).
- Click Export (Phase 2).

### Note near the input box (Phase 1)

A small helper line under the input box in Phase 1: *"Tip: reference exact column names for best results — clarifying questions for ambiguous phrasing arrive in Phase 2."* This sets expectations for the not-yet-built clarification flow without presenting a fake affordance.

## Error States

- **Network/API error** (fetch fails, non-2xx on submit): a dismissible red banner at the top of the thread — "Couldn't reach the server — check it's running and try again."
- **Query failed** (`status="failed"`): a red answer card with the specific `error_message`, never a raw stack trace, per the failed-answer card described above.
- **Upload failed:** inline error on the Upload & Session screen, as described above.
- All error copy is specific and human ("Couldn't reach the database — retrying" style), per `harness/patterns/ui-ux.md`; colour is never the only signal (an icon + text always accompanies red states).

## Tech Stack

Next.js 15 + React 19, static export (`output: 'export'`, `basePath: '/app'`), Tailwind v4 for styling (existing skeleton conventions: `postcss.config.mjs` + `@source` in `globals.css`, unmodified). Phase 2 adds `react-plotly.js` + `plotly.js` for chart rendering. No markdown renderer is needed — answer text is a plain sentence, not LLM-authored markdown; the code panel is a plain monospace `<pre>` block (no syntax-highlighting library — kept minimal per `harness/patterns/code.md`'s "no premature abstraction"). `tests/e2e/` (Playwright) covers the primary journey per phase, run against the live build at `http://localhost:8001/app/`.

> **Assumed:** a plain `<pre>` block (no syntax-highlighting library) for the generated-code panel is not specified in the brief; it satisfies "shown, collapsed by default, expandable" without adding a new frontend dependency. If the user wants syntax colouring, that's a cheap Phase-2+ addition.
