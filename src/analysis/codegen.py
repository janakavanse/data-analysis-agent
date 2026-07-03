"""Schema-only prompt construction for the generate_code node.

The function signature below makes it structurally impossible to pass a
pandas.DataFrame or raw data through this module: parameters are only a
DatasetSchema (aggregate metadata), plain strings, and small text dicts.
"""
import json
import re
from dataclasses import dataclass
from pathlib import Path

from config.settings import get_settings
from domain.dataset import DatasetSchema

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "codegen.md"

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL)

_VALID_STATUSES = ("ok", "needs_clarification", "unanswerable")


@dataclass
class CodegenDecision:
    status: str
    code: str | None
    followups: list[str]
    message: str | None


class CodegenResponseError(ValueError):
    """Raised when the model's response cannot be parsed into the expected
    structured JSON contract."""


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


def parse_codegen_response(text: str) -> CodegenDecision:
    """Parses the model's structured JSON decision out of its response text
    (handling an optional ```json fence around the object). Raises
    CodegenResponseError if the response cannot be parsed into the expected
    {status, code, followups, message} shape — this surfaces as a normal
    LLM-call failure rather than a silent wrong-shape crash downstream."""
    raw = text.strip()
    match = _JSON_FENCE_RE.search(raw)
    candidate = match.group(1).strip() if match else raw

    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise CodegenResponseError(
            f"Could not parse JSON from model response: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise CodegenResponseError("Model response JSON was not an object")

    status = payload.get("status")
    if status not in _VALID_STATUSES:
        raise CodegenResponseError(
            f"Model response had invalid or missing 'status': {status!r}"
        )

    code = payload.get("code")
    if status == "ok" and (not isinstance(code, str) or not code.strip()):
        raise CodegenResponseError("status=='ok' but 'code' was missing/empty")
    if status != "ok":
        code = None

    followups = payload.get("followups") or []
    if not isinstance(followups, list):
        raise CodegenResponseError("'followups' must be a list")
    followups = [f for f in followups if isinstance(f, str) and f.strip()][:3]

    message = payload.get("message")
    if status != "ok" and (not isinstance(message, str) or not message.strip()):
        raise CodegenResponseError(
            f"status=={status!r} but 'message' was missing/empty"
        )
    if status == "ok":
        message = None

    return CodegenDecision(status=status, code=code, followups=followups, message=message)
