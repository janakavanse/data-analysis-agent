"""Plan helper: turn a question + privacy-safe schema/profile into an analysis plan.

The payload sent to the LLM contains ONLY the schema, the column profile
(aggregates, no rows), and prior conversation messages. It NEVER contains raw
cell values.
"""

from __future__ import annotations

import json
from typing import Any

from analysis import load_prompt, with_retry
from llm.client import LLMClient


def build_plan_payload(
    question: str,
    schema: dict,
    profile: dict,
    messages: list | None = None,
) -> dict:
    """Build the exact LLM payload for the plan step (for the privacy audit).

    Returns {"node": "plan", "system": ..., "user": ...}. Privacy-safe by
    construction: only schema + profile + question + history.
    """
    system = load_prompt("plan")
    parts: list[str] = []
    if messages:
        history = "\n".join(
            f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages
        )
        parts.append(f"Conversation so far:\n{history}\n")
    parts.append(f"Question: {question}\n")
    parts.append(f"Schema (columns + dtypes):\n{json.dumps(schema)}\n")
    parts.append(f"Column profile (aggregates only, no rows):\n{json.dumps(profile)}")
    user = "\n".join(parts)
    return {"node": "plan", "system": system, "user": user}


def generate_plan(
    question: str,
    schema: dict,
    profile: dict,
    messages: list | None = None,
    *,
    client: Any | None = None,
) -> tuple[str, dict]:
    """Generate an analysis plan. Returns (plan_text, llm_payload)."""
    payload = build_plan_payload(question, schema, profile, messages)
    llm = client or LLMClient()
    text = with_retry(
        lambda: llm.call_model(payload["user"], system=payload["system"]),
        op="plan",
    )
    return (text or "").strip(), payload
