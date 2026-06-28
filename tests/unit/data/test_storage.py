from pathlib import Path

import pytest

from data import storage


@pytest.fixture(autouse=True)
def _isolated_datasets_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DATASETS_DIR", str(tmp_path / "datasets"))
    yield


def test_save_upload_writes_bytes_and_returns_path():
    raw = b"a,b\n1,2\n"
    ds_id, path = storage.save_upload(raw, "sales.csv")
    assert ds_id
    p = Path(path)
    assert p.is_file()
    assert p.read_bytes() == raw
    # layout: <root>/<dataset_id>/<filename>
    assert p.name == "sales.csv"
    assert p.parent.name == ds_id


def test_save_upload_uses_provided_dataset_id():
    ds_id, path = storage.save_upload(b"x\n1\n", "f.csv", dataset_id="fixed-id")
    assert ds_id == "fixed-id"
    assert Path(path).parent.name == "fixed-id"


def test_save_upload_sanitizes_filename():
    _, path = storage.save_upload(b"x\n1\n", "../../evil.csv")
    assert Path(path).name == "evil.csv"


def test_resolve_path_returns_existing_file():
    _, path = storage.save_upload(b"x\n1\n", "f.csv")
    resolved = storage.resolve_path(path)
    assert resolved.is_file()


def test_resolve_path_missing_raises():
    with pytest.raises(FileNotFoundError):
        storage.resolve_path("/no/such/file.csv")
