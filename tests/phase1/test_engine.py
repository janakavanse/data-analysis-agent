"""Phase 1 — analysis engine tests.

Run against REAL DuckDB on a LARGE (>=250k-row) CSV fixture, proving generated
code executes on the FULL dataset (not the <=20-row sample), that the privacy
boundary / denylist / timeout hold, and that errors are captured (never raised).
"""

import time

import pandas as pd
import pytest

from analysis import engine, storage

LARGE_ROWS = 250_000


@pytest.fixture
def isolated_data_dir(tmp_path, monkeypatch):
    """Point the engine's DuckDB + parquet at a fresh tmp dir per test."""
    monkeypatch.setenv("AGENT_DATA_DIR", str(tmp_path))
    storage.reset_connection()
    yield tmp_path
    storage.reset_connection()


@pytest.fixture
def large_csv(tmp_path):
    """A >=250k-row CSV whose FULL-data sum differs from any <=20-row sample sum.

    Column ``x`` ramps from 0..LARGE_ROWS-1 so the head(20) sum (0..19 = 190) is
    tiny compared with the true full sum — a sampled answer cannot match it.
    """
    path = tmp_path / "large.csv"
    df = pd.DataFrame(
        {
            "x": range(LARGE_ROWS),
            "category": [f"cat_{i % 5}" for i in range(LARGE_ROWS)],
            "amount": [1.5 for _ in range(LARGE_ROWS)],
        }
    )
    df.to_csv(path, index=False)
    return path, df


def test_ingest_extracts_schema_sample_rowcount(isolated_data_dir, large_csv):
    path, df = large_csv
    meta = engine.ingest_file(str(path), "large.csv", "big1")

    assert meta["row_count"] == LARGE_ROWS
    assert meta["duckdb_table"] == "ds_big1"
    assert meta["parquet_path"].endswith("big1.parquet")

    names = {c["name"] for c in meta["schema"]}
    assert names == {"x", "category", "amount"}

    # Sample is bounded to <= SAMPLE_ROWS and is JSON-safe dicts.
    assert len(meta["sample"]) <= engine.SAMPLE_ROWS == 20
    assert len(meta["sample"]) == 20
    assert all(isinstance(r, dict) for r in meta["sample"])


def test_execute_runs_on_full_dataset_not_sample(isolated_data_dir, large_csv):
    """The decisive test: the full-data sum must NOT equal the 20-row sample sum."""
    path, df = large_csv
    engine.ingest_file(str(path), "large.csv", "big2")

    full_sum_truth = int(df["x"].sum())  # 0+1+...+(N-1)
    sample_sum = int(df["x"].head(20).sum())  # 0+...+19 = 190
    assert full_sum_truth != sample_sum  # sanity: fixture is large enough

    out = engine.execute("result = df['x'].sum()", "big2")
    assert out["error"] is None, out["error"]
    assert out["result"]["scalar"] == full_sum_truth

    # And via DuckDB SQL on the full table (the preferred path for big data).
    out_sql = engine.execute(
        "result = con.execute(f'SELECT SUM(x) AS s FROM \"{table}\"').df()",
        "big2",
    )
    assert out_sql["error"] is None, out_sql["error"]
    assert out_sql["result"]["rows"][0][0] == full_sum_truth


def test_execute_captures_key_numbers(isolated_data_dir, large_csv):
    path, _ = large_csv
    engine.ingest_file(str(path), "large.csv", "kn")
    out = engine.execute(
        "total = df['amount'].sum()\nkey_numbers = {'total_amount': total}\nresult = total",
        "kn",
    )
    assert out["error"] is None, out["error"]
    assert out["key_numbers"]["total_amount"] == pytest.approx(LARGE_ROWS * 1.5)


def test_execute_error_is_captured_not_raised(isolated_data_dir, large_csv):
    path, _ = large_csv
    engine.ingest_file(str(path), "large.csv", "err")
    out = engine.execute("result = df['does_not_exist'].sum()", "err")
    assert out["error"] is not None
    assert "KeyError" in out["error"] or "does_not_exist" in out["error"]
    assert out["result"] is None  # degraded, not crashed


def test_denylist_rejects_os_import(isolated_data_dir, large_csv):
    path, _ = large_csv
    engine.ingest_file(str(path), "large.csv", "deny")
    out = engine.execute("import os\nresult = os.getcwd()", "deny")
    assert out["error"] is not None
    assert "guard" in out["error"].lower()
    assert out["result"] is None


@pytest.mark.parametrize("snippet", ["open('/etc/passwd')", "__import__('os')", "eval('1+1')"])
def test_denylist_rejects_dangerous_patterns(isolated_data_dir, large_csv, snippet):
    path, _ = large_csv
    engine.ingest_file(str(path), "large.csv", "deny2")
    out = engine.execute(f"result = {snippet}", "deny2")
    assert out["error"] is not None
    assert "guard" in out["error"].lower()


def test_make_llm_context_is_bounded(isolated_data_dir, large_csv):
    """The privacy redaction point returns only schema + <=20 sample + prior_result."""
    path, _ = large_csv
    engine.ingest_file(str(path), "large.csv", "ctx")
    ctx = engine.make_llm_context("ctx", prior_result={"columns": ["s"], "rows": [[1]]})

    assert set(ctx.keys()) == {"schema", "sample", "prior_result"}
    assert len(ctx["sample"]) <= engine.SAMPLE_ROWS
    assert ctx["prior_result"] == {"columns": ["s"], "rows": [[1]]}

    # No bulk rows leak: a value present only deep in the dataset (x == 200000)
    # must NOT appear anywhere in the serialized context.
    import json

    serialized = json.dumps(ctx)
    assert "200000" not in serialized
    assert len(serialized.encode("utf-8")) < 10_000  # bounded regardless of data size


def test_result_truncated_to_max_rows(isolated_data_dir, large_csv):
    path, _ = large_csv
    engine.ingest_file(str(path), "large.csv", "trunc")
    # group by produces 5 rows here, but ask for raw rows to test the row cap.
    out = engine.execute("result = df[['x']]", "trunc")
    assert out["error"] is None, out["error"]
    assert len(out["result"]["rows"]) <= engine.MAX_RESULT_ROWS == 200


def test_unsupported_file_raises_badfile(isolated_data_dir, tmp_path):
    bad = tmp_path / "data.json"
    bad.write_text('{"a": 1}')
    with pytest.raises(engine.BadFileError):
        engine.ingest_file(str(bad), "data.json", "bad")


def test_empty_file_raises_badfile(isolated_data_dir, tmp_path):
    empty = tmp_path / "empty.csv"
    empty.write_text("")
    with pytest.raises(engine.BadFileError):
        engine.ingest_file(str(empty), "empty.csv", "empty")


def test_execute_timeout(isolated_data_dir, large_csv):
    """A pathological snippet is bounded by the wall-clock deadline (captured)."""
    path, _ = large_csv
    engine.ingest_file(str(path), "large.csv", "to")
    # Temporarily shrink the deadline so the test is fast.
    original = engine.EXEC_TIMEOUT_S
    engine.EXEC_TIMEOUT_S = 1
    try:
        start = time.monotonic()
        out = engine.execute("while True:\n    pass\nresult = 1", "to")
        elapsed = time.monotonic() - start
    finally:
        engine.EXEC_TIMEOUT_S = original
    assert out["error"] is not None
    assert "timed out" in out["error"].lower()
    assert elapsed < 5  # bounded by the 1s deadline, not hung
