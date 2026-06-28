import json

import pandas as pd

from data import ingest, profile

CSV = (
    "revenue,region,units\n"
    "10.0,west,3\n"
    "20.0,east,\n"          # missing units
    "30.0,west,5\n"
    ",south,2\n"            # missing revenue
)


def _frame(tmp_path):
    p = tmp_path / "d.csv"
    p.write_text(CSV)
    return ingest.load_csv(p)


def test_profile_shape_and_columns(tmp_path):
    df = _frame(tmp_path)
    prof = profile.build_profile(df)
    assert set(prof.keys()) == {"columns"}
    names = [c["name"] for c in prof["columns"]]
    assert names == ["revenue", "region", "units"]
    for col in prof["columns"]:
        assert set(col.keys()) == {
            "name", "dtype", "missing", "distinct", "min", "max", "mean",
        }


def test_numeric_stats(tmp_path):
    df = _frame(tmp_path)
    cols = {c["name"]: c for c in profile.build_profile(df)["columns"]}

    rev = cols["revenue"]
    assert rev["missing"] == 1
    assert rev["min"] == 10.0
    assert rev["max"] == 30.0
    assert rev["mean"] == 20.0
    assert rev["distinct"] == 3

    units = cols["units"]
    assert units["missing"] == 1


def test_non_numeric_stats_are_null(tmp_path):
    df = _frame(tmp_path)
    cols = {c["name"]: c for c in profile.build_profile(df)["columns"]}
    region = cols["region"]
    assert region["min"] is None
    assert region["max"] is None
    assert region["mean"] is None
    assert region["missing"] == 0
    assert region["distinct"] == 3  # west, east, south


def test_json_serializable(tmp_path):
    df = _frame(tmp_path)
    prof = profile.build_profile(df)
    # Must round-trip through JSON (no numpy scalars / NaN leaking through).
    dumped = json.dumps(prof)
    assert json.loads(dumped) == prof


def test_profile_contains_no_raw_cell_values(tmp_path):
    """PRIVACY INVARIANT: the profile must not embed any raw row/cell value."""
    df = _frame(tmp_path)
    prof = profile.build_profile(df)
    blob = json.dumps(prof)

    # No raw categorical cell values may appear.
    for raw in ["west", "east", "south"]:
        assert raw not in blob

    # Min/max are aggregates and legitimately appear; but no full set of
    # individual numeric records should be present. Verify by checking a value
    # that is neither min/max/mean nor a count is absent.
    # revenue values: 10,20,30 -> 20 is the mean (allowed). Inject a distinct
    # interior value into a fresh frame and confirm it does not surface.
    df2 = pd.DataFrame({"x": [1.0, 7.0, 100.0]})  # mean ~36, no value == 7 except raw
    prof2 = profile.build_profile(df2)
    blob2 = json.dumps(prof2)
    assert "7.0" not in blob2 and '"7"' not in blob2

    # The profile must not carry any list of per-row data.
    for col in prof["columns"]:
        for value in col.values():
            assert not isinstance(value, (list, dict)), (
                "profile entries must be flat aggregates, not collections of rows"
            )


def test_empty_numeric_column_stats_none(tmp_path):
    df = pd.DataFrame({"all_null": pd.Series([None, None], dtype="float64")})
    cols = profile.build_profile(df)["columns"]
    assert cols[0]["min"] is None
    assert cols[0]["max"] is None
    assert cols[0]["mean"] is None
    assert cols[0]["missing"] == 2
