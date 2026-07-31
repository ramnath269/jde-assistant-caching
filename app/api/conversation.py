from fastapi import APIRouter

from app.services.dependencies import conversation_manager

router = APIRouter(
    prefix="/conversation",
    tags=["Conversation"],
)


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: str):
    return conversation_manager.get_messages(conversation_id)


@router.delete("/{conversation_id}")
async def clear_conversation(conversation_id: str):
    conversation_manager.clear(conversation_id)

    return {
        "success": True,
        "message": "Conversation cleared.",
    }