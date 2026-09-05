from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from app.config import settings
from app.core.logger import logger

# Protocol version we ask for at initialize(). The server echoes back the
# version it actually negotiated; that echoed value is what we send on the
# MCP-Protocol-Version header for every subsequent request.
PROTOCOL_VERSION = "2024-11-05"


class MCPAuthExpiredError(Exception):
    """
    The bearer token this client was constructed with was rejected (HTTP 401).

    Not recoverable by re-initializing -- the MCP server gates the entire
    /mcp surface behind OAuth now, so initialize() would 401 with the same
    stale token. The only way back is a fresh /auth/login.
    """


class MCPClient:
    """
    JSON-RPC client for Streamable HTTP MCP servers, bound to ONE
    authenticated JDE user for its whole lifetime.

    The MCP server wraps its entire /mcp surface (including initialize
    itself) in RequireAuthMiddleware, so every request -- not just tool
    calls -- must carry this user's bearer token. That's why this is no
    longer a single process-wide singleton: one instance is created per
    logged-in user, right after their /auth/login, and closed on logout.
    """

    def __init__(self, bearer_token: str) -> None:
        self._client = httpx.AsyncClient(
            timeout=settings.request_timeout,
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {bearer_token}",
            },
            follow_redirects=True,
        )

        self._request_id = 0
        self._session_id: str | None = None
        self._protocol_version: str = PROTOCOL_VERSION
        # Serializes re-initialization so concurrent requests that all hit a
        # dead session create ONE new session between them, not one each.
        self._reinit_lock = asyncio.Lock()

    @property
    def session_id(self) -> str | None:
        return self._session_id

    async def close(self) -> None:
        await self._client.aclose()

    async def initialize(self) -> None:

        logger.info("Initializing MCP session...")

        self._session_id = None

        response = await self._send(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": "jde-assistant",
                    "version": "2.0",
                },
            },
        )

        negotiated = (response.get("result") or {}).get("protocolVersion")
        if negotiated:
            self._protocol_version = negotiated

        # Required by the MCP spec after initialize; we were skipping it.
        await self._send("notifications/initialized", None, notification=True)

        logger.info("MCP session established: %s", self._session_id)

    async def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Send a JSON-RPC request, transparently re-establishing the MCP
        transport session if the server no longer recognises ours.

        Streamable-HTTP sessions live only in the MCP server's memory, so
        any restart or redeploy of that server invalidates our cached
        mcp-session-id and the next call comes back 404 "Session not found"
        (400 on some servers). Re-initialize and retry once.

        A 401 is a different failure and must NOT be treated the same way:
        it means our bearer token itself is stale/revoked, and initialize()
        would 401 again with that same token -- retrying can't fix it. It's
        raised as MCPAuthExpiredError so the caller can send the user back
        through /auth/login instead of looping.
        """

        # A re-initialize in flight has already torn down self._session_id;
        # waiting for it beats firing a request that is guaranteed to 404.
        if self._session_id is None and self._reinit_lock.locked():
            async with self._reinit_lock:
                pass

        # Snapshot BEFORE the send, not in the except block: by the time we
        # handle the failure another coroutine may have stored a fresh session
        # id, and comparing against that would re-initialize a healthy session.
        session_at_send = self._session_id

        try:
            return await self._send(method, params)

        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                raise MCPAuthExpiredError(
                    "The MCP server rejected this bearer token; it has "
                    "expired or been revoked."
                ) from exc

            if not self._is_session_lost(exc.response):
                raise

            logger.warning(
                "MCP session %s rejected (HTTP %s) - re-initializing",
                session_at_send,
                exc.response.status_code,
            )

            async with self._reinit_lock:
                # Another coroutine may have already rebuilt the session while
                # we waited for the lock; don't throw away its fresh session.
                if self._session_id == session_at_send:
                    await self.initialize()

            return await self._send(method, params)

    async def _send(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        notification: bool = False,
    ) -> dict[str, Any]:
        """Single JSON-RPC round trip. No session recovery -- see request()."""

        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        }

        # Notifications carry no id and get an empty 202 back.
        if not notification:
            self._request_id += 1
            payload["id"] = self._request_id

        headers = {}

        if self._session_id:
            headers["mcp-session-id"] = self._session_id
            headers["MCP-Protocol-Version"] = self._protocol_version

        response = await self._client.post(
            settings.mcp_server_url,
            json=payload,
            headers=headers,
        )

        response.raise_for_status()

        if "mcp-session-id" in response.headers:
            self._session_id = response.headers["mcp-session-id"]

        if notification or response.status_code == 202 or not response.text.strip():
            return {}

        return self._parse_response(response.text)

    @staticmethod
    def _is_session_lost(response: httpx.Response) -> bool:
        """
        True when a non-2xx response means "your session is gone", as opposed
        to a genuine application error.

        404 is the spec'd answer for an unknown/expired session id. 400 is
        ambiguous -- it is also a malformed request -- so only treat it as a
        lost session when the body actually says so.
        """

        if response.status_code == 404:
            return True

        if response.status_code == 400:
            return "session" in response.text.lower()

        return False

    async def list_tools(self) -> list[dict]:

        response = await self.request("tools/list")

        return response["result"]["tools"]

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict,
    ) -> dict:

        response = await self.request(
            "tools/call",
            {
                "name": tool_name,
                "arguments": arguments,
            },
        )

        return response["result"]

    @staticmethod
    def _parse_response(text: str) -> dict:
        text = text.strip()

        # Plain JSON response
        if text.startswith("{"):
            return json.loads(text)

        # Server-Sent Events response
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                return json.loads(line[len("data:"):].strip())

        raise ValueError(f"Unable to parse MCP response:\n{text}")
