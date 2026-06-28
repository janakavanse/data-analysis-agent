"""Code-generation helper: turn a plan + schema into runnable pandas.

The generated code assumes a pre-loaded ``df`` and assigns the answer to
``result``. The payload sent to the LLM contains ONLY the schema, plan, and (on
a repair) the prior code + execution error — NEVER raw rows.
"""

from __future__ import annotations

import json
import re
from typing import Any

from analysis import load_prompt, with_retry
from llm.client import LLMClient

_FENCE_RE = re.compile(r"^```(?:python|py)?\s*\n?|\n?```$", re.IGNORECASE)


def _strip_fences(code: str) -> str:
    """Remove surrounding markdown code fences the model may emit anyway."""
    text = code.strip()
    if text.startswith("```"):
        text = _FENCE_RE.sub("", text)
        # second pass for a trailing fence not caught by the anchored regex
        text = text.strip()
        if text.endswith("```"):
            text = text[: -3].strip()
    return text.strip()


def build_codegen_payload(
    plan: str,
    schema: dict,
    prior_code: str | None = None,
    error: str | None = None,
) -> dict:
    """Build the exact LLM payload for the codegen step (for the privacy audit).

    On a repair attempt, the prior code and the captured execution error are
    appended. Privacy-safe: schema + plan + prior-code + error only — no rows.
    """
    system = load_prompt("codegen")
    parts: list[str] = [
        f"Analysis plan:\n{plan}\n",
        f"Schema (columns + dtypes):\n{json.dumps(schema)}",
    ]
    if prior_code and error:
        parts.append(
            "\nYour previous code FAILED. Fix it.\n"
            f"Previous code:\n{prior_code}\n\n"
            f"Execution error:\n{error}\n\n"
            "Return corrected code only."
        )
    user = "\n".join(parts)
    node = "generate_code_repair" if (prior_code and error) else "generate_code"
    return {"node": node, "system": system, "user": user}


def generate_code(
    plan: str,
    schema: dict,
    prior_code: str | None = None,
    error: str | None = None,
    *,
    client: Any | None = None,
) -> tuple[str, dict]:
    """Generate pandas code. Returns (code_text, llm_payload)."""
    payload = build_codegen_payload(plan, schema, prior_code, error)
    llm = client or LLMClient()
    raw = with_retry(
        lambda: llm.call_model(payload["user"], system=payload["system"]),
        op=payload["node"],
    )
    return _strip_fences(raw or ""), payload
