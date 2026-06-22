"""Tests for the destructive SQL guard: rejects DROP/DELETE/TRUNCATE/ALTER etc."""
import pytest
from data_analyst.agent.tools import is_destructive


@pytest.mark.parametrize("sql", [
    "DROP TABLE my_table",
    "drop table my_table",
    "DELETE FROM my_table WHERE id = 1",
    "delete from orders",
    "TRUNCATE TABLE users",
    "ALTER TABLE users ADD COLUMN email TEXT",
    "CREATE TABLE new_tbl (id INT)",
    "INSERT INTO t VALUES (1, 'a')",
    "UPDATE t SET a = 1 WHERE b = 2",
])
def test_destructive_statements_blocked(sql: str):
    assert is_destructive(sql) is True


@pytest.mark.parametrize("sql", [
    "SELECT * FROM orders",
    "SELECT COUNT(*) FROM users",
    "SELECT a, b FROM t WHERE c > 10 ORDER BY a LIMIT 5",
    "WITH cte AS (SELECT 1 AS n) SELECT * FROM cte",
])
def test_safe_statements_allowed(sql: str):
    assert is_destructive(sql) is False
