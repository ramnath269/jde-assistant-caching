# app/services/dependencies.py

from app.services.mcp_client import MCPClient
from app.services.jde_auth_client import JDEAuthClient
from app.services.tool_manager import ToolManager
from app.services.claude_service import ClaudeService
from app.services.conversation_manager import ConversationManager
from app.services.session_manager import SessionManager

mcp_client = MCPClient()

jde_auth_client = JDEAuthClient()

tool_manager = ToolManager(mcp_client)

conversation_manager = ConversationManager()

session_manager = SessionManager()

claude_service = ClaudeService(tool_manager, conversation_manager, session_manager)