"""The six nodes of the conversational-analysis loop.

Privacy invariant (hard): the only data that ever reaches the LLM is the
schema (column names + dtypes), the N-row sample, the prior chat turns, and
the question. The full DataFrame is fetched from the in-process store inside
``execute_analysis`` and never serialized into a prompt.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from sqlalchemy import select

from analysis.store import (
    ensure_loaded,
    extract_sample,
    extract_schema as df_extract_schema,
)
from analysis.sandbox import run_pandas
from db.models import Dataset, Message, Session as SessionRow
from db.session import create_db_session
from graph.state import AgentState
from llm.client import LLMClient

_PROMPTS = Path(__file__).parent.parent / "prompts"
_SAMPLE_ROWS = 5
_PRIOR_TURN_WINDOW = 6  # sliding window: last ~6 turns


def _load_prompt(name: str) -> str:
    return (_PROMPTS / name).read_text(encoding="utf-8").strip()


# --------------------------------------------------------------------------- #
# extract_schema
# --------------------------------------------------------------------------- #
def extract_schema(state: AgentState) -> AgentState:
    """Load the session DataFrame + derive privacy-safe context and prior turns.

    No LLM. Reads the Dataset row for file_path/file_type so the DataFrame can
    be lazily reloaded after a restart, then derives schema + sample. Also
    reads the last K chat turns from the DB into ``prior_turns``.
    """
    try:
        session_id = state["session_id"]

        with create_db_session() as db:
            dataset = db.execute(
                select(Dataset).where(Dataset.session_id == session_id)
            ).scalars().first()
            if dataset is None:
                return {
                    **state,
                    "error": f"No dataset found for session {session_id!r}.",
                }
            file_path = dataset.file_path
            file_type = dataset.file_type

            prior = db.execute(
                select(Message)
                .where(Message.session_id == session_id)
                .order_by(Message.created_at.asc())
            ).scalars().all()
            # Materialize inside the session — instances expire on commit/close.
            prior_turns = [
                {"role": m.role, "content": m.content}
                for m in prior
            ][-_PRIOR_TURN_WINDOW:]

        df = ensure_loaded(session_id, file_path, file_type)
        schema = df_extract_schema(df)
        sample_rows = extract_sample(df, n=_SAMPLE_ROWS)

        return {
            **state,
            "schema": schema,
            "sample_rows": sample_rows,
            "prior_turns": prior_turns,
            "file_path": file_path,
            "file_type": file_type,
        }
    except Exception as exc:  # noqa: BLE001 — surfaced to handle_error
        return {**state, "error": f"Failed to load dataset context: {exc}"}


# --------------------------------------------------------------------------- #
# plan_analysis
# --------------------------------------------------------------------------- #
_FENCE_RE = re.compile(r"```(?:python|py)?\s*\n?(.*?)```", re.DOTALL | re.IGNORECASE)


def _parse_code(raw: str) -> str:
    """Extract the pandas snippet from a fenced block, robustly.

    Falls back to the raw text (stripped) if no fence is present.
    """
    if not raw:
        return ""
    match = _FENCE_RE.search(raw)
    if match:
        return match.group(1).strip()
    return raw.strip()


def _build_plan_prompt(state: AgentState) -> str:
    parts: list[str] = []
    parts.append("Schema (column name -> dtype):")
    parts.append(json.dumps(state.get("schema", []), ensure_ascii=False))
    parts.append("")
    parts.append(f"Sample rows (first {_SAMPLE_ROWS}, context only — NOT the full data):")
    parts.append(json.dumps(state.get("sample_rows", []), ensure_ascii=False))

    prior = state.get("prior_turns") or []
    if prior:
        parts.append("")
        parts.append("Prior conversation (for follow-up context):")
        for turn in prior:
            parts.append(f"  {turn.get('role')}: {turn.get('content')}")

    parts.append("")
    parts.append(f"Question: {state['question']}")

    exec_error = state.get("exec_error")
    if exec_error:
        parts.append("")
        parts.append(
            "Your previous code failed with this error — fix it and return "
            "corrected code:"
        )
        parts.append(str(exec_error))

    return "\n".join(parts)


def plan_analysis(state: AgentState) -> AgentState:
    """REAL Gemini: turn the privacy-safe context + question into pandas code."""
    try:
        system = _load_prompt("analysis.md")
        prompt = _build_plan_prompt(state)
        raw = LLMClient().call_model(prompt, system=system)
        code = _parse_code(raw or "")
        if not code:
            return {**state, "error": "The model returned no usable pandas code."}
        return {**state, "code": code}
    except Exception as exc:  # noqa: BLE001
        return {**state, "error": f"Planning the analysis failed: {exc}"}


# --------------------------------------------------------------------------- #
# execute_analysis
# --------------------------------------------------------------------------- #
def execute_analysis(state: AgentState) -> AgentState:
    """Run the snippet locally over the FULL DataFrame in the sandbox.

    On success: set ``result_repr`` and clear any prior ``exec_error``.
    On error: if ``retries < 1`` increment and set ``exec_error`` (routes back
    to plan_analysis); otherwise set ``error`` (routes to handle_error).
    """
    session_id = state["session_id"]
    retries = state.get("retries", 0)
    try:
        df = ensure_loaded(
            session_id,
            state.get("file_path") or "",
            state.get("file_type") or "csv",
        )
        result_repr = run_pandas(state["code"], df)
        return {**state, "result_repr": result_repr, "exec_error": None}
    except Exception as exc:  # noqa: BLE001 — sandbox raises with original text
        message = str(exc)
        if retries < 1:
            return {**state, "exec_error": message, "retries": retries + 1}
        return {
            **state,
            "error": f"The analysis code failed after a repair attempt: {message}",
        }


# --------------------------------------------------------------------------- #
# format_answer
# --------------------------------------------------------------------------- #
def _result_table(result_repr: dict | None) -> dict | None:
    """The result_repr is already the show-the-work table/scalar bundle."""
    return result_repr


def _templated_answer(question: str, result_repr: dict | None) -> str:
    """Fallback answer built from the computed result (still shows the work)."""
    if not result_repr:
        return "The analysis completed but produced no result."
    if result_repr.get("kind") == "scalar":
        return f"Result for \"{question}\": {result_repr.get('value')}"
    columns = result_repr.get("columns") or []
    rows = result_repr.get("rows") or []
    return (
        f"Result for \"{question}\": a table with columns {columns} "
        f"({len(rows)} row(s)). See the computed result below."
    )


def format_answer(state: AgentState) -> AgentState:
    """REAL Gemini: phrase a plain-English answer; fall back to a template.

    A Gemini failure here does NOT fail the turn — the work is already
    computed, so we fall back to a templated answer that still shows it.
    """
    question = state["question"]
    result_repr = state.get("result_repr")
    code = state.get("code")

    try:
        system = _load_prompt("format_answer.md")
        prompt = (
            f"Question: {question}\n\n"
            f"Computed result (from the full local dataset):\n"
            f"{json.dumps(result_repr, ensure_ascii=False)}"
        )
        answer = (LLMClient().call_model(prompt, system=system) or "").strip()
        if not answer:
            answer = _templated_answer(question, result_repr)
    except Exception:  # noqa: BLE001 — never fail the turn on phrasing
        answer = _templated_answer(question, result_repr)

    output_payload = {
        "answer": answer,
        "code": code,
        "result_table": _result_table(result_repr),
    }
    return {**state, "answer": answer, "output_payload": output_payload}


# --------------------------------------------------------------------------- #
# finalize
# --------------------------------------------------------------------------- #
def finalize(state: AgentState) -> AgentState:
    """Persist the user + assistant messages and mark the turn completed."""
    session_id = state["session_id"]
    question = state["question"]
    answer = state.get("answer") or ""
    code = state.get("code")
    result_repr = state.get("result_repr")

    with create_db_session() as db:
        db.add(
            Message(
                session_id=session_id,
                role="user",
                content=question,
            )
        )
        db.add(
            Message(
                session_id=session_id,
                role="assistant",
                content=answer,
                code=code,
                result_json=(
                    json.dumps(result_repr, ensure_ascii=False)
                    if result_repr is not None
                    else None
                ),
                status="completed",
            )
        )
        session_row = db.get(SessionRow, session_id)
        if session_row is not None:
            session_row.updated_at = session_row.updated_at  # touch via onupdate

    return {**state, "status": "completed"}


# --------------------------------------------------------------------------- #
# handle_error
# --------------------------------------------------------------------------- #
def handle_error(state: AgentState) -> AgentState:
    """Surface the readable error; persist nothing as a successful answer."""
    error = state.get("error") or state.get("exec_error") or "Unknown error"
    return {
        **state,
        "status": "failed",
        "answer": error,
        "output_payload": {"answer": error, "code": state.get("code"), "result_table": None},
    }
