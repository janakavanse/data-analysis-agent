"""Local disk storage for uploaded dataset files, and the ONLY place file bytes
are ever loaded into a pandas DataFrame. Never call `load_dataframe` from any
code path that could pass the resulting frame to the LLM.
"""
from pathlib import Path

import pandas as pd


def _uploads_root() -> Path:
    # repo root: src/analysis/storage.py -> parents[2] = repo root
    return Path(__file__).resolve().parent.parent.parent / "data" / "uploads"


def save_upload(session_id: str, dataset_id: str, filename: str, content: bytes) -> Path:
    """Writes `content` to data/uploads/<session_id>/<dataset_id>/<filename> and
    returns the resulting path, creating directories as needed."""
    directory = _uploads_root() / session_id / dataset_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_bytes(content)
    return path


def load_dataframe(storage_path: str, file_type: str) -> pd.DataFrame:
    """Loads the full dataset from disk into a pandas DataFrame. This is the
    ONLY place raw file bytes are parsed into a dataframe."""
    if file_type == "csv":
        return pd.read_csv(storage_path)
    if file_type == "xlsx":
        return pd.read_excel(storage_path, sheet_name=0, engine="openpyxl")
    raise ValueError(f"Unsupported file_type: {file_type!r}")
