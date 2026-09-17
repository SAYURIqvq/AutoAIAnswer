from __future__ import annotations

MAX_CONVERSATION_MESSAGES = 6
MAX_TURN_CHARS = 600


def cap_conversation_memory(items: list[dict[str, str]] | None) -> list[dict[str, str]]:
    if not items:
        return []
    capped: list[dict[str, str]] = []
    for item in items[-MAX_CONVERSATION_MESSAGES:]:
        role = str(item.get("role") or "user")
        if role not in {"user", "assistant"}:
            role = "user"
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        if len(content) > MAX_TURN_CHARS:
            content = content[:MAX_TURN_CHARS]
        capped.append({"role": role, "content": content})
    return capped
