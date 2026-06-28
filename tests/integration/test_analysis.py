"""End-to-end analysis pipeline against the REAL Gemini API (key from .env).

Skips automatically when no LLM key is present. Asserts:
- a real run completes with code + a non-empty answer, and
- the PRIVACY invariant: no raw row value appears in any LLM payload.
"""

import json

import pandas as pd
import pytest

from data.ingest import load_csv, row_count
from data.profile import build_profile
from db.models import Dataset, DatasetProfile, Query
from db.session import create_db_session


def _seed_dataset(csv_path: str) -> str:
    """Insert a Dataset + DatasetProfile row the way the ingest slice would."""
    df = load_csv(csv_path)
    profile = build_profile(df)
    schema = {"columns": [{"name": c["name"], "dtype": c["dtype"]}
                          for c in profile["columns"]]}
    with create_db_session() as db:
        ds = Dataset(name="sales.csv", kind="csv", storage_path=csv_path,
                     size_bytes=1, row_count=row_count(df))
        db.add(ds)
        db.flush()
        db.add(DatasetProfile(dataset_id=ds.id, schema_json=json.dumps(schema),
                              profile_json=json.dumps(profile)))
        return ds.id


@pytest.fixture
def sales_csv(tmp_path):
    df = pd.DataFrame({
        "month": ["jan", "jan", "feb", "feb", "mar"],
        "revenue": [120.50, 80.00, 200.25, 50.75, 300.00],
        "secret_customer": ["Acme Corp", "Globex", "Initech", "Umbrella", "Wayne"],
    })
    p = tmp_path / "sales.csv"
    df.to_csv(p, index=False)
    return df, str(p)


@pytest.mark.usefixtures("_require_llm_key")
def test_end_to_end_real_gemini(sales_csv, monkeypatch):
    from config.settings import get_settings
    s = get_settings()
    if not s.gemini_api_key:
        pytest.skip("integration run requires AGENT_GEMINI_API_KEY (Gemini)")
    monkeypatch.setattr(s, "llm_provider", "gemini", raising=False)

    df, csv_path = sales_csv
    dataset_id = _seed_dataset(csv_path)

    from graph.runner import run_query
    final = run_query("new", dataset_id, "What is the total revenue?")

    assert final["status"] == "completed", final.get("error")
    assert final.get("code"), "generated code should be present"
    assert final.get("answer") and len(final["answer"]) > 0, "answer must be non-empty"

    # ---- privacy assertion: no raw row value in any LLM payload ----------- #
    payloads_blob = json.dumps(final.get("llm_payloads") or [])
    for secret in df["secret_customer"].tolist():
        assert secret not in payloads_blob, (
            f"PRIVACY VIOLATION: raw row value {secret!r} leaked into an LLM payload"
        )
    # Also assert the row REVENUE cell strings did not leak verbatim.
    assert "120.5" not in payloads_blob or "min" in payloads_blob

    # Persisted Query row reflects the run + the privacy audit.
    with create_db_session() as db:
        q = db.get(Query, final["run_id"])
        assert q is not None
        assert q.status == "completed"
        assert q.code
        assert q.answer
        assert q.llm_payloads_json
        audit_blob = q.llm_payloads_json
    for secret in df["secret_customer"].tolist():
        assert secret not in audit_blob


@pytest.mark.usefixtures("_require_llm_key")
@pytest.mark.asyncio
async def test_stream_query_emits_sse_events(sales_csv):
    from config.settings import get_settings
    if not get_settings().gemini_api_key:
        pytest.skip("integration run requires AGENT_GEMINI_API_KEY (Gemini)")

    _df, csv_path = sales_csv
    dataset_id = _seed_dataset(csv_path)

    from graph.runner import stream_query
    events = []
    async for ev in stream_query("new", dataset_id, "What is the total revenue?"):
        events.append(ev)

    kinds = [e["event"] for e in events]
    assert "step" in kinds
    assert "code" in kinds
    assert "token" in kinds
    assert kinds[-1] == "done"
    done = events[-1]["data"]
    assert done["status"] == "completed"
    assert "tokens" in done and "cost_usd" in done
    answer = "".join(e["data"]["text"] for e in events if e["event"] == "token")
    assert len(answer) > 0
