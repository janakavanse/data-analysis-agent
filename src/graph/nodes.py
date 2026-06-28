"""Graph nodes for the code-execution analysis agent.

PRIVACY BOUNDARY (enforced here):
  The ONLY dataset data ever sent to the LLM is ``state["llm_context"]`` — the
  schema + a small sample (+ a small prior result on revise), built by
  ``analysis.engine.make_llm_context`` in the ``profile`` node. No node ever
  passes ``df`` or bulk rows to the LLM. ``execute_locally`` is the only place the
  full data is touched, and it runs locally — its output is never echoed back to
  the model except as a small error/code string on the revise loop.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from analysis.cost import estimate_cost
from analysis.engine import execute, make_llm_context
from graph.state import AgentState
from llm.client import LLMClient
from observability.events import get_logger

_PROMPT_DIR = Path(__file__).parent.parent / "prompts"
_log = get_logger("agent.nodes")

_CODE_FENCE = re.compile(r"```(?:python)?\s*(.*?)```", re.DOTALL)


def _load_prompt(name: str) -> str:
    return (_PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


def _accumulate(state: AgentState, tokens_in: int, tokens_out: int) -> dict:
    """Roll token usage into the state and recompute the running cost estimate."""
    total_in = state.get("tokens_in", 0) + tokens_in
    total_out = state.get("tokens_out", 0) + tokens_out
    model = LLMClient().model
    return {
        "tokens_in": total_in,
        "tokens_out": total_out,
        "cost_estimate": estimate_cost(model, total_in, total_out),
    }


def _extract_code(text: str) -> str:
    """Pull the single fenced python block; fall back to the whole text."""
    m = _CODE_FENCE.search(text or "")
    if m:
        return m.group(1).strip()
    return (text or "").strip()


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def profile(state: AgentState) -> AgentState:
    """Materialize the privacy-bounded LLM context from the dataset.

    This is where the redaction happens: make_llm_context returns ONLY
    schema + sample (+ prior_result). DuckDB read failure is fatal.
    """
    try:
        llm_context = make_llm_context(state["dataset_id"])
        return {**state, "llm_context": llm_context, "stage": "planning"}
    except Exception as exc:  # noqa: BLE001
        return {**state, "error": f"Failed to load dataset: {exc}", "stage": "planning"}


def plan(state: AgentState) -> AgentState:
    """Decide approach + SIMPLE/MULTI. Sees ONLY llm_context (schema+sample)."""
    try:
        system = _load_prompt("plan")
        ctx = state.get("llm_context", {})
        prompt = (
            f"Question: {state['question']}\n\n"
            f"Schema: {json.dumps(ctx.get('schema', []))}\n\n"
            f"Sample rows (truncated): {json.dumps(ctx.get('sample', []))}"
        )
        res = LLMClient().complete(prompt, system=system)
        text = res.text.strip()
        first_line = text.splitlines()[0].strip().upper() if text else ""
        is_simple = first_line.startswith("SIMPLE")
        return {
            **state,
            "plan": text,
            "is_simple": is_simple,
            "stage": "coding",
            **_accumulate(state, res.tokens_in, res.tokens_out),
        }
    except Exception as exc:  # noqa: BLE001
        return {**state, "error": f"Planning failed: {exc}", "stage": "coding"}


def generate_code(state: AgentState) -> AgentState:
    """Write pandas/DuckDB code assigning `result`. Sees ONLY schema/sample
    (+ prior code and error string on revise — never bulk data)."""
    try:
        system = _load_prompt("generate_code")
        ctx = state.get("llm_context", {})

        parts = [
            f"Question: {state['question']}",
            f"Approach: {state.get('plan', '')}",
            f"Schema: {json.dumps(ctx.get('schema', []))}",
            f"Sample rows (truncated): {json.dumps(ctx.get('sample', []))}",
        ]

        prior = state.get("exec_result") or {}
        is_revise = bool(prior.get("error"))
        if is_revise:
            parts.append(
                "Your previous code FAILED. Fix it.\n"
                f"Previous code:\n{state.get('code', '')}\n\n"
                f"Error:\n{prior['error']}"
            )

        prompt = "\n\n".join(parts)
        res = LLMClient().complete(prompt, system=system)
        code = _extract_code(res.text)

        # On a revise pass, bump the retry counter (the router caps at MAX_REVISIONS).
        revisions = state.get("revisions", 0) + (1 if is_revise else 0)

        # Transparency: store the EXACT bounded context the LLM saw. The data
        # portion is schema + sample + (small) prior result only — never df.
        llm_payload = {
            "system": system,
            "prompt": prompt,
            "context": {
                "schema": ctx.get("schema", []),
                "sample": ctx.get("sample", []),
                "prior_result": ctx.get("prior_result"),
            },
        }

        return {
            **state,
            "code": code,
            "llm_payload": llm_payload,
            "revisions": revisions,
            "stage": "running",
            **_accumulate(state, res.tokens_in, res.tokens_out),
        }
    except Exception as exc:  # noqa: BLE001
        return {**state, "error": f"Code generation failed: {exc}", "stage": "running"}


def execute_locally(state: AgentState) -> AgentState:
    """The observe step — run the code on the FULL data locally.

    Errors are CAPTURED into exec_result.error (never raised), to feed the
    revise loop. Bulk data never leaves this node.
    """
    exec_result = execute(state.get("code", ""), state["dataset_id"])
    code_hash = hash(state.get("code", "")) & 0xFFFFFFFF
    _log.info(
        "execute_code",
        run_id=state.get("run_id"),
        code_hash=f"{code_hash:08x}",
        ok=not exec_result.get("error"),
        error=exec_result.get("error"),
    )
    return {**state, "exec_result": exec_result, "stage": "running"}


def _result_to_table(result) -> dict:
    """Normalize an exec result into a {columns, rows} small table."""
    if isinstance(result, dict) and "columns" in result and "rows" in result:
        return {"columns": result["columns"], "rows": result["rows"]}
    # scalar or other shape — wrap it
    return {"columns": ["value"], "rows": [[result]]}


def summarize(state: AgentState) -> AgentState:
    """Plain-language answer over the SMALL result only."""
    try:
        system = _load_prompt("summarize")
        exec_result = state.get("exec_result") or {}
        result = exec_result.get("result")
        key_numbers = exec_result.get("key_numbers") or {}
        summary_table = _result_to_table(result) if result is not None else {"columns": [], "rows": []}
        # Reached summarize with an unresolved exec error => exhausted revisions:
        # return a flagged best-guess rather than crashing.
        flagged = bool(exec_result.get("error"))

        prompt_parts = [
            f"Question: {state['question']}",
            f"Computed result (small): {json.dumps(summary_table, default=str)}",
            f"Key numbers: {json.dumps(key_numbers, default=str)}",
        ]
        if flagged:
            prompt_parts.append(
                "NOTE: The analysis code could not run cleanly after retries. "
                f"What was attempted:\n{state.get('code', '')}\n"
                f"Last error: {exec_result.get('error')}\n"
                "Frame the answer as an approximate best-guess and say what was tried."
            )
        prompt = "\n\n".join(prompt_parts)

        res = LLMClient().complete(prompt, system=system)
        return {
            **state,
            "answer": res.text.strip(),
            "key_numbers": key_numbers,
            "summary_table": summary_table,
            "flagged": flagged,
            "stage": "charting",
            **_accumulate(state, res.tokens_in, res.tokens_out),
        }
    except Exception as exc:  # noqa: BLE001
        return {**state, "error": f"Summarize failed: {exc}", "stage": "charting"}


def _fallback_chart(table: dict) -> dict:
    """Rule-based chart when the LLM JSON is invalid.

    2-col table -> bar (categorical x) or line (numeric/ordered x).
    """
    columns = table.get("columns", [])
    rows = table.get("rows", [])
    if len(columns) < 2 or not rows:
        return {"data": [], "layout": {"title": "No chart available"}}

    xs = [r[0] for r in rows]
    ys = [r[1] for r in rows]
    x_numeric = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in xs)
    chart_type = "line" if x_numeric else "bar"
    return {
        "data": [{"type": chart_type, "x": xs, "y": ys}],
        "layout": {"title": f"{columns[1]} by {columns[0]}"},
    }


def _parse_chart_json(text: str) -> dict | None:
    raw = text.strip()
    m = _CODE_FENCE.search(raw)
    if m:
        raw = m.group(1).strip()
    # strip a leading ```json / trailing ``` if any survived
    raw = raw.strip().removeprefix("json").strip()
    try:
        spec = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None
    if isinstance(spec, dict) and "data" in spec and "layout" in spec:
        return spec
    return None


def select_chart(state: AgentState) -> AgentState:
    """Pick a Plotly figure spec; rule-based fallback on invalid JSON."""
    table = state.get("summary_table") or {"columns": [], "rows": []}
    try:
        system = _load_prompt("select_chart")
        prompt = (
            f"Question: {state['question']}\n\n"
            f"Result table: {json.dumps(table, default=str)}"
        )
        res = LLMClient().complete(prompt, system=system)
        spec = _parse_chart_json(res.text) or _fallback_chart(table)
        return {
            **state,
            "chart_spec": spec,
            "stage": "charting",
            **_accumulate(state, res.tokens_in, res.tokens_out),
        }
    except Exception:  # noqa: BLE001 — charting must never fail the run
        return {**state, "chart_spec": _fallback_chart(table), "stage": "charting"}


def suggest_followups(state: AgentState) -> AgentState:
    """Phase 2 stub — returns no follow-ups in Phase 1."""
    return {**state, "followups": []}


def finalize(state: AgentState) -> AgentState:
    return {**state, "stage": "done"}


def handle_error(state: AgentState) -> AgentState:
    _log.error("run_failed", run_id=state.get("run_id"), error=state.get("error"))
    return {**state, "stage": "done"}
