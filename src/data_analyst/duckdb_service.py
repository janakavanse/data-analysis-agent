import logging
import threading
import re
from typing import TYPE_CHECKING

import duckdb

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def is_destructive(sql: str) -> bool:
    """Return True if the SQL contains a destructive statement that should be blocked."""
    # Normalise: collapse whitespace, uppercase for matching
    normalised = re.sub(r"\s+", " ", sql.strip().upper())
    destructive_patterns = [
        r"\bDROP\b",
        r"\bDELETE\b",
        r"\bTRUNCATE\b",
        r"\bALTER\b",
        r"\bCREATE\b",
        r"\bINSERT\b",
        r"\bUPDATE\b",
        r"\bREPLACE\b",
        r"\bGRANT\b",
        r"\bREVOKE\b",
    ]
    for pattern in destructive_patterns:
        if re.search(pattern, normalised):
            return True
    return False


class DuckDBService:
    def __init__(self, duckdb_path: str) -> None:
        self._conn = duckdb.connect(duckdb_path)
        self._lock = threading.Lock()

    def register_dataset(self, dataset: object) -> None:
        """Register a dataset as a DuckDB view.

        For Excel files, expects that the CSV conversion has already been done
        and `dataset.file_path` points to the CSV file.
        """
        table_name = dataset.table_name  # type: ignore[attr-defined]
        file_path = dataset.file_path  # type: ignore[attr-defined]

        with self._lock:
            sql = (
                f"CREATE OR REPLACE VIEW {table_name} AS "
                f"SELECT * FROM read_csv_auto('{file_path}', header=true)"
            )
            self._conn.execute(sql)
            logger.info("Registered DuckDB view: %s -> %s", table_name, file_path)

    def deregister_dataset(self, table_name: str) -> None:
        """Drop the DuckDB view for a dataset."""
        with self._lock:
            self._conn.execute(f"DROP VIEW IF EXISTS {table_name}")
            logger.info("Deregistered DuckDB view: %s", table_name)

    def execute_query(self, sql: str) -> list[dict]:
        """Execute a SELECT query and return results as a list of dicts."""
        with self._lock:
            rel = self._conn.execute(sql)
            columns = [desc[0] for desc in rel.description]
            rows = rel.fetchall()
            return [dict(zip(columns, row)) for row in rows]

    def list_tables(self) -> list[str]:
        """Return the names of all registered tables/views."""
        with self._lock:
            rel = self._conn.execute("SHOW TABLES")
            return [row[0] for row in rel.fetchall()]

    def describe_table(self, table_name: str) -> list[dict]:
        """Return column info for a table/view."""
        with self._lock:
            rel = self._conn.execute(f"DESCRIBE {table_name}")
            columns = [desc[0] for desc in rel.description]
            return [dict(zip(columns, row)) for row in rel.fetchall()]

    def get_sample_rows(self, table_name: str, n: int = 5) -> list[dict]:
        """Return up to n sample rows from a table/view."""
        with self._lock:
            rel = self._conn.execute(f"SELECT * FROM {table_name} LIMIT {n}")
            columns = [desc[0] for desc in rel.description]
            return [dict(zip(columns, row)) for row in rel.fetchall()]

    def register_all_datasets(self, db_session: "Session") -> None:
        """Re-register all active datasets from the SQLite catalogue."""
        from data_analyst.db.models import Dataset

        datasets = db_session.query(Dataset).filter(Dataset.is_active == True).all()  # noqa: E712
        for ds in datasets:
            try:
                self.register_dataset(ds)
            except Exception as exc:
                logger.warning(
                    "Failed to register dataset %s (%s): %s",
                    ds.table_name,
                    ds.id,
                    exc,
                )

    def health_check(self) -> bool:
        """Return True if DuckDB is responsive."""
        try:
            with self._lock:
                self._conn.execute("SHOW TABLES")
            return True
        except Exception:
            return False


_duckdb_service: DuckDBService | None = None


def get_duckdb_service() -> DuckDBService:
    global _duckdb_service
    if _duckdb_service is None:
        from data_analyst.config.settings import get_settings
        settings = get_settings()
        from pathlib import Path
        Path(settings.duckdb_path).parent.mkdir(parents=True, exist_ok=True)
        _duckdb_service = DuckDBService(settings.duckdb_path)
    return _duckdb_service


def reset_duckdb_service() -> None:
    """Reset the singleton — used in tests."""
    global _duckdb_service
    _duckdb_service = None
