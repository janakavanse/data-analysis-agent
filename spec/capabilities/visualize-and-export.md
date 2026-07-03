# Capability: Visualize and Export

## What It Does

Renders an interactive chart when a question naturally produces one, and lets the user download a cleaned/filtered version of the data a question computed — both ephemeral, viewed/downloaded in the moment, never saved to a persistent library.

## Inputs

| Input | Type | Source | Required |
|-------|------|--------|----------|
| `generated_code` (may assign a `chart` variable) | Python source | Same `generate_code` call as `ask-question.md` | no — only when a chart is appropriate for the question |
| `query_id` + export `format` | string (UUID) + `"csv"`/`"xlsx"` | `POST /queries/{id}/export` | yes, for export |
| `Query.generated_code` + `Dataset.storage_path` | text / path | `queries`/`datasets` tables | yes, for export |

## Outputs

| Output | Type | Destination |
|--------|------|-------------|
| Chart spec | Plotly figure JSON (`fig.to_json()`) | `Query.chart_spec_json`, rendered client-side via `react-plotly.js` |
| Exported file | CSV or XLSX binary stream | HTTP file download, this request only — never persisted to a library |

## External Calls

| System | Operation | On Failure |
|--------|-----------|------------|
| Restricted-exec sandbox (chart) | The same `execute_code` sandbox additionally reads an optional `chart` variable (a `plotly.graph_objects.Figure`) out of the generated code's local namespace | If `chart` isn't assigned, `chart_spec_json` stays `null` — this is a normal, non-error outcome (not every question produces a chart) |
| Restricted-exec sandbox (export) | Re-executes the query's already-audited `generated_code` against the dataset file (via the stable Phase-1 sandbox interface) to regenerate the dataframe-shaped result, then streams it as CSV/XLSX | 500 if the dataset file has moved/changed since the original run; 400 if the query's code produced no dataframe-shaped result (e.g. a pure scalar answer with nothing to export) |

## Business Rules

- **No new LLM call for either chart generation or export.** The chart is a byproduct of the same single `generate_code` call already required for the answer; export re-runs the already-generated, already-audited code rather than asking the LLM again.
- Charts, tables, and exported files are **ephemeral** — there is no "past charts" or "past exports" browser, in this phase or any future one (see `spec/roadmap.md` → Out of Scope). An export is generated fresh on each `POST /queries/{id}/export` call and streamed directly; nothing is written to a persistent download library.
- The chart is rendered entirely client-side from the JSON spec — no server-side image rendering, no chart image files on disk.
- Export always reflects the **full** dataset's computation (same "never sample, never truncate" rule as `ask-question.md`) — only the row limit that applies to the on-screen **table preview** (50 rows) is a display-layer cap; the exported file contains the complete result.

## Success Criteria

- [ ] A question that naturally groups/aggregates data (e.g. "show a breakdown of X by Y") produces a non-null `chart_spec_json` that `react-plotly.js` renders as a real interactive chart (hoverable/zoomable), not a static image.
- [ ] A question with a purely scalar answer (e.g. "what is the total X") leaves `chart_spec_json` null, and the UI shows no chart panel for that turn (not an empty/broken one).
- [ ] Exporting a completed query that filtered/transformed the data (e.g. "show me all rows where X > 100") downloads a CSV/XLSX containing exactly the filtered rows the answer described — verified by re-computing the expected row count independently in the test and asserting the exported file matches it, against a fixture large enough (≥ 5,000 rows) that a truncated export would be observably wrong.
- [ ] Attempting to export a query whose answer was a pure scalar (no dataframe-shaped result) returns a 400 with a clear message, not a broken/empty file.
- [ ] No exported file or chart is ever retrievable after the fact from a "past exports" or "past charts" list — the only permanent record is the `Query` row's `generated_code` (an auditor can re-derive the same output, but the system itself doesn't store it a second time).
