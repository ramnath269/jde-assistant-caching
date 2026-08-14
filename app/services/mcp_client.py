from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import settings
from app.core.logger import logger


class MCPClient:
    """
    JSON-RPC client for Streamable HTTP MCP servers.
    """

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=settings.request_timeout,
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            follow_redirects=True,
        )

        self._request_id = 0
        self._session_id: str | None = None

    @property
    def session_id(self) -> str | None:
        return self._session_id

    async def close(self) -> None:
        await self._client.aclose()

    async def initialize(self) -> None:

        logger.info("Initializing MCP session...")

        await self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "jde-assistant",
                    "version": "2.0",
                },
            },
        )

        logger.info("MCP session established.")

    async def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:

        self._request_id += 1

        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params or {},
        }

        headers = {}

        if self._session_id:
            headers["mcp-session-id"] = self._session_id

        if extra_headers:
            headers.update(extra_headers)

        response = await self._client.post(
            settings.mcp_server_url,
            json=payload,
            headers=headers,
        )

        response.raise_for_status()

        if "mcp-session-id" in response.headers:
            self._session_id = response.headers["mcp-session-id"]
        return self._parse_response(response.text)

    async def list_tools(self) -> list[dict]:

        response = await self.request("tools/list")

        return response["result"]["tools"]

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict,
        jde_session_id: str | None = None,
    ) -> dict:

        extra_headers = (
            {"X-JDE-Session": jde_session_id}
            if jde_session_id
            else None
        )

        response = await self.request(
            "tools/call",
            {
                "name": tool_name,
                "arguments": arguments,
            },
            extra_headers=extra_headers,
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