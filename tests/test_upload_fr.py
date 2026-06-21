"""FR: /datasets/upload convenience endpoint — matches frontend upload form.

POST /datasets/upload creates a dataset and ingests a single file in one shot,
returning dataset_id, row_count, and schema (matches what the frontend upload panel sends).
"""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.server import app


@pytest_asyncio.fixture
async def _client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_datasets_upload_convenience_endpoint(_client):
    """POST /datasets/upload creates dataset + uploads file in one shot (matches frontend)."""
    form = {"name": "quicktest"}
    files = {"file": ("q.csv", "a,b\n1,2\n3,4\n", "text/csv")}
    resp = (await _client.post("/datasets/upload", data=form, files=files)).json()
    assert resp["ok"], resp
    assert resp["data"]["row_count"] == 2
    assert resp["data"]["dataset_id"]
    assert "schema" in resp["data"]
