from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.services.dependencies import conversation_manager
from app.services.session_manager import UserSession

router = APIRouter(
    prefix="/conversation",
    tags=["Conversation"],
    dependencies=[Depends(get_current_user)],
)


def _require_owner(conversation_id: str, session: UserSession) -> None:
    if conversation_id not in session.conversation_ids:
        raise HTTPException(
            status_code=403,
            detail="You do not have access to this conversation.",
        )


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    session: UserSession = Depends(get_current_user),
):
    _require_owner(conversation_id, session)

    return conversation_manager.get_display_messages(conversation_id)


@router.delete("/{conversation_id}")
async def clear_conversation(
    conversation_id: str,
    session: UserSession = Depends(get_current_user),
):
    _require_owner(conversation_id, session)

    conversation_manager.clear(conversation_id)

    return {
        "success": True,
        "message": "Conversation cleared.",
    }