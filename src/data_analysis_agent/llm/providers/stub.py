from data_analysis_agent.llm.providers.base import LLMProvider
from data_analysis_agent.llm.types import LLMResult


class StubLLMProvider(LLMProvider):
    """Offline stub — returns plausible shaped output without any API call."""

    def complete(self, prompt: str) -> LLMResult:
        if "<node:analyze>" in prompt:
            text = (
                "Based on the data provided, here is the analysis:\n\n"
                "The dataset contains structured tabular data across multiple columns. "
                "Looking at the values and distributions, the patterns suggest a typical "
                "business dataset with numerical and categorical features.\n\n"
                "**Note:** This is a stub response generated in offline mode. "
                "Set DATAANALYSIS_OPENROUTER_API_KEY to get real answers."
            )
        else:
            text = "(stub) No response — unrecognized node tag in prompt."

        return LLMResult(
            text=text,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            estimated_cost_usd=0.0,
        )
