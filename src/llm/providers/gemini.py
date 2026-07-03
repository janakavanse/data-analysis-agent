from google import genai
from google.genai import types


class GeminiProvider:
    # "gemini-3.1-pro" (the harness's nominal default, spec/architecture.md)
    # returns 404 NOT_FOUND against the live API for the key configured in
    # this environment — the actual available model in this account's
    # model list is "gemini-3.1-pro-preview". Override via AGENT_LLM_MODEL
    # if your account has a different available model name.
    DEFAULT_MODEL = "gemini-3.1-pro-preview"

    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model or self.DEFAULT_MODEL

    def call_model(self, prompt: str, *, system: str | None = None) -> str:
        config = types.GenerateContentConfig(
            system_instruction=system,
        ) if system else None
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=config,
        )
        return response.text

    def call_model_with_usage(self, prompt: str, *, system: str | None = None) -> tuple[str, dict]:
        config = types.GenerateContentConfig(
            system_instruction=system,
        ) if system else None
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=config,
        )
        usage = response.usage_metadata
        prompt_tokens = getattr(usage, "prompt_token_count", None) or 0
        completion_tokens = getattr(usage, "candidates_token_count", None) or 0
        thinking_tokens = getattr(usage, "thoughts_token_count", None) or 0
        total_tokens = getattr(usage, "total_token_count", None) or (
            prompt_tokens + completion_tokens + thinking_tokens
        )
        return response.text, {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "thinking_tokens": thinking_tokens,
            "total_tokens": total_tokens,
        }
