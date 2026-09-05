from __future__ import annotations

import json
from typing import Any


def parse_text_payload(result: Any) -> dict[str, Any] | None:
    """
    MCP tool results come back as {content: [{type: text, text: ...}],
    isError}. `text` is a JSON-encoded business payload. Returns the
    decoded payload, or None if the shape doesn't match.
    """

    if not isinstance(result, dict) or result.get("isError"):
        return None

    content = result.get("content")

    if not isinstance(content, list) or not content:
        return None

    first = content[0]
    text = first.get("text") if isinstance(first, dict) else None

    if not text:
        return None

    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return None

    return parsed if isinstance(parsed, dict) else None
