import io
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

current_session_id: ContextVar[str | None] = ContextVar("current_session_id", default=None)


@dataclass
class SessionResources:
    by_id: dict[str, Any] = field(default_factory=dict)


_SESSIONS: dict[str, SessionResources] = {}


def get_session(session_id: str) -> SessionResources:
    return _SESSIONS.setdefault(session_id, SessionResources())


def release_session(session_id: str) -> None:
    """Drop a session's resources — call ONLY on explicit session delete, NEVER per question."""
    _SESSIONS.pop(session_id, None)


def load_resource(session_id: str, data: str, resource_id: str = "main") -> str:
    """Parse an uploaded blob (CSV or JSON) and stash the DataFrame in the session bag."""
    try:
        df = pd.read_csv(io.StringIO(data))
    except Exception:
        try:
            df = pd.read_json(io.StringIO(data))
        except Exception as e:
            raise ValueError(f"Could not parse data as CSV or JSON: {e}") from e
    get_session(session_id).by_id[resource_id] = df
    return resource_id
