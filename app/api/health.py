from fastapi import APIRouter

from app.services.dependencies import (
    claude_service,
    mcp_client,
    tool_manager,
)

router = APIRouter(tags=["Health"])


@router.get("/")
async def root():
    return {
        "name": "JDE Assistant",
        "status": "running",
    }


@router.get("/health")
async def health():
    return {
        "status": "healthy",
        "mcp": {
            "connected": mcp_client.session_id is not None,
            "session_id": mcp_client.session_id,
        },
        "tools": {
            "count": tool_manager.count,
        },
        "claude": {
            "initialized": claude_service.health()["initialized"],
        },
    }