# UI

---

## UI Type

Single-page web chat app (Next.js 15 static export + React 19 + Tailwind), served at `http://localhost:8001/app/`. Replaces the baseline transform form in `frontend/src/app/page.tsx`.

## Views / Screens

### Screen: Analysis Workspace (single page)

**Purpose:** Upload a dataset and converse with it; every answer shows its work.

**Layout:** a left/top **upload + dataset header** zone, a central **chat transcript**, a bottom **question input**, and a right/side rail of **labelled stubs** for coming-soon features.

**Key elements:**
- **Drag/drop upload zone** (REAL, Phase 1) — drop or pick a CSV. On success shows the filename, row count, and column chips (from `schema`). Excel is accepted visually but labelled "CSV only for now — Excel coming soon" (stub until Phase 4).
- **Chat transcript** (REAL, Phase 1) — user bubbles + assistant bubbles. Each assistant bubble shows the plain-English **answer** plus a collapsible **"Show the work"** panel containing:
  - the **pandas code** that ran (monospace block), and
  - the **result table / value** it produced.
- **Question input** (REAL, Phase 1) — text box + send; disabled until a dataset is uploaded; supports follow-ups (history is threaded server-side).
- **Coming-soon rail** (STUBS, Phase 1 — clearly labelled, non-functional):
  - **"Charts"** — a greyed panel labelled "Inline charts — coming soon (Phase 2)".
  - **"One-shot report"** — a disabled "Generate report" button labelled "Auto profile + findings + charts — coming soon (Phase 3)".
  - **"Insights"** — a greyed panel labelled "Auto-findings — coming soon (Phase 5)".
  - **"Excel"** — note on the upload zone, "Excel support — coming soon (Phase 4)".

**Actions available:**
- Upload a CSV (real).
- Ask a question; expand/collapse "Show the work" (real).
- Reload the page — the transcript for the current `session_id` re-renders (real, Phase 1).

## Error States

- **Upload failure:** inline red banner on the drop zone ("Could not read this file as CSV"). No session created.
- **Analysis failure:** the assistant bubble shows a readable message ("Could not analyze that — try rephrasing") with no code/result; the rest of the chat is unaffected.
- **Loading:** a typing/skeleton indicator in the transcript while the question runs; the input is disabled during the run.
- **Stub clarity:** every non-functional surface carries a visible "coming soon (Phase N)" label so it is never mistaken for a bug.

## Tech Stack

Next.js 15 + React 19 + Tailwind, static export to `frontend/out/`, served single-origin at `/app`. Talks to `POST /datasets`, `POST /sessions/{id}/ask`, `GET /sessions/{id}`.
