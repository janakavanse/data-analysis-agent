"""Sandbox execution tests — no LLM key required, pure local execution."""
import pandas as pd
import pytest

from analysis.sandbox import SandboxExecutionError, execute_generated_code


@pytest.fixture
def dataset_path(tmp_path):
    df = pd.DataFrame({"amount": [10, 20, 30, 40], "category": ["a", "b", "a", "b"]})
    path = tmp_path / "data.csv"
    df.to_csv(path, index=False)
    return str(path)


def test_valid_code_produces_answer_and_table(dataset_path):
    code = (
        "mean_amount = df['amount'].mean()\n"
        "answer = f'The average amount is {mean_amount}.'\n"
        "table = df.groupby('category', as_index=False)['amount'].mean()\n"
    )
    result = execute_generated_code(code, dataset_path, "csv")

    assert "25.0" in result["answer"]
    assert result["table"] is not None
    assert len(result["table"]) == 2
    assert all(isinstance(row["amount"], (int, float)) for row in result["table"])


def test_import_os_is_blocked(dataset_path):
    code = "import os\nanswer = 'should not get here'\n"
    with pytest.raises(SandboxExecutionError):
        execute_generated_code(code, dataset_path, "csv")


def test_open_builtin_is_blocked(dataset_path):
    code = "f = open('nope.txt', 'w')\nanswer = 'should not get here'\n"
    with pytest.raises(SandboxExecutionError):
        execute_generated_code(code, dataset_path, "csv")


def test_buggy_code_raises_concise_error(dataset_path):
    code = "answer = str(df['does_not_exist'].mean())\n"
    with pytest.raises(SandboxExecutionError) as exc_info:
        execute_generated_code(code, dataset_path, "csv")
    assert len(str(exc_info.value)) < 400


def test_missing_answer_variable_raises(dataset_path):
    code = "x = df['amount'].mean()\n"
    with pytest.raises(SandboxExecutionError, match="did not produce an 'answer'"):
        execute_generated_code(code, dataset_path, "csv")


def test_infinite_loop_times_out(dataset_path):
    code = "while True:\n    pass\n"
    with pytest.raises(SandboxExecutionError, match="timed out"):
        execute_generated_code(code, dataset_path, "csv", timeout_seconds=1)
