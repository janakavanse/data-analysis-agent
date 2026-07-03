"""Restricted-exec sandbox for running LLM-generated pandas code against the
real, locally-loaded dataframe. Not a full container sandbox — a pragmatic
allow-listed-builtins + thread-based timeout guard (Windows has no
signal.alarm), per spec/architecture.md.
"""
import builtins
import threading

import pandas as pd

from analysis.storage import load_dataframe

_SAFE_BUILTINS = (
    "len", "range", "min", "max", "sum", "sorted", "list", "dict", "set",
    "tuple", "str", "int", "float", "bool", "abs", "round", "enumerate",
    "zip", "map", "filter", "any", "all", "isinstance", "print",
)

_MAX_TABLE_ROWS = 50


class SandboxExecutionError(Exception):
    pass


def _to_native(value):
    """Cast numpy/pandas scalars to native Python types for JSON-safety."""
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, AttributeError):
            return value
    return value


def execute_generated_code(
    code: str,
    dataset_path: str,
    file_type: str,
    timeout_seconds: int = 10,
) -> dict:
    """Runs `code` in a restricted globals dict with `df`/`pd` in scope,
    inside a worker thread bounded by `timeout_seconds`. Returns
    {"answer": str, "table": list[dict] | None}. Raises SandboxExecutionError
    on any failure (bug, missing 'answer', or timeout)."""
    # Local variable only — never returned, logged, or placed in AgentState.
    df = load_dataframe(dataset_path, file_type)

    restricted_globals: dict = {
        "__builtins__": {name: getattr(builtins, name) for name in _SAFE_BUILTINS},
        "pd": pd,
        "df": df,
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
        raise SandboxExecutionError(f"Execution timed out after {timeout_seconds}s")

    if exception_box:
        exc = exception_box[0]
        message = f"{type(exc).__name__}: {exc}"
        # Keep the error message concise and free of any potential raw-data leakage.
        if len(message) > 300:
            message = message[:300] + "..."
        raise SandboxExecutionError(message)

    answer = restricted_globals.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        raise SandboxExecutionError("Generated code did not produce an 'answer' variable")

    table = None
    raw_table = restricted_globals.get("table")
    if isinstance(raw_table, pd.DataFrame):
        capped = raw_table.head(_MAX_TABLE_ROWS)
        table = [
            {k: _to_native(v) for k, v in row.items()}
            for row in capped.to_dict(orient="records")
        ]

    return {"answer": answer, "table": table}
