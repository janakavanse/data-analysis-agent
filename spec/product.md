# Product

> Filled by the **spec-writer** from intake. Part 1 of the 4-part spec contract (see `harness/harness.md`).
> Leave the `<!-- FILL IN -->` markers until the spec-writer completes them. This file is the **intent of
> record** for the domain: the spec is truth here. (The reused tested core is truth in its own zone — see
> `spec/constitution.md` § two-zone model.) Every success criterion below must map to **≥1 capability** in
> `spec/capabilities/`; the analyze pre-flight fails the build if any criterion has no capability.

## What it does

A data analysis agent that lets users upload CSV, JSON, or Excel files and ask analytical questions in
plain English. The agent writes and executes Python code (using pandas and numpy) to compute statistics,
filter data, aggregate values, and surface insights — then shows the user both the answer and the code
that produced it. A data analyst or business user drops a file into the chat, asks questions like "what
is the average revenue by region?" or "which rows have missing values?", and gets a correct numeric answer
plus the reproducible code, all in one browser-based session. Follow-up questions on the same file work
without re-uploading. P1 is file upload and Python-powered analysis; P2 adds SQL database exploration;
P3 adds external data sources.

## Success criteria (these feed the outcome eval — keep them testable)

- [x] When given a CSV file and asked a statistical question (e.g. "what is the average of column X?"),
  the agent computes and returns the correct numeric answer using Python/pandas. (→ file-analysis)
- [x] When asked a follow-up analytical question on the same session (same uploaded file), the agent
  retains the file context across turns and answers without requiring the user to re-upload. (→ file-analysis)
- [x] [P2 stub] When given a SQLite connection string, the agent can introspect the schema and answer
  natural-language queries by generating and running SQL. Returns a stub confirmation until promoted. (→ sql-explorer)

## Domain instructions (the agent's system-prompt guidance for this domain)

You are a data analysis agent. The user has uploaded a data file (CSV, JSON, or Excel). Your job is to
answer their analytical questions accurately by writing and executing Python code with pandas and numpy.

Rules:
- Always show the Python code you used to produce the answer. Wrap it in a code block.
- Be precise with numbers: include units and round to a sensible precision (e.g. 2 decimal places for
  currency, integers for counts).
- Refuse any code that accesses the filesystem outside the session's uploaded data directory. Only read
  from the session-scoped file path provided; never write, delete, or open other paths.
- Refuse destructive operations: never generate or execute code containing DELETE, DROP, TRUNCATE, rm,
  shutil.rmtree, os.remove, or any file-mutation call.
- If the user's question is ambiguous, make the most reasonable interpretation and state it explicitly.
- If the data file is not yet loaded or is empty, tell the user to upload a file before asking questions.
- Do not invent data values; compute everything from the actual loaded file.

## Out of scope (Future Phases)

- External database connections (PostgreSQL, MySQL, remote servers) — v1 only supports SQLite stub (P2)
- Google Sheets, REST API data sources, or cloud storage (S3, GCS) — P3 stub only
- Multi-file cross-join analysis (joining two uploaded files) — deferred post-P1
- Real-time or streaming data sources
- Chart or visualization rendering (e.g. matplotlib output) — text and numeric answers only in v1
- Scheduled or automated analysis without user interaction
