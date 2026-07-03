# Capability: Upload and Profile a Dataset

## What It Does

Accepts one uploaded CSV or Excel file, stores it locally, and extracts a schema profile (columns, types, and aggregate stats) — without ever reading the file's content into anything that leaves the local machine.

## Inputs

| Input | Type | Source | Required |
|-------|------|--------|----------|
| File | `.csv` or `.xlsx` binary | User upload (`POST /sessions/{id}/datasets`, `multipart/form-data`) | yes |
| `session_id` | string (UUID) | URL path, from a prior `POST /sessions` | yes |

## Outputs

| Output | Type | Destination |
|--------|------|-------------|
| `Dataset` row (storage_path, schema_json, row_count, column_count) | DB record | SQLite `datasets` table |
| Raw file bytes | binary | Local disk: `data/uploads/<session_id>/<dataset_id>/<original_filename>` |
| Dataset profile summary | JSON | API response, rendered as the dataset-profile card in the UI |

## External Calls

| System | Operation | On Failure |
|--------|-----------|------------|
| Local filesystem | Write the uploaded file to `data/uploads/<session_id>/<dataset_id>/` | 500, structured error, nothing partially written is left referenced by a `Dataset` row |
| pandas / openpyxl (local, in-process) | Parse the file and compute per-column stats | 400 with a human-readable "couldn't be read as a spreadsheet" message if parsing fails |

Note: **no LLM call** happens in this capability — profiling is pure local computation.

## Business Rules

- Only `.csv` and `.xlsx` are accepted; anything else is rejected with a 400 before any file is written to disk.
- `schema_json` contains, per column: `name`, `dtype`, `null_count`, `min`/`max` (numeric/date columns only), and `distinct_sample` (only for columns below a low-cardinality threshold — e.g. ≤ 20 distinct values; `null` otherwise). This is a deliberate privacy boundary: high-cardinality columns (names, IDs, free text) never have sample values extracted.
  > **Assumed:** the 20-distinct-value low-cardinality threshold is not specified in the brief; it's a reasonable default balancing "give the LLM enough signal to write correct filter code" against "never leak individual identifying values." Confirm or adjust with the user if a different threshold is wanted.
- `row_count`/`column_count` reflect the **full** file, never a sample or a truncated read.
- Re-uploading within the same session creates a new `Dataset` row; it does not delete or merge with the previous one (no cross-`Dataset` joins are ever performed — see `spec/roadmap.md` Out of Scope).
- The raw file content and every individual row value are never transmitted anywhere outside the local process — only `schema_json` (aggregate/metadata only) is ever read by the LLM-facing code in the `ask-question` capability.

## Success Criteria

- [ ] Uploading a valid CSV with ≥ 5,000 rows returns a `Dataset` with `row_count` equal to the file's true row count (not truncated).
- [ ] Uploading a valid `.xlsx` file is profiled correctly (dtype inference, null counts) using `openpyxl`.
- [ ] Uploading a `.txt` or `.json` file is rejected with a 400 and a specific message, and no `Dataset` row or disk file is created.
- [ ] A column with > 20 distinct string values has `distinct_sample = null` in `schema_json`; a column with ≤ 20 distinct values has a non-empty `distinct_sample`.
- [ ] The uploaded file's bytes are found on local disk at the documented `storage_path` and nowhere else (no copy sent to any external API).
