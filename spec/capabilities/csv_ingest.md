# Capability: CSV Ingest

## What It Does

Accepts a CSV file uploaded by the user, extracts column metadata (names, row count), persists a dataset record, and stores the file on the server filesystem — returning dataset metadata (id, filename, row count, column names) to the caller.

## Inputs

| Input | Type | Source | Required |
|-------|------|---------|----------|
| `session_id` | string (UUID) | URL path parameter | Yes |
| `file` | multipart/form-data file upload | HTTP request body | Yes |

## Outputs

| Output | Type | Destination |
|--------|------|-------------|
| `dataset_id` | string (UUID) | JSON response body |
| `filename` | string | JSON response body |
| `row_count` | integer | JSON response body |
| `column_names` | array of strings | JSON response body |
| CSV file on disk | binary | `data/uploads/<session_id>/<dataset_id>_<filename>` |
| `DatasetRow` | DB record | SQLite `datasets` table |

## External Calls

| System | Operation | On Failure |
|--------|-----------|------------|
| Filesystem | Write uploaded bytes to `data/uploads/<session_id>/` | HTTP 500; error message returned to client |
| SQLite | INSERT `DatasetRow` | HTTP 500; file already written is left in place (not rolled back) |

## Business Rules

- Only `.csv` files are accepted. Files with any other extension or MIME type are rejected with HTTP 422.
- Maximum file size: 50 MB. Requests exceeding this limit are rejected with HTTP 413.
- `session_id` must exist in the `sessions` table. Unknown session IDs are rejected with HTTP 404.
- Column names are stored as a JSON array string in the `datasets` table.
- Raw CSV rows are never stored in the database — only the file path, column names, and row count.
- The upload directory `data/uploads/<session_id>/` is created if it does not exist.
- The filename stored in `DatasetRow.filename` is the original filename from the upload (sanitised: alphanumeric, hyphens, underscores, dot only — path separators stripped).
- The file is stored as `<dataset_id>_<sanitised_filename>` to avoid collisions from repeated uploads of the same filename.

## Success Criteria

- [ ] `POST /sessions/{session_id}/datasets` with a valid CSV returns HTTP 200 and a JSON body containing `dataset_id`, `filename`, `row_count` (correct count), and `column_names` (correct list).
- [ ] The file appears on disk at `data/uploads/<session_id>/<dataset_id>_<filename>` and can be re-read by pandas with identical column names.
- [ ] A `DatasetRow` is inserted into SQLite with the correct `session_id`, `filename`, `row_count`, `column_names`, and `file_path`.
- [ ] Uploading a non-CSV file (e.g. `.xlsx`) returns HTTP 422.
- [ ] Uploading with an unknown `session_id` returns HTTP 404.
- [ ] Two uploads of the same filename in the same session result in two distinct `DatasetRow` records and two distinct files on disk.
