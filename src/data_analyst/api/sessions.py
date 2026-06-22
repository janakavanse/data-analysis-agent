import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from data_analyst.api._common import api_error
from data_analyst.db.models import Session as SessionModel, ConversationTurn
from data_analyst.db.session import get_session
from data_analyst.domain.schemas import SessionHistoryResponse, TurnResponse

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/sessions/{session_id}/history", response_model=SessionHistoryResponse)
def get_session_history(
    session_id: str,
    db: Session = Depends(get_session),
) -> SessionHistoryResponse:
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if session is None:
        raise api_error("NOT_FOUND", f"Session '{session_id}' not found", 404)

    turns = (
        db.query(ConversationTurn)
        .filter(ConversationTurn.session_id == session_id)
        .order_by(ConversationTurn.turn_index)
        .all()
    )

    return SessionHistoryResponse(
        session_id=session_id,
        created_at=session.created_at,
        last_active=session.last_active,
        turns=[
            TurnResponse(
                role=t.role,
                content=t.content,
                turn_index=t.turn_index,
                created_at=t.created_at,
            )
            for t in turns
        ],
    )
