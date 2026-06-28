"""In-process DataFrame store + privacy-safe extraction.

The active DataFrame for a session lives in an in-process registry keyed by
``session_id`` (single user, single process per ``architecture.md``). It is
never serialized to the LLM or to the checkpoint. Only the schema (column
names + dtypes) and a tiny N-row sample are ever extracted for prompting —
that sample is the single place raw row-level data is exposed, by design.

On a server restart the registry is empty; ``ensure_loaded`` lazily reloads
the DataFrame from the persisted upload file so chat history still works.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd


class DataFrameNotLoadedError(RuntimeError):
    """Raised when a session has no DataFrame in the store and none can be loaded."""


# session_id -> DataFrame held in this process only.
_REGISTRY: dict[str, pd.DataFrame] = {}


def load_dataframe(file_path: str, file_type: str = "csv") -> pd.DataFrame:
    """Read an uploaded file into a pandas DataFrame.

    Phase 1 supports CSV only; Excel arrives in a later phase.
    """
    ftype = (file_type or "csv").lower()
    if ftype == "csv":
        return pd.read_csv(file_path)
    raise ValueError(f"Unsupported file_type {file_type!r} (Phase 1 supports 'csv' only)")


def register(session_id: str, df: pd.DataFrame) -> None:
    """Store the active DataFrame for a session in the in-process registry."""
    _REGISTRY[session_id] = df


def get_dataframe(session_id: str) -> pd.DataFrame:
    """Return the registered DataFrame for a session, or raise a clear error."""
    df = _REGISTRY.get(session_id)
    if df is None:
        raise DataFrameNotLoadedError(
            f"No DataFrame loaded for session {session_id!r}. "
            "Upload a dataset or reload it via ensure_loaded() first."
        )
    return df


def ensure_loaded(session_id: str, file_path: str, file_type: str = "csv") -> pd.DataFrame:
    """Return the DataFrame for a session, lazily reloading from disk if absent.

    Lets chat history survive a server restart: if the registry has been
    cleared, the DataFrame is re-read from the persisted upload file and
    re-registered.
    """
    df = _REGISTRY.get(session_id)
    if df is None:
        df = load_dataframe(file_path, file_type)
        register(session_id, df)
    return df


def extract_schema(df: pd.DataFrame) -> list[dict]:
    """Return ``[{"name": col, "dtype": str(dtype)}, ...]`` for every column."""
    return [{"name": str(col), "dtype": str(dtype)} for col, dtype in df.dtypes.items()]


def extract_sample(df: pd.DataFrame, n: int = 5) -> list[dict]:
    """Return the first ``n`` rows as JSON-safe dicts.

    This is the ONLY raw data that may reach the LLM. NaN/NaT and numpy
    scalar types are normalized to ``None`` / native Python so the result is
    always ``json.dumps``-able.
    """
    head = df.head(n)
    rows: list[dict] = []
    for _, row in head.iterrows():
        rows.append({str(col): to_json_safe(row[col]) for col in head.columns})
    return rows


def row_count(df: pd.DataFrame) -> int:
    """Return the number of rows in the DataFrame."""
    return int(len(df))


def to_json_safe(value: Any) -> Any:
    """Convert a pandas/numpy scalar to a plain JSON-serializable Python value.

    Handles NaN/NaT/None -> None, numpy integers/floats/bools -> native,
    Timestamps -> ISO strings, and falls back to ``str`` for anything exotic.
    """
    if value is None:
        return None

    # pandas NA / NaT
    try:
        if value is pd.NA or value is pd.NaT:
            return None
    except Exception:
        pass

    # NaN floats (numpy or python) -> None
    if isinstance(value, float) and math.isnan(value):
        return None

    # numpy scalars expose .item() for the native python value
    item = getattr(value, "item", None)
    if callable(item):
        try:
            native = value.item()
            if isinstance(native, float) and math.isnan(native):
                return None
            return native
        except Exception:
            pass

    if isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value

    # pandas Timestamp / Timedelta and other objects -> string
    if isinstance(value, pd.Timestamp):
        return value.isoformat()

    # Fall back to native via a generic NA check then str()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    return str(value)
