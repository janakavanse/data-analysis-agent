"""Tests for AuditLog: insert + read, and failure non-fatality."""
import json
import logging

import pytest
from sqlalchemy.orm import Session
from unittest.mock import patch, MagicMock

from data_analyst.db.models import AuditLog


def test_insert_and_read_audit_log(isolated_db):
    with Session(isolated_db) as session:
        entry = AuditLog(
            session_id="sess-001",
            user_question="How many orders?",
            generated_sql="SELECT COUNT(*) FROM orders",
            datasets_touched=json.dumps(["orders"]),
            row_count_returned=1,
            latency_ms=250,
        )
        session.add(entry)
        session.commit()
        entry_id = entry.id

    with Session(isolated_db) as session:
        loaded = session.get(AuditLog, entry_id)
        assert loaded is not None
        assert loaded.session_id == "sess-001"
        assert loaded.user_question == "How many orders?"
        assert loaded.generated_sql == "SELECT COUNT(*) FROM orders"
        assert loaded.row_count_returned == 1
        assert loaded.latency_ms == 250
        touched = json.loads(loaded.datasets_touched)
        assert "orders" in touched
        assert loaded.logged_at is not None


def test_audit_log_sql_error_field(isolated_db):
    """sql_error field is nullable and stores error strings."""
    with Session(isolated_db) as session:
        entry = AuditLog(
            session_id="sess-err",
            user_question="Bad query?",
            generated_sql="SELECT * FROM nonexistent",
            sql_error="Table 'nonexistent' does not exist",
            datasets_touched=json.dumps([]),
            row_count_returned=None,
            latency_ms=50,
        )
        session.add(entry)
        session.commit()
        entry_id = entry.id

    with Session(isolated_db) as session:
        loaded = session.get(AuditLog, entry_id)
        assert loaded is not None
        assert loaded.sql_error == "Table 'nonexistent' does not exist"


def test_audit_log_sql_error_nullable(isolated_db):
    """sql_error defaults to None when not provided."""
    with Session(isolated_db) as session:
        entry = AuditLog(
            session_id="sess-ok",
            user_question="Good query?",
            generated_sql="SELECT 1",
            datasets_touched=json.dumps([]),
            row_count_returned=1,
            latency_ms=10,
        )
        session.add(entry)
        session.commit()
        entry_id = entry.id

    with Session(isolated_db) as session:
        loaded = session.get(AuditLog, entry_id)
        assert loaded is not None
        assert loaded.sql_error is None


def test_audit_log_write_failure_is_non_fatal(isolated_db, caplog):
    """A failing audit log write must not propagate an exception to the caller."""

    def _write_audit_log_safely(session, **kwargs) -> None:
        """Simulates how the agent runner will write audit logs — failure is swallowed."""
        try:
            entry = AuditLog(**kwargs)
            session.add(entry)
            session.flush()
        except Exception as exc:
            logging.getLogger(__name__).error("Audit log write failed: %s", exc)
            session.rollback()

    # Simulate a session that raises on flush
    failing_session = MagicMock()
    failing_session.add = MagicMock()
    failing_session.flush = MagicMock(side_effect=RuntimeError("DB is locked"))
    failing_session.rollback = MagicMock()

    # Should not raise even though the session is broken
    with caplog.at_level(logging.ERROR):
        _write_audit_log_safely(
            failing_session,
            session_id="sess-002",
            user_question="Trigger failure",
            generated_sql="SELECT 1",
            datasets_touched=json.dumps([]),
            row_count_returned=0,
            latency_ms=100,
        )

    # rollback was called
    failing_session.rollback.assert_called_once()
    # error was logged
    assert any("Audit log write failed" in r.message for r in caplog.records)


def test_multiple_audit_log_entries(isolated_db):
    """Multiple entries can coexist; all are readable."""
    with Session(isolated_db) as session:
        for i in range(3):
            session.add(AuditLog(
                session_id=f"sess-{i}",
                user_question=f"Question {i}",
                datasets_touched=json.dumps([]),
                row_count_returned=i,
                latency_ms=100 + i,
            ))
        session.commit()

    with Session(isolated_db) as session:
        all_logs = session.query(AuditLog).all()
        assert len(all_logs) == 3
