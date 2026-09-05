from __future__ import annotations

from typing import Any

from app.core.logger import logger
from app.models import MCPTool
from app.services.mcp_client import MCPClient


class ToolNotFoundError(Exception):
    """Raised when a requested tool is not loaded."""


class ToolManager:
    """
    Manages MCP tools.

    Responsibilities:
    - Load tools from the MCP server
    - Cache tool metadata
    - Execute tools
    - Reload tools
    """

    def __init__(self, mcp_client: MCPClient):
        self._client = mcp_client
        self._tools: dict[str, MCPTool] = {}

    async def load(self) -> None:
        """Load all tools from the MCP server."""

        logger.info("Loading MCP tools...")

        tools = await self._client.list_tools()

        loaded: dict[str, MCPTool] = {}

        for tool in tools:
            loaded[tool["name"]] = MCPTool(
                name=tool["name"],
                description=tool.get("description", ""),
                inputSchema=tool.get("inputSchema", {}),
            )

        # Stable ordering improves Claude prompt cache hits
        self._tools = dict(sorted(loaded.items()))

        logger.info("Loaded %d tools.", len(self._tools))

    async def reload(self) -> None:
        """Reload all tools."""

        logger.info("Reloading MCP tools...")
        await self.load()

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """
        Execute a tool through MCP. Identity is carried by this instance's
        MCPClient (bound to one user's bearer token at construction), not
        passed per call.
        """

        if tool_name not in self._tools:
            raise ToolNotFoundError(
                f"Tool '{tool_name}' is not loaded."
            )

        logger.info("Executing tool: %s", tool_name)

        return await self._client.call_tool(
            tool_name,
            arguments,
        )

    def all(self) -> list[MCPTool]:
        """Return all tools."""

        return list(self._tools.values())

    def get(self, tool_name: str) -> MCPTool | None:
        """Get a tool by name."""

        return self._tools.get(tool_name)

    def exists(self, tool_name: str) -> bool:
        """Check whether a tool exists."""

        return tool_name in self._tools

    def names(self) -> list[str]:
        """Return all tool names."""

        return list(self._tools.keys())

    @property
    def count(self) -> int:
        """Return the number of loaded tools."""

        return len(self._tools)

    def health(self) -> dict[str, Any]:
        """Return ToolManager health information."""

        return {
            "loaded": self.count,
            "tools": self.names(),
        }