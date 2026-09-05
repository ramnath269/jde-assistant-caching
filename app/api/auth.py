import base64
import binascii

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.core.logger import logger
from app.models import LoginRequest, LoginResponse
from app.services.claude_service import build_claude_tools
from app.services.dependencies import jde_auth_client, session_manager
from app.services.mcp_client import MCPClient
from app.services.session_manager import UserSession
from app.services.tool_manager import ToolManager

router = APIRouter(tags=["Auth"])


def _decode_password(encoded: str) -> str:
    """
    The login page base64-encodes the password before posting it
    (browser btoa); the MCP server expects it in the clear.
    """

    try:
        password = base64.b64decode(encoded, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        # Deliberately vague, and never log the value itself.
        logger.warning("Rejected a login with a non-base64 password field.")
        raise HTTPException(
            status_code=400,
            detail="Malformed credentials.",
        )

    if not password:
        raise HTTPException(
            status_code=400,
            detail="Password must not be empty.",
        )

    return password


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):

    password = _decode_password(request.password)

    try:
        status_code, body = await jde_auth_client.login(
            request.username,
            password,
            request.environment,
        )
    except Exception:
        logger.exception("MCP /auth/login call failed")
        raise HTTPException(
            status_code=502,
            detail="Unable to reach the authentication service.",
        )

    if status_code == 403:
        # JDE's own wording - relayed as-is, it's what distinguishes a
        # typo from JDE being down.
        raise HTTPException(
            status_code=401,
            detail=body.get("error", "Invalid username or password."),
        )

    if status_code != 200:
        logger.error(
            "MCP /auth/login failed (%s): %s",
            status_code,
            body.get("error", body),
        )
        raise HTTPException(
            status_code=500,
            detail="Authentication service is currently unavailable.",
        )

    access_token = body.get("token")
    if not access_token:
        logger.error("MCP /auth/login returned 200 but no token: %s", body)
        raise HTTPException(
            status_code=502,
            detail="Authentication service returned an unexpected response.",
        )

    resolved_username = body.get("username") or request.username

    # Every subsequent /mcp call this user makes goes through their own
    # MCPClient, carrying this bearer token - see mcp_client.py's docstring
    # for why this can no longer be one shared connection for all users.
    mcp_client = MCPClient(access_token)
    tools = ToolManager(mcp_client)

    try:
        await mcp_client.initialize()
        await tools.load()
    except Exception:
        logger.exception(
            "MCP session setup failed after JDE login for user '%s'",
            resolved_username,
        )
        await mcp_client.close()
        raise HTTPException(
            status_code=502,
            detail="Logged in to JDE, but could not establish an MCP session.",
        )

    session = await session_manager.create(
        username=resolved_username,
        environment=body.get("environment") or request.environment,
        mcp_access_token=access_token,
        mcp_client=mcp_client,
        tool_manager=tools,
        claude_tools=build_claude_tools(tools.all()),
    )

    logger.info(
        "User '%s' logged in with %d tools visible (RBAC-filtered).",
        session.username,
        tools.count,
    )

    return LoginResponse(
        session_token=session.session_token,
        username=session.username,
        environment=session.environment,
    )


@router.post("/logout")
async def logout(session: UserSession = Depends(get_current_user)):

    await session.mcp_client.close()

    session_manager.logout(session.session_token)

    return {
        "success": True,
        "message": "Logged out.",
    }
