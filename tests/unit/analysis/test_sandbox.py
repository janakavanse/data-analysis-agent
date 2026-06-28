"""Unit tests for the restricted pandas sandbox (`run_pandas`).

Pure unit — no LLM. Verifies the result_repr shape, JSON-safety, and that the
privacy/security restrictions (imports, file access, dunder escapes) are
enforced.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from src.analysis.sandbox import SandboxError, run_pandas


@pytest.fixture
def df():
    return pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0], "g": ["a", "a", "b", "b"]})


def test_scalar_result(df):
    repr_ = run_pandas("result = df['x'].mean()", df)
    assert repr_["kind"] == "scalar"
    assert repr_["value"] == pytest.approx(2.5)
    json.dumps(repr_)  # must not raise


def test_scalar_is_native_not_numpy(df):
    repr_ = run_pandas("result = df['x'].sum()", df)
    assert isinstance(repr_["value"], (int, float))
    assert not type(repr_["value"]).__module__.startswith("numpy")


def test_dataframe_result_is_table(df):
    code = "result = df.groupby('g')['x'].mean().reset_index()"
    repr_ = run_pandas(code, df)
    assert repr_["kind"] == "table"
    assert repr_["columns"] == ["g", "x"]
    assert len(repr_["rows"]) == 2
    json.dumps(repr_)


def test_series_result_is_table(df):
    repr_ = run_pandas("result = df.groupby('g')['x'].sum()", df)
    assert repr_["kind"] == "table"
    # index column + value column
    assert len(repr_["columns"]) == 2
    assert len(repr_["rows"]) == 2
    json.dumps(repr_)


def test_result_repr_json_safe_with_nan(df):
    # max of an empty selection -> NaN scalar must serialize to None
    code = "result = df[df['x'] > 100]['x'].max()"
    repr_ = run_pandas(code, df)
    assert repr_["kind"] == "scalar"
    assert repr_["value"] is None
    assert "NaN" not in json.dumps(repr_)


def test_import_os_blocked(df):
    with pytest.raises(SandboxError):
        run_pandas("import os\nresult = os.getcwd()", df)


def test_open_file_blocked(df):
    with pytest.raises(SandboxError):
        run_pandas("result = open('/etc/passwd').read()", df)


def test_dunder_escape_blocked(df):
    with pytest.raises(SandboxError):
        run_pandas("result = ().__class__.__bases__", df)


def test_eval_blocked(df):
    with pytest.raises(SandboxError):
        run_pandas("result = eval('1+1')", df)


def test_missing_result_raises(df):
    with pytest.raises(SandboxError):
        run_pandas("y = df['x'].mean()", df)


def test_exec_error_message_preserved(df):
    with pytest.raises(SandboxError) as exc:
        run_pandas("result = df['nonexistent_col'].mean()", df)
    # The original error text must be readable for the repair loop.
    assert "nonexistent_col" in str(exc.value)


def test_safe_builtins_available(df):
    repr_ = run_pandas("result = len(df)", df)
    assert repr_ == {"kind": "scalar", "value": 4}


def test_df_not_mutated_across_calls(df):
    before = df.copy()
    run_pandas("result = df.sort_values('x', ascending=False).head(1)", df)
    pd.testing.assert_frame_equal(df, before)
