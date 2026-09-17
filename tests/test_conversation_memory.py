from ai_screenshot_assistant.core.conversation import MAX_CONVERSATION_MESSAGES, MAX_TURN_CHARS, cap_conversation_memory


def test_cap_conversation_memory_keeps_recent_turns_only() -> None:
    items = [{"role": "user", "content": f"msg-{index}"} for index in range(20)]

    capped = cap_conversation_memory(items)

    assert len(capped) == MAX_CONVERSATION_MESSAGES
    assert capped[0]["content"] == "msg-14"
    assert capped[-1]["content"] == "msg-19"


def test_cap_conversation_memory_truncates_long_turns() -> None:
    capped = cap_conversation_memory([{"role": "assistant", "content": "A" * 5000}])

    assert capped == [{"role": "assistant", "content": "A" * MAX_TURN_CHARS}]


def test_cap_conversation_memory_skips_empty_items() -> None:
    assert cap_conversation_memory([{"role": "user", "content": "  "}]) == []
    assert cap_conversation_memory(None) == []
