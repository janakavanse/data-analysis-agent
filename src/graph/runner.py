"""Entry points into the analysis graph.

``run_analysis`` is the user-facing entry the API slice calls: one question
over the active DataFrame for a session, returning the show-the-work payload.
The legacy ``run_agent`` / ``RunRow`` bookkeeping is retained for orthogonal
agent-run tracking and is not user-facing.
"""

from uuid import uuid4

from graph.agent import agentic_ai
from graph.state import AgentState
from db.session import create_db_session
from db.models import RunRow


def run_analysis(session_id: str, question: str) -> dict:
    """Run one analysis turn over the session's DataFrame.

    Args:
        session_id: the session whose active DataFrame the question is asked of.
        question: the user's plain-English question.

    Returns:
        The ``output_payload`` ``{answer, code, result_table}`` on success. On a
        failed turn, returns ``{answer, code, result_table, status, error}`` where
        ``answer`` carries the readable error message (status == "failed").

    Synchronous; the DataFrame is fetched from the in-process store (lazily
    reloaded from disk if absent) inside the graph — never serialized to the LLM.
    """
    initial: AgentState = {
        "run_id": str(uuid4()),
        "session_id": session_id,
        "question": question,
        "retries": 0,
        "error": None,
    }
    final = agentic_ai.invoke(initial)

    payload = final.get("output_payload") or {
        "answer": final.get("answer") or final.get("error") or "No answer produced.",
        "code": final.get("code"),
        "result_table": final.get("result_repr"),
    }

    status = final.get("status", "completed")
    if status == "failed":
        return {
            **payload,
            "status": "failed",
            "error": final.get("error") or payload.get("answer"),
        }
    return {**payload, "status": "completed"}


def run_agent(input_text: str) -> str:
    """Legacy agent-run bookkeeping entry (not user-facing).

    Retained for the orthogonal ``RunRow`` tracking table. It records a run row
    against the supplied input text. Kept importable so existing run tracking
    continues to work; the conversational-analysis path uses ``run_analysis``.
    """
    with create_db_session() as session:
        run = RunRow(input_text=input_text, status="completed")
        session.add(run)
        session.flush()
        run_id = run.id

    return run_id
