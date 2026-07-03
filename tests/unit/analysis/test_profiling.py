"""Profiling tests — pure pandas, no LLM key required."""
import pandas as pd
import pytest

from analysis.profiling import profile_dataframe


def test_profile_dataframe_basic_stats():
    df = pd.DataFrame(
        {
            "amount": [10.0, 20.0, None, 40.0],
            "category": ["food", "travel", "food", None],
            "id": [f"row-{i}" for i in range(4)],
        }
    )

    schema = profile_dataframe(df)

    assert schema.row_count == 4
    by_name = {c.name: c for c in schema.columns}

    amount = by_name["amount"]
    assert amount.dtype == "float64"
    assert amount.null_count == 1
    assert amount.min == 10.0
    assert amount.max == 40.0
    # numeric column stats are min/max, not a distinct sample
    assert amount.distinct_sample is None or len(amount.distinct_sample) <= 20

    category = by_name["category"]
    assert category.null_count == 1
    assert category.min is None
    assert category.max is None
    assert category.distinct_sample is not None
    assert set(category.distinct_sample) == {"food", "travel"}


def test_profile_dataframe_high_cardinality_column_has_no_sample():
    df = pd.DataFrame({"unique_id": [f"id-{i}" for i in range(50)]})

    schema = profile_dataframe(df)

    col = schema.columns[0]
    assert col.distinct_sample is None


def test_profile_dataframe_never_leaks_raw_rows():
    """The schema must never contain a distinctive cell value from a
    high-cardinality column — only aggregate stats."""
    df = pd.DataFrame(
        {
            "secret_note": [f"very-secret-value-{i}" for i in range(30)],
            "amount": list(range(30)),
        }
    )

    schema = profile_dataframe(df)
    dump = schema.model_dump_json()

    assert "very-secret-value-0" not in dump


def test_profile_dataframe_empty_raises_value_error():
    df = pd.DataFrame()
    with pytest.raises(ValueError):
        profile_dataframe(df)
