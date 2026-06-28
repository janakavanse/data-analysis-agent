"""End-to-end analysis-loop tests against REAL Gemini (keys from .env).

Skips if no LLM key is configured. Uses the autouse isolated-SQLite DB and
settings-reset fixtures from tests/conftest.py. The fixture DataFrame has 500
rows where the full-data mean diverges sharply from any 5-row sample, so a
correct answer can only come from the FULL local computation — never the
sample the LLM is allowed to see.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from analysis import store
from analysis.store import extract_sample, extract_schema, row_count
from db.models import Dataset, Message, Session as SessionRow
from db.session import create_db_session


N = 500
SAMPLE_SCORE = 10.0          # value in the first 5 (sampled) rows
BULK_SCORE = 1000.0          # value in the remaining 495 rows
# Full-data mean ~990.1; sample-only mean is 10.0 — observably different.


def _make_fixture_df() -> pd.DataFrame:
    scores = [SAMPLE_SCORE] * 5 + [BULK_SCORE] * (N - 5)
    return pd.DataFrame(
        {
            "id": list(range(N)),
            "score": scores,
            "region": (["north", "south"] * (N // 2)),
        }
    )


def _seed_session(tmp_path) -> tuple[str, pd.DataFrame]:
    """Persist Session + Dataset rows and register the DF in the store."""
    df = _make_fixture_df()
    csv_path = tmp_path / "fixture.csv"
    df.to_csv(csv_path, index=False)

    with create_db_session() as db:
        session = SessionRow()
        db.add(session)
        db.flush()
        session_id = session.id
        db.add(
            Dataset(
                session_id=session_id,
                filename="fixture.csv",
                file_path=str(csv_path),
                file_type="csv",
                row_count=row_count(df),
                schema_json=json.dumps(extract_schema(df)),
                sample_json=json.dumps(extract_sample(df, n=5)),
            )
        )

    # Register the active DataFrame in the in-process store under the session.
    store.register(session_id, df)
    return session_id, df


@pytest.mark.usefixtures("_require_llm_key")
def test_full_data_answer_not_sample(tmp_path):
    """The returned answer matches the FULL-DATA mean, not the 5-row sample."""
    from graph.runner import run_analysis

    session_id, df = _seed_session(tmp_path)
    true_mean = float(df["score"].mean())

    payload = run_analysis(session_id, "What is the average of the score column?")

    assert payload.get("status") == "completed", payload
    # (b) the work is shown: code + result table present
    assert payload.get("code"), "expected the pandas code to be shown"
    result_table = payload.get("result_table")
    assert result_table is not None, "expected the computed result to be shown"

    # (a) the computed result equals the full-data computation, not the sample.
    if result_table.get("kind") == "scalar":
        computed = float(result_table["value"])
    else:  # a 1-cell table is also acceptable
        computed = float(result_table["rows"][0][-1])
    assert computed == pytest.approx(true_mean, rel=1e-6), (
        f"computed {computed} != full-data mean {true_mean}"
    )
    # Definitively not the sample-only answer.
    assert computed != pytest.approx(SAMPLE_SCORE)

    # Persisted: a user + an assistant message for the turn.
    with create_db_session() as db:
        msgs = (
            db.query(Message)
            .filter(Message.session_id == session_id)
            .order_by(Message.created_at.asc())
            .all()
        )
        roles = [m.role for m in msgs]
        assistant_rows = [
            (m.status, m.code) for m in msgs if m.role == "assistant"
        ]
    assert "user" in roles and "assistant" in roles
    assistant_status, assistant_code = assistant_rows[-1]
    assert assistant_status == "completed"
    assert assistant_code


@pytest.mark.usefixtures("_require_llm_key")
def test_followup_uses_prior_context(tmp_path):
    """A follow-up referencing the prior turn is answered using prior_turns."""
    from graph.runner import run_analysis

    session_id, df = _seed_session(tmp_path)
    true_mean = float(df["score"].mean())

    first = run_analysis(session_id, "What is the average of the score column?")
    assert first.get("status") == "completed", first

    # The follow-up never names the column — it can only resolve via prior turns.
    followup = run_analysis(session_id, "And what is the maximum of that same column?")
    assert followup.get("status") == "completed", followup
    table = followup.get("result_table")
    assert table is not None
    if table.get("kind") == "scalar":
        computed = float(table["value"])
    else:
        computed = float(table["rows"][0][-1])
    assert computed == pytest.approx(BULK_SCORE, rel=1e-6), (
        f"follow-up max {computed} != expected {BULK_SCORE}; prior context not used"
    )
    # sanity: the prior mean is still the full-data mean, proving the same df.
    assert true_mean == pytest.approx(df["score"].mean())


@pytest.mark.usefixtures("_require_llm_key")
def test_prompt_payload_is_sample_only(tmp_path, monkeypatch):
    """PRIVACY: the LLM prompt carries the sample rows but NOT the full data."""
    import llm.client as client_module

    captured: list[str] = []
    original = client_module.LLMClient.call_model

    def _spy(self, prompt, *, system=None):
        captured.append(prompt)
        if system:
            captured.append(system)
        return original(self, prompt, system=system)

    monkeypatch.setattr(client_module.LLMClient, "call_model", _spy)

    session_id, df = _seed_session(tmp_path)
    payload = run_analysis_safe(session_id, "What is the average of the score column?")
    assert payload.get("status") == "completed", payload

    plan_prompt = captured[0]  # first call is plan_analysis' user content

    # The 5-row sample IS present (privacy-allowed context).
    sample_ids = [str(i) for i in range(5)]
    assert all(sid in plan_prompt for sid in sample_ids), "sample rows missing from prompt"

    # The FULL data is NOT present: bulk-only id values (>=5) must be absent.
    leaked = [i for i in range(5, N) if f'"id": {i}' in plan_prompt or f"'id': {i}" in plan_prompt]
    assert not leaked, f"full data leaked into prompt for ids {leaked[:5]}..."

    # Stronger bound: the prompt must not contain anywhere near 500 data rows.
    # Count occurrences of the bulk-only score value in any prompt sent.
    bulk_token = str(int(BULK_SCORE))
    bulk_hits = sum(p.count(bulk_token) for p in captured)
    assert bulk_hits <= 5, (
        f"prompt(s) contained the bulk value {bulk_hits} times — looks like full data leaked"
    )


def run_analysis_safe(session_id: str, question: str) -> dict:
    """Import locally so monkeypatch of LLMClient is in place before the run."""
    from graph.runner import run_analysis

    return run_analysis(session_id, question)
