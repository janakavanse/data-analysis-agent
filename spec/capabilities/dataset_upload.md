# Capability: Dataset Upload

## What It Does
Accepts a CSV file the user drags into the web app, loads it into a pandas DataFrame on the local machine, derives its schema and a tiny sample, and opens a chat session bound to that dataset.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| file | uploaded file (CSV) | drag/drop or file picker in the web UI | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| session_id | string (uuid) | response body; UI keeps it for subsequent questions |
| schema | list of `{name, dtype}` | response body + persisted (see [data.md](../data.md) `Dataset`) |
| row_count | int | response body + persisted |
| sample_rows | list of objects (first N rows, default 5) | response body + persisted; shown nowhere raw to the user, used only for the LLM prompt |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| Local filesystem | Save uploaded bytes under the managed `data/uploads/` dir; load with `pandas.read_csv` | Return 400 with a plain-English message ("Could not read this file as CSV"); no session created |

## Business Rules
- The uploaded file is stored on the local machine only. The raw bytes and the full DataFrame never leave the machine and are never sent to the LLM.
- Only the derived schema (column names + dtypes), `row_count`, and the first N sample rows (N=5, configurable) are persisted to the DB and are the ONLY dataset-derived material the LLM is ever shown.
- Messy data is loaded as-is with pandas defaults (mixed types become `object`, missing values become `NaN`). The user is NOT asked any cleaning questions at upload time.
- Phase 1 accepts CSV only. Excel (`.xlsx`/`.xls`) is a labelled stub in the UI and is delivered in a later phase.
- One active dataset per session. Uploading a new file starts a new session.

## Success Criteria
- [ ] POST of a valid CSV returns 200 with a `session_id`, a `schema` whose column names match the file header, the correct `row_count`, and exactly N `sample_rows`.
- [ ] The persisted `Dataset` row stores schema + sample + row_count but NOT the full row data.
- [ ] POST of a non-CSV / corrupt file returns 400 with a readable message and creates no session.
- [ ] A CSV with missing values and mixed-type columns uploads without error and without prompting the user.
