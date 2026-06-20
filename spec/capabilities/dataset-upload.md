# Capability: Dataset Upload

## What & why

A user uploads a CSV or JSON file through the UI. The agent parses the file, creates a dynamically-named
SQLite table (`ds_<uuid>`), records metadata in a `datasets` table (id, name, table_name, schema_json,
file_type, row_count), and returns a schema summary — column names, inferred types, sample rows, and row
count — so the user knows what they have before asking questions. Serves the "uploaded file results in a
correct datasets row and schema summary" success criterion in `spec/product.md`.

## Acceptance criteria (EARS — these ARE the eval inputs)

- WHEN the user uploads a valid CSV file the system SHALL parse it into a new SQLite table named `ds_<uuid>`, record a row in the `datasets` table with correct `file_type`, `row_count`, `schema_json`, and `table_name`, and return a schema summary containing column names, inferred types, and at least 3 sample rows.
- WHEN the user uploads a valid JSON file (array of objects) the system SHALL parse it into a new SQLite table, record metadata in `datasets`, and return the same schema summary format as CSV.
- WHEN the user uploads a file with no rows (header-only CSV or empty JSON array) the system SHALL record a `datasets` row with `row_count` of 0 and return a schema summary noting the file is empty.
- IF the uploaded file is not valid CSV or JSON (e.g. binary, malformed) THEN the system SHALL return an error message describing the parse failure and SHALL NOT create a `datasets` row or a data table.
- IF the upload contains a file larger than 50 MB THEN the system SHALL reject it before parsing and return a clear size-limit error.

## Tools & layers touched

- tool: `upload_dataset`  (in-process @tool — `harness/patterns/tools-and-mcp.md`)
- layers: Persistence (domain tables `datasets` + dynamic `ds_<uuid>` data tables) — `harness/patterns/persistence.md`

## Evaluation

- outcome evaluation_steps:
  - Does the answer include a schema summary with column names and their inferred types?
  - Does the answer state the row count of the uploaded file?
  - Does the answer include at least 3 sample rows (or note the file is empty if row_count is 0)?
  - Is the answer free of invented column names or types not present in the actual file?
- expect_tools: [upload_dataset, finish]
- forbid_tools: [query_dataset, generate_chart]

## Notes

- The `datasets` domain table is the registry: every upload gets one row keyed by `id` (uuid), with
  `name` (original filename), `table_name` (`ds_<uuid>`), `schema_json` (JSON object mapping column
  name → inferred SQLite type), `file_type` (`csv` | `json`), and `row_count`.
- The dynamic data tables (`ds_<uuid>`) are created inline by the tool using `CREATE TABLE IF NOT EXISTS`
  with columns inferred from the file headers and types.
- The tool must use `aiosqlite` / async SQLAlchemy to avoid blocking the event loop during parse + write.
- Out of scope for this capability: file conversion, multi-sheet Excel, partial-file preview, schema
  overrides by the user.
