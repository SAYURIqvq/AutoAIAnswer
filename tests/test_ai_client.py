from ai_screenshot_assistant.ai.client import OpenRouterVisionClient, ProviderConfig, parse_ai_result


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


def test_parse_multi_question_text() -> None:
    result = parse_ai_result(
        "【第1题】TCP 特点\n答案：B\n解析：面向连接\n\n【第2题】UDP 特点\n答案：A\n解析：无连接"
    )

    assert "【第1题】" in result.text
    assert result.answer == "【第1题】TCP 特点 B；【第2题】UDP 特点 A"
    assert result.reason is not None
    assert "面向连接" in result.reason
    assert "无连接" in result.reason


def test_parse_questions_json() -> None:
    result = parse_ai_result(
        '{"questions":[{"question":"第1题","answer":"B","reason":"TCP"},{"question":"第2题","answer":"A","reason":"UDP"}]}'
    )

    assert result.answer == "第1题 B；第2题 A"
    assert result.reason == "第1题：TCP\n第2题：UDP"


def test_openrouter_request_disables_reasoning_and_uses_low_latency_stream(monkeypatch) -> None:
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def raise_for_status(self):
            return None

        def iter_lines(self, **kwargs):
            captured["iter_lines_kwargs"] = kwargs
            yield b'data: {"choices":[{"delta":{"content":"A"}}]}'
            yield b"data: [DONE]"

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        captured["stream"] = kwargs["stream"]
        return Response()

    monkeypatch.setattr("ai_screenshot_assistant.ai.client.requests.post", fake_post)
    client = OpenRouterVisionClient(
        ProviderConfig(
            name="OpenRouter",
            api_key="key",
            base_url="https://openrouter.ai/api/v1",
            model="qwen/qwen3.8-flash",
        )
    )

    assert list(client.analyze_image_stream(b"png")) == ["A"]
    assert captured["stream"] is True
    assert captured["json"]["stream"] is True
    assert captured["json"]["reasoning_effort"] == "none"
    assert captured["iter_lines_kwargs"] == {"chunk_size": 1, "decode_unicode": False}
