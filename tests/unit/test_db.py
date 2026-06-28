"""DB layer tests — no LLM key required."""
from sqlalchemy.orm import Session
from db.models import Dataset


def _make_dataset(**kwargs) -> Dataset:
    defaults = dict(
        name="sales.csv",
        kind="csv",
        storage_path="/data/sales.csv",
        size_bytes=1024,
    )
    defaults.update(kwargs)
    return Dataset(**defaults)


def test_dataset_roundtrip(_isolated_db):
    with Session(_isolated_db) as s:
        ds = _make_dataset(name="hello world")
        s.add(ds)
        s.commit()
        ds_id = ds.id

    with Session(_isolated_db) as s:
        fetched = s.get(Dataset, ds_id)
        assert fetched is not None
        assert fetched.name == "hello world"
        assert fetched.kind == "csv"
        assert fetched.size_bytes == 1024
        assert fetched.row_count is None
        assert fetched.created_at is not None


def test_dataset_update(_isolated_db):
    with Session(_isolated_db) as s:
        ds = _make_dataset()
        s.add(ds)
        s.commit()
        ds_id = ds.id

    with Session(_isolated_db) as s:
        ds = s.get(Dataset, ds_id)
        ds.row_count = 500
        s.commit()

    with Session(_isolated_db) as s:
        ds = s.get(Dataset, ds_id)
        assert ds.row_count == 500


def test_multiple_datasets_independent(_isolated_db):
    with Session(_isolated_db) as s:
        for i in range(3):
            s.add(_make_dataset(name=f"file {i}"))
        s.commit()
        rows = s.query(Dataset).all()
        ids = [r.id for r in rows]

    assert len(ids) == 3
    assert len(set(ids)) == 3  # all unique
