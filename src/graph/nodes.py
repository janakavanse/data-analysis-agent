import json
import time
from datetime import datetime, timezone

from analysis import codegen, sandbox
from db.models import QueryRow
from db.session import create_db_session
from domain.dataset import DatasetSchema
from graph.state import AgentState
from llm.client import LLMClient
from observability.events import get_logger

logger = get_logger("graph.nodes")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _set_status(query_id: str, status: str) -> None:
    with create_db_session() as db:
        row = db.get(QueryRow, query_id)
        if row is not None:
            row.status = status


def generate_code(state: AgentState) -> AgentState:
    is_retry = state.get("last_error") is not None
    _set_status(state["query_id"], "generating_code")

    schema = DatasetSchema(**state["dataset_schema"])
    system_prompt, user_prompt = codegen.build_codegen_prompt(
        schema,
        state["question"],
        state.get("conversation_history", []),
        state.get("last_error") if is_retry else None,
    )

    client = LLMClient()
    start = time.monotonic()
    try:
        text, usage = client.call_model_with_usage(user_prompt, system=system_prompt)
    except Exception as exc:  # noqa: BLE001 - fatal LLM-call failure
        logger.error(
            "generate_code.llm_call_failed",
            query_id=state["query_id"],
            error=str(exc),
        )
        return {**state, "error": str(exc)}

    latency_ms = int((time.monotonic() - start) * 1000)
    try:
        decision = codegen.parse_codegen_response(text)
    except codegen.CodegenResponseError as exc:
        logger.error(
            "generate_code.response_parse_failed",
            query_id=state["query_id"],
            error=str(exc),
        )
        return {**state, "error": str(exc)}

    logger.info(
        "generate_code.completed",
        query_id=state["query_id"],
        question=state["question"],
        token_usage=usage,
        latency_ms=latency_ms,
        model=getattr(client._provider, "_model", None),
        is_retry=is_retry,
        status_decision=decision.status,
    )

    return {
        **state,
        "generated_code": decision.code,
        "status_decision": decision.status,
        "followups": decision.followups,
        "clarification_message": decision.message,
        "token_usage": usage,
        "retry_count": 1 if is_retry else state.get("retry_count", 0),
        "error": None,
    }


def execute_code(state: AgentState) -> AgentState:
    _set_status(state["query_id"], "running_analysis")
    try:
        result = sandbox.execute_generated_code(
            state["generated_code"],
            state["dataset_path"],
            state["file_type"],
        )
    except sandbox.SandboxExecutionError as exc:
        logger.warning(
            "execute_code.failed",
            query_id=state["query_id"],
            error=str(exc),
            retry_count=state.get("retry_count", 0),
        )
        return {**state, "last_error": str(exc)}

    logger.info("execute_code.succeeded", query_id=state["query_id"])
    return {
        **state,
        "answer_text": result["answer"],
        "result_table": result["table"],
        "chart_spec_json": result.get("chart_spec_json"),
        "last_error": None,
    }


def finalize_clarification(state: AgentState) -> AgentState:
    """Terminal path for status_decision in {needs_clarification, unanswerable}.
    No code was ever executed; persists the message and status directly."""
    status_decision = state.get("status_decision") or "unanswerable"
    message = state.get("clarification_message") or "The question could not be answered."
    with create_db_session() as db:
        row = db.get(QueryRow, state["query_id"])
        if row is not None:
            row.status = status_decision
            row.error_message = message
            row.generated_code = None
            row.suggested_followups_json = None
            row.completed_at = _now()

    logger.info(
        "query.terminal_clarification",
        query_id=state["query_id"],
        status_decision=status_decision,
    )
    return {**state, "status": status_decision}


def handle_error(state: AgentState) -> AgentState:
    error_message = state.get("error") or state.get("last_error") or "Unknown error"
    with create_db_session() as db:
        row = db.get(QueryRow, state["query_id"])
        if row is not None:
            row.status = "failed"
            row.error_message = error_message
            row.completed_at = _now()

    logger.error("query.failed", query_id=state["query_id"], error=error_message)
    return {**state, "status": "failed"}


def finalize(state: AgentState) -> AgentState:
    token_usage = state.get("token_usage") or {}
    result_table = state.get("result_table")
    followups = state.get("followups") or []
    chart_spec_json = state.get("chart_spec_json")
    with create_db_session() as db:
        row = db.get(QueryRow, state["query_id"])
        if row is not None:
            row.status = "completed"
            row.answer_text = state.get("answer_text")
            row.result_table_json = json.dumps(result_table) if result_table is not None else None
            row.generated_code = state.get("generated_code")
            row.retry_count = state.get("retry_count", 0)
            row.prompt_tokens = token_usage.get("prompt_tokens")
            row.completion_tokens = token_usage.get("completion_tokens")
            row.thinking_tokens = token_usage.get("thinking_tokens")
            row.total_tokens = token_usage.get("total_tokens")
            row.chart_spec_json = chart_spec_json
            row.suggested_followups_json = json.dumps(followups) if followups else None
            row.completed_at = _now()

    logger.info("query.completed", query_id=state["query_id"])
    return {**state, "status": "completed"}
