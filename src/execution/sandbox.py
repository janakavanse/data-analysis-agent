"""Public API for running LLM-generated pandas code against a local dataset.

This is the ``execute_pandas`` tool from spec/agent.md and the privacy boundary
described in spec/architecture.md: it is the only place raw rows are touched, and
it runs out-of-process so a crash, hang, or runaway allocation can never take
down the main agent.

Usage (from the ``execute_locally`` graph node)::

    from execution.sandbox import run_pandas
    res = run_pandas(code, dataset_path)
    if not res["ok"]:
        ...  # feed res["error"] into the one-shot repair loop

The child process (``execution.runner_proc``) loads the CSV into ``df``, runs the
code, and assigns its output to ``result``. We invoke it with ``sys.executable``
in its own process group, pass the job via stdin, and enforce a wall-clock
timeout by killing the whole group on overrun.

Result envelope (success)::

    {
        "ok": True,
        "kind": "scalar" | "table" | "text",
        "payload": <computed value — local-only, for the graph>,
        "result_summary": <aggregates / shape only — LLM-visible>,
        "stdout": <captured stdout>,
        "duration_ms": <int>,
    }

Result envelope (failure — never raised, fed to the repair loop)::

    {
        "ok": False,
        "error_type": "Timeout" | "<ExceptionName>" | "ProcessError" | ...,
        "error": <message string>,
        "stdout": <captured stdout, if any>,
        "duration_ms": <int>,
    }
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from observability.events import get_logger

logger = get_logger("execution.sandbox")

# Defaults: a single-user local tool. Wall-clock is the hard guard on every
# platform; the memory limit is best-effort (honoured on Linux, typically
# ignored by macOS/darwin — see runner_proc._apply_limits).
DEFAULT_TIMEOUT_S = 30.0
DEFAULT_MEM_LIMIT_MB = 2048


def run_pandas(
    code: str,
    dataset_path: str | os.PathLike[str],
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    mem_limit_mb: int | None = DEFAULT_MEM_LIMIT_MB,
) -> dict:
    """Run ``code`` against the CSV at ``dataset_path`` in a restricted subprocess.

    Returns a structured envelope (see module docstring). Never raises for code
    errors or timeouts — those are returned as ``{"ok": False, ...}`` so the
    graph can drive its one-shot repair loop.
    """
    started = time.monotonic()
    # Resolve to an ABSOLUTE path here, in the caller's cwd, before it is handed
    # to the child. The child's _isolate_filesystem() chdir's into a temp dir, so
    # a relative path (e.g. the ./data/datasets/<id>/<file> stored by
    # data/storage.py) would no longer resolve after that chdir -> FileNotFound.
    path = Path(dataset_path).resolve()

    if not code or not code.strip():
        return _fail("EmptyCode", "no code supplied", started)
    if not path.is_file():
        return _fail("MissingDataset", f"dataset file not found: {path}", started)

    job = json.dumps({
        "code": code,
        "path": str(path),
        "mem_limit_mb": mem_limit_mb,
    })

    # New session/process group so a timeout can kill any children the code spawns.
    popen_kwargs: dict = {
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "cwd": os.getcwd(),
        "text": True,
    }
    if os.name == "posix":
        popen_kwargs["start_new_session"] = True

    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "execution.runner_proc"],
            env={**os.environ, "PYTHONPATH": _pythonpath()},
            **popen_kwargs,
        )
    except OSError as exc:
        return _fail("ProcessError", f"failed to start sandbox: {exc}", started)

    try:
        out, err = proc.communicate(input=job, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _kill(proc)
        proc.communicate()
        dur = _ms(started)
        logger.warning("sandbox.timeout", timeout_s=timeout_s, duration_ms=dur)
        return {
            "ok": False,
            "error_type": "Timeout",
            "error": f"execution exceeded the {timeout_s:.0f}s wall-clock limit",
            "stdout": "",
            "duration_ms": dur,
        }

    dur = _ms(started)

    if not out.strip():
        # No envelope on stdout => crash (e.g. OOM kill / segfault). stderr tail helps.
        tail = (err or "").strip().splitlines()[-5:]
        logger.warning("sandbox.no_output", returncode=proc.returncode, duration_ms=dur)
        return {
            "ok": False,
            "error_type": "ProcessError",
            "error": f"sandbox produced no result (exit {proc.returncode}): {' '.join(tail)}",
            "stdout": "",
            "duration_ms": dur,
        }

    try:
        envelope = json.loads(out)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "error_type": "ProtocolError",
            "error": "could not decode sandbox output",
            "stdout": out[:2000],
            "duration_ms": dur,
        }

    envelope["duration_ms"] = dur
    if envelope.get("ok"):
        logger.info(
            "sandbox.ok",
            kind=envelope.get("kind"),
            duration_ms=dur,
            summary=envelope.get("result_summary"),
        )
    else:
        logger.warning(
            "sandbox.code_error",
            error_type=envelope.get("error_type"),
            duration_ms=dur,
        )
    return envelope


def _fail(error_type: str, message: str, started: float) -> dict:
    return {
        "ok": False,
        "error_type": error_type,
        "error": message,
        "stdout": "",
        "duration_ms": _ms(started),
    }


def _kill(proc: subprocess.Popen) -> None:
    """Kill the whole process group (posix) or the process (other)."""
    try:
        if os.name == "posix":
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        else:  # pragma: no cover - non-posix
            proc.kill()
    except (ProcessLookupError, OSError):
        pass


def _pythonpath() -> str:
    src = str(Path(__file__).resolve().parents[1])
    existing = os.environ.get("PYTHONPATH", "")
    return f"{src}{os.pathsep}{existing}" if existing else src


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
