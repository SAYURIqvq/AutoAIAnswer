from __future__ import annotations

from dataclasses import dataclass

TIER_GOOD = "good"
TIER_MEDIUM = "medium"
TIER_SIMPLE = "simple"
DEFAULT_MODEL_TIER = TIER_GOOD

TIER_ALIASES = {
    "good": TIER_GOOD,
    "high": TIER_GOOD,
    "best": TIER_GOOD,
    "好": TIER_GOOD,
    "medium": TIER_MEDIUM,
    "mid": TIER_MEDIUM,
    "中等": TIER_MEDIUM,
    "simple": TIER_SIMPLE,
    "low": TIER_SIMPLE,
    "easy": TIER_SIMPLE,
    "简单": TIER_SIMPLE,
}

TIER_LABELS = {
    TIER_GOOD: "好",
    TIER_MEDIUM: "中等",
    TIER_SIMPLE: "简单",
}

# DeepSeek 官方目前只有 deepseek-flash 具备原生视觉；v4-pro 不能看图。
DEEPSEEK_VISION_MODEL = "deepseek-flash"

# 通义千问 VL 为中国模型；好档用更贵的 Thinking 提升解题准确度。
OPENROUTER_TIER_MODELS = {
    TIER_GOOD: "qwen/qwen3-vl-235b-a22b-thinking",
    TIER_MEDIUM: "qwen/qwen3-vl-32b-instruct",
    TIER_SIMPLE: "qwen/qwen3-vl-8b-instruct",
}

CHINESE_MODEL_MARKERS = (
    "qwen/",
    "qwen3",
    "deepseek",
    "alibaba",
    "z-ai/",
    "zhipu",
    "glm-",
    "moonshot",
    "minimax",
    "stepfun",
    "step/",
    "baidu/",
    "ernie",
    "tencent/",
    "hunyuan",
    "bytedance",
    "doubao",
    "thudm",
    "internlm",
    "01-ai",
    "yi/",
)

FOREIGN_MODEL_MARKERS = (
    "openai/",
    "gpt-",
    "o1-",
    "anthropic/",
    "claude",
    "google/",
    "gemini",
    "meta-llama",
    "llama-",
    "mistral",
    "x-ai/",
    "grok",
    "cohere/",
    "amazon/",
    "perplexity/",
    "nvidia/",
    "microsoft/",
)


def normalize_model_tier(value: str | None) -> str:
    key = str(value or "").strip().lower()
    return TIER_ALIASES.get(key, DEFAULT_MODEL_TIER)


def is_chinese_model(model_id: str | None) -> bool:
    lowered = str(model_id or "").strip().lower()
    if not lowered:
        return False
    if any(marker in lowered for marker in FOREIGN_MODEL_MARKERS):
        return False
    return any(marker in lowered for marker in CHINESE_MODEL_MARKERS)


def tier_options() -> list[tuple[str, str, str]]:
    return [
        (TIER_GOOD, TIER_LABELS[TIER_GOOD], OPENROUTER_TIER_MODELS[TIER_GOOD]),
        (TIER_MEDIUM, TIER_LABELS[TIER_MEDIUM], OPENROUTER_TIER_MODELS[TIER_MEDIUM]),
        (TIER_SIMPLE, TIER_LABELS[TIER_SIMPLE], f"{DEEPSEEK_VISION_MODEL} / {OPENROUTER_TIER_MODELS[TIER_SIMPLE]}"),
    ]


@dataclass(frozen=True)
class ModelChoice:
    tier: str
    label: str
    provider: str
    model: str
    deepseek_model: str
    openrouter_model: str
    display_name: str

    def to_payload(self) -> dict[str, str]:
        return {
            "tier": self.tier,
            "label": self.label,
            "provider": self.provider,
            "model": self.model,
            "display_name": self.display_name,
        }


def resolve_model_choice(
    tier: str | None,
    *,
    has_deepseek: bool,
    has_openrouter: bool,
) -> ModelChoice:
    normalized = normalize_model_tier(tier)
    openrouter_model = OPENROUTER_TIER_MODELS[normalized]
    deepseek_model = DEEPSEEK_VISION_MODEL
    if has_openrouter and normalized in {TIER_GOOD, TIER_MEDIUM}:
        provider = "openrouter"
        model = openrouter_model
    elif has_deepseek and normalized == TIER_SIMPLE:
        provider = "deepseek"
        model = deepseek_model
    elif has_openrouter:
        provider = "openrouter"
        model = openrouter_model
    elif has_deepseek:
        provider = "deepseek"
        model = deepseek_model
    else:
        provider = "none"
        model = ""
    if model and not is_chinese_model(model):
        provider = "none"
        model = ""
    label = TIER_LABELS[normalized]
    if model:
        vendor = "OpenRouter" if provider == "openrouter" else "DeepSeek"
        display_name = f"{label} / {vendor} / {model}"
    else:
        display_name = f"{label} / 未配置 Key"
    return ModelChoice(
        tier=normalized,
        label=label,
        provider=provider,
        model=model,
        deepseek_model=deepseek_model,
        openrouter_model=openrouter_model,
        display_name=display_name,
    )
