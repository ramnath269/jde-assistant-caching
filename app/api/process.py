from fastapi import APIRouter, HTTPException

from app.models import ChatRequest, ChatResponse
from app.services.dependencies import claude_service

router = APIRouter(tags=["Chat"])


@router.post("/process", response_model=ChatResponse)
async def process(request: ChatRequest):

    try:
        result = await claude_service.process(request.prompt)
        return ChatResponse(**result)

    except Exception as ex:
        raise HTTPException(
            status_code=500,
            detail=str(ex),
        )