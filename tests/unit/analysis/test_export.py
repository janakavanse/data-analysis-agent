"""Export execution tests — no LLM key required, pure local execution."""
import io

import openpyxl
import pandas as pd
import pytest

from analysis.export import (
    DatasetUnavailableError,
    NoDataframeResultError,
    export_query_result,
)


@pytest.fixture
def large_dataset_path(tmp_path):
    """A ≥5,000-row CSV fixture — large enough that a truncated (50-row
    capped) export would be observably wrong."""
    n = 6000
    df = pd.DataFrame(
        {
            "id": range(1, n + 1),
            "amount": [float(i) for i in range(1, n + 1)],
            "category": ["a" if i % 2 == 0 else "b" for i in range(1, n + 1)],
        }
    )
    path = tmp_path / "large.csv"
    df.to_csv(path, index=False)
    return str(path), df


def test_export_csv_returns_full_uncapped_rows(large_dataset_path):
    """Filters rows > 100 and exports — the exported file must contain
    exactly the independently-recomputed expected row count, not the
    50-row on-screen preview cap."""
    path, df = large_dataset_path
    expected_rows = (df["amount"] > 100).sum()
    assert expected_rows > 50  # sanity: this really exercises the uncapped path

    code = (
        "filtered = df[df['amount'] > 100]\n"
        "answer = f'{len(filtered)} rows matched.'\n"
        "table = filtered\n"
    )
    content, filename, content_type = export_query_result(code, path, "csv", "csv")

    assert filename == "export.csv"
    assert content_type == "text/csv"
    exported_df = pd.read_csv(io.BytesIO(content))
    assert len(exported_df) == expected_rows


def test_export_xlsx_returns_full_uncapped_rows(large_dataset_path):
    path, df = large_dataset_path
    expected_rows = (df["amount"] > 100).sum()

    code = (
        "filtered = df[df['amount'] > 100]\n"
        "answer = f'{len(filtered)} rows matched.'\n"
        "table = filtered\n"
    )
    content, filename, content_type = export_query_result(code, path, "csv", "xlsx")

    assert filename == "export.xlsx"
    assert "spreadsheet" in content_type
    workbook = openpyxl.load_workbook(io.BytesIO(content))
    sheet = workbook["Sheet1"]
    # rows minus header row
    assert sheet.max_row - 1 == expected_rows


def test_export_with_chart_generating_code_using_px_go(large_dataset_path):
    """Generated code that builds a plotly chart (using go/px, unused by
    export but referenced in the code) must not raise NameError on
    re-execution — export.py's restricted globals must expose go/px."""
    path, df = large_dataset_path
    expected_rows = (df["amount"] > 100).sum()

    code = (
        "filtered = df[df['amount'] > 100]\n"
        "answer = f'{len(filtered)} rows matched.'\n"
        "table = filtered\n"
        "chart = px.bar(filtered.groupby('category').size().reset_index(name='count'), "
        "x='category', y='count')\n"
        "fig2 = go.Figure()\n"
    )
    content, filename, content_type = export_query_result(code, path, "csv", "csv")

    assert filename == "export.csv"
    exported_df = pd.read_csv(io.BytesIO(content))
    assert len(exported_df) == expected_rows


def test_export_no_dataframe_result_raises(large_dataset_path):
    path, _df = large_dataset_path
    code = "answer = 'total is 42'\n"
    with pytest.raises(NoDataframeResultError):
        export_query_result(code, path, "csv", "csv")


def test_export_missing_dataset_file_raises(tmp_path):
    missing_path = str(tmp_path / "does-not-exist.csv")
    code = "table = df\nanswer = 'ok'\n"
    with pytest.raises(DatasetUnavailableError):
        export_query_result(code, missing_path, "csv", "csv")


def test_export_re_execution_failure_raises(large_dataset_path):
    path, _df = large_dataset_path
    code = "table = df['does_not_exist']\nanswer = 'ok'\n"
    with pytest.raises(DatasetUnavailableError):
        export_query_result(code, path, "csv", "csv")
