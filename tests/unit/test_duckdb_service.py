"""Tests for DuckDBService: CSV registration, SELECT, deregister, Excel path."""
import csv
import pytest
from pathlib import Path


def _write_csv(path: Path, rows: int = 5) -> Path:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "name", "value", "flag", "ts"])
        writer.writeheader()
        for i in range(rows):
            writer.writerow({"id": i, "name": f"item_{i}", "value": i * 1.5, "flag": i % 2 == 0, "ts": f"2024-01-0{i+1}"})
    return path


class _FakeDataset:
    """Minimal stand-in for a Dataset ORM row."""
    def __init__(self, table_name: str, file_path: str):
        self.table_name = table_name
        self.file_path = file_path


def test_register_and_query_csv(isolated_duckdb, tmp_path):
    csv_path = _write_csv(tmp_path / "sales.csv", rows=5)
    ds = _FakeDataset("sales", str(csv_path))
    isolated_duckdb.register_dataset(ds)

    result = isolated_duckdb.execute_query("SELECT COUNT(*) AS cnt FROM sales")
    assert result[0]["cnt"] == 5


def test_execute_query_returns_list_of_dicts(isolated_duckdb, tmp_path):
    csv_path = _write_csv(tmp_path / "data.csv", rows=3)
    ds = _FakeDataset("data_tbl", str(csv_path))
    isolated_duckdb.register_dataset(ds)

    rows = isolated_duckdb.execute_query("SELECT * FROM data_tbl")
    assert isinstance(rows, list)
    assert len(rows) == 3
    assert "id" in rows[0]
    assert "name" in rows[0]


def test_deregister_then_query_raises(isolated_duckdb, tmp_path):
    csv_path = _write_csv(tmp_path / "temp.csv")
    ds = _FakeDataset("temp_view", str(csv_path))
    isolated_duckdb.register_dataset(ds)

    # Confirm it works first
    result = isolated_duckdb.execute_query("SELECT COUNT(*) AS n FROM temp_view")
    assert result[0]["n"] == 5

    isolated_duckdb.deregister_dataset("temp_view")

    with pytest.raises(Exception):
        isolated_duckdb.execute_query("SELECT * FROM temp_view")


def test_excel_csv_path(isolated_duckdb, tmp_path):
    """Excel workflow: convert .xlsx to .csv, register the CSV path."""
    import openpyxl
    import pandas as pd

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["product", "revenue", "qty"])
    ws.append(["Widget A", 100.0, 10])
    ws.append(["Widget B", 200.0, 20])
    xlsx_path = tmp_path / "sales.xlsx"
    wb.save(str(xlsx_path))

    # Mimic what the upload endpoint does: convert to CSV
    df = pd.read_excel(xlsx_path, sheet_name=0, engine="openpyxl")
    csv_path = tmp_path / "sales.csv"
    df.to_csv(csv_path, index=False)

    ds = _FakeDataset("excel_sales", str(csv_path))
    isolated_duckdb.register_dataset(ds)

    rows = isolated_duckdb.execute_query("SELECT * FROM excel_sales")
    assert len(rows) == 2
    assert rows[0]["product"] == "Widget A"


def test_list_tables(isolated_duckdb, tmp_path):
    csv_path = _write_csv(tmp_path / "things.csv", rows=2)
    ds = _FakeDataset("things", str(csv_path))
    isolated_duckdb.register_dataset(ds)

    tables = isolated_duckdb.list_tables()
    assert "things" in tables


def test_describe_table(isolated_duckdb, tmp_path):
    csv_path = _write_csv(tmp_path / "desc_test.csv", rows=1)
    ds = _FakeDataset("desc_test", str(csv_path))
    isolated_duckdb.register_dataset(ds)

    info = isolated_duckdb.describe_table("desc_test")
    assert isinstance(info, list)
    assert len(info) > 0
    # First column in the DuckDB DESCRIBE result is the column name
    col_names = [row.get("column_name") or row.get("Field") or list(row.values())[0] for row in info]
    assert "id" in col_names


def test_get_sample_rows(isolated_duckdb, tmp_path):
    csv_path = _write_csv(tmp_path / "sample_test.csv", rows=10)
    ds = _FakeDataset("sample_test", str(csv_path))
    isolated_duckdb.register_dataset(ds)

    sample = isolated_duckdb.get_sample_rows("sample_test", n=3)
    assert len(sample) == 3


def test_health_check(isolated_duckdb):
    assert isolated_duckdb.health_check() is True
