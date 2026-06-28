"""Local analysis engine: ingest, the privacy redaction point, and local code execution.

This module is the *analysis compute* layer. It loads uploaded CSV/Excel files
into DuckDB (the full dataset, never sent to the LLM), exposes a single bounded
context builder (``make_llm_context`` — the one privacy redaction point), and runs
LLM-generated pandas/SQL code locally on the FULL dataset under a static denylist
and a wall-clock timeout (``execute``).

Privacy boundary (architecture.md): the LLM only ever sees schema + a tiny sample
+ a capped prior result. ``make_llm_context`` is the only function that produces
LLM-facing dataset context, and it never reads or returns bulk rows.
"""

from __future__ import annotations

import contextlib
import io
import math
import threading
import traceback
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from analysis import storage

# --- Constants (exported; consumed by graph-loop) ---------------------------
SAMPLE_ROWS: int = 20
MAX_RESULT_ROWS: int = 200
MAX_RESULT_BYTES: int = 50_000  # ~50 KB serialized result cap
EXEC_TIMEOUT_S: int = 25

# Static denylist patterns rejected BEFORE exec. The local user is trusted, but
# this guard stops generated code from touching the filesystem / network / shell.
_DENYLIST: tuple[str, ...] = (
    "import os",
    "import sys",
    "import subprocess",
    "import socket",
    "import shutil",
    "import importlib",
    "from os",
    "from sys",
    "from subprocess",
    "from socket",
    "from shutil",
    "subprocess",
    "socket",
    "open(",
    "eval(",
    "exec(",
    "__import__",
    "importlib",
    "os.system",
    "os.popen",
)


class BadFileError(Exception):
    """Raised when an uploaded file is empty, unsupported, or cannot be parsed."""


def table_name(dataset_id: str) -> str:
    """The DuckDB table name for a dataset (``ds_<id>``)."""
    return f"ds_{dataset_id}"


# --- JSON-safety helpers ----------------------------------------------------

