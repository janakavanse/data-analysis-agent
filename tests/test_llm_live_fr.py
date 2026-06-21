"""FR-001 Iteration 9 gate — real LLM integration (skipped if no API key).

These tests require ANALYST_LLM_API_KEY to be set.
"""
import json
import os
import pytest
import tempfile
from src.config import get_settings

_NEEDS_KEY = pytest.mark.skipif(
    not get_settings().llm_api_key,
    reason="no ANALYST_LLM_API_KEY — real-run tests skipped in stub mode"
)


@_NEEDS_KEY
@pytest.mark.asyncio
async def test_real_llm_query_returns_answer():
    """WHEN user sends NL question with real LLM, system SHALL return answer within 30s."""
    import time
    from src.runner import run_agent
    from httpx import AsyncClient, ASGITransport
    from src.server import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        ds_id = (await c.post("/datasets", json={"name": "live_test"})).json()["data"]["id"]
        csv_data = "product,sales\nApples,150\nBananas,200\nCherries,75\n"
        files = {"file": ("sales.csv", csv_data, "text/csv")}
        await c.post(f"/datasets/{ds_id}/files", files=files)

    start = time.time()
    from src.llm import get_model
    model = get_model()
    result = await run_agent(
        goal="What is the total sales across all products?",
        dataset_id=ds_id,
        model=model,
    )
    elapsed = time.time() - start

    assert result["status"] == "completed", result.get("answer")
    assert result["answer"], "answer should not be empty"
    assert elapsed < 30, f"took {elapsed:.1f}s — exceeds 30s limit"


@pytest.mark.asyncio
async def test_large_file_warning_returned_by_execute_sql_tool():
    """WHEN SQL would scan file > 100 MB, execute_sql SHALL return LARGE_FILE_WARNING."""
    from src.tools import execute_sql
    from unittest.mock import patch

    # Mock at src.tools level since that is where os is imported
    with patch("src.tools.duck.dataset_path", return_value="/fake/path.duckdb"):
        with patch("src.tools.os.path.getsize", return_value=110 * 1024 * 1024):
            with patch("src.tools.os.path.exists", return_value=True):
                result = execute_sql.invoke({
                    "dataset_id": "fake_id",
                    "sql": "SELECT * FROM t",
                    "confirmed_large": False
                })

    assert "LARGE_FILE_WARNING" in result or "warning" in result.lower()


@pytest.mark.asyncio
async def test_large_file_proceeds_with_confirmed():
    """IF user confirms, execute_sql with confirmed_large=True SHALL proceed past the warning."""
    import duckdb
    from src.tools import execute_sql
    from unittest.mock import patch
    from src import duck

    # Create a real small DuckDB file with actual data
    with tempfile.TemporaryDirectory() as td:
        db_path = os.path.join(td, "fake_id.duckdb")
        con = duckdb.connect(db_path)
        con.execute("CREATE TABLE t AS SELECT 1 as x")
        con.close()

        with patch.object(duck, "dataset_path", return_value=db_path):
            with patch("src.tools.os.path.getsize", return_value=110 * 1024 * 1024):
                result = execute_sql.invoke({
                    "dataset_id": "fake_id",
                    "sql": "SELECT x FROM t",
                    "confirmed_large": True   # user confirmed
                })

    # Should get actual rows, not a warning
    assert "LARGE_FILE_WARNING" not in result
    parsed = json.loads(result)
    assert "rows" in parsed
