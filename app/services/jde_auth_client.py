from __future__ import annotations

from typing import Any

import httpx

from app.config import settings
from app.core.logger import logger


class JDEAuthClient:
    """
    Talks to the MCP server's one REST auth route, POST /auth/login -
    distinct from the JSON-RPC tools/* endpoint used for everything else.

    That server has no /auth/logout or /auth/session route (it issues OAuth
    bearer tokens with their own TTL, not a revocable session id), so this
    client is deliberately just the one call.
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
        )

        return response.status_code, _safe_json(response)


def _safe_json(response: httpx.Response) -> dict[str, Any]:
    try:
        return response.json()
    except ValueError:
        return {}
