"""Child-process entry point for the local pandas sandbox.

Invoked as: python -m execution.runner_proc

Reads a JSON job from stdin:
    {"code": "<pandas code>", "path": "<csv path>", "mem_limit_mb": <int|null>}

Loads the CSV into a DataFrame named ``df``, executes the user code (which must
assign its output to a variable named ``result``), and writes a JSON envelope to
stdout describing either the captured result or a typed failure.

Hardening applied in-process (best effort for a single-user local tool):
  - chdir into a private temp dir so relative writes land there, not the cwd
  - socket creation is blocked, so the executed code cannot open the network
  - RLIMIT_AS (address space) is set where the platform honours it (Linux);
    on macOS/darwin RLIMIT_AS is generally NOT enforced — the parent's
    wall-clock timeout is the hard guard there.

The parent (``execution.sandbox``) owns the wall-clock timeout and kills the
process group on overrun. This module never raises to stdout: any failure is
serialised as ``{"ok": false, ...}``.
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import traceback
from contextlib import redirect_stdout

# Cap on how many rows/items we are willing to serialise back to the parent.
# The full result stays local; this only bounds the IPC payload size.
MAX_TABLE_ROWS = 1000


def _apply_limits(mem_limit_mb: int | None) -> None:
    """Best-effort resource limits. Silently skips what the platform lacks."""
    try:
        import resource
    except ImportError:  # pragma: no cover - non-unix
        return

    if mem_limit_mb is not None:
        nbytes = mem_limit_mb * 1024 * 1024
        # RLIMIT_AS is honoured on Linux; macOS often ignores it. Try anyway.
        for name in ("RLIMIT_AS", "RLIMIT_DATA"):
            limit = getattr(resource, name, None)
            if limit is None:
                continue
            try:
                soft, hard = resource.getrlimit(limit)
                new_hard = nbytes if hard == resource.RLIM_INFINITY else min(nbytes, hard)
                resource.setrlimit(limit, (nbytes, new_hard))
            except (ValueError, OSError):
                # Platform refused this limit (typical for RLIMIT_AS on darwin).
                pass


def _block_network() -> None:
    """Prevent the executed code from opening network sockets."""
    import socket

    def _denied(*_args, **_kwargs):
        raise OSError("network access is disabled in the sandbox")

    socket.socket = _denied  # type: ignore[assignment]
    socket.create_connection = _denied  # type: ignore[assignment]
    if hasattr(socket, "create_server"):
        socket.create_server = _denied  # type: ignore[assignment]


def _isolate_filesystem() -> str:
    """Chdir into a fresh temp dir; relative writes stay contained there."""
    workdir = tempfile.mkdtemp(prefix="sandbox-")
    os.chdir(workdir)
    return workdir


def _summarize(result, pd) -> dict:
    """Build the structured envelope + a privacy-safe summary.

    The ``payload`` carries the computed value back to the (local) graph.
    ``result_summary`` is the LLM-visible view: aggregates / shape only, never
    raw rows beyond what the user's own aggregation legitimately produced.
    """
    # Scalar-ish: numbers, strings, bools, None, numpy scalars.
    if result is None or isinstance(result, (int, float, str, bool)):
        value = result
        if hasattr(result, "item") and not isinstance(result, (str, bytes)):
            try:
                value = result.item()
            except (ValueError, AttributeError):
                value = result
        return {
            "kind": "scalar",
            "payload": value,
            "result_summary": {"kind": "scalar", "value": value},
        }

    # numpy scalar (e.g. np.int64 from df['x'].sum())
    if hasattr(result, "item") and not hasattr(result, "__len__"):
        value = result.item()
        return {
            "kind": "scalar",
            "payload": value,
            "result_summary": {"kind": "scalar", "value": value},
        }

    # pandas Series -> table (index/value pairs), e.g. a groupby aggregation.
    if isinstance(result, pd.Series):
        full_len = len(result)
        truncated = result.head(MAX_TABLE_ROWS)
        records = [
            {"key": _jsonable(k), "value": _jsonable(v)}
            for k, v in truncated.items()
        ]
        return {
            "kind": "table",
            "payload": records,
            "result_summary": {
                "kind": "table",
                "shape": [full_len, 2],
                "columns": ["key", "value"],
                "row_count": full_len,
                "truncated": full_len > MAX_TABLE_ROWS,
            },
        }

    # pandas DataFrame -> table (list of records).
    if isinstance(result, pd.DataFrame):
        full_rows = len(result)
        truncated = result.head(MAX_TABLE_ROWS)
        records = json.loads(truncated.to_json(orient="records", date_format="iso"))
        return {
            "kind": "table",
            "payload": records,
            "result_summary": {
                "kind": "table",
                "shape": [full_rows, result.shape[1]],
                "columns": [str(c) for c in result.columns],
                "row_count": full_rows,
                "truncated": full_rows > MAX_TABLE_ROWS,
            },
        }

    # Lists / dicts / other JSON-able containers -> text fallback.
    try:
        payload = _jsonable(result)
        return {
            "kind": "text",
            "payload": payload,
            "result_summary": {"kind": "text", "type": type(result).__name__},
        }
    except (TypeError, ValueError):
        text = str(result)
        return {
            "kind": "text",
            "payload": text,
            "result_summary": {"kind": "text", "type": type(result).__name__},
        }


def _jsonable(value):
    """Coerce numpy / pandas scalars and nested containers to JSON-native types."""
    if value is None or isinstance(value, (int, float, str, bool)):
        return value
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return str(value)


def main() -> int:
    raw = sys.stdin.read()
    try:
        job = json.loads(raw)
        code = job["code"]
        path = job["path"]
        mem_limit_mb = job.get("mem_limit_mb")
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        sys.stdout.write(json.dumps({
            "ok": False,
            "error_type": "BadJob",
            "error": f"invalid job payload: {exc}",
            "stdout": "",
        }))
        return 0

    _apply_limits(mem_limit_mb)
    _block_network()
    _isolate_filesystem()

    captured = io.StringIO()
    try:
        import pandas as pd  # imported after limits so its alloc counts

        df = pd.read_csv(path)
        ns: dict = {"df": df, "pd": pd}
        with redirect_stdout(captured):
            exec(code, ns)  # noqa: S102 - sandboxed by design
        if "result" not in ns:
            sys.stdout.write(json.dumps({
                "ok": False,
                "error_type": "NoResult",
                "error": "code did not assign a variable named 'result'",
                "stdout": captured.getvalue(),
            }))
            return 0
        envelope = _summarize(ns["result"], pd)
        envelope["ok"] = True
        envelope["stdout"] = captured.getvalue()
        sys.stdout.write(json.dumps(envelope))
        return 0
    except Exception as exc:  # noqa: BLE001 - all user-code errors are data
        sys.stdout.write(json.dumps({
            "ok": False,
            "error_type": type(exc).__name__,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(limit=6),
            "stdout": captured.getvalue(),
        }))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
