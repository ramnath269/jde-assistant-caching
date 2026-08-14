from __future__ import annotations

from typing import Any

import httpx

from app.config import settings
from app.core.logger import logger


class JDEAuthClient:
    """
    Talks to the MCP server's REST auth surface (/auth/login,
    /auth/logout, /auth/session) - distinct from the JSON-RPC
    tools/* endpoint used for everything else.
    """

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=settings.request_timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def login(
        self,
        username: str,
        password: str,
        environment: str,
    ) -> tuple[int, dict[str, Any]]:

        response = await self._client.post(
            f"{settings.jde_mcp_url}/auth/login",
            json={
                "username": username,
                "password": password,
                "environment": environment,
            },
            headers={
                "X-Client-Secret": settings.jde_mcp_client_secret,
            },
        )

        return response.status_code, _safe_json(response)

    async def logout(self, mcp_session_id: str) -> None:
        """
        Best-effort: the caller clears the local session regardless
        of whether this succeeds.
        """

        try:
            await self._client.post(
                f"{settings.jde_mcp_url}/auth/logout",
                headers={"X-JDE-Session": mcp_session_id},
            )
        except httpx.HTTPError:
            logger.warning("MCP /auth/logout call failed; clearing local session anyway.")

    async def get_session(self, mcp_session_id: str) -> tuple[int, dict[str, Any]]:

        response = await self._client.get(
            f"{settings.jde_mcp_url}/auth/session",
            headers={"X-JDE-Session": mcp_session_id},
        )

        return response.status_code, _safe_json(response)


def _safe_json(response: httpx.Response) -> dict[str, Any]:
    try:
        return response.json()
    except ValueError:
        return {}
