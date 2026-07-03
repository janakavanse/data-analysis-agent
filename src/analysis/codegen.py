"""Schema-only prompt construction for the generate_code node.

The function signature below makes it structurally impossible to pass a
pandas.DataFrame or raw data through this module: parameters are only a
DatasetSchema (aggregate metadata), plain strings, and small text dicts.
"""
import re
from pathlib import Path

from config.settings import get_settings
from domain.dataset import DatasetSchema

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "codegen.md"

_CODE_FENCE_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8").strip()


def build_codegen_prompt(
    schema: DatasetSchema,
    question: str,
    history: list[dict],
    prior_error: str | None,
) -> tuple[str, str]:
    """Returns (system_prompt, user_prompt). No parameter here can ever carry
    a DataFrame or raw row data — only schema metadata and plain strings."""
    system_prompt = _load_system_prompt()

    n_turns = get_settings().conversation_history_turns
    recent_history = history[-n_turns:] if n_turns > 0 else []

    parts: list[str] = []
    parts.append(f"Dataset schema (JSON, aggregate metadata only):\n{schema.model_dump_json()}")

    if recent_history:
        history_lines = ["Prior conversation turns in this session (most recent last):"]
        for turn in recent_history:
            history_lines.append(f"Q: {turn.get('question', '')}")
            history_lines.append(f"A: {turn.get('answer', '')}")
        parts.append("\n".join(history_lines))

    parts.append(f"Question: {question}")

    if prior_error:
        parts.append(
            "The previous attempt failed with this execution error:\n"
            f"{prior_error}\n"
            "Produce corrected code that avoids this error."
        )

    user_prompt = "\n\n".join(parts)
    return system_prompt, user_prompt


def extract_code_from_response(text: str) -> str:
    """Strips a fenced ```python ... ``` block, or returns the bare text if
    no fence is found."""
    match = _CODE_FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    return text.strip()
