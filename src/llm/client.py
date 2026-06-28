"""LLM client — auto-provider, with usage accounting and transient-error retry.

``complete()`` returns an :class:`LLMResult` carrying the text plus prompt/completion
token counts (used for cost accounting in the graph). ``call_model()`` is kept as a
thin back-compat wrapper returning just the text.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from config.settings import get_settings


@dataclass(frozen=True)
class LLMResult:
    text: str
    tokens_in: int
    tokens_out: int


# Errors worth retrying with backoff — transient rate-limit / server faults.
# We match on the string form so we do not need to import each provider SDK's
# exception hierarchy here.
_RETRYABLE_MARKERS = (
    "429",
    "500",
    "502",
    "503",
    "504",
    "rate limit",
    "resource exhausted",
    "overloaded",
    "deadline",
    "unavailable",
    "timeout",
)

_MAX_ATTEMPTS = 3
_BASE_BACKOFF_S = 1.0


def _is_retryable(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(marker in msg for marker in _RETRYABLE_MARKERS)


def _make_provider():
    s = get_settings()
    provider = s.llm_provider

    # auto-detect from whichever key is set
    if not provider:
        if s.anthropic_api_key:
            provider = "anthropic"
        elif s.gemini_api_key:
            provider = "gemini"
        else:
            raise RuntimeError(
                "No LLM provider configured. Set AGENT_ANTHROPIC_API_KEY or "
                "AGENT_GEMINI_API_KEY in .env, or set AGENT_LLM_PROVIDER explicitly."
            )

    if provider == "anthropic":
        from llm.providers.anthropic import AnthropicProvider
        return AnthropicProvider(api_key=s.anthropic_api_key, model=s.llm_model)
    if provider == "gemini":
        from llm.providers.gemini import GeminiProvider
        return GeminiProvider(api_key=s.gemini_api_key, model=s.llm_model)

    raise RuntimeError(f"Unknown LLM provider: {provider!r}. Supported: anthropic, gemini")


class LLMClient:
    def __init__(self) -> None:
        self._provider = _make_provider()

    @property
    def model(self) -> str:
        """The resolved model id (for cost accounting)."""
        return self._provider.model

    def complete(self, prompt: str, *, system: str | None = None) -> LLMResult:
        """Call the model and return text + token usage, retrying transient errors."""
        last_exc: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                return self._provider.complete(prompt, system=system)
            except Exception as exc:  # noqa: BLE001 — re-raised after retries
                last_exc = exc
                if attempt < _MAX_ATTEMPTS - 1 and _is_retryable(exc):
                    time.sleep(_BASE_BACKOFF_S * (2 ** attempt))
                    continue
                raise
        # Unreachable, but keeps type-checkers happy.
        raise last_exc  # type: ignore[misc]

    def call_model(self, prompt: str, *, system: str | None = None) -> str:
        """Back-compat: return just the completion text."""
        return self.complete(prompt, system=system).text
