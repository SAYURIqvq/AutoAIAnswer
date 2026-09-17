from ai_screenshot_assistant.ai.models import (
    DEEPSEEK_VISION_MODEL,
    OPENROUTER_TIER_MODELS,
    is_chinese_model,
    normalize_model_tier,
    resolve_model_choice,
)


def test_normalize_model_tier_accepts_chinese_labels() -> None:
    assert normalize_model_tier("好") == "good"
    assert normalize_model_tier("中等") == "medium"
    assert normalize_model_tier("简单") == "simple"
    assert normalize_model_tier("unknown") == "good"


def test_only_chinese_models_are_allowed() -> None:
    assert is_chinese_model("qwen/qwen3-vl-235b-a22b-thinking")
    assert is_chinese_model("deepseek-flash")
    assert is_chinese_model("z-ai/glm-4.5v") is True
    assert is_chinese_model("openai/gpt-4o") is False
    assert is_chinese_model("anthropic/claude-3.5-sonnet") is False
    assert is_chinese_model("google/gemini-2.5-pro") is False
    assert is_chinese_model("meta-llama/llama-3.1-70b") is False


def test_good_tier_uses_expensive_qwen_when_openrouter_exists() -> None:
    choice = resolve_model_choice("good", has_deepseek=True, has_openrouter=True)

    assert choice.provider == "openrouter"
    assert choice.model == OPENROUTER_TIER_MODELS["good"]
    assert "thinking" in choice.model
    assert is_chinese_model(choice.model)


def test_medium_tier_uses_qwen_32b() -> None:
    choice = resolve_model_choice("medium", has_deepseek=False, has_openrouter=True)

    assert choice.provider == "openrouter"
    assert choice.model == "qwen/qwen3-vl-32b-instruct"


def test_simple_tier_uses_deepseek_flash_when_available() -> None:
    choice = resolve_model_choice("simple", has_deepseek=True, has_openrouter=True)

    assert choice.provider == "deepseek"
    assert choice.model == DEEPSEEK_VISION_MODEL


def test_simple_tier_falls_back_to_qwen_8b_without_deepseek() -> None:
    choice = resolve_model_choice("simple", has_deepseek=False, has_openrouter=True)

    assert choice.provider == "openrouter"
    assert choice.model == "qwen/qwen3-vl-8b-instruct"


def test_all_configured_openrouter_tiers_are_chinese_qwen_models() -> None:
    for model_id in OPENROUTER_TIER_MODELS.values():
        assert is_chinese_model(model_id)
        assert model_id.startswith("qwen/")
        assert "gpt" not in model_id
        assert "claude" not in model_id
        assert "gemini" not in model_id
    good = resolve_model_choice("good", has_deepseek=True, has_openrouter=False)
    medium = resolve_model_choice("medium", has_deepseek=True, has_openrouter=False)

    assert good.provider == "deepseek"
    assert medium.provider == "deepseek"
    assert good.model == DEEPSEEK_VISION_MODEL
    assert medium.model == DEEPSEEK_VISION_MODEL
