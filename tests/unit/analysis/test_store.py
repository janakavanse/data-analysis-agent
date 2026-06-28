"""Unit tests for the in-process DataFrame store + privacy-safe extraction."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from src.analysis import store


@pytest.fixture
def csv_path(tmp_path):
    """A tiny CSV with a numeric col, a string col, and one NaN cell."""
    p = tmp_path / "tiny.csv"
    p.write_text(
        "x,label\n"
        "1,a\n"
        "2,b\n"
        ",c\n"          # NaN in x
        "4,d\n"
        "5,e\n"
        "6,f\n"
    )
    return str(p)


def test_load_dataframe_reads_csv(csv_path):
    df = store.load_dataframe(csv_path, "csv")
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["x", "label"]
    assert len(df) == 6


def test_load_dataframe_rejects_non_csv(csv_path):
    with pytest.raises(ValueError):
        store.load_dataframe(csv_path, "xlsx")


def test_extract_schema_dtypes(csv_path):
    df = store.load_dataframe(csv_path)
    schema = store.extract_schema(df)
    assert {s["name"] for s in schema} == {"x", "label"}
    by_name = {s["name"]: s["dtype"] for s in schema}
    # x has a NaN -> pandas reads it as float
    assert "float" in by_name["x"]
    assert "object" in by_name["label"] or "str" in by_name["label"]


def test_extract_sample_length_and_json_safe(csv_path):
    df = store.load_dataframe(csv_path)
    sample = store.extract_sample(df, n=3)
    assert len(sample) == 3
    # Must be json.dumps-able (no NaN, no numpy types)
    dumped = json.dumps(sample)
    assert isinstance(dumped, str)


def test_extract_sample_nan_becomes_null(csv_path):
    df = store.load_dataframe(csv_path)
    sample = store.extract_sample(df, n=5)
    # Row index 2 (0-based) has the empty x -> must serialize to None, not NaN
    assert sample[2]["x"] is None
    # And json.dumps emits literal null
    assert "NaN" not in json.dumps(sample)
    assert "null" in json.dumps(sample)


def test_extract_sample_defaults_to_five(csv_path):
    df = store.load_dataframe(csv_path)
    assert len(store.extract_sample(df)) == 5


def test_row_count(csv_path):
    df = store.load_dataframe(csv_path)
    assert store.row_count(df) == 6
    assert isinstance(store.row_count(df), int)


def test_register_and_get(csv_path):
    df = store.load_dataframe(csv_path)
    store.register("sess-1", df)
    got = store.get_dataframe("sess-1")
    assert got is df


def test_get_dataframe_missing_raises():
    with pytest.raises(store.DataFrameNotLoadedError):
        store.get_dataframe("does-not-exist-xyz")


def test_ensure_loaded_lazy_reload(csv_path):
    # Simulate a fresh process: nothing registered for this session.
    sid = "reload-sess"
    store._REGISTRY.pop(sid, None)
    df = store.ensure_loaded(sid, csv_path, "csv")
    assert isinstance(df, pd.DataFrame)
    # Now it is registered and the same object is returned.
    assert store.get_dataframe(sid) is df
    again = store.ensure_loaded(sid, csv_path, "csv")
    assert again is df
