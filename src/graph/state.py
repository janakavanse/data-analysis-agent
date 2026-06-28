from typing import TypedDict


class AgentState(TypedDict, total=False):
    """State for the privacy-preserving analysis pipeline (see spec/agent.md).

    Privacy invariant: ``schema``, ``profile``, ``result_summary`` are the ONLY
    data-derived fields the LLM nodes (plan / generate_code / summarize) may read.
    Raw rows live only inside ``execute_locally`` (the sandbox) and never enter
    this state.
    """

    # Identity
    run_id: str          # query/run id, set at init
    session_id: str      # conversation id
    dataset_id: str      # active dataset

    # Input
    question: str        # user's natural-language question
    messages: list       # prior turns [{role, content}] — conversation memory

    # Privacy-safe context (LLM-visible)
    schema: dict         # column names + dtypes
    profile: dict        # column profiles/summaries (NO rows)
    dataset_path: str    # local file path — used by execute_locally ONLY

    # Pipeline data
    plan: str            # analysis plan from `plan`
    code: str            # pandas from `generate_code`
    exec_result: dict    # structured result from sandbox (local, raw-derived)
    result_summary: dict # privacy-safe summary of exec_result for the LLM

    # Output
    answer: str          # plain-language answer (streamed by the runner)
    repair_attempted: bool  # one-shot code repair guard (True once any exec error seen)
    exec_failures: int      # count of sandbox execution failures (drives the repair loop)

    # Privacy audit — exactly what was sent to the LLM, per node
    llm_payloads: list   # [{node, system, user}, ...] — recorded to queries.llm_payloads_json

    # Token accounting (best-effort, from the summarize stream)
    prompt_tokens: int
    completion_tokens: int

    # Control
    error: str | None
    status: str          # "completed" | "failed"
