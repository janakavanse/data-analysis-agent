# Product

> Filled by the **spec-writer** from intake. Part 1 of the 4-part spec contract (see `harness/harness.md`).

## What it does

A data analysis agent for analysts and data-savvy users who want to explore tabular data without writing SQL
or Python. Users upload CSV or JSON files through a browser UI; the agent parses each file into a named
SQLite table, records schema metadata, and returns a schema summary so the user knows what they have.
From that point the user can ask natural-language questions in a multi-turn chat session — the agent
translates each question to SQL, runs it, and returns a formatted answer (table + prose summary). At any
point the user can request a visualisation ("show revenue by region as a bar chart") and the agent produces
a Plotly JSON chart spec that the UI renders inline. All data stays local — no external data warehouse,
no external API calls for queries or charts. The product solves the "I have a CSV and I want answers fast"
problem without requiring technical expertise.

## Success criteria (these feed the outcome eval — keep them testable)

- [ ] A freshly uploaded CSV or JSON file results in a `datasets` table row with correct `schema_json`,
  `row_count`, and `file_type` values, and the agent returns a schema summary containing column names,
  inferred types, and at least 3 sample rows.
- [ ] A natural-language question about an uploaded dataset produces a SQL query that runs without error,
  and the answer includes the raw result data and a prose summary that directly addresses the question.
- [ ] In a multi-turn session (same `thread_id`), the user can ask a follow-up question without
  re-specifying the dataset, and the agent correctly scopes the follow-up SQL to the same table used in
  the prior turn.
- [ ] A natural-language chart request returns a valid Plotly JSON spec (parseable, correct `type` field,
  non-empty `data` array), and the UI renders the chart inline without a page reload.
- [ ] Any query that contains a mutating SQL keyword (`DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`,
  `TRUNCATE`) is refused before execution, and the agent returns a clear refusal message.

## Domain instructions (the agent's system-prompt guidance for this domain)

You are a data analysis assistant. Your only job is to help the user understand and explore datasets they
have uploaded. You have access to the following tools: `upload_dataset` (parse a file into a SQLite table),
`list_datasets` (show available datasets), `query_dataset` (run a SELECT query against a dataset table),
`generate_chart` (produce a Plotly JSON chart spec from query results), `write_todos` (track intermediate
steps), and `finish` (return your final answer to the user).

Rules you must follow without exception:
- Only execute SELECT statements. Never emit SQL containing DROP, DELETE, UPDATE, INSERT, ALTER, or
  TRUNCATE — refuse clearly if the user asks for anything that would mutate or destroy data.
- Always ground your answers in actual query results. Do not invent data, statistics, or column values.
  If the query returns no rows, say so explicitly.
- When the user asks a question about a dataset, identify the correct table from the active session
  context (the `datasets` metadata) before writing SQL. Never guess table or column names — look them
  up first.
- Return chart specifications as valid Plotly JSON. Do not describe a chart in prose when the user asked
  for one — call `generate_chart` and put the spec in your `finish` answer.
- Keep answers concise and factual. Lead with the direct answer or chart, then add a brief interpretation
  (1–3 sentences). Avoid filler phrases ("Great question!", "Certainly!").
- If the user asks you to do something outside data analysis (write code for them, browse the web,
  manage files outside the upload flow), decline politely and redirect to what you can do.

## Primary journey (UI design — drives the Next.js interface)

The UI is a single-page chat application. The journey:

1. **Upload panel** (top or sidebar): a file picker (CSV / JSON) with a drag-and-drop zone and an
   "Upload" button. On success the panel shows the dataset name, row count, and column list returned
   by the agent.
2. **Chat window** (main area): a message thread showing the full conversation. Each user message is
   right-aligned; each agent response is left-aligned and rendered as markdown (tables, code blocks,
   bold). Inline charts appear directly in the message stream — the `answer` field may carry a Plotly
   JSON spec; when it does, the UI renders `<Plot data={spec.data} layout={spec.layout} />` inline
   below the prose portion.
3. **Input bar** (bottom): a text input + "Send" button. On submit, the message is appended to the
   thread, the agent is called via `POST /runs` (SSE stream for token-by-token delivery), and the
   answer builds up live in the thread.
4. **Session header** (top bar): shows active dataset name, thread_id, and a running token + cost total
   for the session. A "New session" button clears localStorage and starts a fresh thread.
5. **Trace link**: each agent response shows a small "trace" link that deep-links to `/traces` for that
   run_id.

`thread_id` and `active_dataset_id` are persisted in `localStorage` so a page reload resumes the same
conversation and dataset context.

## Out of scope (Future Phases)

- Multi-user accounts, authentication, or dataset sharing between users.
- Persistent long-term memory across separate sessions (cross-run recall).
- External data sources (databases, APIs, cloud warehouses) — only local file uploads.
- Scheduled queries, reports, or alerts.
- Export of charts or query results to files.
- Multi-agent orchestration or sub-agent parallelism.
- Human-in-the-loop approval flows (all operations are read-only SELECT; no mutation risk requiring HITL).
- Automatic dashboard generation — charts are always user-requested, never auto-built.
- Support for file formats beyond CSV and JSON (Excel, Parquet, etc.).
