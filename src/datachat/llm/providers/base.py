from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float  # estimated USD cost for this call


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> LLMResult:
        """Send a prompt and return the result with token counts and cost."""
        ...
