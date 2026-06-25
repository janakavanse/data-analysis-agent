"""Unit tests for the session-scoped pool with the dataset/two-level model: grouped snapshot,
(dataset, capability) routing, dataset-namespaced tables, reuse, LRU eviction, cleanup. Datasets
are stubbed (no DB) by patching ``_load_datasets``; the MCP servers + DuckDB are exercised for real."""
import asyncio

import pandas as pd
import pytest

import data_analysis_agent.tools.mcp.pool as pool_module
from data_analysis_agent.tools.mcp.pool import SessionPoolManager


def _dataset(tmp_path, name, tables_spec):
    """Build a (dataset_dict, tables_dicts) pair with real Parquet files."""
    tables = []
    for table_name, frame in tables_spec.items():
        pq = tmp_path / f"{name}__{table_name}.parquet"
        pd.DataFrame(frame).to_parquet(pq)
        tables.append({
            "table_name": table_name,
            "parquet_path": str(pq),
            "column_names": list(frame.keys()),
            "capability_description": f"Query {table_name}",
        })
    dataset = {"id": name, "name": name, "type": "parquet", "tool_description": f"Dataset {name}"}
    return dataset, tables


@pytest.fixture
def patch_datasets(monkeypatch):
    """Return a mutable {session_id: [(dataset, tables), ...]} map, bypassing the DB."""
    mapping: dict[str, list] = {}
    monkeypatch.setattr(pool_module, "_load_datasets", lambda sid: mapping.get(sid, []))
    return mapping


def test_snapshot_grouped_and_two_level_routing(tmp_path, patch_datasets):
    patch_datasets["s1"] = [_dataset(tmp_path, "sales_db", {
        "orders": {"id": [1, 2, 3], "cust": [10, 10, 20], "amount": [5, 7, 3]},
        "customers": {"id": [10, 20], "region": ["N", "S"]},
    })]
    mgr = SessionPoolManager(8, 1000)

    async def body():
        await mgr.acquire("s1")
        snap = mgr.snapshot("s1")
        ok = await mgr.call_tool("s1", "sales_db", "orders", {
            "query": "SELECT c.region, SUM(o.amount) AS t FROM orders o JOIN customers c "
                     "ON o.cust = c.id GROUP BY c.region ORDER BY c.region"
        })
        bad_ds = await mgr.call_tool("s1", "nope", "orders", {"query": "SELECT 1"})
        bad_cap = await mgr.call_tool("s1", "sales_db", "nope", {"query": "SELECT 1"})
        return snap, ok, bad_ds, bad_cap

    snap, ok, bad_ds, bad_cap = asyncio.run(body())
    assert len(snap) == 1 and snap[0]["dataset"] == "sales_db"
    assert sorted(c["table"] for c in snap[0]["capabilities"]) == ["customers", "orders"]
    assert ok == ("region,t\nN,12\nS,3", False)            # within-dataset JOIN
    assert bad_ds[1] is True and "Unknown tool" in bad_ds[0]
    assert bad_cap[1] is True and "Unknown capability" in bad_cap[0]


def test_capability_carries_columns_and_description(tmp_path, patch_datasets):
    patch_datasets["s1"] = [_dataset(tmp_path, "d", {"orders": {"id": [1], "total": [5]}})]
    mgr = SessionPoolManager(8, 1000)
    asyncio.run(mgr.acquire("s1"))
    cap = mgr.snapshot("s1")[0]["capabilities"][0]
    assert cap["table"] == "orders"
    assert cap["columns"] == ["id", "total"]
    assert cap["description"] == "Query orders"


def test_two_datasets_same_table_name_no_collision(tmp_path, patch_datasets):
    a = _dataset(tmp_path, "alpha", {"items": {"x": [1, 2]}})
    b = _dataset(tmp_path, "beta", {"items": {"x": [1, 2, 3]}})
    patch_datasets["s1"] = [a, b]
    mgr = SessionPoolManager(8, 1000)

    async def body():
        await mgr.acquire("s1")
        ca = await mgr.call_tool("s1", "alpha", "items", {"query": "SELECT COUNT(*) AS c FROM items"})
        cb = await mgr.call_tool("s1", "beta", "items", {"query": "SELECT COUNT(*) AS c FROM items"})
        return ca, cb

    ca, cb = asyncio.run(body())
    assert ca == ("c\n2", False) and cb == ("c\n3", False)  # dataset namespaces the table


def test_acquire_reuses_pool(tmp_path, patch_datasets):
    patch_datasets["s1"] = [_dataset(tmp_path, "d", {"t": {"x": [1]}})]
    mgr = SessionPoolManager(8, 1000)

    async def body():
        return await mgr.acquire("s1") is await mgr.acquire("s1")

    assert asyncio.run(body()) is True


def test_no_datasets_raises(patch_datasets):
    mgr = SessionPoolManager(8, 1000)
    with pytest.raises(pool_module.NoDataSourcesError):
        asyncio.run(mgr.acquire("missing"))


def test_lru_eviction(tmp_path, patch_datasets):
    for sid in ("s1", "s2", "s3"):
        patch_datasets[sid] = [_dataset(tmp_path, f"d_{sid}", {"t": {"x": [1]}})]
    mgr = SessionPoolManager(max_pools=2, idle_seconds=1000)

    async def body():
        await mgr.acquire("s1")
        await mgr.acquire("s2")
        await mgr.acquire("s3")  # exceeds cap → evicts LRU (s1)

    asyncio.run(body())
    assert mgr.snapshot("s1") == []   # evicted
    assert mgr.snapshot("s2") and mgr.snapshot("s3")


def test_close_is_idempotent(tmp_path, patch_datasets):
    patch_datasets["s1"] = [_dataset(tmp_path, "d", {"t": {"x": [1]}})]
    mgr = SessionPoolManager(8, 1000)
    asyncio.run(mgr.acquire("s1"))
    mgr.close("s1")
    mgr.close("s1")  # must not raise
    assert mgr.snapshot("s1") == []
