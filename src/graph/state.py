from typing import TypedDict


class AgentState(TypedDict, total=False):
    """State for the conversational-analysis loop.

    The DataFrame itself is NEVER held in state — it never serializes to the
    LLM or a checkpoint. It is fetched from the in-process store by
    ``session_id`` inside ``execute_analysis``. Only the privacy-safe context
    (schema + N sample rows + prior turns + the question) reaches the LLM.
    """

    # Identity
    run_id: str
    session_id: str

    # Input
    question: str
    schema: list[dict]          # [{name, dtype}, ...] — privacy-safe
    sample_rows: list[dict]     # first N rows (default 5) — the ONLY raw data the LLM sees
    prior_turns: list[dict]     # [{role, content}, ...] — sliding-window chat context

    # Pipeline data (populated progressively)
    code: str | None            # pandas snippet emitted by plan_analysis
    result_repr: dict | None    # {kind, columns?, rows?, value?}
    exec_error: str | None      # traceback from a failed exec — drives the repair retry
    retries: int                # repair attempts so far (cap = 1)

    # Reload metadata (so execute/extract can lazily reload the DataFrame)
    file_path: str | None
    file_type: str | None

    # Output
    answer: str | None
    output_payload: dict | None  # {answer, code, result_table}

    # Control
    error: str | None
    status: str | None           # "completed" | "failed"
