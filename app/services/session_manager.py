from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from app.services.mcp_client import MCPClient
from app.services.tool_manager import ToolManager


@dataclass
class UserSession:

    session_token: str

    username: str

    environment: str

    # Bearer token minted by the MCP server at login. A credential in the
    # sense that anyone holding it can act as this user (within their RBAC
    # role) - keep it server-side, never send it to the browser, never log
    # it. There is no refresh token for this login path, so once the MCP
    # server's own TTL on it expires, mcp_client's calls start 401ing and
    # this session has to be re-established via a fresh /auth/login.
    mcp_access_token: str

    # This user's own MCP connection: every request it sends carries
    # mcp_access_token, including the initialize() handshake itself, because
    # the MCP server gates its whole /mcp surface behind OAuth now. Not
    # shared across users - see mcp_client.py's docstring.
    mcp_client: MCPClient

    # This user's own tool catalog, as returned by the MCP server's
    # RBAC-filtered tools/list for their bearer token - different users can
    # legitimately see a different tool set here.
    tool_manager: ToolManager

    # Claude-formatted tool definitions built from tool_manager.all() at
    # login (and again on /tools/reload). Precomputed so every chat turn
    # doesn't re-derive it; content is stable across a session so Claude's
    # own prompt caching still hits per user.
    claude_tools: tuple[dict[str, Any], ...] = ()

    created_at: float = field(default_factory=time.time)

    expires_at: float | None = None

    conversation_ids: list[str] = field(default_factory=list)


class SessionManager:
    """
    Tracks logged-in users, their MCP connection, and the conversations
    they own. In-memory only, mirroring ConversationManager.
    """

    def __init__(self) -> None:
        self._by_username: dict[str, UserSession] = {}
        self._by_token: dict[str, UserSession] = {}

    async def create(
        self,
        username: str,
        environment: str,
        mcp_access_token: str,
        mcp_client: MCPClient,
        tool_manager: ToolManager,
        claude_tools: tuple[dict[str, Any], ...],
        expires_at: float | None = None,
    ) -> UserSession:

        existing = self._by_username.get(username)
        if existing:
            self._by_token.pop(existing.session_token, None)
            # A second login for a username that's already logged in orphans
            # the old MCP connection - close it rather than leaking it.
            await existing.mcp_client.close()

        session = UserSession(
            session_token=secrets.token_urlsafe(32),
            username=username,
            environment=environment,
            mcp_access_token=mcp_access_token,
            mcp_client=mcp_client,
            tool_manager=tool_manager,
            claude_tools=claude_tools,
            expires_at=expires_at,
        )

        self._by_username[username] = session
        self._by_token[session.session_token] = session

        return session

    def get_by_token(self, session_token: str) -> UserSession | None:
        return self._by_token.get(session_token)

    def get_by_username(self, username: str) -> UserSession | None:
        return self._by_username.get(username)

    def add_conversation(self, username: str, conversation_id: str) -> None:
        session = self._by_username.get(username)

        if session and conversation_id not in session.conversation_ids:
            session.conversation_ids.append(conversation_id)

    def logout(self, session_token: str) -> None:
        session = self._by_token.pop(session_token, None)

        if session:
            self._by_username.pop(session.username, None)

    def count(self) -> int:
        return len(self._by_token)

    async def close_all(self) -> None:
        """Close every active user's MCP connection. Called at shutdown."""

        for session in list(self._by_token.values()):
            await session.mcp_client.close()
