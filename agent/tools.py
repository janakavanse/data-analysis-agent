from langchain_core.tools import tool


@tool
def file_load() -> str:
    """Load and inspect the uploaded data file for this session. Returns the file shape, column names, data types, and first few rows. Call this before running any analysis."""
    from .sessions import current_session_id, get_session
    sid = current_session_id.get()
    sess = get_session(sid) if sid else None
    df = sess.by_id.get("main") if sess else None
    if df is None:
        return "No data file is loaded for this session. Please upload a CSV or JSON file first."
    lines = [
        f"Shape: {df.shape[0]} rows × {df.shape[1]} columns",
        f"Columns: {list(df.columns)}",
        f"Data types:\n{df.dtypes.to_string()}",
        f"First 3 rows:\n{df.head(3).to_string()}",
    ]
    return "\n".join(lines)


@tool
def python_exec(code: str) -> str:
    """Execute a single Python expression on the loaded DataFrame (df) using pandas (pd) and numpy (np). Must be one expression — not multi-line code or import statements. Examples: df.mean(), df['col'].value_counts(), df.describe(). Returns the result as text."""
    import pandas as pd
    import numpy as np
    from .sessions import current_session_id, get_session
    from .guardrails import safe_eval
    sid = current_session_id.get()
    sess = get_session(sid) if sid else None
    df = sess.by_id.get("main") if sess else None
    if df is None:
        return "No data file is loaded for this session. Please upload a file first."
    try:
        result = safe_eval(code, {"df": df, "pd": pd, "np": np})
        return str(result)[:2000]
    except ValueError as e:
        return f"Code rejected by safety check: {e}. Use only pandas/numpy expressions on df."
    except Exception as e:
        return f"Execution error: {type(e).__name__}: {e}"


@tool
def sql_explorer(query: str = "") -> str:
    """Explore SQL databases with natural language queries. (P2 stub — coming in v2)"""
    return "SQL explorer coming in v2 — connect a SQLite file and ask schema or query questions once this capability is promoted."


@tool
def multi_source_fetch(source: str = "") -> str:
    """Analyze data from multiple external sources like Google Sheets or REST APIs. (P3 stub — coming in v3)"""
    return "Multi-source analysis coming in v3 — external data source connectors (Google Sheets, REST APIs) will be available once this capability is promoted."


@tool
def write_todos(todos: list[str]) -> str:
    """Record a short ordered plan (the Deep-Agent planning scratchpad). Call before multi-step work."""
    return "Plan recorded:\n" + "\n".join(f"{i+1}. {t}" for i, t in enumerate(todos))


@tool
def finish(answer: str) -> str:
    """Return the final answer to the user and end the run. Call exactly once when done."""
    return answer


TOOLS = [file_load, python_exec, sql_explorer, multi_source_fetch, write_todos, finish]
TOOL_MAP = {t.name: t for t in TOOLS}
FINISH = "finish"
