"""Unit tests for the local pandas execution sandbox.

These run real subprocesses against real CSV files written to tmp_path — no
mocking of the executor. They assert correctness of the computed values, the
structured envelope shape, the privacy-safe summary, and that errors / timeouts
are returned as typed failures rather than crashing the parent.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from execution.sandbox import run_pandas


@pytest.fixture
def csv_path(tmp_path):
    p = tmp_path / "data.csv"
    p.write_text(
        "x,y,group\n"
        "1,10,a\n"
        "2,20,b\n"
        "3,30,a\n"
        "4,40,b\n"
        "5,50,a\n"
    )
    return str(p)


def test_scalar_sum(csv_path):
    res = run_pandas("result = df['x'].sum()", csv_path)
    assert res["ok"] is True
    assert res["kind"] == "scalar"
    assert res["payload"] == 15
    assert res["result_summary"] == {"kind": "scalar", "value": 15}
    assert "duration_ms" in res


def test_scalar_mean(csv_path):
    res = run_pandas("result = df['y'].mean()", csv_path)
    assert res["ok"] is True
    assert res["kind"] == "scalar"
    assert res["payload"] == pytest.approx(30.0)


def test_groupby_table(csv_path):
    res = run_pandas("result = df.groupby('group')['x'].sum()", csv_path)
    assert res["ok"] is True
    assert res["kind"] == "table"
    rows = {r["key"]: r["value"] for r in res["payload"]}
    assert rows == {"a": 9, "b": 6}  # a:1+3+5=9, b:2+4=6
    # privacy-safe summary carries shape, not extra raw rows
    assert res["result_summary"]["kind"] == "table"
    assert res["result_summary"]["row_count"] == 2
    assert res["result_summary"]["truncated"] is False


def test_dataframe_result(csv_path):
    res = run_pandas("result = df[df['x'] > 3]", csv_path)
    assert res["ok"] is True
    assert res["kind"] == "table"
    assert len(res["payload"]) == 2
    assert res["result_summary"]["columns"] == ["x", "y", "group"]
    assert res["result_summary"]["row_count"] == 2


def test_stdout_captured(csv_path):
    res = run_pandas("print('hello from sandbox')\nresult = 1", csv_path)
    assert res["ok"] is True
    assert "hello from sandbox" in res["stdout"]


def test_code_error_is_typed_failure(csv_path):
    res = run_pandas("result = df['does_not_exist'].sum()", csv_path)
    assert res["ok"] is False
    assert res["error_type"] == "KeyError"
    assert "does_not_exist" in res["error"]
    # the parent did not crash; we got a dict back


def test_missing_result_variable(csv_path):
    res = run_pandas("x = df['x'].sum()", csv_path)
    assert res["ok"] is False
    assert res["error_type"] == "NoResult"


def test_empty_code():
    res = run_pandas("   ", "/nonexistent.csv")
    assert res["ok"] is False
    assert res["error_type"] == "EmptyCode"


def test_missing_dataset():
    res = run_pandas("result = 1", "/no/such/file.csv")
    assert res["ok"] is False
    assert res["error_type"] == "MissingDataset"


def test_timeout_is_killed_within_limit(csv_path):
    start = time.monotonic()
    res = run_pandas("result = 1\nwhile True:\n    pass", csv_path, timeout_s=2.0)
    elapsed = time.monotonic() - start
    assert res["ok"] is False
    assert res["error_type"] == "Timeout"
    # killed promptly, not hanging forever
    assert elapsed < 8.0


def test_network_is_blocked(csv_path):
    code = (
        "import socket\n"
        "try:\n"
        "    socket.create_connection(('1.1.1.1', 80), timeout=2)\n"
        "    result = 'CONNECTED'\n"
        "except Exception as e:\n"
        "    result = 'BLOCKED'\n"
    )
    res = run_pandas(code, csv_path)
    assert res["ok"] is True
    assert res["payload"] == "BLOCKED"


def test_relative_dataset_path_survives_child_chdir(tmp_path, monkeypatch):
    """Regression: a RELATIVE dataset path (as data/storage.py stores) must
    still load after the child's _isolate_filesystem() chdir's away.

    Reproduces the live-run condition: the file is reachable via a relative path
    from the *caller's* cwd, but the child process chdir's into a private temp
    dir before pd.read_csv(path). run_pandas must resolve the path to absolute
    up-front so the read still works. Against the old relative-path behaviour
    the child would FileNotFound and this would return ok=False.
    """
    # Mirror storage.py's shape: ./data/datasets/<id>/<file>, all relative.
    rel_dir = Path("data/datasets/abc123")
    (tmp_path / rel_dir).mkdir(parents=True)
    (tmp_path / rel_dir / "sales.csv").write_text("x\n1\n2\n3\n")

    # Caller's cwd is tmp_path; the path passed in is purely relative and only
    # resolves from here — exactly the run-path the bug masked.
    monkeypatch.chdir(tmp_path)
    rel_path = os.path.join("data", "datasets", "abc123", "sales.csv")
    assert not os.path.isabs(rel_path)

    res = run_pandas("result = df['x'].sum()", rel_path)

    assert res["ok"] is True, res
    assert res["kind"] == "scalar"
    assert res["payload"] == 6


def test_summary_has_no_raw_rows_for_large_table(tmp_path):
    # A wide aggregation: summary must report shape, not embed all rows.
    rows = "n\n" + "\n".join(str(i) for i in range(5000))
    p = tmp_path / "big.csv"
    p.write_text(rows)
    res = run_pandas("result = df", str(p), timeout_s=30.0)
    assert res["ok"] is True
    summary = res["result_summary"]
    assert summary["row_count"] == 5000
    assert summary["truncated"] is True
    # the summary itself does not contain the 5000 raw values
    assert "payload" not in summary
