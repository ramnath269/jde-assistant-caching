from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field


@dataclass
class UserSession:

    session_token: str

    username: str

    # Opaque reference handed out by the MCP server. It is a credential
    # in the sense that anyone holding it can act as this user - keep
    # it server-side, never send it to the browser, never log it.
    mcp_session_id: str

    environment: str

    created_at: float = field(default_factory=time.time)

    expires_at: float | None = None

    conversation_ids: list[str] = field(default_factory=list)


class SessionManager:
    """
    Tracks logged-in users, their JDE token, and the conversations
    they own. In-memory only, mirroring ConversationManager.
    """

    def __init__(self) -> None:
        self._by_username: dict[str, UserSession] = {}
        self._by_token: dict[str, UserSession] = {}

    def create(
        self,
        username: str,
        mcp_session_id: str,
        environment: str,
        expires_at: float | None = None,
    ) -> UserSession:

        existing = self._by_username.get(username)
        if existing:
            self._by_token.pop(existing.session_token, None)

        session = UserSession(
            session_token=secrets.token_urlsafe(32),
            username=username,
            mcp_session_id=mcp_session_id,
            environment=environment,
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
