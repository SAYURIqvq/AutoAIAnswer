import pytest
import requests

from ai_screenshot_assistant.ai.client import FailoverVisionClient, ProviderConfig
from ai_screenshot_assistant.ai.models import MODEL_ROUTES, resolve_model_choice


class FakeClient:
    def __init__(self, error=None):
        self.calls = 0
        self.error = error

    def analyze_images_stream(self, images, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        yield "答案：A"


def config(name, key="test-only"):
    return ProviderConfig(name, key, "https://example.test", "unused")


@pytest.mark.parametrize("route_id", list(MODEL_ROUTES))
def test_selected_route_uses_its_own_model_and_provider(route_id):
    router = FailoverVisionClient(config("DeepSeek"), config("Qwen"),
                                 model_tier=route_id, doubao=config("Doubao"))
    route = MODEL_ROUTES[route_id]
    assert router.current_provider == route.provider
    assert router.current_model_id() == route.model
    clients = {name: FakeClient() for name in ("qwen", "deepseek", "doubao")}
    for name, client in clients.items():
        setattr(router, name, client)
    assert list(router.analyze_images_stream([b"image"])) == ["答案：A"]
    assert {name: client.calls for name, client in clients.items()} == {
        name: int(name == route.provider) for name in clients}


@pytest.mark.parametrize("status", [400, 401, 402, 404, 429, 500])
@pytest.mark.parametrize("route_id", ["qwen-122b", "deepseek-flash", "doubao-seed-2-1-turbo"])
def test_errors_never_send_request_to_another_provider(status, route_id):
    router = FailoverVisionClient(config("DeepSeek"), config("Qwen"),
                                 model_tier=route_id, doubao=config("Doubao"))
    selected = router.current_provider
    response = requests.Response()
    response.status_code = status
    error = requests.HTTPError(response=response)
    clients = {name: FakeClient(error if name == selected else None)
               for name in ("qwen", "deepseek", "doubao")}
    for name, client in clients.items():
        setattr(router, name, client)
    with pytest.raises(requests.HTTPError):
        list(router.analyze_images_stream([b"image"]))
    assert router.current_provider == selected
    assert all(client.calls == int(name == selected) for name, client in clients.items())


def test_missing_selected_key_does_not_use_other_saved_keys():
    router = FailoverVisionClient(config("DeepSeek"), config("Qwen", ""), model_tier="qwen-122b")
    router.deepseek = FakeClient()
    with pytest.raises(RuntimeError, match="未配置 Key"):
        list(router.analyze_images_stream([b"image"]))
    assert router.deepseek.calls == 0


def test_switching_routes_updates_model_without_replacing_keys():
    router = FailoverVisionClient(config("DeepSeek", "deepseek-test"), config("Qwen", "qwen-test"))
    router.apply_model_tier("qwen-122b")
    assert router.current_model_id() == "qwen3.5-122b-a10b"
    assert router.qwen.provider.api_key == "qwen-test"
    router.apply_model_tier("simple")
    assert router.current_provider == "deepseek"
    assert router.deepseek.provider.api_key == "deepseek-test"
