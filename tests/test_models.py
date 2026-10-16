import pytest
from ai_screenshot_assistant.ai.models import (
    MODEL_ROUTES, DEFAULT_MODEL_TIER, is_chinese_model,
    normalize_model_tier, resolve_model_choice, route_options,
)

@pytest.mark.parametrize("old,new", [
    ("good", "qwen-vl-plus"), ("好", "qwen-vl-plus"),
    ("medium", "qwen-vl-flash"), ("simple", "deepseek-flash"),
    ("openrouter-deepseek-flash", "qwen-flash"),
    ("openrouter-deepseek", "qwen-flash"),
    ("openrouter-qwen-122b", "qwen-122b"),
    ("openrouter-qwen-235b", "qwen-vl-plus"),
    ("openrouter-qwen-32b", "qwen-vl-flash"),
    ("openrouter-qwen-8b", "qwen-vl-flash"),
    ("openrouter-qwen-30b-thinking", "qwen-vl-plus"),
    ("doubao", "doubao-seed-2-1-turbo"),
    ("doubao-seed-vision", "doubao-seed-2-1-turbo"),
    ("unknown", DEFAULT_MODEL_TIER),
])
def test_old_saved_routes_migrate(old, new):
    assert normalize_model_tier(old) == new

@pytest.mark.parametrize("route", list(MODEL_ROUTES.values()))
def test_routes_require_the_selected_platform_key(route):
    flags = {"has_deepseek": False, "has_qwen": False, "has_doubao": False}
    missing = resolve_model_choice(route.route_id, **flags)
    assert missing.provider == "none"
    assert "未配置 Key" in missing.display_name
    flags["has_" + route.provider] = True
    ready = resolve_model_choice(route.route_id, **flags)
    assert ready.provider == route.provider
    assert ready.model == route.model
    assert ready.route == route.route_id
    assert is_chinese_model(ready.model)
    if route.provider == "qwen":
        assert ready.qwen_model == route.model
        assert "/" not in route.model
        assert route.model.startswith("qwen")

@pytest.mark.parametrize("model", ["openai/gpt-4o", "anthropic/claude-sonnet", "google/gemini", "meta-llama/llama"])
def test_foreign_models_not_allowed(model):
    assert not is_chinese_model(model)


def test_options_have_unique_ids_and_no_openrouter_provider():
    options = route_options()
    assert len({row[0] for row in options}) == len(options)
    assert all("OpenRouter" not in row[1] for row in options)
    assert sum(route.provider == "qwen" for route in MODEL_ROUTES.values()) == 8
    for route_id, label, description in options:
        assert MODEL_ROUTES[route_id].model in description
        assert label


def test_phone_and_desktop_have_identical_model_options():
    from html.parser import HTMLParser
    from pathlib import Path
    class Options(HTMLParser):
        def __init__(self):
            super().__init__()
            self.values = []
        def handle_starttag(self, tag, attrs):
            if tag == 'option':
                self.values.append(dict(attrs)['value'])
    parser = Options()
    parser.feed((Path(__file__).resolve().parents[1] / 'ai_screenshot_assistant/web/static/index.html').read_text(encoding='utf-8'))
    assert set(parser.values) == set(MODEL_ROUTES)
