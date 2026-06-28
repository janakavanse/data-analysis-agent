"""Privacy-local pandas analysis engine.

The DataFrame store keeps uploaded data in-process (it never leaves the
machine) and exposes only privacy-safe extracts (schema + N-row sample) for
prompting. The sandbox executes LLM-written pandas locally with restricted
builtins, no imports/IO, and a wall-clock timeout.
"""

from analysis.sandbox import SandboxError, run_pandas
from analysis.store import (
    DataFrameNotLoadedError,
    ensure_loaded,
    extract_sample,
    extract_schema,
    get_dataframe,
    load_dataframe,
    register,
    row_count,
)

__all__ = [
    "DataFrameNotLoadedError",
    "ensure_loaded",
    "extract_sample",
    "extract_schema",
    "get_dataframe",
    "load_dataframe",
    "register",
    "row_count",
    "SandboxError",
    "run_pandas",
]
