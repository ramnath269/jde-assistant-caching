from fastapi import APIRouter, HTTPException

from app.services.dependencies import tool_manager

router = APIRouter(
    prefix="/tools",
    tags=["Tools"],
)


@router.get("")
async def list_tools():

    return {
        "count": tool_manager.count,
        "tools": tool_manager.all(),
    }


@router.get("/{tool_name}")
async def get_tool(tool_name: str):

    tool = tool_manager.get(tool_name)

    if tool is None:
        raise HTTPException(
            status_code=404,
            detail="Tool not found.",
        )

    return tool


@router.post("/reload")
async def reload_tools():

    await tool_manager.reload()

    return {
        "success": True,
        "tool_count": tool_manager.count,
    }