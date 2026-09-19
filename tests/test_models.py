from ai_screenshot_assistant.ai.models import (
    DEEPSEEK_VISION_MODEL,
    DOUBAO_VISION_MODEL,
    OPENROUTER_TIER_MODELS,
    OPENROUTER_QWEN_235B,
    OPENROUTER_QWEN_32B,
    OPENROUTER_QWEN_8B,
    ROUTE_DEEPSEEK_FLASH,
    ROUTE_DOUBAO_SEED_VISION,
    ROUTE_OPENROUTER_QWEN_235B,
    ROUTE_OPENROUTER_QWEN_32B,
    is_chinese_model,
    normalize_model_tier,
    resolve_model_choice,
    route_options,
)


def test_normalize_model_tier_accepts_chinese_labels() -> None:
    assert normalize_model_tier("好") == ROUTE_OPENROUTER_QWEN_235B
    assert normalize_model_tier("中等") == ROUTE_OPENROUTER_QWEN_32B
    assert normalize_model_tier("简单") == ROUTE_DEEPSEEK_FLASH
    assert normalize_model_tier("unknown") == ROUTE_OPENROUTER_QWEN_235B
    assert normalize_model_tier("good") == ROUTE_OPENROUTER_QWEN_235B
    assert normalize_model_tier("doubao-seed-vision") == ROUTE_DOUBAO_SEED_VISION


def test_only_chinese_models_are_allowed() -> None:
    assert is_chinese_model("qwen/qwen3-vl-235b-a22b-thinking")
    assert is_chinese_model("deepseek-flash")
    assert is_chinese_model(DOUBAO_VISION_MODEL)
    assert is_chinese_model("z-ai/glm-4.5v") is True
    assert is_chinese_model("openai/gpt-4o") is False
    assert is_chinese_model("anthropic/claude-3.5-sonnet") is False
    assert is_chinese_model("google/gemini-2.5-pro") is False
    assert is_chinese_model("meta-llama/llama-3.1-70b") is False


def test_good_tier_uses_expensive_qwen_when_openrouter_exists() -> None:
    choice = resolve_model_choice("good", has_deepseek=True, has_openrouter=True)

    assert choice.provider == "openrouter"
    assert choice.route == ROUTE_OPENROUTER_QWEN_235B
    assert choice.model == OPENROUTER_QWEN_235B
    assert "thinking" in choice.model
    assert is_chinese_model(choice.model)


def test_medium_tier_uses_qwen_32b() -> None:
    choice = resolve_model_choice("medium", has_deepseek=False, has_openrouter=True)

    assert choice.provider == "openrouter"
    assert choice.route == ROUTE_OPENROUTER_QWEN_32B
    assert choice.model == OPENROUTER_QWEN_32B


def test_simple_tier_uses_deepseek_flash_when_available() -> None:
    choice = resolve_model_choice("simple", has_deepseek=True, has_openrouter=True)

    assert choice.provider == "deepseek"
    assert choice.route == ROUTE_DEEPSEEK_FLASH
    assert choice.model == DEEPSEEK_VISION_MODEL


def test_simple_tier_falls_back_to_qwen_8b_without_deepseek() -> None:
    choice = resolve_model_choice("simple", has_deepseek=False, has_openrouter=True)

    assert choice.provider == "openrouter"
    assert choice.model == OPENROUTER_QWEN_8B


def test_doubao_route_requires_doubao_key() -> None:
    missing = resolve_model_choice(
        ROUTE_DOUBAO_SEED_VISION,
        has_deepseek=True,
        has_openrouter=True,
        has_doubao=False,
    )
    ready = resolve_model_choice(
        ROUTE_DOUBAO_SEED_VISION,
        has_deepseek=True,
        has_openrouter=True,
        has_doubao=True,
    )

    assert missing.provider == "none"
    assert "未配置 Key" in missing.display_name
    assert ready.provider == "doubao"
    assert ready.model == DOUBAO_VISION_MODEL
    assert ready.display_name == f"豆包 / {DOUBAO_VISION_MODEL}"


def test_openrouter_route_without_key_is_unavailable() -> None:
    choice = resolve_model_choice("good", has_deepseek=True, has_openrouter=False)

    assert choice.provider == "none"
    assert choice.model == ""


def test_route_options_list_explicit_models() -> None:
    options = route_options()
    ids = [item[0] for item in options]
    assert ids == [
        ROUTE_DOUBAO_SEED_VISION,
        ROUTE_OPENROUTER_QWEN_235B,
        ROUTE_OPENROUTER_QWEN_32B,
        ROUTE_DEEPSEEK_FLASH,
    ]
    assert DOUBAO_VISION_MODEL in {item[2] for item in options}


def test_all_configured_openrouter_tiers_are_chinese_qwen_models() -> None:
    for model_id in OPENROUTER_TIER_MODELS.values():
        assert is_chinese_model(model_id)
        assert model_id.startswith("qwen/")
        assert "gpt" not in model_id
        assert "claude" not in model_id
        assert "gemini" not in model_id
