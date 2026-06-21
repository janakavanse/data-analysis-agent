"""
Integration tests for live Gemini API calls.

These tests are skipped if GEMINI_API_KEY is absent or is a placeholder value.
Run with:  ANALYST_LLM_PROVIDER=gemini uv run --extra dev pytest tests/integration/test_live_llm.py -v
"""

import json
import os

import pytest

GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
SKIP_LIVE = not GEMINI_KEY or GEMINI_KEY.lower() in ("stub", "your-key-here", "")

pytestmark = pytest.mark.skipif(SKIP_LIVE, reason="GEMINI_API_KEY not set or is stub")


def test_gemini_client_returns_valid_json():
    """Real Gemini call returns JSON with intent and sql keys."""
    from src.integrations.llm import GeminiClient

    client = GeminiClient(model="gemini-2.5-flash", api_key=GEMINI_KEY)
    prompt = (
        "Datasets available: sales\n"
        "User question: show top 5 rows of sales\n"
        "Return JSON with keys: intent (table|chart), sql, "
        "and for chart: x_col, y_col."
    )
    raw = client.complete(prompt)
    parsed = json.loads(raw)

    assert "intent" in parsed
    assert parsed["intent"] in ("table", "chart")
    assert "sql" in parsed
    assert len(parsed["sql"]) > 5


def test_gemini_client_has_complete_callable():
    """GeminiClient is instantiated correctly and exposes complete()."""
    from src.integrations.llm import GeminiClient

    client = GeminiClient(model="gemini-2.5-flash", api_key=GEMINI_KEY)
    assert hasattr(client, "complete")
    assert callable(client.complete)


def test_gemini_chart_intent_works():
    """Real Gemini call for a 'plot' question returns chart intent."""
    from src.integrations.llm import GeminiClient

    client = GeminiClient(model="gemini-2.5-flash", api_key=GEMINI_KEY)
    prompt = (
        "Datasets available: sales\n"
        "User question: plot revenue over product\n"
        "Return JSON with keys: intent (table|chart), sql, x_col, y_col."
    )
    raw = client.complete(prompt)
    parsed = json.loads(raw)
    assert parsed.get("intent") == "chart"
    assert "x_col" in parsed
    assert "y_col" in parsed
