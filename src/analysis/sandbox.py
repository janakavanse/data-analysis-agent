"""Restricted local execution of LLM-written pandas (`run_pandas`).

This is the agent's single "tool": it runs a pandas snippet over the
in-process DataFrame in a *restricted* environment. The snippet may only
touch ``df`` and ``pd`` plus a small allow-list of safe builtins. Imports,
file/network/IO, ``eval``/``exec``/``compile``, and dunder access are
blocked so private data cannot be exfiltrated and the host cannot be reached.

The snippet must assign its answer to a variable named ``result``. The result
(DataFrame / Series / scalar) is serialized to the ``result_repr`` shape
``{kind, columns?, rows?, value?}`` with all values JSON-safe.

Timeout: execution runs in a daemon worker thread with a wall-clock
``join`` timeout. Pure-Python compute releasing-or-not the GIL is bounded by
``timeout_s``; on overrun we raise rather than block the request forever.
(A daemon thread is portable across platforms and works off the main thread,
unlike ``signal.alarm``.)
"""

from __future__ import annotations

import math
import threading
from typing import Any

import pandas as pd

from analysis.store import to_json_safe

DEFAULT_TIMEOUT_S = 10.0

# Curated safe builtins. Notably ABSENT: __import__, open, eval, exec, compile,
# input, globals, locals, vars, getattr, setattr, delattr, __build_class__.
_SAFE_BUILTINS: dict[str, Any] = {
    name: __builtins__[name] if isinstance(__builtins__, dict) else getattr(__builtins__, name)
    for name in (
        "len", "range", "sum", "min", "max", "abs", "round", "sorted",
        "list", "dict", "set", "tuple", "str", "int", "float", "bool",
        "enumerate", "zip", "map", "filter", "reversed", "all", "any",
    )
}


class SandboxError(RuntimeError):
    """Raised when a snippet is rejected or fails to execute.

    The message includes the original error text so the graph's repair loop
    can feed it back to the model.
    """


def _reject_dangerous_source(code: str) -> None:
    """Static pre-check blocking obvious escape attempts before exec.

    Defense-in-depth on top of the restricted builtins: catches ``import`` and
    dunder access even when phrased to dodge the runtime guard.
    """
    lowered = code
    banned = ("__import__", "__builtins__", "__globals__", "__class__",
              "__subclasses__", "__bases__", "__mro__", "__loader__",
              "__getattribute__")
    for token in banned:
        if token in lowered:
            raise SandboxError(f"Disallowed token in code: {token}")
    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            raise SandboxError("Imports are not allowed in the sandbox")


def _serialize_result(result: Any) -> dict:
    """Convert the snippet's ``result`` into the JSON-safe result_repr shape."""
    if isinstance(result, pd.DataFrame):
        columns = [str(c) for c in result.columns]
        rows = [[to_json_safe(v) for v in row] for row in result.itertuples(index=False, name=None)]
        return {"kind": "table", "columns": columns, "rows": rows}

    if isinstance(result, pd.Series):
        index_name = str(result.index.name) if result.index.name is not None else "index"
        value_name = str(result.name) if result.name is not None else "value"
        columns = [index_name, value_name]
        rows = [[to_json_safe(idx), to_json_safe(val)] for idx, val in result.items()]
        return {"kind": "table", "columns": columns, "rows": rows}

    value = to_json_safe(result)
    # Guard against NaN slipping through (json.dumps would emit NaN otherwise).
    if isinstance(value, float) and math.isnan(value):
        value = None
    return {"kind": "scalar", "value": value}


def run_pandas(code: str, df: pd.DataFrame, timeout_s: float = DEFAULT_TIMEOUT_S) -> dict:
    """Execute ``code`` over ``df`` in a restricted env; return the result_repr.

    Args:
        code: pandas snippet that assigns its answer to ``result``.
        df: the in-process DataFrame (read-only intent; ops return new objects).
        timeout_s: wall-clock budget for the snippet.

    Returns:
        ``{kind, columns?, rows?, value?}`` — JSON-safe.

    Raises:
        SandboxError: on a rejected/dangerous snippet, missing ``result``,
            timeout, or any execution error (original message preserved).
    """
    if not isinstance(code, str) or not code.strip():
        raise SandboxError("No code provided to execute")

    _reject_dangerous_source(code)

    sandbox_globals: dict[str, Any] = {
        "__builtins__": _SAFE_BUILTINS,
        "pd": pd,
        "df": df,
    }
    sandbox_locals: dict[str, Any] = {}

    holder: dict[str, Any] = {}
    error_holder: dict[str, BaseException] = {}

    def _worker() -> None:
        try:
            exec(compile(code, "<sandbox>", "exec"), sandbox_globals, sandbox_locals)  # noqa: S102
            if "result" not in sandbox_locals and "result" not in sandbox_globals:
                raise SandboxError(
                    "Snippet did not assign a variable named 'result'"
                )
            holder["result"] = sandbox_locals.get("result", sandbox_globals.get("result"))
        except BaseException as exc:  # noqa: BLE001 - surfaced to caller verbatim
            error_holder["error"] = exc

    worker = threading.Thread(target=_worker, daemon=True)
    worker.start()
    worker.join(timeout=timeout_s)

    if worker.is_alive():
        raise SandboxError(f"Code execution exceeded the {timeout_s:.0f}s time limit")

    if "error" in error_holder:
        exc = error_holder["error"]
        if isinstance(exc, SandboxError):
            raise exc
        raise SandboxError(f"{type(exc).__name__}: {exc}") from exc

    return _serialize_result(holder["result"])
