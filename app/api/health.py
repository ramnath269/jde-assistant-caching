from fastapi import APIRouter

from app.services.dependencies import claude_service, session_manager

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
        # There's no single MCP connection to report on anymore - each
        # logged-in user has their own (see session_manager.py).
        "active_sessions": session_manager.count(),
        "claude": claude_service.health(),
    }