def _json_safe(value: Any) -> Any:
    """Coerce a single value into something JSON-serializable.

    Dates/timestamps are stringified; NaN/NaT/None become None; numpy scalars are
    unwrapped to native Python; everything else falls back to ``str``.
    """
    if value is None:
        return None
    if isinstance(value, (datetime, date, time, pd.Timestamp)):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return None if math.isnan(value) else value
    # numpy scalars expose .item()
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _json_safe(item())
        except Exception:
            return str(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode("utf-8", "replace")
        except Exception:
            return str(value)
    return str(value)


def _frame_sample(df: pd.DataFrame, n: int) -> list[dict[str, Any]]:
    """Return up to ``n`` rows as JSON-safe dicts."""
    head = df.head(n)
    return [
        {col: _json_safe(val) for col, val in row.items()}
        for _, row in head.iterrows()
    ]


def _schema_from_frame(df: pd.DataFrame) -> list[dict[str, str]]:
    return [{"name": str(col), "dtype": str(dtype)} for col, dtype in df.dtypes.items()]


# --- Ingest -----------------------------------------------------------------

def ingest_file(file_path: str, original_name: str, dataset_id: str) -> dict:
    """Load a CSV/.xlsx file into DuckDB table ``ds_<dataset_id>`` + a parquet copy.

    Returns ``{schema, sample (<=SAMPLE_ROWS), row_count, duckdb_table, parquet_path}``.
    Raises ``BadFileError`` on empty / unsupported / unparseable input.
    """
    src = Path(file_path)
    if not src.exists():
        raise BadFileError(f"File not found: {file_path}")
    if src.stat().st_size == 0:
        raise BadFileError("Uploaded file is empty.")

    ext = (Path(original_name).suffix or src.suffix).lower()
    con = storage.get_connection()
    tbl = table_name(dataset_id)

    try:
        # Drop any stale table for this dataset id (re-ingest is idempotent).
        con.execute(f'DROP TABLE IF EXISTS "{tbl}"')

        if ext in (".csv", ".tsv", ".txt"):
            # DuckDB's native, vectorized CSV reader handles 100MB efficiently.
            con.execute(
                f'CREATE TABLE "{tbl}" AS SELECT * FROM read_csv_auto(?, SAMPLE_SIZE=-1)',
                [str(src)],
            )
        elif ext in (".xlsx", ".xls"):
            # Excel: read via pandas (openpyxl) then register the frame into DuckDB.
            frame = pd.read_excel(src)
            if frame.shape[1] == 0:
                raise BadFileError("Excel file has no columns.")
            con.register("_ingest_tmp", frame)
            try:
                con.execute(f'CREATE TABLE "{tbl}" AS SELECT * FROM _ingest_tmp')
            finally:
                con.unregister("_ingest_tmp")
        else:
            raise BadFileError(f"Unsupported file type: {ext or '(none)'}")
    except BadFileError:
        raise
    except Exception as exc:  # parse failure / malformed file
        raise BadFileError(f"Could not parse file: {exc}") from exc

    # Row count + emptiness check.
    row_count = int(con.execute(f'SELECT COUNT(*) FROM "{tbl}"').fetchone()[0])
    col_count = len(con.execute(f'SELECT * FROM "{tbl}" LIMIT 0').description)
    if col_count == 0:
        con.execute(f'DROP TABLE IF EXISTS "{tbl}"')
        raise BadFileError("File has no columns.")
    if row_count == 0:
        con.execute(f'DROP TABLE IF EXISTS "{tbl}"')
        raise BadFileError("File has no data rows.")

    # Write the parquet copy for fast re-reads / rebuilds.
    parquet_path = storage.parquet_dir() / f"{dataset_id}.parquet"
    con.execute(
        f"COPY \"{tbl}\" TO '{parquet_path.as_posix()}' (FORMAT PARQUET)"
    )

    # Schema + sample derived from a bounded read (LIMIT — never the full table).
    sample_df = con.execute(
        f'SELECT * FROM "{tbl}" LIMIT {SAMPLE_ROWS}'
    ).df()
    schema = _schema_from_frame(sample_df)
    sample = _frame_sample(sample_df, SAMPLE_ROWS)

    return {
        "schema": schema,
        "sample": sample,
        "row_count": row_count,
        "duckdb_table": tbl,
        "parquet_path": str(parquet_path),
    }


# --- The privacy redaction point -------------------------------------------

def make_llm_context(dataset_id: str, prior_result: dict | None = None) -> dict:
    """THE single privacy redaction point.

    Returns ONLY ``{schema, sample (<=SAMPLE_ROWS), prior_result}``. It re-derives
    schema + sample from the DuckDB table using a ``LIMIT`` read — it NEVER reads
    or returns bulk rows. The ``prior_result`` (a previously-capped execution
    result) is passed through unchanged.
    """
    con = storage.get_connection()
    tbl = table_name(dataset_id)
    # Bounded read: LIMIT SAMPLE_ROWS guarantees no bulk rows are materialized.
    sample_df = con.execute(f'SELECT * FROM "{tbl}" LIMIT {SAMPLE_ROWS}').df()
    return {
        "schema": _schema_from_frame(sample_df),
        "sample": _frame_sample(sample_df, SAMPLE_ROWS),
        "prior_result": prior_result,
    }


# --- Local code execution ---------------------------------------------------

def _denylist_hit(code: str) -> str | None:
    lowered = code.lower()
    for pattern in _DENYLIST:
        if pattern in lowered:
            return pattern
    return None


def _normalize_result(value: Any) -> dict | Any:
    """Normalize a generated ``result`` into a capped JSON-safe shape.

    A DataFrame/Series becomes ``{"columns": [...], "rows": [[...]]}`` capped to
    MAX_RESULT_ROWS and ~MAX_RESULT_BYTES. A scalar/dict/list is wrapped JSON-safe.
    """
    if isinstance(value, pd.DataFrame):
        capped = value.head(MAX_RESULT_ROWS)
        columns = [str(c) for c in capped.columns]
        rows = [[_json_safe(v) for v in row] for row in capped.itertuples(index=False, name=None)]
        rows = _byte_cap_rows(columns, rows)
        return {
            "columns": columns,
            "rows": rows,
            "truncated": len(value) > MAX_RESULT_ROWS or len(rows) < min(len(value), MAX_RESULT_ROWS),
        }
    if isinstance(value, pd.Series):
        capped = value.head(MAX_RESULT_ROWS)
        columns = ["index", str(capped.name) if capped.name is not None else "value"]
        rows = [[_json_safe(idx), _json_safe(val)] for idx, val in capped.items()]
        rows = _byte_cap_rows(columns, rows)
        return {"columns": columns, "rows": rows, "truncated": len(value) > MAX_RESULT_ROWS}
    if isinstance(value, dict):
        return {"scalar": {str(k): _json_safe(v) for k, v in value.items()}}
    if isinstance(value, (list, tuple)):
        capped = list(value)[:MAX_RESULT_ROWS]
        return {"scalar": [_json_safe(v) for v in capped]}
    return {"scalar": _json_safe(value)}


def _byte_cap_rows(columns: list[str], rows: list[list[Any]]) -> list[list[Any]]:
    """Drop trailing rows until the serialized size is under MAX_RESULT_BYTES."""
    import json

    while rows:
        try:
            size = len(json.dumps({"columns": columns, "rows": rows}).encode("utf-8"))
        except (TypeError, ValueError):
            size = MAX_RESULT_BYTES + 1
        if size <= MAX_RESULT_BYTES:
            break
        # Drop ~10% of rows at a time for speed, at least one.
        drop = max(1, len(rows) // 10)
        rows = rows[: len(rows) - drop]
    return rows


def execute(code: str, dataset_id: str) -> dict:
    """Run LLM-generated code locally on the FULL dataset.

    Namespace exposes ``pd`` (pandas), ``con`` (the DuckDB connection), ``df`` (the
    full frame), and ``table`` (the table-name string). The generated snippet must
    assign ``result`` and may assign ``key_numbers``. Enforces a static denylist
    (before exec), a wall-clock timeout, and stdout capture. ALL execution errors
    are captured into the returned ``error`` field — this function never raises.

    Returns ``{"result", "key_numbers", "stdout", "error"}``.
    """
    # 1. Static guard — reject dangerous patterns BEFORE running anything.
    hit = _denylist_hit(code)
    if hit is not None:
        return {
            "result": None,
            "key_numbers": {},
            "stdout": "",
            "error": f"Blocked by execution guard: disallowed pattern {hit!r}.",
        }

    con = storage.get_connection()
    tbl = table_name(dataset_id)

    # 2. Run in a worker thread so we can enforce a wall-clock timeout.
    outcome: dict[str, Any] = {}

    def _runner() -> None:
        stdout_buf = io.StringIO()
        namespace: dict[str, Any] = {
            "pd": pd,
            "con": con,
            "table": tbl,
        }
        try:
            # Materialize the full frame for convenience; generated code may also
            # push heavy aggregation into DuckDB via `con`/SQL on `table`.
            namespace["df"] = con.execute(f'SELECT * FROM "{tbl}"').df()
            with contextlib.redirect_stdout(stdout_buf):
                exec(compile(code, "<generated>", "exec"), namespace)
            result = namespace.get("result", None)
            key_numbers = namespace.get("key_numbers", {})
            if not isinstance(key_numbers, dict):
                key_numbers = {"value": _json_safe(key_numbers)}
            else:
                key_numbers = {str(k): _json_safe(v) for k, v in key_numbers.items()}
            outcome["result"] = _normalize_result(result) if result is not None else None
            outcome["key_numbers"] = key_numbers
            outcome["stdout"] = stdout_buf.getvalue()[:MAX_RESULT_BYTES]
            outcome["error"] = None
        except Exception:
            outcome["result"] = None
            outcome["key_numbers"] = {}
            outcome["stdout"] = stdout_buf.getvalue()[:MAX_RESULT_BYTES]
            outcome["error"] = traceback.format_exc()

    worker = threading.Thread(target=_runner, daemon=True)
    worker.start()
    worker.join(timeout=EXEC_TIMEOUT_S)

    if worker.is_alive():
        # Timed out. The daemon thread is abandoned (single trusted local user;
        # in-process exec cannot be force-killed safely — the deadline bounds the
        # user-visible wait, matching the architecture's documented posture).
        return {
            "result": None,
            "key_numbers": {},
            "stdout": "",
            "error": f"Execution timed out after {EXEC_TIMEOUT_S}s.",
        }

    return {
        "result": outcome.get("result"),
        "key_numbers": outcome.get("key_numbers", {}),
        "stdout": outcome.get("stdout", ""),
        "error": outcome.get("error"),
    }
