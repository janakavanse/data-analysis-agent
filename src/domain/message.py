"""Pydantic models for chat-turn requests/responses.

``AskRequest`` is the body of ``POST /sessions/{id}/ask``. ``AskData`` is the
show-the-work answer payload. ``TranscriptMessage`` is one turn returned in the
session transcript (``GET /sessions/{id}``).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class AskRequest(BaseModel):
    """Body of ``POST /sessions/{id}/ask``: a plain-English question."""

    question: str


class AskData(BaseModel):
    """The show-the-work answer for one question.

    ``status`` is ``completed`` or ``failed``. On ``failed`` the ``answer``
    carries a readable message and ``code``/``result_table`` may be null.
    """

    answer: str
    code: str | None = None
    result_table: dict[str, Any] | None = None
    status: str


class TranscriptMessage(BaseModel):
    """One turn in the replayable transcript.

    User turns carry only ``role``/``content``/``created_at``; assistant turns
    additionally carry ``code``, ``result_table``, and ``status``.
    """

    role: str
    content: str
    code: str | None = None
    result_table: dict[str, Any] | None = None
    status: str | None = None
    created_at: str | None = None
