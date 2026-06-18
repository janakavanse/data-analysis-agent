from <package>.graph.agent import agent_graph
from <package>.graph.state import AgentState
from <package>.db.session import create_db_session, init_db
from <package>.db.models import RunRow


def run_agent() -> str:
    init_db()
    with create_db_session() as session:
        run = RunRow()
        session.add(run)
        session.flush()
        run_id = run.id

    initial: AgentState = {"run_id": run_id, "error": None}
    final = agent_graph.invoke(initial)

    with create_db_session() as session:
        run = session.get(RunRow, run_id)
        run.status = final.get("status", "completed")
        run.error_message = final.get("error")

    return run_id
