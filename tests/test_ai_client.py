import io

from PIL import Image

from ai_screenshot_assistant.ai.client import (
    AI_IMAGE_MAX_SIDE,
    ALBUM_IMAGE_MAX_SIDE,
    CancellationToken,
    OpenRouterVisionClient,
    ProviderConfig,
    _prepare_image_for_ai,
    _prepare_image_for_album,
    parse_ai_result,
)
from ai_screenshot_assistant.ai.prompt import VISION_PROMPT


def test_cancellation_token_closes_attached_response() -> None:
    class Response:
        closed = False

        def close(self):
            self.closed = True

    response = Response()
    token = CancellationToken()
    token.attach_response(response)
    token.cancel()

    assert response.closed is True
    assert token.cancelled is True


def test_parse_json_ai_result() -> None:
    result = parse_ai_result('{"question":"q","answer":"B","reason":"because","confidence":0.95}')

    assert result.answer == "B"
    assert result.reason == "because"
    assert result.confidence == "0.95"


def test_shared_vision_prompt_forbids_deep_thinking() -> None:
    assert "禁止先分析" in VISION_PROMPT
    assert "先写思考过程" in VISION_PROMPT
    assert "答案：" in VISION_PROMPT
    assert "解析：" in VISION_PROMPT


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


def test_extract_stream_delta_ignores_reasoning() -> None:
    data = '{"choices":[{"delta":{"reasoning_content":"先看图"}}]}'

    assert OpenRouterVisionClient._extract_delta(data) == ""


def test_extract_stream_delta_prefers_content_over_reasoning() -> None:
    data = '{"choices":[{"delta":{"content":"答案：B","reasoning_content":"思考过程"}}]}'

    assert OpenRouterVisionClient._extract_delta(data) == "答案：B"


def test_extract_responses_api_ignores_reasoning_delta() -> None:
    data = '{"type":"response.reasoning_text.delta","delta":"慢慢想"}'

    assert OpenRouterVisionClient._extract_delta(data) == ""


def test_extract_responses_api_text_delta() -> None:
    data = '{"type":"response.output_text.delta","delta":"看见了题目"}'

    assert OpenRouterVisionClient._extract_delta(data) == "看见了题目"


def test_doubao_uses_ark_responses_api(monkeypatch) -> None:
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def raise_for_status(self):
            return None

        def iter_lines(self, **kwargs):
            yield b'data: {"type":"response.output_text.delta","delta":"cat"}'
            yield b"data: [DONE]"

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        captured["verify"] = kwargs["verify"]
        return Response()

    monkeypatch.setattr("ai_screenshot_assistant.ai.client.requests.post", fake_post)
    client = OpenRouterVisionClient(
        ProviderConfig(
            name="Doubao",
            api_key="key",
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            model="doubao-seed-1-6-vision-250815",
        )
    )

    assert list(client.analyze_image_stream(b"png")) == ["cat"]
    assert captured["url"] == "https://ark.cn-beijing.volces.com/api/v3/responses"
    assert captured["json"]["model"] == "doubao-seed-1-6-vision-250815"
    assert captured["json"]["stream"] is True
    assert captured["verify"] is False
    assert captured["json"]["thinking"] == {"type": "disabled"}
    content = captured["json"]["input"][0]["content"]
    assert content[0]["type"] == "input_image"
    assert str(content[0]["image_url"]).startswith("data:image/")
    assert content[-1]["type"] == "input_text"
    assert "messages" not in captured["json"]


def test_doubao_turbo_uses_chat_completions(monkeypatch) -> None:
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def raise_for_status(self):
            return None

        def iter_lines(self, **kwargs):
            yield b'data: {"choices":[{"delta":{"content":"ok"}}]}'
            yield b"data: [DONE]"

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        return Response()

    monkeypatch.setattr("ai_screenshot_assistant.ai.client.requests.post", fake_post)
    client = OpenRouterVisionClient(
        ProviderConfig(
            name="Doubao",
            api_key="key",
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            model="doubao-seed-2-1-turbo-260628",
        )
    )

    assert list(client.analyze_image_stream(b"png")) == ["ok"]
    assert captured["url"] == "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
    assert captured["json"]["model"] == "doubao-seed-2-1-turbo-260628"
    assert captured["json"]["messages"][0]["content"][-1]["type"] == "text"
    assert captured["json"]["thinking"] == {"type": "disabled"}
    assert "先写思考过程" in captured["json"]["messages"][0]["content"][-1]["text"]
    assert "input" not in captured["json"]


