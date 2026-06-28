# Capability: Profile Dataset

## What It Does
On upload of a single CSV, loads the file locally with pandas and produces a structured profile — column names, dtypes, numeric ranges, distinct/missing-value counts, and a few sample rows — persisted with the dataset and shown to the user.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| file | multipart CSV upload | user (browser upload) | yes |
| display_name | string | derived from original filename | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| dataset_id | string (uuid) | API response + `datasets` row |
| profile | JSON object (per-column type/range/missing + row count + N sample rows) | `datasets.profile_json` + API response |
| on-disk file path | string | `datasets.file_path` (file stays local) |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| Local filesystem | Write uploaded bytes to `data/uploads/<dataset_id>.csv` | Abort upload; return `api_error("UPLOAD_FAILED", ...)` |
| pandas | `read_csv` + profiling (no LLM) | Return `api_error("MALFORMED_FILE", message=actual parse error, 400)`; no row persisted |

## Business Rules
- Profiling is 100% local — pandas only, **no LLM call**. The file never leaves the machine.
- Reject files over `AGENT_MAX_UPLOAD_MB` (default 100 MB) before parsing, with a clear size error.
- Only `.csv` accepted in Phase 1; `.xlsx`/multi-sheet are rejected with "Excel support coming in a later phase" (the upload UI labels this as a stub).
- The sample-row count sent later to the LLM is capped by `AGENT_SAMPLE_ROWS` (default 20) — never the full data.
- A malformed file surfaces the **actual pandas error text**, not a generic message.

## Success Criteria
- [ ] Uploading a valid CSV returns `200` with a `dataset_id` and a `profile` containing every column with a dtype and a missing-count.
- [ ] The full file is written under `data/uploads/` and a `datasets` row exists with `profile_json` populated.
- [ ] Uploading a structurally broken CSV returns `400` with the real pandas error in the message and creates no dataset row.
- [ ] No outbound LLM/network call is made during profiling (verified by the profile completing with the Gemini key absent).
