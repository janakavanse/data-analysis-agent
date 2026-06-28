"""DB layer tests — no LLM key required.

Exercises the Phase-1 written tables (DatasetRow, RunRow) against the isolated
in-memory/tmp sqlite engine from conftest. No LLM, no network.
"""
from sqlalchemy.orm import Session

from db.models import DatasetRow, RunRow


def _make_dataset(**overrides) -> DatasetRow:
    fields = dict(
        name="sales.csv",
        storage_path="/data/sales.csv",
        parquet_path="/data/sales.parquet",
        duckdb_table="ds_sales",
        schema_json=[{"name": "amount", "type": "DOUBLE"}],
        sample_json=[{"amount": 1.0}],
        row_count=42,
    )
    fields.update(overrides)
    return DatasetRow(**fields)


def test_dataset_row_roundtrip(_isolated_db):
    with Session(_isolated_db) as s:
        ds = _make_dataset()
        s.add(ds)
        s.commit()
        dataset_id = ds.id

    with Session(_isolated_db) as s:
        fetched = s.get(DatasetRow, dataset_id)
        assert fetched is not None
        assert fetched.name == "sales.csv"
        assert fetched.duckdb_table == "ds_sales"
        assert fetched.row_count == 42
        assert fetched.schema_json == [{"name": "amount", "type": "DOUBLE"}]
        assert fetched.sample_json == [{"amount": 1.0}]
        # Phase-2 stub columns default to None / unset in Phase 1
        assert fetched.profile_json is None
        assert fetched.session_id is None
        assert fetched.created_at is not None


def test_run_row_roundtrip_with_defaults(_isolated_db):
    with Session(_isolated_db) as s:
        ds = _make_dataset()
        s.add(ds)
        s.commit()
        dataset_id = ds.id

        run = RunRow(dataset_id=dataset_id, question="What is the total amount?")
        s.add(run)
        s.commit()
        run_id = run.id

    with Session(_isolated_db) as s:
        fetched = s.get(RunRow, run_id)
        assert fetched is not None
        assert fetched.dataset_id == dataset_id
        assert fetched.question == "What is the total amount?"
        # column defaults applied on insert
        assert fetched.stage == "planning"
        assert fetched.status == "running"
        assert fetched.flagged is False
        assert fetched.tokens_in == 0
        assert fetched.tokens_out == 0
        assert fetched.cost_estimate == 0.0
        assert fetched.revisions == 0
        assert fetched.llm_payload_json == {}
        # nullable result columns unset until the run completes
        assert fetched.code is None
        assert fetched.answer is None
        assert fetched.result_json is None
        assert fetched.completed_at is None
        assert fetched.started_at is not None


def test_run_row_completion_update(_isolated_db):
    with Session(_isolated_db) as s:
        ds = _make_dataset()
        s.add(ds)
        s.commit()
        run = RunRow(dataset_id=ds.id, question="sum?")
        s.add(run)
        s.commit()
        run_id = run.id

    with Session(_isolated_db) as s:
        run = s.get(RunRow, run_id)
        run.code = "df['amount'].sum()"
        run.result_json = {"total": 99.5}
        run.key_numbers_json = {"total": 99.5}
        run.chart_spec_json = {"type": "bar"}
        run.answer = "The total is 99.5"
        run.tokens_in = 120
        run.tokens_out = 45
        run.cost_estimate = 0.0012
        run.stage = "finalize"
        run.status = "completed"
        s.commit()

    with Session(_isolated_db) as s:
        run = s.get(RunRow, run_id)
        assert run.status == "completed"
        assert run.stage == "finalize"
        assert run.code == "df['amount'].sum()"
        assert run.result_json == {"total": 99.5}
        assert run.chart_spec_json == {"type": "bar"}
        assert run.answer == "The total is 99.5"
        assert run.tokens_in == 120
        assert run.tokens_out == 45
        assert run.cost_estimate == 0.0012


def test_multiple_runs_have_unique_ids(_isolated_db):
    with Session(_isolated_db) as s:
        ds = _make_dataset()
        s.add(ds)
        s.commit()
        dataset_id = ds.id
        for i in range(3):
            s.add(RunRow(dataset_id=dataset_id, question=f"q {i}"))
        s.commit()
        runs = s.query(RunRow).all()
        ids = [r.id for r in runs]

    assert len(ids) == 3
    assert len(set(ids)) == 3  # all unique
