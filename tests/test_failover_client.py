import requests

from ai_screenshot_assistant.ai.client import FailoverVisionClient, ProviderConfig


class FakeClient:
    def __init__(self, chunks=None, error=None):
        self.chunks = chunks or []
        self.error = error
        self.calls = 0

    def analyze_image_stream(self, _png):
        self.calls += 1
        if self.error is not None:
            raise self.error
        yield from self.chunks


def http_error(status: int) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError(f"HTTP {status}", response=response)


def config(name: str) -> ProviderConfig:
    return ProviderConfig(name=name, api_key="key", base_url="https://example.test", model="vision")


def test_deepseek_402_switches_to_openrouter_for_session() -> None:
    changes = []
    client = FailoverVisionClient(config("DeepSeek"), config("OpenRouter"), changes.append)
    deepseek = FakeClient(error=http_error(402))
    openrouter = FakeClient(chunks=["答案：B", "\n解析：测试"])
    client.deepseek = deepseek
    client.openrouter = openrouter

    assert list(client.analyze_image_stream(b"png")) == ["答案：B", "\n解析：测试"]
    assert list(client.analyze_image_stream(b"png")) == ["答案：B", "\n解析：测试"]
    assert client.current_provider == "openrouter"
    assert changes == ["openrouter"]
    assert deepseek.calls == 1
    assert openrouter.calls == 2


def test_non_402_does_not_switch() -> None:
    client = FailoverVisionClient(config("DeepSeek"), config("OpenRouter"))
    client.deepseek = FakeClient(error=http_error(429))
    client.openrouter = FakeClient(chunks=["unused"])

    try:
        list(client.analyze_image_stream(b"png"))
    except requests.HTTPError as exc:
        assert exc.response.status_code == 429
    else:
        raise AssertionError("429 should propagate")
    assert client.current_provider == "deepseek"
    assert client.openrouter.calls == 0


def test_openrouter_402_does_not_loop_back() -> None:
    client = FailoverVisionClient(config("DeepSeek"), config("OpenRouter"))
    client.current_provider = "openrouter"
    client.openrouter = FakeClient(error=http_error(402))

    try:
        list(client.analyze_image_stream(b"png"))
    except requests.HTTPError as exc:
        assert exc.response.status_code == 402
    else:
        raise AssertionError("OpenRouter 402 should propagate")
    assert client.current_provider == "openrouter"
