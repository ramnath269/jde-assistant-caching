from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.services.claude_service import build_claude_tools
from app.services.session_manager import UserSession

router = APIRouter(
    prefix="/tools",
    tags=["Tools"],
)


@router.get("")
async def list_tools(session: UserSession = Depends(get_current_user)):

    return {
        "count": session.tool_manager.count,
        "tools": session.tool_manager.all(),
    }


@router.get("/{tool_name}")
async def get_tool(
    tool_name: str,
    session: UserSession = Depends(get_current_user),
):

    tool = session.tool_manager.get(tool_name)

    if tool is None:
        raise HTTPException(
            status_code=404,
            detail="Tool not found.",
        )

    return tool


@router.post("/reload")
async def reload_tools(session: UserSession = Depends(get_current_user)):

    await session.tool_manager.reload()
    session.claude_tools = build_claude_tools(session.tool_manager.all())

    return {
        "success": True,
        "tool_count": session.tool_manager.count,
    }
