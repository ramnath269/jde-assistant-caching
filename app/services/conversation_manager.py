from collections import defaultdict
from typing import Any

class ConversationManager:

    def __init__(self):
        self._conversations: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def create_if_not_exists(self, conversation_id: str):
        self._conversations.setdefault(conversation_id, [])

    def get_messages(
        self,
        conversation_id: str,
    ) -> list[dict[str, Any]]:
        return list(self._conversations.get(conversation_id, []))


    def append(
        self,
        conversation_id: str,
        message: dict[str, Any],
    ) -> None:
        self._conversations[conversation_id].append(message)

    def clear(
        self,
        conversation_id: str,
    ) -> None:
        self._conversations.pop(conversation_id, None)