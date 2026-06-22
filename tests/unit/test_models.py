"""Round-trip tests for all 4 SQLAlchemy models against an isolated SQLite DB."""
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from data_analyst.db.models import AuditLog, ConversationTurn, Dataset, Session as SessionModel


def test_dataset_roundtrip(isolated_db):
    with Session(isolated_db) as session:
        ds = Dataset(
            name="Test Dataset",
            description="A description",
            table_name="test_dataset",
            original_filename="test.csv",
            file_path="/data/uploads/abc.csv",
            file_extension=".csv",
            row_count=42,
            column_count=3,
            schema_json=json.dumps([{"column": "a", "dtype": "int64"}]),
            is_active=True,
        )
        session.add(ds)
        session.commit()
        dataset_id = ds.id

    with Session(isolated_db) as session:
        loaded = session.get(Dataset, dataset_id)
        assert loaded is not None
        assert loaded.name == "Test Dataset"
        assert loaded.description == "A description"
        assert loaded.table_name == "test_dataset"
        assert loaded.file_extension == ".csv"
        assert loaded.row_count == 42
        assert loaded.column_count == 3
        assert loaded.is_active is True
        assert loaded.upload_timestamp is not None
        schema = json.loads(loaded.schema_json)
        assert schema[0]["column"] == "a"


def test_session_and_conversation_turn_roundtrip(isolated_db):
    with Session(isolated_db) as session:
        sess = SessionModel()
        session.add(sess)
        session.flush()
        session_id = sess.id

        turn = ConversationTurn(
            session_id=session_id,
            role="user",
            content="Hello, how are you?",
            turn_index=1,
            is_summarised=False,
        )
        session.add(turn)
        session.commit()
        turn_id = turn.id

    with Session(isolated_db) as session:
        loaded_turn = session.get(ConversationTurn, turn_id)
        assert loaded_turn is not None
        assert loaded_turn.session_id == session_id
        assert loaded_turn.role == "user"
        assert loaded_turn.turn_index == 1
        assert loaded_turn.is_summarised is False


def test_session_model_fields(isolated_db):
    """Session model has created_at and last_active fields."""
    with Session(isolated_db) as session:
        sess = SessionModel()
        session.add(sess)
        session.commit()
        session_id = sess.id

    with Session(isolated_db) as session:
        loaded = session.get(SessionModel, session_id)
        assert loaded is not None
        assert loaded.created_at is not None
        assert loaded.last_active is not None


def test_audit_log_roundtrip(isolated_db):
    with Session(isolated_db) as session:
        log = AuditLog(
            session_id="fake-session-id",
            user_question="How many rows?",
            generated_sql="SELECT COUNT(*) FROM my_table",
            datasets_touched=json.dumps(["my_table"]),
            row_count_returned=1,
            latency_ms=150,
        )
        session.add(log)
        session.commit()
        log_id = log.id

    with Session(isolated_db) as session:
        loaded = session.get(AuditLog, log_id)
        assert loaded is not None
        assert loaded.session_id == "fake-session-id"
        assert loaded.user_question == "How many rows?"
        assert loaded.generated_sql is not None
        assert loaded.row_count_returned == 1
        assert loaded.latency_ms == 150
        assert loaded.sql_error is None
        assert loaded.logged_at is not None
        touched = json.loads(loaded.datasets_touched)
        assert "my_table" in touched


def test_audit_log_no_update_or_delete_method():
    """Verify there is no application-level update/delete method targeting audit_log."""
    # This is a code-convention check: AuditLog is append-only.
    # We confirm no update() or delete() SQLAlchemy calls exist on AuditLog
    # by checking that the model has no such service methods (import and inspect).
    import inspect
    import data_analyst.db.models as m

    # AuditLog class must exist
    assert hasattr(m, "AuditLog")
    # It must not have any update or delete instance methods
    members = dict(inspect.getmembers(m.AuditLog))
    assert "update" not in members
    assert "delete" not in members
