import logging

from google import genai
from google.genai import types

from datachat.llm.providers.base import LLMProvider, LLMResult

logger = logging.getLogger(__name__)

# gemini-2.5-flash pricing (USD per million tokens, non-thinking tier)
_INPUT_COST_PER_M = 0.30
_OUTPUT_COST_PER_M = 2.50


def _compute_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * _INPUT_COST_PER_M + output_tokens * _OUTPUT_COST_PER_M) / 1_000_000


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def generate(self, prompt: str) -> LLMResult:
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
            )
            usage = response.usage_metadata
            input_tokens = getattr(usage, "prompt_token_count", 0) or 0
            output_tokens = getattr(usage, "candidates_token_count", 0) or 0
            cost = _compute_cost(input_tokens, output_tokens)
            return LLMResult(
                text=response.text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
            )
        except Exception as exc:
            logger.error("Gemini API error: %s", exc)
            raise
