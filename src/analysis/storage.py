"""On-disk storage for the analysis engine.

Owns the persistent DuckDB connection (the *analysis compute* engine) and the
filesystem layout under the data root. This is deliberately separate from the
SQLite app-state engine in ``src/db`` — DuckDB holds the full uploaded data and
runs generated code locally; SQLite holds durable application state. The two
never share a connection (see architecture.md "DuckDB vs SQLite").

The data root defaults to ``./data`` but is overridable via the ``AGENT_DATA_DIR``
environment variable so tests can isolate their DuckDB file and parquet copies.
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb

_connection: "duckdb.DuckDBPyConnection | None" = None
_connection_path: Path | None = None


def data_root() -> Path:
    """Root directory for all on-disk analysis artifacts.

    Honours ``AGENT_DATA_DIR`` (read live, not cached) so tests can point the
    engine at a temp directory via monkeypatch/env.
    """
    root = Path(os.environ.get("AGENT_DATA_DIR", "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def uploads_dir() -> Path:
    """Directory holding the original uploaded files."""
    d = data_root() / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def parquet_dir() -> Path:
    """Directory holding the columnar parquet copies for fast re-reads."""
    d = data_root() / "parquet"
    d.mkdir(parents=True, exist_ok=True)
    return d


def duckdb_path() -> Path:
    """Path to the persistent DuckDB analysis database file."""
    return data_root() / "analysis.duckdb"


def get_connection() -> "duckdb.DuckDBPyConnection":
    """Return the lazily-created persistent DuckDB connection.

    A single connection is reused across the process (lazy singleton, mirroring
    the ``db/session.py`` engine pattern). If the resolved data root changes
    (e.g. a test sets ``AGENT_DATA_DIR`` to a fresh tmp dir), the connection is
    transparently re-opened against the new file.
    """
    global _connection, _connection_path
    target = duckdb_path()
    if _connection is not None and _connection_path == target:
        return _connection
    if _connection is not None:
        try:
            _connection.close()
        except Exception:
            pass
    _connection = duckdb.connect(str(target))
    _connection_path = target
    return _connection


def reset_connection() -> None:
    """Close and forget the cached connection (used by tests)."""
    global _connection, _connection_path
    if _connection is not None:
        try:
            _connection.close()
        except Exception:
            pass
    _connection = None
    _connection_path = None
