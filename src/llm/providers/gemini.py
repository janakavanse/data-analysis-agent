from google import genai
from google.genai import types

from llm.client import LLMResult


class GeminiProvider:
    DEFAULT_MODEL = "gemini-2.5-flash"

    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model or self.DEFAULT_MODEL

    @property
    def model(self) -> str:
        return self._model

    def complete(self, prompt: str, *, system: str | None = None) -> LLMResult:
        config = types.GenerateContentConfig(
            system_instruction=system,
        ) if system else None
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=config,
        )
        tokens_in, tokens_out = _usage(response)
        return LLMResult(text=response.text or "", tokens_in=tokens_in, tokens_out=tokens_out)

    def call_model(self, prompt: str, *, system: str | None = None) -> str:
        return self.complete(prompt, system=system).text


def _usage(response) -> tuple[int, int]:
    meta = getattr(response, "usage_metadata", None)
    if meta is None:
        return 0, 0
    tokens_in = getattr(meta, "prompt_token_count", 0) or 0
    tokens_out = getattr(meta, "candidates_token_count", 0) or 0
    return int(tokens_in), int(tokens_out)