def test_doubao_mini_lite_and_pro_use_responses_api(monkeypatch) -> None:
    captured: dict = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def raise_for_status(self):
            return None

        def iter_lines(self, **kwargs):
            yield b'data: {"type":"response.output_text.delta","delta":"ok"}'
            yield b"data: [DONE]"

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        return Response()

    monkeypatch.setattr("ai_screenshot_assistant.ai.client.requests.post", fake_post)
    for model in (
        "doubao-seed-2-0-mini-260428",
        "doubao-seed-2-0-lite-260428",
        "doubao-seed-2-1-pro-260915",
    ):
        captured.clear()
        client = OpenRouterVisionClient(
            ProviderConfig(
                name="Doubao",
                api_key="key",
                base_url="https://ark.cn-beijing.volces.com/api/v3",
                model=model,
            )
        )
        assert list(client.analyze_image_stream(b"png")) == ["ok"]
        assert captured["url"] == "https://ark.cn-beijing.volces.com/api/v3/responses"
        assert captured["json"]["model"] == model
        assert captured["json"]["thinking"] == {"type": "disabled"}
        assert captured["json"]["input"][0]["content"][0]["type"] == "input_image"


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
    assert "先写思考过程" in captured["json"]["messages"][0]["content"][-1]["text"]
    assert captured["iter_lines_kwargs"] == {"chunk_size": 1, "decode_unicode": False}


def test_thinking_model_keeps_reasoning_enabled(monkeypatch) -> None:
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def raise_for_status(self):
            return None

        def iter_lines(self, **kwargs):
            yield b'data: {"choices":[{"delta":{"content":"A"}}]}'
            yield b"data: [DONE]"

    def fake_post(url, **kwargs):
        captured["json"] = kwargs["json"]
        return Response()

    monkeypatch.setattr("ai_screenshot_assistant.ai.client.requests.post", fake_post)
    client = OpenRouterVisionClient(
        ProviderConfig(
            name="OpenRouter",
            api_key="key",
            base_url="https://openrouter.ai/api/v1",
            model="qwen/qwen3-vl-235b-a22b-thinking",
        )
    )

    assert list(client.analyze_image_stream(b"png")) == ["A"]
    assert "reasoning_effort" not in captured["json"]
    assert captured["json"]["model"] == "qwen/qwen3-vl-235b-a22b-thinking"


def test_openrouter_deepseek_flash_disables_reasoning(monkeypatch) -> None:
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def raise_for_status(self):
            return None

        def iter_lines(self, **kwargs):
            yield b'data: {"choices":[{"delta":{"content":"B"}}]}'
            yield b"data: [DONE]"

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        return Response()

    monkeypatch.setattr("ai_screenshot_assistant.ai.client.requests.post", fake_post)
    client = OpenRouterVisionClient(
        ProviderConfig(
            name="OpenRouter",
            api_key="key",
            base_url="https://openrouter.ai/api/v1",
            model="deepseek/deepseek-v4.1-flash",
        )
    )

    assert list(client.analyze_image_stream(b"png")) == ["B"]
    assert captured["url"].endswith("/chat/completions")
    assert captured["json"]["model"] == "deepseek/deepseek-v4.1-flash"
    assert captured["json"]["reasoning_effort"] == "none"


def test_large_images_are_resized_and_compressed_for_ai() -> None:
    source = Image.new("RGB", (2200, 1600), color=(245, 245, 245))
    source_buffer = io.BytesIO()
    source.save(source_buffer, format="PNG")

    image_bytes, mime_type = _prepare_image_for_ai(source_buffer.getvalue())

    assert mime_type == "image/jpeg"
    prepared = Image.open(io.BytesIO(image_bytes))
    assert max(prepared.size) == AI_IMAGE_MAX_SIDE


def test_album_images_keep_higher_resolution_than_ai() -> None:
    source = Image.new("RGB", (2200, 1600), color=(245, 245, 245))
    source_buffer = io.BytesIO()
    source.save(source_buffer, format="PNG")
    png = source_buffer.getvalue()

    album_bytes, album_mime = _prepare_image_for_album(png)
    ai_bytes, ai_mime = _prepare_image_for_ai(png)

    album = Image.open(io.BytesIO(album_bytes))
    ai_image = Image.open(io.BytesIO(ai_bytes))
    assert album_mime in {"image/png", "image/jpeg"}
    assert ai_mime == "image/jpeg"
    assert max(album.size) == 2200
    assert max(album.size) <= ALBUM_IMAGE_MAX_SIDE
    assert max(ai_image.size) == AI_IMAGE_MAX_SIDE
    assert max(album.size) > max(ai_image.size)
