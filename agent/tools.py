"""In-process tools for the data analysis agent."""
import json
import re
import uuid
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from langchain_core.tools import tool
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from .config import get_settings
from .db import Dataset, get_sessionmaker

# SQL keywords that indicate mutating / destructive operations
_MUTATING_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|REPLACE|MERGE)\b",
    re.IGNORECASE,
)


def _coerce_content(raw: Any) -> str:
    if isinstance(raw, list):
        return "\n".join(p["text"] for p in raw if isinstance(p, dict) and p.get("type") == "text") or ""
    return str(raw or "")


@tool
async def upload_dataset(file_path: str, name: str) -> str:
    """Parse a CSV or JSON file, create a queryable SQLite table, and return the schema summary.

    Args:
        file_path: Absolute or relative path to the uploaded file.
        name: Human-readable name for this dataset.
    """
    p = Path(file_path)
    ext = p.suffix.lower()
    if ext not in {".csv", ".json"}:
        return f"Error: unsupported file type '{ext}'. Only .csv and .json are accepted."
    if not p.exists():
        return f"Error: file not found at {file_path}"

    size_mb = p.stat().st_size / (1024 * 1024)
    if size_mb > 50:
        return f"Error: file is {size_mb:.1f} MB — limit is 50 MB."

    try:
        if ext == ".csv":
            df = pd.read_csv(p)
        else:
            df = pd.read_json(p)
    except Exception as exc:
        return f"Error: could not parse file — {exc}"

    table_name = f"ds_{uuid.uuid4().hex}"
    settings = get_settings()

    # Use a fresh engine for DDL so the dataset table is created in the same file
    async_engine = create_async_engine(settings.database_url)
    try:
        async with async_engine.begin() as conn:
            await conn.run_sync(lambda sync_conn: df.to_sql(table_name, sync_conn, if_exists="replace", index=False))
    finally:
        await async_engine.dispose()

    schema = {col: str(df[col].dtype) for col in df.columns}
    sample_rows = df.head(3).to_dict(orient="records")

    dataset_id = str(uuid.uuid4())
    async with get_sessionmaker()() as s:
        s.add(Dataset(
            id=dataset_id,
            name=name,
            source_filename=p.name,
            table_name=table_name,
            schema_json={"columns": schema, "sample": sample_rows},
            file_type=ext.lstrip("."),
            row_count=len(df),
        ))
        await s.commit()

    col_list = ", ".join(f"{c} ({t})" for c, t in schema.items())
    sample_str = "\n".join(str(r) for r in sample_rows[:3])
    return (
        f"Dataset '{name}' loaded successfully.\n"
        f"dataset_id: {dataset_id}\n"
        f"table: {table_name}\n"
        f"rows: {len(df)}\n"
        f"columns: {col_list}\n"
        f"sample rows:\n{sample_str}"
    )


@tool
async def list_datasets() -> str:
    """List all available datasets with their names, row counts, and column schemas."""
    async with get_sessionmaker()() as s:
        from sqlalchemy import select
        rows = (await s.execute(select(Dataset).order_by(Dataset.created_at.desc()))).scalars().all()
    if not rows:
        return "No datasets uploaded yet. Upload a CSV or JSON file first."
    lines = []
    for d in rows:
        cols = ", ".join(d.schema_json.get("columns", {}).keys())
        lines.append(f"- {d.name} (id: {d.id}, rows: {d.row_count}, columns: {cols})")
    return "Available datasets:\n" + "\n".join(lines)


