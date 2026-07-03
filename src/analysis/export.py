"""Export support: re-executes an already-audited query's `generated_code`
against the dataset file to regenerate the FULL (uncapped) dataframe result,
then serializes it to CSV or XLSX bytes for streaming.

Deliberately does NOT reuse `sandbox.execute_generated_code`'s `table` output
(that path is capped at 50 rows for the on-screen preview). This module
implements a thin, export-specific execution helper that mirrors the
sandbox's restricted-exec approach without the cap, and without touching
`analysis/sandbox.py` (owned by a parallel slice).
"""
import builtins
import io
import threading

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from analysis.storage import load_dataframe

_SAFE_BUILTINS = (
    "len", "range", "min", "max", "sum", "sorted", "list", "dict", "set",
    "tuple", "str", "int", "float", "bool", "abs", "round", "enumerate",
    "zip", "map", "filter", "any", "all", "isinstance", "print",
)


class ExportError(Exception):
    """Base export error."""


class NoDataframeResultError(ExportError):
    """The generated code produced no dataframe-shaped ('table') result."""


class DatasetUnavailableError(ExportError):
    """The dataset file is missing/moved, or re-execution otherwise failed."""


def _execute_for_export(code: str, dataset_path: str, file_type: str, timeout_seconds: int = 10) -> pd.DataFrame:
    """Re-runs `code` against the full dataframe and returns the FULL,
    uncapped `table` variable it produces. Raises NoDataframeResultError if
    no dataframe-shaped result was produced, or DatasetUnavailableError on
    any execution/dataset failure."""
    try:
        df = load_dataframe(dataset_path, file_type)
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise DatasetUnavailableError(f"Failed to load dataset: {exc}") from exc

    restricted_globals: dict = {
        "__builtins__": {name: getattr(builtins, name) for name in _SAFE_BUILTINS},
        "pd": pd,
        "df": df,
        "go": go,
        "px": px,
    }

    exception_box: list[Exception] = []

    def _run() -> None:
        try:
            exec(code, restricted_globals)
        except Exception as exc:  # noqa: BLE001 - deliberately broad, sandboxed
            exception_box.append(exc)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)

    if thread.is_alive():
        raise DatasetUnavailableError(f"Re-execution timed out after {timeout_seconds}s")

    if exception_box:
        exc = exception_box[0]
        raise DatasetUnavailableError(f"Re-execution failed: {type(exc).__name__}: {exc}")

    raw_table = restricted_globals.get("table")
    if not isinstance(raw_table, pd.DataFrame):
        raise NoDataframeResultError(
            "Generated code produced no dataframe-shaped 'table' result to export."
        )

    return raw_table


def export_query_result(code: str, dataset_path: str, file_type: str, export_format: str) -> tuple[bytes, str, str]:
    """Returns (bytes, filename, content_type) for the exported file.

    `export_format` must be "csv" or "xlsx"."""
    if export_format not in ("csv", "xlsx"):
        raise ValueError(f"Unsupported export format: {export_format!r}")

    table = _execute_for_export(code, dataset_path, file_type)

    if export_format == "csv":
        buffer = io.StringIO()
        table.to_csv(buffer, index=False)
        return buffer.getvalue().encode("utf-8"), "export.csv", "text/csv"

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        table.to_excel(writer, index=False, sheet_name="Sheet1")
    return (
        buffer.getvalue(),
        "export.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
