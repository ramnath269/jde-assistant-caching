from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.core.logger import logger
from app.models import LoginRequest, LoginResponse
from app.services.dependencies import jde_auth_client, session_manager
from app.services.session_manager import UserSession

router = APIRouter(tags=["Auth"])


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):

    try:
        status_code, body = await jde_auth_client.login(
            request.username,
            request.password,
            request.environment,
        )
    except Exception:
        logger.exception("MCP /auth/login call failed")
        raise HTTPException(
            status_code=502,
            detail="Unable to reach the authentication service.",
        )

    if status_code == 200:
        session = session_manager.create(
            username=request.username,
            mcp_session_id=body["session_id"],
            environment=body.get("environment", request.environment),
            expires_at=body.get("expires_at"),
        )

        return LoginResponse(
            session_token=session.session_token,
            username=session.username,
            environment=session.environment,
        )

    if status_code == 403:
        # JDE's own wording - relayed as-is, it's what distinguishes a
        # typo from JDE being down.
        raise HTTPException(
            status_code=401,
            detail=body.get("error", "Invalid username or password."),
        )

    if status_code == 401:
        logger.error("MCP server rejected our client secret: %s", body)
        raise HTTPException(
            status_code=500,
            detail="Authentication service is misconfigured.",
        )

    logger.error(
        "MCP /auth/login failed (%s): %s",
        status_code,
        body.get("error", body),
    )
    raise HTTPException(
        status_code=500,
        detail="Authentication service is currently unavailable.",
    )


@router.post("/logout")
async def logout(session: UserSession = Depends(get_current_user)):

    await jde_auth_client.logout(session.mcp_session_id)

    session_manager.logout(session.session_token)

    return {
        "success": True,
        "message": "Logged out.",
    }
