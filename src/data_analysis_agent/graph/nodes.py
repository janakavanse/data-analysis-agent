import structlog

from data_analysis_agent.graph.state import AgentState

log = structlog.get_logger()


def load_data(state: AgentState) -> AgentState:
    try:
        from data_analysis_agent.tools.csv_parser import parse_csv
        col_names, row_count, sample = parse_csv(state["csv_path"])
        return {
            **state,
            "column_names": col_names,
            "row_count": row_count,
            "data_sample": sample,
        }
    except Exception as exc:
        log.error("load_data.failed", run_id=state.get("run_id"), error=str(exc))
        return {**state, "error": f"Failed to read CSV: {exc}"}


def analyze(state: AgentState) -> AgentState:
    try:
        from data_analysis_agent.llm.client import get_llm_client
        prompt = (
            "<node:analyze>\n"
            f"Dataset columns: {', '.join(state.get('column_names', []))}\n\n"
            f"Sample data (first 5 rows):\n{state.get('data_sample', '')}\n\n"
            f"User question: {state['question']}\n\n"
            "Please answer the user's question based on the data above. "
            "Be concise and accurate."
        )
        result = get_llm_client().complete(prompt)
        prior_requests = state.get("api_request_count", 0)
        log.info(
            "analyze.done",
            run_id=state.get("run_id"),
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            estimated_cost_usd=result.estimated_cost_usd,
        )
        return {
            **state,
            "answer": result.text,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "total_tokens": result.total_tokens,
            "estimated_cost_usd": result.estimated_cost_usd,
            "api_request_count": prior_requests + 1,
        }
    except Exception as exc:
        log.error("analyze.failed", run_id=state.get("run_id"), error=str(exc))
        return {**state, "error": f"LLM analysis failed: {exc}"}


def finalize(state: AgentState) -> AgentState:
    try:
        from data_analysis_agent.db.session import create_db_session
        from data_analysis_agent.db.models import QueryRecordRow, AgentRunRow
        with create_db_session() as session:
            qr = session.get(QueryRecordRow, state["query_record_id"])
            if qr:
                qr.answer = state.get("answer", "")
                qr.status = "completed"
                qr.input_tokens = state.get("input_tokens", 0)
                qr.output_tokens = state.get("output_tokens", 0)
                qr.total_tokens = state.get("total_tokens", 0)
                qr.estimated_cost_usd = state.get("estimated_cost_usd")
                qr.api_request_count = state.get("api_request_count", 1)
            run = session.get(AgentRunRow, state["run_id"])
            if run:
                run.status = "completed"
        log.info("finalize.done", run_id=state.get("run_id"))
        return state
    except Exception as exc:
        log.error("finalize.failed", run_id=state.get("run_id"), error=str(exc))
        return {**state, "error": f"Finalize failed: {exc}"}


def handle_error(state: AgentState) -> AgentState:
    try:
        from data_analysis_agent.db.session import create_db_session
        from data_analysis_agent.db.models import QueryRecordRow, AgentRunRow
        error_msg = state.get("error", "Unknown error")
        with create_db_session() as session:
            qr = session.get(QueryRecordRow, state.get("query_record_id", ""))
            if qr:
                qr.status = "failed"
                qr.error_message = error_msg
            run = session.get(AgentRunRow, state.get("run_id", ""))
            if run:
                run.status = "failed"
                run.error_message = error_msg
        log.error("pipeline.failed", run_id=state.get("run_id"), error=error_msg)
    except Exception as exc:
        log.error("handle_error.db_write_failed", error=str(exc))
    return state
