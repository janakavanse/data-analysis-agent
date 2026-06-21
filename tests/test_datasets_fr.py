"""FR-001 dataset management criteria — one test per EARS criterion.

Covers:
  1. Upload confirms name, row_count, column list
  2. List returns name, file_format, row_count, upload_timestamp
  3. Multiple datasets remain available for independent querying (cross-dataset access)
"""
import csv as csv_mod
import io
import json
import os
import tempfile

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage, ToolMessage

from src.server import app


# ---------------------------------------------------------------------------
# Client fixture
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _csv_bytes(rows: list[list]) -> bytes:
    buf = io.StringIO()
    csv_mod.writer(buf).writerows(rows)
    return buf.getvalue().encode()


def _tc(name: str, args: dict, tid: str):
    return {"id": tid, "name": name, "args": args, "type": "tool_call"}


def _tool_msgs(messages) -> list[ToolMessage]:
    return [m for m in messages if isinstance(m, ToolMessage)]


# ---------------------------------------------------------------------------
# Test 1 — Upload confirms name, row_count, column list
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upload_registers_with_row_count_and_columns(client):
    """WHEN user uploads CSV the system SHALL confirm name, row_count, column list."""
    # Create dataset
    r = (await client.post("/datasets", json={"name": "fr-sales"})).json()
    assert r["ok"], r
    ds_id = r["data"]["id"]

    csv_data = _csv_bytes([
        ["product", "price", "qty"],
        ["Widget", 9.99, 100],
        ["Gadget", 29.99, 50],
        ["Doohickey", 4.99, 200],
    ])
    files = {"file": ("sales.csv", csv_data, "text/csv")}
    resp = (await client.post(f"/datasets/{ds_id}/files", files=files)).json()

    assert resp["ok"], resp
    data = resp["data"]

    # row_count
    assert data["n_rows"] == 3, f"Expected 3 rows, got {data['n_rows']}"

    # column list present and correct
    col_names = {c["name"] for c in data["columns"]}
    assert {"product", "price", "qty"} == col_names, (
        f"Expected columns product/price/qty, got {col_names}")

    # filename echoed back
    assert data["filename"] == "sales.csv", f"Expected filename sales.csv, got {data['filename']!r}"


# ---------------------------------------------------------------------------
# Test 2 — GET /datasets returns file_format, row_count, upload_timestamp
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_datasets_returns_format_rowcount_timestamp(client):
    """WHEN user lists datasets the system SHALL return name, file_format, row_count, upload_timestamp."""
    # Create a fresh dataset and upload a file
    r = (await client.post("/datasets", json={"name": "fr-products"})).json()
    assert r["ok"], r
    ds_id = r["data"]["id"]

    csv_data = _csv_bytes([
        ["item", "cost"],
        ["Alpha", 10],
        ["Beta", 20],
    ])
    files = {"file": ("products.csv", csv_data, "text/csv")}
    up = (await client.post(f"/datasets/{ds_id}/files", files=files)).json()
    assert up["ok"], up

    # List datasets and find ours
    listing = (await client.get("/datasets")).json()
    assert listing["ok"], listing

    our_entry = next((d for d in listing["data"] if d["id"] == ds_id), None)
    assert our_entry is not None, f"Dataset {ds_id} not found in listing"

    # name
    assert our_entry["name"] == "fr-products"

    # file_format — derived from .csv extension
    assert our_entry["file_format"] == "csv", (
        f"Expected file_format='csv', got {our_entry['file_format']!r}")

    # row_count
    assert our_entry["row_count"] == 2, (
        f"Expected row_count=2, got {our_entry['row_count']}")

    # upload_timestamp — must be a non-empty ISO string
    ts = our_entry.get("upload_timestamp")
    assert ts is not None, "upload_timestamp must not be None after a file is uploaded"
    # Should parse as an ISO datetime without raising
    from datetime import datetime
    try:
        datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError as e:
        pytest.fail(f"upload_timestamp is not a valid ISO datetime: {ts!r} — {e}")


# ---------------------------------------------------------------------------
# Test 3 — Two datasets remain independently queryable (cross-dataset access)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cross_dataset_queries_without_reuploading(client):
    """WHILE session active, all uploaded datasets SHALL be available for cross-dataset queries.

    Simplified verification: upload two datasets, confirm both appear in GET /datasets
    with correct metadata, then run an agent query against each independently via
    a FakeModel that calls execute_sql and confirms results come from the right dataset.
    """
    from src.runner import run_agent

    # --- Dataset A: fruits ---
    r_a = (await client.post("/datasets", json={"name": "fr-fruits"})).json()
    ds_a = r_a["data"]["id"]
    csv_a = _csv_bytes([["fruit", "count"], ["apple", 10], ["banana", 5]])
    await client.post(f"/datasets/{ds_a}/files",
                      files={"file": ("fruits.csv", csv_a, "text/csv")})

    # --- Dataset B: veggies ---
    r_b = (await client.post("/datasets", json={"name": "fr-veggies"})).json()
    ds_b = r_b["data"]["id"]
    csv_b = _csv_bytes([["veggie", "count"], ["carrot", 30], ["broccoli", 20], ["spinach", 15]])
    await client.post(f"/datasets/{ds_b}/files",
                      files={"file": ("veggies.csv", csv_b, "text/csv")})

    # Both must appear in GET /datasets
    listing = (await client.get("/datasets")).json()
    ids_in_listing = {d["id"] for d in listing["data"]}
    assert ds_a in ids_in_listing, "Dataset A (fruits) missing from listing"
    assert ds_b in ids_in_listing, "Dataset B (veggies) missing from listing"

    # Confirm correct row counts for each
    entry_a = next(d for d in listing["data"] if d["id"] == ds_a)
    entry_b = next(d for d in listing["data"] if d["id"] == ds_b)
    assert entry_a["row_count"] == 2, f"Dataset A expected 2 rows, got {entry_a['row_count']}"
    assert entry_b["row_count"] == 3, f"Dataset B expected 3 rows, got {entry_b['row_count']}"

    # Query each dataset independently via FakeModel
    class FakeQueryModel:
        """Calls execute_sql against a given dataset_id and returns the row count."""

        def __init__(self, target_ds_id: str, sql: str):
            self._ds = target_ds_id
            self._sql = sql

        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            tms = _tool_msgs(messages)
            n = len(tms)
            if n == 0:
                return AIMessage(content="", tool_calls=[
                    _tc("execute_sql", {"dataset_id": self._ds, "sql": self._sql}, "t1")])
            data = json.loads(tms[-1].content) if tms else {}
            rows = data.get("rows", [])
            answer = f"count={rows[0][0]}" if rows else "no rows"
            return AIMessage(content="", tool_calls=[
                _tc("finish", {"answer": answer}, "t2")])

    # Query A — expect count of 2 fruit rows
    res_a = await run_agent(
        "How many fruit rows?",
        model=FakeQueryModel(ds_a, "SELECT COUNT(*) FROM fruits"),
    )
    assert res_a["status"] == "completed"
    assert "2" in res_a["answer"], (
        f"Expected count=2 from fruits dataset, got: {res_a['answer']!r}")

    # Query B — expect count of 3 veggie rows
    res_b = await run_agent(
        "How many veggie rows?",
        model=FakeQueryModel(ds_b, "SELECT COUNT(*) FROM veggies"),
    )
    assert res_b["status"] == "completed"
    assert "3" in res_b["answer"], (
        f"Expected count=3 from veggies dataset, got: {res_b['answer']!r}")
