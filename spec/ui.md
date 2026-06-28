# UI

> DataChat web UI — Next.js 15 + React 19 static export served single-origin at `http://localhost:8001/app/`. Tech details and the static-export rules are in [`architecture.md`](architecture.md); this file describes screens, interactions, and exactly what is **REAL** vs a **labelled STUB** in Phase 1 (so a stub is never mistaken for a bug). Replaces the skeleton's `transform_text` form in `frontend/src/app/page.tsx` — keep `next.config.ts`, `postcss.config.mjs`, and the `@source` line in `globals.css` untouched.

---

## UI Type

Single-page web app: a chat-style data-analysis workbench. Three regions — a left **library sidebar**, a center **chat/analysis panel**, and a right **profile/observability panel**. One owner, no login.

## Views / Screens

### Screen: Empty State (first run) — REAL

**Purpose:** Greet the owner with a clear upload prompt before any data exists.

**Key elements:**
- A large centered **upload dropzone / "Upload a CSV" button** (REAL — accepts `.csv`).
- Short copy: "Upload a CSV to start. Your data stays on this machine — only the column names and a few sample rows are sent to the model."
- A faint, **clearly-labelled** preview of the workbench layout (sidebar/profile) marked "appears after upload."

**Actions:** select/drag a CSV → `POST /api/datasets` → on success, transition to the workbench with the profile loaded.

### Screen: Workbench — center Chat / Analysis Panel — REAL

**Purpose:** Ask questions and read answers for the active dataset.

**Key elements (all REAL in Phase 1):**
- **Chat thread** — prior turns rendered from the dataset's history (rehydrated on load via `GET /api/datasets/{id}`).
- **Question input** + send button.
- On submit, an SSE stream drives:
  - a **step/status indicator** ("Planning… → Generating code… → Running locally… → Writing answer…") from `event: status`.
  - a **streamed plain-English answer** (tokens appended live).
  - a **key-numbers strip** (headline aggregates from `key_numbers`).
  - a **summary table** (from `result_table`).
  - a **collapsible "Show code" panel** revealing the executed pandas (from `event: code`) — collapsed by default.
  - a **per-question tokens + cost** line (from `event: done`).
- **Example starter questions** appear once a dataset is loaded (REAL — static suggestions like "How many rows?", "What's the average of <numeric column>?", seeded from the profile's column names).
- **Error rendering** — on `event: error`, show the **real error message and the offending code** in an error card (not a generic toast); the input stays usable. A failed run still appears in history.

### Screen: Workbench — right Profile / Observability Panel — REAL

**Purpose:** Show what the agent knows about the data and how it answered.

**Key elements (REAL in Phase 1):**
- **Dataset profile** — row count; per-column name, dtype, missing count, numeric min/max/mean; sample rows.
- **Run history** — list of past questions for this dataset (question, status, cost, time) from `GET /api/datasets/{id}/messages`; clicking one expands its full plan, code, result, tokens, and cost (`GET /api/messages/{id}`).
- **"What was sent to the model" note** — a small reassurance line stating only schema + N sample rows left the machine (reinforces the privacy promise).

### Screen: Workbench — left Library Sidebar — STUB (real in Phase 3)

**Purpose:** (future) switch between previously-uploaded datasets across days.

**Phase 1 behaviour:** shows the single active dataset, plus a **clearly-labelled disabled section** "Your library — coming soon" with a couple of greyed, non-interactive placeholder rows and a disabled "Save cleaned dataset" button. Visibly a preview, not a bug.

## Phase 1 — REAL vs STUB map

| Surface | Phase 1 | Notes |
|---------|---------|-------|
| Upload CSV + empty state | **REAL** | `.csv` only |
| Auto-profile panel | **REAL** | local pandas profile |
| Chat: ask → streamed answer | **REAL** | SSE plan→code→execute→synthesize |
| Key-numbers strip + summary table | **REAL** | from the computed result |
| Collapsible "Show code" | **REAL** | executed pandas |
| Per-question tokens + cost | **REAL** | from `event: done` |
| Conversation history (per dataset, across days) | **REAL** | rehydrated from DB |
| Run-history browser | **REAL** | audit trail |
| Example starter questions | **REAL** | seeded from profile |
| Interactive charts / dashboard | **STUB** | labelled "Charts coming soon" placeholder card → Phase 2 |
| Follow-up question suggestions (AI-generated) | **STUB** | labelled placeholder under each answer → Phase 2 |
| Library sidebar (multi-dataset, cross-day switch) | **STUB** | labelled "coming soon", disabled → Phase 3 |
| Save derived/cleaned dataset | **STUB** | disabled button → Phase 3 |
| Excel / multi-sheet upload | **STUB** | upload rejects `.xlsx` with "coming in a later phase" → Phase 4 |
| Multi-file join / compare | **STUB** | labelled placeholder → Phase 4 |
| Running daily cost total | **STUB** | greyed total in header "daily total — coming soon" → Phase 5 |
| Confirm-before-heavy-work prompt | **STUB** | not shown in Phase 1 → Phase 5 |

**Stub rule:** every stub carries a visible "coming soon / later phase" label and is non-interactive (disabled). No stub renders fake data that could be mistaken for a real answer.

## Error States

- **Upload error** (malformed/oversized/unsupported): inline error on the dropzone with the real message ("coming in a later phase" for `.xlsx`).
- **Analysis error** (`event: error`): error card with the real error + offending code; input remains usable; the failed run is in history.
- **Network error** (server down): "Network error — is the server running on :8001?"
- **Loading/streaming**: step indicator + live token append (never a bare spinner with no feedback).

## Tech Stack

Next.js 15 + React 19, static export (`output: 'export'`, `basePath: '/app'`, `trailingSlash: true`), Tailwind v4 (`@tailwindcss/postcss`, `@source "../";`). Streaming consumed via the `EventSource`/`fetch`+`ReadableStream` SSE pattern. Served by FastAPI at `/app/`. Playwright E2E in `tests/e2e/` covers the primary journey (upload → ask → streamed answer with numbers + table + code + cost).
