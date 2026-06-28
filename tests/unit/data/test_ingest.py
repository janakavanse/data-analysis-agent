import pytest

from data import ingest
from data.ingest import (
    DatasetParseError,
    DatasetTooLargeError,
    MAX_UPLOAD_BYTES,
)


def _write_csv(tmp_path, content: str, name: str = "d.csv"):
    p = tmp_path / name
    p.write_text(content)
    return p


def test_load_csv_infers_dtypes_and_rows(tmp_path):
    p = _write_csv(tmp_path, "revenue,region\n10.5,west\n20.0,east\n30.0,west\n")
    df = ingest.load_csv(p)
    assert ingest.row_count(df) == 3
    assert list(df.columns) == ["revenue", "region"]
    assert str(df["revenue"].dtype) == "float64"
    # pandas infers a string dtype for text columns (object on <3.0, str on 3.0+)
    assert str(df["region"].dtype) in ("object", "str")


def test_load_csv_missing_file_raises_parse_error(tmp_path):
    with pytest.raises(DatasetParseError):
        ingest.load_csv(tmp_path / "nope.csv")


def test_load_csv_empty_raises_parse_error(tmp_path):
    p = _write_csv(tmp_path, "")
    with pytest.raises(DatasetParseError):
        ingest.load_csv(p)


def test_load_csv_bad_csv_raises_parse_error(tmp_path):
    # Ragged rows with an embedded unbalanced quote -> parser error.
    p = _write_csv(tmp_path, 'a,b\n"unterminated,1\n2,3,4,5,6\n')
    with pytest.raises(DatasetParseError):
        ingest.load_csv(p)


def test_check_size_over_cap_raises():
    with pytest.raises(DatasetTooLargeError):
        ingest.check_size(MAX_UPLOAD_BYTES + 1)


def test_check_size_at_cap_ok():
    ingest.check_size(MAX_UPLOAD_BYTES)  # no raise


def test_load_csv_over_cap_raises(tmp_path):
    # Create a sparse file just over the cap without writing 100MB of data.
    p = tmp_path / "big.csv"
    with open(p, "wb") as fh:
        fh.write(b"a,b\n1,2\n")
        fh.truncate(MAX_UPLOAD_BYTES + 1)
    assert p.stat().st_size == MAX_UPLOAD_BYTES + 1
    with pytest.raises(DatasetTooLargeError):
        ingest.load_csv(p)
