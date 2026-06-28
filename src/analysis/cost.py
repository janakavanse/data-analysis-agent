"""Per-model LLM cost accounting.

Holds a small price table (USD per 1k tokens, split into prompt/completion) and a
helper to estimate the cost of a single call. Prices default to realistic
Gemini-flash-tier values and are overridable via environment variables so the
table can be tuned without a code change:

    AGENT_PRICE_<MODEL>_IN   — prompt $ per 1k tokens
    AGENT_PRICE_<MODEL>_OUT  — completion $ per 1k tokens

where ``<MODEL>`` is the model id upper-cased with non-alphanumerics replaced by
``_`` (e.g. ``gemini-2.5-flash`` -> ``GEMINI_2_5_FLASH``).
"""

from __future__ import annotations

import os
import re

# USD per 1,000 tokens. Defaults reflect the cheap Gemini-flash tier the spec
# targets (keep-cost-low goal). Values are deliberately small but non-zero so a
# per-question estimate is always a positive float.
PRICE_TABLE: dict[str, dict[str, float]] = {
    "gemini-2.5-flash": {"in": 0.00030, "out": 0.00250},
    "gemini-2.5-flash-lite": {"in": 0.00010, "out": 0.00040},
    "gemini-2.5-pro": {"in": 0.00125, "out": 0.01000},
    # Anthropic kept for back-compat with the skeleton's default provider.
    "claude-3-5-haiku-latest": {"in": 0.00080, "out": 0.00400},
}

# Fallback price for an unknown model — never zero, so cost is always surfaced.
_DEFAULT_PRICE: dict[str, float] = {"in": 0.00050, "out": 0.00200}


def _env_key(model: str, side: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", model).upper().strip("_")
    return f"AGENT_PRICE_{slug}_{side.upper()}"


def _price_for(model: str) -> dict[str, float]:
    base = PRICE_TABLE.get(model, _DEFAULT_PRICE)
    in_price = base["in"]
    out_price = base["out"]
    env_in = os.environ.get(_env_key(model, "in"))
    env_out = os.environ.get(_env_key(model, "out"))
    if env_in is not None:
        try:
            in_price = float(env_in)
        except ValueError:
            pass
    if env_out is not None:
        try:
            out_price = float(env_out)
        except ValueError:
            pass
    return {"in": in_price, "out": out_price}


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Estimate the USD cost of a single LLM call from its token usage."""
    price = _price_for(model)
    tokens_in = max(0, int(tokens_in or 0))
    tokens_out = max(0, int(tokens_out or 0))
    cost = (tokens_in / 1000.0) * price["in"] + (tokens_out / 1000.0) * price["out"]
    return round(cost, 8)
