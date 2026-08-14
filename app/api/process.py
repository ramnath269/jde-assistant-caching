from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.models import ChatRequest, ChatResponse
from app.services.claude_service import AuthExpiredError
from app.services.dependencies import claude_service
from app.services.session_manager import UserSession

router = APIRouter(tags=["Chat"])


@router.post("/process", response_model=ChatResponse)
async def process(
    request: ChatRequest,
    session: UserSession = Depends(get_current_user),
):

    try:
        result = await claude_service.process(
            request.prompt,
            session,
            request.conversation_id,
        )
        return ChatResponse(**result)

    except AuthExpiredError as ex:
        raise HTTPException(
            status_code=401,
            detail=str(ex),
        )

    except Exception as ex:
        raise HTTPException(
            status_code=500,
            detail=str(ex),
        )