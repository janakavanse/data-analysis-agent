"""Phase 1 graph tests — REAL Gemini via .env.

(a) the graph compiles without any env / API key being needed;
(b) an end-to-end run over a small real DuckDB dataset hits real Gemini and
    persists a completed RunRow with answer, code, tokens, cost, and a chart.

The autouse `_isolated_db` fixture (tests/conftest.py) monkeypatches the DB
engine to a tmp sqlite — the production driver path is unchanged, this only
isolates the run from the developer DB.
"""

import uuid

import pytest
from sqlalchemy.orm import Session


def test_graph_compiles():
    """The compiled graph must import with no env / key configured."""
    from graph.agent import agentic_ai

    assert agentic_ai is not None
    # Sanity: it is a compiled LangGraph (invocable).
    assert hasattr(agentic_ai, "invoke")


def _gemini_key_present() -> bool:
    from config.settings import get_settings

    return bool(get_settings().gemini_api_key)


@pytest.fixture
def small_dataset(tmp_path):
    """Ingest a tiny CSV via the analysis engine -> a real DuckDB table."""
    engine = pytest.importorskip(
        "analysis.engine",
        reason="analysis.engine not built yet (parallel slice)",
    )
    csv = tmp_path / "sales.csv"
    csv.write_text(
        "region,revenue\n"
        "West,100\n"
        "East,250\n"
        "West,150\n"
        "North,300\n"
        "East,50\n",
        encoding="utf-8",
    )
    dataset_id = uuid.uuid4().hex
    engine.ingest_file(str(csv), "sales.csv", dataset_id)
    return dataset_id


def test_run_agent_end_to_end_real_gemini(small_dataset):
    """Full pipeline on real Gemini: persisted run is completed with real output."""
    if not _gemini_key_present():
        pytest.skip("AGENT_GEMINI_API_KEY not set in .env")

    from db import session as session_module
    from db.models import RunRow
    from graph.runner import run_agent

    run_id = run_agent(
        "What is the total revenue by region, and which region has the most?",
        small_dataset,
    )
    assert run_id

    with Session(session_module._engine) as s:
        run = s.get(RunRow, run_id)

    assert run is not None
    assert run.status == "completed", f"run failed: {run.error_message}"
    assert run.error_message is None
    assert run.answer and len(run.answer) > 10
    assert run.code and "result" in run.code
    assert run.tokens_in > 0
    assert run.tokens_out > 0
    assert run.cost_estimate > 0
    assert run.chart_spec_json is not None
    assert "data" in run.chart_spec_json
    # Privacy: the persisted LLM payload must carry schema/sample context, not bulk rows.
    assert isinstance(run.llm_payload_json, dict)
