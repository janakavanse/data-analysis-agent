# UI

## UI Type

Web chat interface — a two-panel browser layout with a CSV file management panel and a conversational chat window. Built as a Next.js 15 static export, served by FastAPI at `/app`.

---

## Views / Screens

### Screen: Main Analyst View (single page)

**Purpose:** The entire application is one page. On load, a session is created automatically. The user uploads CSVs in the left panel and asks questions in the right chat panel.

**Layout:**

```
┌─────────────────────────────────────────────────────────────┐
│  Data Analyst Agent                                          │
├──────────────────┬──────────────────────────────────────────┤
│  LEFT PANEL      │  CHAT PANEL                              │
│  (file mgmt)     │  (conversation)                          │
│                  │                                          │
│  ┌────────────┐  │  ┌─────────────────────────────────┐    │
│  │ CSV Upload  │  │  │  [assistant] Welcome! Upload…   │    │
│  │ dropzone   │  │  └─────────────────────────────────┘    │
│  └────────────┘  │                                          │
│                  │  ┌─────────────────────────────────┐    │
│  Uploaded files: │  │  [user] What are the columns?   │    │
│  ┌────────────┐  │  └─────────────────────────────────┘    │
│  │ sales.csv  │  │                                          │
│  │ 1,200 rows │  │  ┌─────────────────────────────────┐    │
│  └────────────┘  │  │  [assistant] The dataset has 3  │    │
│                  │  │  columns: Month, Region, Revenue │    │
│  [STUB Phase 3]  │  │                                  │    │
│  Multi-file      │  │  ┌──────────────────────────┐   │    │
│  queries coming  │  │  │ Month │ Region │ Revenue  │   │    │
│  in Phase 3      │  │  │ Jan   │ North  │ 52400    │   │    │
│  — not yet active│  │  └──────────────────────────┘   │    │
│                  │  │                                  │    │
│                  │  │  [STUB Phase 2]                  │    │
│                  │  │  Charts coming in Phase 2        │    │
│                  │  │  — not yet active                │    │
│                  │  └─────────────────────────────────┘    │
│                  │                                          │
│                  │  ┌─────────────────────────────────┐    │
│                  │  │  Type a question…        [Send]  │    │
│                  │  └─────────────────────────────────┘    │
└──────────────────┴──────────────────────────────────────────┘
```

---

#### Left Panel — File Management

**Key elements:**

- **CSV Upload dropzone:** A drag-and-drop area or click-to-browse file input. Accepts `.csv` files only. Shows upload progress (spinner) while the file is being uploaded.
- **Uploaded file list:** After a successful upload, shows a card per file containing:
  - Filename (e.g. `sales_2024.csv`)
  - Row count (e.g. `1,200 rows`)
  - (Phase 3) A checkbox to select the file for the next query
- **[STUB — Phase 3] Multi-file toggle / cross-file query notice:** A banner or toggle at the bottom of the left panel labelled: `"Multi-file queries coming in Phase 3 — not yet active"`. Styled in muted grey/amber to distinguish it clearly from functional elements. The toggle/checkbox is visible but disabled (not clickable) in Phases 1–2.

**Actions available:**

- Upload a new CSV file (click or drag-and-drop)
- (Phase 3) Select / deselect individual files for a query

---

#### Chat Panel — Conversation

**Key elements:**

- **Message list:** Scrollable list of message bubbles. Two bubble types:
  - **User bubble** (right-aligned, primary colour background): Shows the user's question.
  - **Assistant bubble** (left-aligned, neutral background): Shows:
    - Text answer (prose paragraph)
    - [Optional] Inline data table (if `table_data` is non-null): HTML `<table>` with header row from object keys and data rows. Styled with alternating row shading.
    - [STUB — Phase 2] Chart placeholder inside each assistant bubble: `"Charts coming in Phase 2 — not yet active"` shown as a muted dashed-border box below the table. Appears on every assistant bubble in Phase 1 to show the vision. Disappears when Phase 2 wires in a real chart.
    - [Phase 2] Chart image: `<img src="data:image/png;base64,{chart_b64}">` rendered inline below the table when `chart_b64` is non-null.
- **Thinking indicator:** While awaiting a query response, the assistant bubble shows an animated "Thinking…" indicator (three dots or spinner).
- **Welcome message:** On session creation, an initial assistant message appears: `"Hello! Upload a CSV file on the left, then ask me anything about your data."`
- **Chat input:** Single-line text input + Send button at the bottom of the chat panel. Disabled until at least one CSV is uploaded.

**Actions available:**

- Type a natural-language question and press Enter or click Send
- (Phase 3) The active dataset selection in the left panel determines which files are queried

---

## Error States

| Situation | UI Treatment |
|-----------|-------------|
| Upload fails (server error) | Inline error below the dropzone: `"Upload failed: [error message]. Try again."` File card does not appear. |
| Query fails (Gemini error, file read error) | Assistant message bubble shows the error in red text: `"Something went wrong: [error message]."` |
| Network error | Assistant message bubble or dropzone shows: `"Network error — is the server running?"` |
| No CSV uploaded yet | Chat input is disabled with placeholder text: `"Upload a CSV to start asking questions"` |
| File too large (>50 MB) | Inline error below dropzone: `"File too large. Maximum size is 50 MB."` |
| Non-CSV file dropped | Inline error below dropzone: `"Only .csv files are supported."` |

---

## Stub Labelling Convention

All stub/placeholder surfaces must meet these criteria so they are never mistaken for bugs:

1. Visible text label stating what is coming and in which phase, e.g. `"Charts coming in Phase 2 — not yet active"`.
2. Muted visual treatment (grey text, dashed border, or amber badge) that distinguishes them from functional elements.
3. Non-interactive (disabled, not just styled grey) — clicking or tapping produces no action or network request.
4. Consistent placement: chart stub always appears inside the assistant bubble below the table; multi-file stub always appears at the bottom of the left panel.

---

## Single-Origin Run Path

The canonical test and production run path is single-origin:
1. `cd frontend && pnpm build` — builds the Next.js static export into `frontend/out/`.
2. `uv run python -m src` — starts FastAPI on port 8001, which serves `frontend/out/` at `/app`.
3. Open `http://localhost:8001/app/` (trailing slash required).

`pnpm dev` (`:3000`) is for inner-loop frontend development only and is not the tested path.
