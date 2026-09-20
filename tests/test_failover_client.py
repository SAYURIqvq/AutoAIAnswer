import requests

from ai_screenshot_assistant.ai.client import FailoverVisionClient, ProviderConfig
from ai_screenshot_assistant.ai.models import (
    DOUBAO_MINI_MODEL,
    DOUBAO_PRO_MODEL,
    DOUBAO_VISION_MODEL,
    OPENROUTER_DEEPSEEK_FLASH,
    ROUTE_DOUBAO_MINI,
    ROUTE_DOUBAO_PRO,
    ROUTE_DOUBAO_SEED_VISION,
    ROUTE_OPENROUTER_DEEPSEEK_FLASH,
)


class FakeClient:
    def __init__(self, chunks=None, error=None):
        self.chunks = chunks or []
        self.error = error
        self.calls = 0

    def analyze_image_stream(self, _png, user_text=None, conversation=None):
        self.calls += 1
        if self.error is not None:
            raise self.error
        yield from self.chunks


def http_error(status: int) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError(f"HTTP {status}", response=response)


def config(name: str, api_key: str = "key", model: str = "vision") -> ProviderConfig:
    return ProviderConfig(name=name, api_key=api_key, base_url="https://example.test", model=model)


def test_deepseek_402_switches_to_openrouter_for_session() -> None:
    changes = []
    client = FailoverVisionClient(config("DeepSeek"), config("OpenRouter"), changes.append, model_tier="simple")
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
    client = FailoverVisionClient(config("DeepSeek"), config("OpenRouter"), model_tier="simple")
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


def test_openrouter_402_falls_back_to_deepseek() -> None:
    changes: list[str] = []
    client = FailoverVisionClient(config("DeepSeek"), config("OpenRouter"), changes.append)
    client.openrouter = FakeClient(error=http_error(402))
    client.deepseek = FakeClient(chunks=["答案：C"])

    assert list(client.analyze_image_stream(b"png")) == ["答案：C"]
    assert client.current_provider == "deepseek"
    assert changes == ["deepseek"]


def test_openrouter_only_key_is_used() -> None:
    client = FailoverVisionClient(config("DeepSeek", api_key=""), config("OpenRouter"))
    client.deepseek = FakeClient(chunks=["unused"])
    client.openrouter = FakeClient(chunks=["答案：A"])

    assert client.current_provider == "openrouter"
    assert list(client.analyze_image_stream(b"png")) == ["答案：A"]
    assert client.deepseek.calls == 0
    assert client.openrouter.calls == 1


def test_missing_keys_raise_before_calling_providers() -> None:
    client = FailoverVisionClient(config("DeepSeek", api_key=""), config("OpenRouter", api_key=""))
    client.deepseek = FakeClient(chunks=["unused"])
    client.openrouter = FakeClient(chunks=["unused"])

    assert client.current_provider == "none"
    try:
        list(client.analyze_image_stream(b"png"))
    except RuntimeError as exc:
        assert "至少填写" in str(exc)
    else:
        raise AssertionError("missing keys should raise")
    assert client.deepseek.calls == 0
    assert client.openrouter.calls == 0


def test_good_tier_uses_chinese_openrouter_model_when_both_keys() -> None:
    client = FailoverVisionClient(config("DeepSeek"), config("OpenRouter"), model_tier="good")

    assert client.current_provider == "openrouter"
    assert client.current_model_id() == "qwen/qwen3-vl-235b-a22b-thinking"
    assert client.openrouter.provider.model == "qwen/qwen3-vl-235b-a22b-thinking"
    assert client.deepseek.provider.model == "deepseek-flash"


def test_simple_tier_prefers_deepseek_flash_when_available() -> None:
    client = FailoverVisionClient(config("DeepSeek"), config("OpenRouter"), model_tier="simple")

    assert client.current_provider == "deepseek"
    assert client.current_model_id() == "deepseek-flash"


def test_openrouter_deepseek_flash_route_uses_openrouter() -> None:
    client = FailoverVisionClient(
        config("DeepSeek"),
        config("OpenRouter"),
        model_tier=ROUTE_OPENROUTER_DEEPSEEK_FLASH,
    )

    assert client.current_provider == "openrouter"
    assert client.current_model_id() == OPENROUTER_DEEPSEEK_FLASH
    assert client.openrouter.provider.model == OPENROUTER_DEEPSEEK_FLASH
    assert client.deepseek.provider.model == "deepseek-flash"


def test_official_deepseek_without_key_falls_back_to_openrouter_deepseek() -> None:
    client = FailoverVisionClient(
        config("DeepSeek", api_key=""),
        config("OpenRouter"),
        model_tier="simple",
    )

    assert client.current_provider == "openrouter"
    assert client.current_model_id() == OPENROUTER_DEEPSEEK_FLASH


def test_switching_tier_updates_provider_and_model() -> None:
    changes: list[str] = []
    client = FailoverVisionClient(config("DeepSeek"), config("OpenRouter"), changes.append, model_tier="simple")

    choice = client.apply_model_tier("medium")

    assert choice.tier == "openrouter-qwen-32b"
    assert client.current_provider == "openrouter"
    assert client.current_model_id() == "qwen/qwen3-vl-32b-instruct"
    assert changes == []


def test_doubao_route_uses_ark_model() -> None:
    client = FailoverVisionClient(
        config("DeepSeek"),
        config("OpenRouter"),
        model_tier=ROUTE_DOUBAO_SEED_VISION,
        doubao=config("Doubao", model=DOUBAO_VISION_MODEL),
    )

    assert client.current_provider == "doubao"
    assert client.current_model_id() == DOUBAO_VISION_MODEL
    assert client.doubao.provider.model == DOUBAO_VISION_MODEL


def test_switching_doubao_routes_updates_ark_model() -> None:
    client = FailoverVisionClient(
        config("DeepSeek"),
        config("OpenRouter"),
        model_tier=ROUTE_DOUBAO_MINI,
        doubao=config("Doubao", model=DOUBAO_VISION_MODEL),
    )

    assert client.current_model_id() == DOUBAO_MINI_MODEL
    client.apply_model_tier(ROUTE_DOUBAO_PRO)
    assert client.current_provider == "doubao"
    assert client.current_model_id() == DOUBAO_PRO_MODEL
    assert client.doubao.provider.model == DOUBAO_PRO_MODEL


def test_doubao_402_falls_back_to_openrouter() -> None:
    changes: list[str] = []
    client = FailoverVisionClient(
        config("DeepSeek"),
        config("OpenRouter"),
        changes.append,
        model_tier=ROUTE_DOUBAO_SEED_VISION,
        doubao=config("Doubao"),
    )
    client.doubao = FakeClient(error=http_error(402))
    client.openrouter = FakeClient(chunks=["答案：豆包备份"])
    client.deepseek = FakeClient(chunks=["unused"])

    assert list(client.analyze_image_stream(b"png")) == ["答案：豆包备份"]
    assert client.current_provider == "openrouter"
    assert changes == ["openrouter"]
    assert client.deepseek.calls == 0



def test_deepseek_402_without_openrouter_key_does_not_switch() -> None:
    client = FailoverVisionClient(config("DeepSeek"), config("OpenRouter", api_key=""), model_tier="simple")
    client.deepseek = FakeClient(error=http_error(402))
    client.openrouter = FakeClient(chunks=["unused"])

    try:
        list(client.analyze_image_stream(b"png"))
    except RuntimeError as exc:
        assert "没有其他可用 Key" in str(exc)
    else:
        raise AssertionError("402 without other keys should raise")
    assert client.current_provider == "deepseek"
    assert client.openrouter.calls == 0
