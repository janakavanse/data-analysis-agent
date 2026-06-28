"""Phase 1 — cost accounting tests."""

import pytest

from analysis import cost


def test_estimate_cost_positive_for_gemini_flash():
    c = cost.estimate_cost("gemini-2.5-flash", 1000, 500)
    assert isinstance(c, float)
    assert c > 0.0


def test_estimate_cost_scales_with_tokens():
    small = cost.estimate_cost("gemini-2.5-flash", 1000, 500)
    big = cost.estimate_cost("gemini-2.5-flash", 10_000, 5_000)
    assert big > small
    assert big == pytest.approx(small * 10, rel=1e-6)


def test_price_table_has_gemini_flash():
    assert "gemini-2.5-flash" in cost.PRICE_TABLE
    entry = cost.PRICE_TABLE["gemini-2.5-flash"]
    assert entry["in"] > 0 and entry["out"] > 0


def test_unknown_model_still_costs():
    c = cost.estimate_cost("some-unknown-model", 1000, 1000)
    assert c > 0.0


def test_zero_tokens_zero_cost():
    assert cost.estimate_cost("gemini-2.5-flash", 0, 0) == 0.0


def test_env_override(monkeypatch):
    monkeypatch.setenv("AGENT_PRICE_GEMINI_2_5_FLASH_IN", "1.0")
    monkeypatch.setenv("AGENT_PRICE_GEMINI_2_5_FLASH_OUT", "2.0")
    # 1000 in @ $1/1k + 1000 out @ $2/1k = $1 + $2 = $3
    c = cost.estimate_cost("gemini-2.5-flash", 1000, 1000)
    assert c == pytest.approx(3.0)
