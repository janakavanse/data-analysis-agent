"""LLM-facing analysis helpers: plan, code generation, and answer summarization.

These helpers are the ONLY components that build LLM payloads. By construction
they receive only the privacy-safe schema/profile/result_summary — never raw
rows. Each helper returns both its text output and the exact payload that was
sent to the LLM, so the graph can record the full privacy audit trail.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, TypeVar

from observability.events import get_logger

logger = get_logger("analysis")

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# Transient Gemini error name fragments that justify a retry with backoff.
_TRANSIENT_MARKERS = (
    "429", "500", "502", "503", "504",
    "rate", "quota", "unavailable", "deadline", "timeout",
    "overloaded", "internal", "temporarily",
)

T = TypeVar("T")


def load_prompt(name: str) -> str:
    """Load a system prompt by stem (e.g. 'plan' -> prompts/plan.md)."""
    return (_PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


def _is_transient(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(marker in msg for marker in _TRANSIENT_MARKERS)


def with_retry(fn: Callable[[], T], *, attempts: int = 3, base_delay: float = 0.75,
               op: str = "llm_call") -> T:
    """Call ``fn`` with exponential backoff on transient errors.

    Retries only transient-looking failures (rate limit / 5xx / timeout). A
    non-transient error raises immediately. After ``attempts`` exhausted, the
    last exception propagates so the node can set ``state.error``.
    """
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - classified below
            last = exc
            if attempt >= attempts or not _is_transient(exc):
                logger.warning("analysis.llm_error", op=op, attempt=attempt,
                               transient=_is_transient(exc), error=str(exc))
                raise
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning("analysis.llm_retry", op=op, attempt=attempt,
                           delay_s=round(delay, 2), error=str(exc))
            time.sleep(delay)
    assert last is not None  # unreachable
    raise last


def build_answer_payload(question: str, result_summary: dict) -> dict:
    """Build the exact LLM payload for the summarize step (privacy audit).

    Privacy-safe: question + result_summary (aggregates/shape only) — no rows.
    """
    system = load_prompt("answer")
    user = (
        f"Question: {question}\n\n"
        f"Result summary (aggregates only, no raw rows):\n"
        f"{__import__('json').dumps(result_summary)}"
    )
    return {"node": "summarize", "system": system, "user": user}


def stream_answer(question: str, result_summary: dict, *, client=None):
    """Stream the plain-language answer token-by-token.

    Yields ``("token", chunk)`` for each text chunk and finally
    ``("usage", {"prompt_tokens": int, "completion_tokens": int})``. The whole
    generation is wrapped in :func:`with_retry`'s backoff policy by retrying the
    stream setup; once tokens start flowing we do not retry mid-stream.

    Returns the exact payload via the first yielded ``("payload", dict)`` item
    so the caller can record the privacy audit even though this is a generator.

    Uses the Gemini SDK directly because :class:`LLMClient` does not expose a
    streaming API. This is a helper module, not a graph node; the privacy
    invariant (no rows in the payload) is enforced by ``build_answer_payload``.
    """
    payload = build_answer_payload(question, result_summary)
    yield ("payload", payload)

    if client is not None:
        # Test seam: a fake client that yields chunks then usage.
        for item in client.stream(payload["user"], system=payload["system"]):
            yield item
        return

    from config.settings import get_settings
    from google import genai
    from google.genai import types

    settings = get_settings()
    gclient = genai.Client(api_key=settings.gemini_api_key)
    model = settings.llm_model or "gemini-2.0-flash"
    config = types.GenerateContentConfig(system_instruction=payload["system"])

    def _open_stream():
        return gclient.models.generate_content_stream(
            model=model, contents=payload["user"], config=config
        )

    stream = with_retry(_open_stream, op="summarize")
    prompt_tokens = 0
    completion_tokens = 0
    for chunk in stream:
        text = getattr(chunk, "text", None)
        if text:
            yield ("token", text)
        usage = getattr(chunk, "usage_metadata", None)
        if usage is not None:
            prompt_tokens = getattr(usage, "prompt_token_count", 0) or prompt_tokens
            completion_tokens = (
                getattr(usage, "candidates_token_count", 0) or completion_tokens
            )
    yield ("usage", {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
    })
