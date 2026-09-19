from __future__ import annotations

from dataclasses import dataclass

ROUTE_DOUBAO_SEED_VISION = "doubao-seed-vision"
ROUTE_OPENROUTER_QWEN_235B = "openrouter-qwen-235b"
ROUTE_OPENROUTER_QWEN_32B = "openrouter-qwen-32b"
ROUTE_DEEPSEEK_FLASH = "deepseek-flash"

# Old tier ids remain as aliases of the explicit routes.
TIER_GOOD = "good"
TIER_MEDIUM = "medium"
TIER_SIMPLE = "simple"
DEFAULT_MODEL_TIER = ROUTE_OPENROUTER_QWEN_235B

DEEPSEEK_VISION_MODEL = "deepseek-flash"
DOUBAO_VISION_MODEL = "doubao-seed-1-6-vision-250815"
OPENROUTER_QWEN_235B = "qwen/qwen3-vl-235b-a22b-thinking"
OPENROUTER_QWEN_32B = "qwen/qwen3-vl-32b-instruct"
OPENROUTER_QWEN_8B = "qwen/qwen3-vl-8b-instruct"

OPENROUTER_TIER_MODELS = {
    TIER_GOOD: OPENROUTER_QWEN_235B,
    TIER_MEDIUM: OPENROUTER_QWEN_32B,
    TIER_SIMPLE: OPENROUTER_QWEN_8B,
}

PROVIDER_LABELS = {
    "doubao": "豆包",
    "openrouter": "OpenRouter",
    "deepseek": "DeepSeek",
}


@dataclass(frozen=True)
class ModelRoute:
    route_id: str
    vendor: str
    provider: str
    model: str


MODEL_ROUTES: dict[str, ModelRoute] = {
    ROUTE_DOUBAO_SEED_VISION: ModelRoute(
        ROUTE_DOUBAO_SEED_VISION,
        "豆包",
        "doubao",
        DOUBAO_VISION_MODEL,
    ),
    ROUTE_OPENROUTER_QWEN_235B: ModelRoute(
        ROUTE_OPENROUTER_QWEN_235B,
        "OpenRouter",
        "openrouter",
        OPENROUTER_QWEN_235B,
    ),
    ROUTE_OPENROUTER_QWEN_32B: ModelRoute(
        ROUTE_OPENROUTER_QWEN_32B,
        "OpenRouter",
        "openrouter",
        OPENROUTER_QWEN_32B,
    ),
    ROUTE_DEEPSEEK_FLASH: ModelRoute(
        ROUTE_DEEPSEEK_FLASH,
        "DeepSeek",
        "deepseek",
        DEEPSEEK_VISION_MODEL,
    ),
}

ROUTE_ALIASES = {
    ROUTE_DOUBAO_SEED_VISION: ROUTE_DOUBAO_SEED_VISION,
    "doubao": ROUTE_DOUBAO_SEED_VISION,
    TIER_GOOD: ROUTE_OPENROUTER_QWEN_235B,
    "high": ROUTE_OPENROUTER_QWEN_235B,
    "best": ROUTE_OPENROUTER_QWEN_235B,
    "好": ROUTE_OPENROUTER_QWEN_235B,
    ROUTE_OPENROUTER_QWEN_235B: ROUTE_OPENROUTER_QWEN_235B,
    TIER_MEDIUM: ROUTE_OPENROUTER_QWEN_32B,
    "mid": ROUTE_OPENROUTER_QWEN_32B,
    "中等": ROUTE_OPENROUTER_QWEN_32B,
    ROUTE_OPENROUTER_QWEN_32B: ROUTE_OPENROUTER_QWEN_32B,
    TIER_SIMPLE: ROUTE_DEEPSEEK_FLASH,
    "low": ROUTE_DEEPSEEK_FLASH,
    "easy": ROUTE_DEEPSEEK_FLASH,
    "简单": ROUTE_DEEPSEEK_FLASH,
    ROUTE_DEEPSEEK_FLASH: ROUTE_DEEPSEEK_FLASH,
}

TIER_LABELS = {
    ROUTE_DOUBAO_SEED_VISION: "豆包",
    ROUTE_OPENROUTER_QWEN_235B: "OpenRouter",
    ROUTE_OPENROUTER_QWEN_32B: "OpenRouter",
    ROUTE_DEEPSEEK_FLASH: "DeepSeek",
    TIER_GOOD: "OpenRouter",
    TIER_MEDIUM: "OpenRouter",
    TIER_SIMPLE: "DeepSeek",
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
    key = str(value or "").strip()
    if not key:
        return DEFAULT_MODEL_TIER
    if key in MODEL_ROUTES:
        return key
    if key in ROUTE_ALIASES:
        return ROUTE_ALIASES[key]
    lowered = key.lower()
    if lowered in MODEL_ROUTES:
        return lowered
    return ROUTE_ALIASES.get(lowered, DEFAULT_MODEL_TIER)


def is_chinese_model(model_id: str | None) -> bool:
    lowered = str(model_id or "").strip().lower()
    if not lowered:
        return False
    if any(marker in lowered for marker in FOREIGN_MODEL_MARKERS):
        return False
    return any(marker in lowered for marker in CHINESE_MODEL_MARKERS)


def route_options() -> list[tuple[str, str, str]]:
    return [(route.route_id, route.vendor, route.model) for route in MODEL_ROUTES.values()]


def tier_options() -> list[tuple[str, str, str]]:
    return route_options()


@dataclass(frozen=True)
class ModelChoice:
    tier: str
    label: str
    provider: str
    model: str
    deepseek_model: str
    openrouter_model: str
    display_name: str
    route: str = ""
    doubao_model: str = DOUBAO_VISION_MODEL

    def to_payload(self) -> dict[str, str]:
        return {
            "tier": self.tier,
            "route": self.route or self.tier,
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
    has_doubao: bool = False,
) -> ModelChoice:
    route_id = normalize_model_tier(tier)
    route = MODEL_ROUTES[route_id]
    has_provider = {
        "doubao": has_doubao,
        "openrouter": has_openrouter,
        "deepseek": has_deepseek,
    }
    provider = route.provider
    model = route.model
    openrouter_model = OPENROUTER_QWEN_235B
    if has_provider.get(provider):
        if provider == "openrouter":
            openrouter_model = model
    elif route_id == ROUTE_DEEPSEEK_FLASH and has_openrouter:
        provider = "openrouter"
        model = OPENROUTER_QWEN_8B
        openrouter_model = OPENROUTER_QWEN_8B
    else:
        provider = "none"
        model = ""
    if model and not is_chinese_model(model):
        provider = "none"
        model = ""
    label = f"{route.vendor} · {route.model}"
    if model:
        vendor = PROVIDER_LABELS.get(provider, provider)
        display_name = f"{vendor} / {model}"
    else:
        display_name = f"{route.vendor} / 未配置 Key"
    return ModelChoice(
        tier=route_id,
        label=label,
        provider=provider,
        model=model,
        deepseek_model=DEEPSEEK_VISION_MODEL,
        openrouter_model=openrouter_model,
        display_name=display_name,
        route=route_id,
        doubao_model=DOUBAO_VISION_MODEL,
    )
