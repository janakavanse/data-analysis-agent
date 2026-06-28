"""CSV ingestion: load a stored CSV into a pandas DataFrame.

Enforces a ~100MB size cap (typed error → 413) and surfaces parse failures as
a typed error (→ 400). Loading the real rows is a LOCAL operation only; the
DataFrame never leaves the process toward the LLM.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

# ~100MB cap. The CSV capability rejects anything larger.
MAX_UPLOAD_BYTES = 100 * 1024 * 1024


class DatasetError(Exception):
    """Base class for ingestion failures."""


class DatasetTooLargeError(DatasetError):
    """Uploaded file exceeds the size cap. API maps this to HTTP 413."""

    def __init__(self, size_bytes: int, limit_bytes: int = MAX_UPLOAD_BYTES) -> None:
        self.size_bytes = size_bytes
        self.limit_bytes = limit_bytes
        super().__init__(
            f"file is {size_bytes} bytes; exceeds cap of {limit_bytes} bytes"
        )


class DatasetParseError(DatasetError):
    """File is not parseable as CSV. API maps this to HTTP 400."""


def check_size(size_bytes: int, limit_bytes: int = MAX_UPLOAD_BYTES) -> None:
    """Raise DatasetTooLargeError if size_bytes exceeds the cap."""
    if size_bytes > limit_bytes:
        raise DatasetTooLargeError(size_bytes, limit_bytes)


def load_csv(storage_path: str | Path) -> pd.DataFrame:
    """Load a CSV file into a DataFrame with sensible dtype inference.

    Enforces the size cap from the file on disk and raises DatasetParseError
    on malformed/empty CSV.
    """
    path = Path(storage_path)
    if not path.is_file():
        raise DatasetParseError(f"file not found: {storage_path}")

    check_size(path.stat().st_size)

    try:
        # Default pandas dtype inference; keep memory bounded by not copying.
        df = pd.read_csv(path)
    except pd.errors.EmptyDataError as exc:
        raise DatasetParseError(f"empty or headerless CSV: {exc}") from exc
    except (pd.errors.ParserError, ValueError, UnicodeDecodeError) as exc:
        raise DatasetParseError(f"could not parse CSV: {exc}") from exc

    if df.shape[1] == 0:
        raise DatasetParseError("CSV has no columns")

    return df


def row_count(df: pd.DataFrame) -> int:
    """Number of data rows in the loaded frame."""
    return int(df.shape[0])