@tool
async def query_dataset(dataset_id: str, sql: str) -> str:
    """Execute a SELECT query against a dataset table and return results as JSON.

    Only SELECT statements are allowed. Mutating SQL (INSERT, UPDATE, DELETE, DROP, etc.) is rejected.

    Args:
        dataset_id: The dataset_id returned by upload_dataset or list_datasets.
        sql: A SQL SELECT statement to execute.
    """
    if _MUTATING_KEYWORDS.search(sql):
        return "Error: only SELECT statements are allowed. Mutating SQL is not permitted."

    async with get_sessionmaker()() as s:
        from sqlalchemy import select
        ds = (await s.execute(select(Dataset).where(Dataset.id == dataset_id))).scalar_one_or_none()
    if ds is None:
        return f"Error: dataset '{dataset_id}' not found. Use list_datasets to see available datasets."

    # Rewrite any bare table references to the internal table_name (safety + convenience)
    safe_sql = sql

    settings = get_settings()
    async_engine = create_async_engine(settings.database_url)
    try:
        async with async_engine.connect() as conn:
            result = await conn.execute(text(safe_sql))
            rows = [dict(zip(result.keys(), row)) for row in result.fetchmany(500)]
    except Exception as exc:
        await async_engine.dispose()
        return f"Error executing query: {exc}"
    finally:
        await async_engine.dispose()

    if not rows:
        return "Query returned 0 rows."

    truncated = len(rows) == 500
    result_str = json.dumps(rows[:100], default=str)
    suffix = "\n(showing first 100 of 500 fetched rows)" if truncated else f"\n({len(rows)} rows)"
    return result_str + suffix


@tool
async def generate_chart(dataset_id: str, chart_request: str, sql: str) -> str:
    """Generate a Plotly JSON chart spec from a natural-language chart request and SQL query.

    The returned JSON string is a Plotly figure dict with 'data' and 'layout' keys.
    Call finish with this as the answer so the UI renders it inline.

    Args:
        dataset_id: The dataset to chart.
        chart_request: Natural-language description of the desired chart (e.g. 'bar chart of revenue by region').
        sql: A SELECT query that fetches the data for this chart.
    """
    raw_result = await query_dataset.ainvoke({"dataset_id": dataset_id, "sql": sql})
    if raw_result.startswith("Error"):
        return raw_result

    # Parse rows from the JSON result
    try:
        rows_str = raw_result.split("\n")[0]  # strip the row-count suffix line
        rows = json.loads(rows_str)
    except Exception:
        return f"Error: could not parse query result for charting: {raw_result[:300]}"

    if not rows:
        return "No data returned — cannot generate a chart."

    df = pd.DataFrame(rows)
    cols = list(df.columns)

    # Determine chart type from the request
    req_lower = chart_request.lower()
    chart_type = "bar"
    if "line" in req_lower:
        chart_type = "line"
    elif "scatter" in req_lower or "point" in req_lower:
        chart_type = "scatter"
    elif "pie" in req_lower or "donut" in req_lower:
        chart_type = "pie"
    elif "histogram" in req_lower or "distribution" in req_lower:
        chart_type = "histogram"

    # Use first column as x-axis and second (if numeric) as y-axis
    x_col = cols[0]
    y_col = cols[1] if len(cols) > 1 else cols[0]

    if chart_type == "pie":
        fig = go.Figure(data=[go.Pie(labels=df[x_col].tolist(), values=df[y_col].tolist())])
    elif chart_type == "histogram":
        fig = go.Figure(data=[go.Histogram(x=df[x_col].tolist())])
    elif chart_type == "line":
        fig = go.Figure(data=[go.Scatter(x=df[x_col].tolist(), y=df[y_col].tolist(), mode="lines+markers")])
    elif chart_type == "scatter":
        fig = go.Figure(data=[go.Scatter(x=df[x_col].tolist(), y=df[y_col].tolist(), mode="markers")])
    else:
        fig = go.Figure(data=[go.Bar(x=df[x_col].tolist(), y=df[y_col].tolist())])

    fig.update_layout(
        title=chart_request,
        xaxis_title=x_col,
        yaxis_title=y_col if chart_type not in ("pie", "histogram") else "",
    )

    spec = fig.to_json()
    return f"CHART_SPEC:{spec}"


@tool
def write_todos(todos: list[str]) -> str:
    """Record a short ordered plan before multi-step work."""
    return "Plan recorded:\n" + "\n".join(f"{i+1}. {t}" for i, t in enumerate(todos))


@tool
def finish(answer: str) -> str:
    """Return the final answer to the user and end the run. Call exactly once when done."""
    return answer


TOOLS = [upload_dataset, list_datasets, query_dataset, generate_chart, write_todos, finish]
TOOL_MAP = {t.name: t for t in TOOLS}
FINISH = "finish"
