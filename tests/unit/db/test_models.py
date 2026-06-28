"""Schema tests for the chat entities — Session, Dataset, Message. No LLM key required."""
import json

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Session as OrmSession

import db.models as models
from db.models import Base, Dataset, Message, RunRow
from db.models import Session as SessionModel


def test_expected_tables_registered():
    tables = set(Base.metadata.tables)
    assert {"runs", "sessions", "datasets", "messages"}.issubset(tables)


def test_session_columns():
    cols = SessionModel.__table__.columns
    assert cols["id"].primary_key
    assert not cols["created_at"].nullable
    assert not cols["updated_at"].nullable
    # tz-aware timestamps
    assert cols["created_at"].type.timezone is True
    assert cols["updated_at"].type.timezone is True


def test_dataset_columns_and_fk():
    cols = Dataset.__table__.columns
    assert cols["id"].primary_key
    for required in (
        "session_id",
        "filename",
        "file_path",
        "file_type",
        "row_count",
        "schema_json",
        "sample_json",
        "created_at",
    ):
        assert required in cols, f"missing column {required}"
    # required (non-null) fields per data.md
    for non_null in (
        "session_id",
        "filename",
        "file_path",
        "file_type",
        "row_count",
        "schema_json",
        "sample_json",
        "created_at",
    ):
        assert not cols[non_null].nullable, f"{non_null} should be NOT NULL"
    # FK → sessions.id
    fks = list(cols["session_id"].foreign_keys)
    assert len(fks) == 1
    assert fks[0].column.table.name == "sessions"
    assert fks[0].column.name == "id"
    assert cols["created_at"].type.timezone is True


def test_message_columns_and_nullability():
    cols = Message.__table__.columns
    assert cols["id"].primary_key
    # required
    for non_null in ("session_id", "role", "content", "created_at"):
        assert not cols[non_null].nullable, f"{non_null} should be NOT NULL"
    # assistant-only / optional
    for nullable in ("code", "result_json", "status"):
        assert cols[nullable].nullable, f"{nullable} should be nullable"
    fks = list(cols["session_id"].foreign_keys)
    assert len(fks) == 1
    assert fks[0].column.table.name == "sessions"
    assert cols["created_at"].type.timezone is True


def test_session_dataset_message_roundtrip(_isolated_db):
    schema = json.dumps([{"name": "amount", "dtype": "int64"}])
    sample = json.dumps([{"amount": 10}, {"amount": 20}])
    with OrmSession(_isolated_db) as s:
        sess = SessionModel()
        s.add(sess)
        s.flush()
        session_id = sess.id

        ds = Dataset(
            session_id=session_id,
            filename="sales.csv",
            file_path="data/uploads/sales.csv",
            file_type="csv",
            row_count=2,
            schema_json=schema,
            sample_json=sample,
        )
        user_msg = Message(session_id=session_id, role="user", content="avg amount?")
        asst_msg = Message(
            session_id=session_id,
            role="assistant",
            content="The average is 15.",
            code="df['amount'].mean()",
            result_json=json.dumps({"kind": "scalar", "value": 15}),
            status="completed",
        )
        s.add_all([ds, user_msg, asst_msg])
        s.commit()
        dataset_id = ds.id

    with OrmSession(_isolated_db) as s:
        fetched_ds = s.get(Dataset, dataset_id)
        assert fetched_ds is not None
        assert fetched_ds.session_id == session_id
        assert fetched_ds.row_count == 2
        assert json.loads(fetched_ds.schema_json)[0]["name"] == "amount"

        msgs = (
            s.query(Message)
            .filter(Message.session_id == session_id)
            .order_by(Message.created_at)
            .all()
        )
        assert len(msgs) == 2
        roles = {m.role for m in msgs}
        assert roles == {"user", "assistant"}
        asst = next(m for m in msgs if m.role == "assistant")
        assert asst.status == "completed"
        assert asst.code is not None
        user = next(m for m in msgs if m.role == "user")
        assert user.code is None and user.status is None


def test_runrow_retained():
    # The baseline bookkeeping table is retained per data.md.
    assert RunRow.__tablename__ == "runs"
    assert "runs" in Base.metadata.tables
    # exercised via the models module to keep the import live
    assert models.RunRow is RunRow
