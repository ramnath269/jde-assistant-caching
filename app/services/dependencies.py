# app/services/dependencies.py

from app.services.jde_auth_client import JDEAuthClient
from app.services.claude_service import ClaudeService
from app.services.conversation_manager import ConversationManager
from app.services.session_manager import SessionManager

# mcp_client and tool_manager are NOT process-wide singletons anymore: the
# MCP server gates its whole /mcp surface behind OAuth, so each one has to be
# bound to a specific logged-in user's bearer token. They're created per
# session in app/api/auth.py's login route and live on UserSession instead.

jde_auth_client = JDEAuthClient()

conversation_manager = ConversationManager()

session_manager = SessionManager()

claude_service = ClaudeService(conversation_manager, session_manager)
