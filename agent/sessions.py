import re
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

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


def _chunk(text: str) -> list[str]:
    """Split a document into passages on blank lines (fallback: the whole text)."""
    chunks = [c.strip() for c in re.split(r"\n\s*\n", text) if c.strip()]
    return chunks or [text.strip()]


def load_resource(session_id: str, data: str, resource_id: str = "main") -> str:
    """Stash a provided document (plain text) + its passages in the session bag for retrieval.
    Persists across follow-up turns; released only on explicit session delete (C-SESSION-SCOPE)."""
    sess = get_session(session_id)
    sess.by_id["document"] = data
    sess.by_id["chunks"] = _chunk(data)
    return resource_id
