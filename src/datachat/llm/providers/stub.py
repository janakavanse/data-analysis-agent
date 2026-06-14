from datachat.llm.providers.base import LLMProvider, LLMResult


class StubLLMProvider(LLMProvider):
    """Deterministic stub — branches on <node:query> tag injected by pipeline nodes."""

    def generate(self, prompt: str) -> LLMResult:
        if "<node:query>" in prompt:
            text = (
                "**Stub answer (no Gemini API key set)**\n\n"
                "Based on the uploaded CSV data, here is a stub response. "
                "To get real answers, set the GEMINI_API_KEY environment variable.\n\n"
                "This stub confirms the pipeline is wired correctly end-to-end."
            )
        else:
            text = "Stub response: unrecognised node tag."
        return LLMResult(text=text, input_tokens=0, output_tokens=0, cost_usd=0.0)
