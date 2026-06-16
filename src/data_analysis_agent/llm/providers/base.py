from abc import ABC, abstractmethod

from data_analysis_agent.llm.types import LLMResult


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, prompt: str) -> LLMResult:
        """Send prompt and return result with text and usage stats."""
