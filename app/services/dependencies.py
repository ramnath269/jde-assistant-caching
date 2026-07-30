# app/services/dependencies.py

from app.services.mcp_client import MCPClient
from app.services.tool_manager import ToolManager
from app.services.claude_service import ClaudeService

mcp_client = MCPClient()

tool_manager = ToolManager(mcp_client)

claude_service = ClaudeService(tool_manager)