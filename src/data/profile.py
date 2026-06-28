"""Privacy-safe auto-profiler.

Produces ONLY aggregate statistics per column — dtype, missing count, distinct
count, and (numeric columns only) min/max/mean. This profile is the object that
crosses the privacy boundary to the LLM, so it MUST NOT contain any raw cell
values, sample rows, top-value labels, or anything derived from individual
records. The hard invariant: no raw data leaves this function.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd
from pandas.api import types as ptypes


def _safe_float(value: Any) -> float | None:
    """Convert a numpy/pandas scalar to a JSON-safe float, or None."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def profile_column(series: pd.Series, name: str) -> dict[str, Any]:
    """Build the privacy-safe profile dict for one column.

    Shape: {name, dtype, missing, distinct, min, max, mean}
    Numeric stats (min/max/mean) are None for non-numeric columns.
    """
    is_numeric = ptypes.is_numeric_dtype(series) and not ptypes.is_bool_dtype(series)

    entry: dict[str, Any] = {
        "name": str(name),
        "dtype": str(series.dtype),
        "missing": int(series.isna().sum()),
        "distinct": int(series.nunique(dropna=True)),
        "min": None,
        "max": None,
        "mean": None,
    }

    if is_numeric:
        non_null = series.dropna()
        if not non_null.empty:
            entry["min"] = _safe_float(non_null.min())
            entry["max"] = _safe_float(non_null.max())
            entry["mean"] = _safe_float(non_null.mean())

    return entry


def build_profile(df: pd.DataFrame) -> dict[str, Any]:
    """Build the full JSON-serializable profile for a DataFrame.

    Returns {"columns": [<per-column profile>, ...]}. Matches the
    `profile` shape in spec/api.md. Contains no raw rows or cell values.
    """
    columns = [profile_column(df[col], col) for col in df.columns]
    return {"columns": columns}
