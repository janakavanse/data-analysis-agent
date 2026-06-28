"""Local analysis engine: DuckDB ingest, the privacy redaction point, local code execution, cost."""

from analysis.cost import PRICE_TABLE, estimate_cost
from analysis.engine import (
    BadFileError,
    EXEC_TIMEOUT_S,
    MAX_RESULT_BYTES,
    MAX_RESULT_ROWS,
    SAMPLE_ROWS,
    execute,
    ingest_file,
    make_llm_context,
    table_name,
)
from analysis.storage import (
    data_root,
    get_connection,
    parquet_dir,
    uploads_dir,
)

__all__ = [
    "BadFileError",
    "EXEC_TIMEOUT_S",
    "MAX_RESULT_BYTES",
    "MAX_RESULT_ROWS",
    "SAMPLE_ROWS",
    "PRICE_TABLE",
    "estimate_cost",
    "execute",
    "ingest_file",
    "make_llm_context",
    "table_name",
    "data_root",
    "get_connection",
    "parquet_dir",
    "uploads_dir",
]
