"""Golden-path dataset smoke test: create dataset → upload multiple CSVs → cross-file query."""
import io
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import datachat.db.session as session_module
import datachat.llm.client as llm_client_module
from datachat.db.models import Base
from datachat.llm.providers.stub import StubLLMProvider

CSV_A = b"month,revenue\nJan,1000\nFeb,1200\nMar,900\n"
CSV_B = b"month,revenue\nJan,800\nFeb,1500\nMar,1100\n"


@pytest.fixture(autouse=True)
def _use_sqlite_db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(session_module, "_engine", engine)
    monkeypatch.setattr(session_module, "_SessionLocal", factory)
    monkeypatch.setattr(session_module, "init_db", lambda: None)
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def _use_stub_llm(monkeypatch):
    stub = StubLLMProvider()
    monkeypatch.setattr(llm_client_module, "_provider", stub)
    monkeypatch.setattr(llm_client_module, "_is_stub", True)


@pytest.fixture(autouse=True)
def _use_tmp_upload_dir(tmp_path, monkeypatch):
    import datachat.config.settings as settings_mod
    from datachat.config.settings import Settings
    monkeypatch.setattr(
        settings_mod, "_settings",
        Settings(database_url=f"sqlite:///{tmp_path}/test.db", upload_dir=str(tmp_path / "uploads")),
    )
    (tmp_path / "uploads").mkdir()


@pytest.fixture
def client():
    from datachat.api.app import create_app
    return TestClient(create_app(), raise_server_exceptions=True)


def test_create_dataset(client):
    res = client.post("/api/datasets", json={"name": "Q1 Sales"})
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["name"] == "Q1 Sales"
    assert data["uploads"] == []
    assert "id" in data


def test_list_datasets(client):
    client.post("/api/datasets", json={"name": "DS1"})
    client.post("/api/datasets", json={"name": "DS2"})
    res = client.get("/api/datasets")
    assert res.status_code == 200
    assert len(res.json()["data"]) == 2


def test_get_dataset_not_found(client):
    res = client.get("/api/datasets/nonexistent")
    assert res.status_code == 404


def test_upload_csv_to_dataset(client):
    ds_id = client.post("/api/datasets", json={"name": "Test"}).json()["data"]["id"]

    res = client.post(
        f"/api/datasets/{ds_id}/uploads",
        files={"file": ("a.csv", io.BytesIO(CSV_A), "text/csv")},
    )
    assert res.status_code == 200
    upload = res.json()["data"]["upload"]
    assert upload["original_filename"] == "a.csv"
    assert upload["row_count"] == 3
    assert "month" in upload["columns"]


def test_upload_rejects_non_csv(client):
    ds_id = client.post("/api/datasets", json={"name": "Test"}).json()["data"]["id"]
    res = client.post(
        f"/api/datasets/{ds_id}/uploads",
        files={"file": ("data.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert res.status_code == 400


def test_golden_path_multi_csv_query(client):
    # Create dataset
    ds_id = client.post("/api/datasets", json={"name": "Revenue"}).json()["data"]["id"]

    # Upload two CSVs
    for name, content in [("file_a.csv", CSV_A), ("file_b.csv", CSV_B)]:
        r = client.post(
            f"/api/datasets/{ds_id}/uploads",
            files={"file": (name, io.BytesIO(content), "text/csv")},
        )
        assert r.status_code == 200, r.text

    # Verify dataset shows 2 uploads
    ds = client.get(f"/api/datasets/{ds_id}").json()["data"]
    assert len(ds["uploads"]) == 2

    # Ask a cross-file question
    res = client.post(
        f"/api/datasets/{ds_id}/queries",
        json={"question": "What is the total revenue across all months and files?"},
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["dataset_id"] == ds_id
    assert len(data["answer"]) > 0
    assert "tokens" in data
    assert "input" in data["tokens"]
    assert "output" in data["tokens"]
    assert "total" in data["tokens"]
    assert "cost_usd" in data

    # Query history
    hist = client.get(f"/api/datasets/{ds_id}/queries").json()["data"]
    assert len(hist) == 1
    assert hist[0]["id"] == data["id"]


def test_query_empty_dataset(client):
    ds_id = client.post("/api/datasets", json={"name": "Empty"}).json()["data"]["id"]
    res = client.post(
        f"/api/datasets/{ds_id}/queries",
        json={"question": "Anything?"},
    )
    assert res.status_code == 404


def test_token_costs_in_stub_are_zero(client):
    ds_id = client.post("/api/datasets", json={"name": "Cost test"}).json()["data"]["id"]
    client.post(
        f"/api/datasets/{ds_id}/uploads",
        files={"file": ("a.csv", io.BytesIO(CSV_A), "text/csv")},
    )
    res = client.post(
        f"/api/datasets/{ds_id}/queries",
        json={"question": "What are the months?"},
    )
    data = res.json()["data"]
    assert data["tokens"]["total"] == 0
    assert data["cost_usd"] == 0.0
