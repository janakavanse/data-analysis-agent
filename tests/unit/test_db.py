"""DB layer tests — no LLM key required."""
from sqlalchemy.orm import Session
from db.models import DatasetRow, QueryRow, SessionRow
import db.session as session_module


def test_session_row_roundtrip(_isolated_db):
    with Session(_isolated_db) as s:
        row = SessionRow()
        s.add(row)
        s.commit()
        session_id = row.id

    with Session(_isolated_db) as s:
        fetched = s.get(SessionRow, session_id)
        assert fetched is not None
        assert fetched.created_at is not None
        assert fetched.last_active_at is not None


def test_dataset_row_roundtrip(_isolated_db):
    with Session(_isolated_db) as s:
        session_row = SessionRow()
        s.add(session_row)
        s.flush()

        dataset = DatasetRow(
            session_id=session_row.id,
            original_filename="expenses.csv",
            storage_path="/data/uploads/x/y/expenses.csv",
            file_type="csv",
            row_count=100,
            column_count=3,
            schema_json='{"columns": [], "row_count": 100}',
        )
        s.add(dataset)
        s.commit()
        dataset_id = dataset.id

    with Session(_isolated_db) as s:
        fetched = s.get(DatasetRow, dataset_id)
        assert fetched is not None
        assert fetched.original_filename == "expenses.csv"
        assert fetched.file_type == "csv"
        assert fetched.row_count == 100
        assert fetched.column_count == 3


def test_query_row_roundtrip_and_status_update(_isolated_db):
    with Session(_isolated_db) as s:
        session_row = SessionRow()
        s.add(session_row)
        s.flush()
        dataset = DatasetRow(
            session_id=session_row.id,
            original_filename="a.csv",
            storage_path="/tmp/a.csv",
            file_type="csv",
            row_count=10,
            column_count=2,
            schema_json="{}",
        )
        s.add(dataset)
        s.flush()

        query = QueryRow(
            session_id=session_row.id,
            dataset_id=dataset.id,
            turn_index=0,
            question="what is the average?",
        )
        s.add(query)
        s.commit()
        query_id = query.id

    with Session(_isolated_db) as s:
        fetched = s.get(QueryRow, query_id)
        assert fetched is not None
        assert fetched.status == "pending"
        assert fetched.retry_count == 0
        assert fetched.answer_text is None

    with Session(_isolated_db) as s:
        fetched = s.get(QueryRow, query_id)
        fetched.status = "completed"
        fetched.answer_text = "The average is 5.5."
        fetched.retry_count = 1
        s.commit()

    with Session(_isolated_db) as s:
        fetched = s.get(QueryRow, query_id)
        assert fetched.status == "completed"
        assert fetched.answer_text == "The average is 5.5."
        assert fetched.retry_count == 1


def test_multiple_queries_independent_turn_index(_isolated_db):
    with Session(_isolated_db) as s:
        session_row = SessionRow()
        s.add(session_row)
        s.flush()
        dataset = DatasetRow(
            session_id=session_row.id,
            original_filename="a.csv",
            storage_path="/tmp/a.csv",
            file_type="csv",
            row_count=10,
            column_count=2,
            schema_json="{}",
        )
        s.add(dataset)
        s.flush()

        ids = []
        for i in range(3):
            q = QueryRow(
                session_id=session_row.id,
                dataset_id=dataset.id,
                turn_index=i,
                question=f"question {i}",
            )
            s.add(q)
        s.commit()

        queries = s.query(QueryRow).order_by(QueryRow.turn_index.asc()).all()
        ids = [q.id for q in queries]

    assert len(ids) == 3
    assert len(set(ids)) == 3
