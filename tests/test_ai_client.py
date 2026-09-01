from ai_screenshot_assistant.ai.client import OpenRouterVisionClient, parse_ai_result


def test_parse_json_ai_result() -> None:
    result = parse_ai_result('{"question":"q","answer":"B","reason":"because","confidence":0.95}')

    assert result.answer == "B"
    assert result.reason == "because"
    assert result.confidence == "0.95"


def test_parse_plain_text_ai_result() -> None:
    result = parse_ai_result("这是一张截图摘要")

    assert result.text == "这是一张截图摘要"
    assert result.answer == "这是一张截图摘要"


def test_parse_answer_first_text() -> None:
    result = parse_ai_result("答案：B\n解析：因为 TCP 面向连接并保证可靠传输。")

    assert result.answer == "B"
    assert result.reason == "因为 TCP 面向连接并保证可靠传输。"


def test_extract_stream_delta() -> None:
    data = '{"choices":[{"delta":{"content":"hello"}}]}'

    assert OpenRouterVisionClient._extract_delta(data) == "hello"
