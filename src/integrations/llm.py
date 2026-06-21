import json as _json


class BaseLLMClient:
    def complete(self, prompt: str, system: str = "") -> str:
        raise NotImplementedError


class StubLLMClient(BaseLLMClient):
    def complete(self, prompt: str, system: str = "") -> str:
        # Extract only the user question line so prompt boilerplate doesn't trigger chart intent
        question_line = prompt
        for line in prompt.splitlines():
            if line.lower().startswith("user question:"):
                question_line = line
                break
        # Extract dataset name from prompt if available
        ds = "sales"
        for line in prompt.splitlines():
            if line.lower().startswith("datasets available:"):
                parts = line.split(":", 1)
                if len(parts) > 1 and parts[1].strip() not in ("", "none"):
                    ds = parts[1].strip().split(",")[0].strip()
                break
        if "plot" in question_line.lower() or "chart" in question_line.lower():
            return _json.dumps({
                "intent": "chart",
                "sql": f"SELECT product, revenue FROM {ds} LIMIT 20",
                "x_col": "product",
                "y_col": "revenue",
            })
        return _json.dumps({"intent": "table", "sql": f"SELECT * FROM {ds} LIMIT 10"})


class GeminiClient(BaseLLMClient):
    """Thin wrapper around google-generativeai."""

    def __init__(self, model: str, api_key: str):
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(
            model_name=model,
            system_instruction=(
                "You are a senior data analyst. Always respond with valid JSON only — "
                "no markdown fences, no explanation, just the JSON object."
            ),
        )

    def complete(self, prompt: str, system: str = "") -> str:
        response = self._model.generate_content(prompt)
        return response.text.strip()


def get_llm_client() -> BaseLLMClient:
    import os

    from src.config import settings

    provider = settings.resolved_llm_provider

    if provider == "stub":
        return StubLLMClient()

    if provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY not set. Add it to .env or set in environment."
            )
        return GeminiClient(model=settings.analyst_llm_model, api_key=api_key)

    raise NotImplementedError(f"Unknown LLM provider: {provider!r}")
