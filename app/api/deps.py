from fastapi import Header, HTTPException

from app.services.dependencies import session_manager
from app.services.session_manager import UserSession


async def get_current_user(authorization: str = Header(...)) -> UserSession:

    scheme, _, token = authorization.partition(" ")

    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=401,
            detail="Missing or malformed Authorization header.",
        )

    session = session_manager.get_by_token(token)

    if session is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session.",
        )

    return session
