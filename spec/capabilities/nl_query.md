# Capability: NL Query

## What It Does

Accepts a natural-language question and a dataset reference, runs analysis against the uploaded CSV data, and returns a structured response containing a prose text answer, an optional inline data table, and (Phase 2) an optional base64-encoded chart image.

## Inputs

| Input | Type | Source | Required |
|-------|------|---------|----------|
| `session_id` | string (UUID) | URL path parameter | Yes |
| `question` | string | JSON request body | Yes |
| `dataset_id` | string (UUID) | JSON request body | Yes (Phase 1–2); at least one required |
| `dataset_ids` | array of strings (UUIDs) | JSON request body | Phase 3 multi-file only; if provided, overrides `dataset_id` |

## Outputs

| Output | Type | Destination |
|--------|------|-------------|
| `run_id` | string (UUID) | JSON response body |
| `answer_text` | string | JSON response body; displayed as the assistant message text in the chat |
| `table_data` | array of objects or null | JSON response body; rendered as an inline HTML table in the chat |
| `chart_b64` | string (base64 PNG) or null | JSON response body (Phase 2); rendered as `<img>` in the chat |
| `status` | `"completed"` or `"failed"` | JSON response body |
| `error` | string or null | JSON response body (present when `status == "failed"`) |
| `RunRow` | DB record | SQLite `runs` table |

## External Calls

| System | Operation | On Failure |
|--------|-----------|------------|
| SQLite | SELECT `DatasetRow` for `dataset_id` + `session_id` | Fatal — returns HTTP 422 with error message |
| Filesystem | Read CSV file via pandas `read_csv` | Fatal — returns HTTP 422 with error message |
| Google Gemini API | `generate_content` (schema + stats + question → answer) | Fatal — returns HTTP 422 with error message; run marked "failed" in DB |
| SQLite | INSERT/UPDATE `RunRow` (status, answer, table, chart) | Non-fatal on update failure; logged |

## Business Rules

- `session_id` must exist in the `sessions` table and the `dataset_id(s)` must belong to that session. Mismatches return HTTP 404.
- The Gemini prompt receives only the DataFrame schema, `.describe()` statistics, and `head(5)` — never raw row data beyond the 5-row preview. This satisfies the "no data leaves the server" constraint.
- If the Gemini response contains no `table_json` block, `table_data` is `null` in the response (non-fatal; the text answer is still returned).
- If the Gemini response contains a malformed `table_json` block (invalid JSON), `table_data` is `null` (non-fatal; logged as a warning).
- A question submitted with an empty string is rejected with HTTP 422 before the graph is invoked.
- Each query creates exactly one `RunRow` in the `runs` table, linked to `session_id` and `dataset_id`.
- On Gemini API error (any exception), the `RunRow` is written with `status = "failed"` and `error_message` set; the API returns HTTP 422 with the error message so the chat displays it.
- (Phase 2) If the Gemini response contains a `chart_spec` block with a valid chart descriptor, a matplotlib PNG is generated in-process and returned as `chart_b64`. If the chart spec is absent or matplotlib fails, `chart_b64` is `null` (non-fatal).
- (Phase 3) If `dataset_ids` contains more than one ID, the DataFrame context includes schema + stats for each dataset, labelled by filename. The question may reference dataset filenames to express join or comparison intent.

## Success Criteria

- [ ] `POST /sessions/{session_id}/queries` with a valid `question` and `dataset_id` returns HTTP 200 and a JSON body with `answer_text` (non-empty string), `status == "completed"`, and `table_data` either null or a non-empty array of objects.
- [ ] The `RunRow` inserted in the `runs` table has `status = "completed"`, `answer_text` matching the response, and `table_json` matching `table_data` (as JSON string).
- [ ] A question that calls for tabular output (e.g. "List the top 5 rows by value") produces a non-null `table_data` array with the correct structure.
- [ ] A question that produces no table (e.g. "What is the average age?") returns `table_data = null` and a non-empty `answer_text`.
- [ ] A missing or unknown `dataset_id` returns HTTP 404 before the graph is invoked.
- [ ] An empty `question` string returns HTTP 422 before the graph is invoked.
- [ ] (Phase 2) A chart-requesting question (e.g. "Show a bar chart of sales by month") returns a non-null `chart_b64` string that is a valid base64-encoded PNG.
- [ ] (Phase 3) A query with two `dataset_ids` returns an answer that references data from both datasets.
