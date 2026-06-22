# Phase 1 stub: only the pure helper that can be unit-tested now.
# Full tool implementations (execute_sql, list_tables, etc.) are in Phase 2.

from data_analyst.duckdb_service import is_destructive  # re-export for import compatibility

__all__ = ["is_destructive"]
