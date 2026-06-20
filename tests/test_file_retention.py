import pytest
import pandas as pd
from agent.sessions import load_resource, get_session, release_session


@pytest.fixture(autouse=True)
def cleanup():
    yield
    release_session("test-retention-sess")


def test_file_retention():
    """Session store must persist the DataFrame across turns — releasing per-question is SESSION_DATA_LOST."""
    sid = "test-retention-sess"
    csv_text = "name,age,salary\nAlice,30,70000\nBob,25,65000\nCarol,35,90000"

    # Turn 1: load the resource
    load_resource(sid, csv_text)

    # Q1: resource is available
    sess = get_session(sid)
    df = sess.by_id.get("main")
    assert df is not None, "Resource must be available on Q1"
    assert list(df.columns) == ["name", "age", "salary"]
    assert df.shape == (3, 3)

    # Q2: resource persists WITHOUT re-loading (no re-upload)
    sess2 = get_session(sid)
    df2 = sess2.by_id.get("main")
    assert df2 is not None, "Resource must persist to Q2 (SESSION_DATA_LOST if missing)"
    assert df2 is df, "Same DataFrame object — not reloaded, not cleared between turns"

    # Verify computation still works on Q2
    mean_salary = float(df2["salary"].mean())
    assert abs(mean_salary - 75000.0) < 1.0, f"Mean salary should be 75000, got {mean_salary}"
