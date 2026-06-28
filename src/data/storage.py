"""Local file storage for uploaded dataset bytes.

Privacy boundary: raw file bytes live ONLY on local disk under the datasets
directory. Nothing here touches the network or any LLM-bound payload.
"""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4


def _datasets_root() -> Path:
    """Root directory for stored dataset bytes (env-overridable for tests)."""
    root = os.environ.get("AGENT_DATASETS_DIR", "./data/datasets")
    return Path(root)


def save_upload(file_bytes: bytes, filename: str, dataset_id: str | None = None) -> tuple[str, str]:
    """Persist uploaded bytes to local disk.

    Layout: <datasets_root>/<dataset_id>/<filename>

    Returns (dataset_id, storage_path). The storage_path is what the Dataset
    record stores; it is never sent to the LLM.
    """
    ds_id = dataset_id or str(uuid4())
    safe_name = Path(filename).name or "upload.csv"
    target_dir = _datasets_root() / ds_id
    target_dir.mkdir(parents=True, exist_ok=True)
    storage_path = target_dir / safe_name
    storage_path.write_bytes(file_bytes)
    return ds_id, str(storage_path)


def resolve_path(storage_path: str) -> Path:
    """Resolve a stored path for later local execution.

    Raises FileNotFoundError if the stored bytes are missing.
    """
    path = Path(storage_path)
    if not path.is_file():
        raise FileNotFoundError(f"stored dataset bytes not found: {storage_path}")
    return path


def resolve_dataset_dir(dataset_id: str) -> Path:
    """Return the directory holding a dataset's bytes."""
    return _datasets_root() / dataset_id
