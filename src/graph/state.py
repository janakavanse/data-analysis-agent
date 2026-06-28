from typing import TypedDict


class AgentState(TypedDict, total=False):
    """LangGraph state for the code-execution analysis agent.

    Phase 1 fields: everything except ``session_id``, ``messages`` (empty list),
    and ``followups`` (empty list) — those activate in Phase 2.
    """

    # Identity
    run_id: str                       # set by runner
    dataset_id: str                   # set by runner (the dataset being analysed)
    session_id: str | None            # Phase 2: persistent session

    # Input
    question: str                     # user's plain-language question
    messages: list                    # conversation history (Phase 2); [] in Phase 1

    # LLM-facing context (privacy-bounded — the ONLY dataset data the LLM sees)
    llm_context: dict                 # {schema, sample, prior_result} from make_llm_context()

    # Pipeline data (populated progressively)
    plan: str                         # plan node output (approach + simple/multi flag)
    is_simple: bool                   # plan node: fast single-pass vs multi-step
    code: str                         # generate_code node: the pandas/SQL snippet
    exec_result: dict                 # execute_locally: {result, key_numbers, stdout, error}
    revisions: int                    # count of generate->execute retries (cap MAX_REVISIONS)

    # Output
    answer: str                       # summarize node: plain-language prose
    key_numbers: dict                 # headline numbers
    summary_table: dict               # the small result as {columns, rows}
    chart_spec: dict                  # select_chart: Plotly figure spec
    followups: list                   # Phase 2: suggested follow-up questions
    llm_payload: dict                 # exact context sent to the LLM (transparency)
    tokens_in: int                    # accumulated across nodes
    tokens_out: int
    cost_estimate: float

    # Control
    stage: str                        # "planning"|"coding"|"running"|"charting"|"done"
    error: str | None                 # set by any node on fatal failure
    flagged: bool                     # best-guess returned after exhausting revisions
