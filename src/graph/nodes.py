"""Graph nodes for the privacy-preserving analysis pipeline (see spec/agent.md).

Privacy boundary (HARD):
- ``plan``, ``generate_code``, ``summarize`` build LLM payloads from ONLY the
  schema / profile / result_summary. They never see raw rows.
- ``execute_locally`` is the ONLY node that loads the real file and runs code,
  via the out-of-process sandbox. It makes NO LLM call.

Every LLM payload is appended to ``state["llm_payloads"]`` so the runner can
persist the full privacy audit to ``queries.llm_payloads_json``.
"""

from __future__ import annotations

from analysis import stream_answer
from analysis.codegen import generate_code as _gen_code
from analysis.planner import generate_plan as _gen_plan
from execution.sandbox import run_pandas
from graph.state import AgentState
from observability.events import get_logger

logger = get_logger("graph.node")


def _record_payload(state: AgentState, payload: dict) -> list:
    payloads = list(state.get("llm_payloads") or [])
    payloads.append(payload)
    return payloads


def plan(state: AgentState) -> AgentState:
    run_id = state.get("run_id")
    try:
        text, payload = _gen_plan(
            state["question"],
            state.get("schema") or {},
            state.get("profile") or {},
            state.get("messages"),
        )
        logger.info("node.plan", run_id=run_id, plan_chars=len(text))
        return {
            **state,
            "plan": text,
            "llm_payloads": _record_payload(state, payload),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("node.plan.error", run_id=run_id, error=str(exc))
        return {**state, "error": f"planning failed: {exc}"}


def generate_code(state: AgentState) -> AgentState:
    run_id = state.get("run_id")
    repairing = bool(state.get("repair_attempted"))
    try:
        prior_code = state.get("code") if repairing else None
        prior_err = state.get("error") if repairing else None
        text, payload = _gen_code(
            state.get("plan") or "",
            state.get("schema") or {},
            prior_code,
            prior_err,
        )
        logger.info("node.generate_code", run_id=run_id, repairing=repairing,
                    code_chars=len(text))
        return {
            **state,
            "code": text,
            "error": None,  # clear any captured exec error we just fed back
            "llm_payloads": _record_payload(state, payload),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("node.generate_code.error", run_id=run_id, error=str(exc))
        return {**state, "error": f"code generation failed: {exc}"}


def execute_locally(state: AgentState) -> AgentState:
    """The privacy boundary: load raw rows + run code in the sandbox. No LLM."""
    run_id = state.get("run_id")
    res = run_pandas(state.get("code") or "", state["dataset_path"])
    if res.get("ok"):
        logger.info("node.execute_locally", run_id=run_id, kind=res.get("kind"),
                    duration_ms=res.get("duration_ms"))
        return {
            **state,
            "exec_result": res,
            "result_summary": res.get("result_summary"),
            "error": None,
        }
    # Sandbox code/timeout error — surface for the one-shot repair router.
    err = f"{res.get('error_type', 'ExecError')}: {res.get('error', '')}".strip()
    failures = int(state.get("exec_failures", 0)) + 1
    logger.warning("node.execute_locally.error", run_id=run_id, error=err,
                   exec_failures=failures)
    return {
        **state,
        "exec_result": res,
        "error": err,
        "exec_failures": failures,
        "repair_attempted": True,  # an exec error has occurred at least once
    }


def summarize(state: AgentState) -> AgentState:
    """Non-streaming summarize for graph.invoke; the runner streams the same helper."""
    run_id = state.get("run_id")
    try:
        chunks: list[str] = []
        payload: dict | None = None
        usage: dict = {}
        for kind, value in stream_answer(
            state["question"], state.get("result_summary") or {}
        ):
            if kind == "payload":
                payload = value
            elif kind == "token":
                chunks.append(value)
            elif kind == "usage":
                usage = value
        answer = "".join(chunks).strip()
        logger.info("node.summarize", run_id=run_id, answer_chars=len(answer))
        out: AgentState = {
            **state,
            "answer": answer,
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
        }
        if payload is not None:
            out["llm_payloads"] = _record_payload(state, payload)
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("node.summarize.error", run_id=run_id, error=str(exc))
        return {**state, "error": f"summarize failed: {exc}"}


def handle_error(state: AgentState) -> AgentState:
    logger.warning("node.handle_error", run_id=state.get("run_id"),
                   error=state.get("error"))
    return {**state, "status": "failed"}


def finalize(state: AgentState) -> AgentState:
    logger.info("node.finalize", run_id=state.get("run_id"))
    return {**state, "status": "completed"}
