"""Full-stack contract tests — httpx + ASGI transport, FakeModel, no key."""
import csv
import json
import io
import pytest
from httpx import AsyncClient, ASGITransport
from langchain_core.messages import AIMessage

from agent.db import init_db
from agent.server import app


class FakeModel:
    def __init__(self, scripted):
        self.s = list(scripted)
        self.i = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, msgs):
        m = self.s[min(self.i, len(self.s) - 1)]
        self.i += 1
        return m


@pytest.fixture
def fake_model_query(monkeypatch):
    scripted = [
        AIMessage(content="", tool_calls=[{"name": "list_datasets", "args": {}, "id": "t1"}]),
        AIMessage(content="", tool_calls=[{"name": "finish", "args": {"answer": "dataset list"}, "id": "t2"}]),
    ]
    model = FakeModel(scripted)
    monkeypatch.setattr("agent.runner.get_model", lambda: model)
    return model


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_post_runs_returns_envelope(fake_model_query):
    await init_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/runs", json={"goal": "list datasets"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    run_data = data["data"]
    assert "run_id" in run_data
    assert "thread_id" in run_data
    assert "answer" in run_data
    assert "cost_usd" in run_data


@pytest.mark.asyncio
async def test_upload_csv_and_list():
    await init_db()
    csv_content = "name,revenue\nalpha,100\nbeta,200\n"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/datasets/upload",
            files={"file": ("test.csv", csv_content.encode(), "text/csv")},
            data={"name": "test_dataset"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["data"]["row_count"] == 2
    assert "dataset_id" in data["data"]

    # list endpoint must return it
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        list_resp = await client.get("/datasets")
    assert list_resp.status_code == 200
    datasets = list_resp.json()["data"]
    assert len(datasets) >= 1
    assert any(d["name"] == "test_dataset" for d in datasets)
