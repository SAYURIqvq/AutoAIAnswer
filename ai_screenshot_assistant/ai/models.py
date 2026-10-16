from __future__ import annotations

from dataclasses import dataclass

TIER_GOOD = "good"
TIER_MEDIUM = "medium"
TIER_SIMPLE = "simple"

ROUTE_DOUBAO_MINI = "doubao-seed-2-0-mini"
ROUTE_DOUBAO_LITE = "doubao-seed-2-0-lite"
ROUTE_DOUBAO_TURBO = "doubao-seed-2-1-turbo"
ROUTE_DOUBAO_PRO = "doubao-seed-2-1-pro"
ROUTE_DOUBAO_SEED_VISION = ROUTE_DOUBAO_TURBO
ROUTE_QWEN_VL_PLUS = "qwen-vl-plus"
ROUTE_QWEN_VL_FLASH = "qwen-vl-flash"
ROUTE_QWEN_122B = "qwen-122b"
ROUTE_QWEN_PLUS = "qwen-plus"
ROUTE_QWEN_FLASH = "qwen-flash"
ROUTE_QWEN_397B = "qwen-397b"
ROUTE_QWEN_27B = "qwen-27b"
ROUTE_QWEN_35B = "qwen-35b"
ROUTE_DEEPSEEK_FLASH = "deepseek-flash"
DEFAULT_MODEL_TIER = ROUTE_QWEN_VL_PLUS

DEEPSEEK_VISION_MODEL = "deepseek-flash"
DOUBAO_MINI_MODEL = "doubao-seed-2-0-mini-260428"
DOUBAO_LITE_MODEL = "doubao-seed-2-0-lite-260428"
DOUBAO_TURBO_MODEL = "doubao-seed-2-1-turbo-260628"
DOUBAO_PRO_MODEL = "doubao-seed-2-1-pro-260915"
DOUBAO_VISION_MODEL = DOUBAO_TURBO_MODEL
DOUBAO_CHAT_COMPLETIONS_MODELS = frozenset({DOUBAO_TURBO_MODEL})
QWEN_VL_PLUS_MODEL = "qwen3-vl-plus"
QWEN_VL_FLASH_MODEL = "qwen3.8-flash"
QWEN_122B_MODEL = "qwen3.5-122b-a10b"
QWEN_PLUS_MODEL = "qwen3.5-plus"
QWEN_FLASH_MODEL = "qwen3.5-flash"

QWEN_TIER_MODELS = {
    TIER_GOOD: QWEN_VL_PLUS_MODEL,
    TIER_MEDIUM: QWEN_VL_FLASH_MODEL,
    TIER_SIMPLE: QWEN_FLASH_MODEL,
}

PROVIDER_LABELS = {
    "doubao": "豆包",
    "qwen": "通义千问",
    "deepseek": "DeepSeek",
}


@dataclass(frozen=True)
class ModelRoute:
    route_id: str
    vendor: str
    provider: str
    model: str
    trait: str


MODEL_ROUTES: dict[str, ModelRoute] = {
    ROUTE_DOUBAO_MINI: ModelRoute(
        ROUTE_DOUBAO_MINI,
        "豆包 Mini",
        "doubao",
        DOUBAO_MINI_MODEL,
        "最快 / 准确一般",
    ),
    ROUTE_DOUBAO_LITE: ModelRoute(
        ROUTE_DOUBAO_LITE,
        "豆包 Lite",
        "doubao",
        DOUBAO_LITE_MODEL,
        "较快 / 准确中等",
    ),
    ROUTE_DOUBAO_TURBO: ModelRoute(
        ROUTE_DOUBAO_TURBO,
        "豆包 Turbo",
        "doubao",
        DOUBAO_TURBO_MODEL,
        "快 / 准确较好",
    ),
    ROUTE_DOUBAO_PRO: ModelRoute(
        ROUTE_DOUBAO_PRO,
        "豆包 Pro",
        "doubao",
        DOUBAO_PRO_MODEL,
        "最准 / 较慢",
    ),
    ROUTE_QWEN_VL_PLUS: ModelRoute(
        ROUTE_QWEN_VL_PLUS, "通义千问", "qwen", QWEN_VL_PLUS_MODEL, "视觉增强 / 准确较好",
    ),
    ROUTE_QWEN_VL_FLASH: ModelRoute(
        ROUTE_QWEN_VL_FLASH, "通义千问", "qwen", QWEN_VL_FLASH_MODEL, "视觉快速 / 成本较低",
    ),
    ROUTE_QWEN_122B: ModelRoute(
        ROUTE_QWEN_122B, "通义千问", "qwen", QWEN_122B_MODEL, "122B / 图文理解",
    ),
    ROUTE_QWEN_PLUS: ModelRoute(
        ROUTE_QWEN_PLUS, "通义千问", "qwen", QWEN_PLUS_MODEL, "图文理解 / 长上下文",
    ),
    ROUTE_QWEN_FLASH: ModelRoute(
        ROUTE_QWEN_FLASH, "通义千问", "qwen", QWEN_FLASH_MODEL, "快速 / 图文理解",
    ),
    ROUTE_QWEN_397B: ModelRoute(
        ROUTE_QWEN_397B, "通义千问", "qwen", "qwen3.5-397b-a17b", "397B / 图文理解",
    ),
    ROUTE_QWEN_27B: ModelRoute(
        ROUTE_QWEN_27B, "通义千问", "qwen", "qwen3.5-27b", "27B / 图文理解",
    ),
    ROUTE_QWEN_35B: ModelRoute(
        ROUTE_QWEN_35B, "通义千问", "qwen", "qwen3.5-35b-a3b", "35B / 图文理解",
    ),
    ROUTE_DEEPSEEK_FLASH: ModelRoute(
        ROUTE_DEEPSEEK_FLASH,
        "DeepSeek 官方",
        "deepseek",
        DEEPSEEK_VISION_MODEL,
        "快 / 准确一般",
    ),
}

ROUTE_ALIASES = {
    ROUTE_DOUBAO_MINI: ROUTE_DOUBAO_MINI,
    ROUTE_DOUBAO_LITE: ROUTE_DOUBAO_LITE,
    ROUTE_DOUBAO_TURBO: ROUTE_DOUBAO_TURBO,
    ROUTE_DOUBAO_PRO: ROUTE_DOUBAO_PRO,
    "doubao-seed-vision": ROUTE_DOUBAO_TURBO,
    "doubao": ROUTE_DOUBAO_TURBO,
    "豆包": ROUTE_DOUBAO_TURBO,
    "doubao-seed-1-6-vision": ROUTE_DOUBAO_TURBO,
    "doubao-seed-1-6-vision-250815": ROUTE_DOUBAO_TURBO,
    "doubao-seed-2-0-mini-260428": ROUTE_DOUBAO_MINI,
    "doubao-seed-2-0-lite-260428": ROUTE_DOUBAO_LITE,
    "doubao-seed-2-1-turbo-260628": ROUTE_DOUBAO_TURBO,
    "doubao-seed-2-1-pro-260915": ROUTE_DOUBAO_PRO,
    DOUBAO_MINI_MODEL: ROUTE_DOUBAO_MINI,
    DOUBAO_LITE_MODEL: ROUTE_DOUBAO_LITE,
    DOUBAO_TURBO_MODEL: ROUTE_DOUBAO_TURBO,
    DOUBAO_PRO_MODEL: ROUTE_DOUBAO_PRO,
    TIER_GOOD: ROUTE_QWEN_VL_PLUS,
    "high": ROUTE_QWEN_VL_PLUS,
    "best": ROUTE_QWEN_VL_PLUS,
    "好": ROUTE_QWEN_VL_PLUS,
    TIER_MEDIUM: ROUTE_QWEN_VL_FLASH,
    "mid": ROUTE_QWEN_VL_FLASH,
    "中等": ROUTE_QWEN_VL_FLASH,
    TIER_SIMPLE: ROUTE_DEEPSEEK_FLASH,
    "low": ROUTE_DEEPSEEK_FLASH,
    "easy": ROUTE_DEEPSEEK_FLASH,
    "简单": ROUTE_DEEPSEEK_FLASH,
    ROUTE_DEEPSEEK_FLASH: ROUTE_DEEPSEEK_FLASH,
    ROUTE_QWEN_VL_PLUS: ROUTE_QWEN_VL_PLUS,
    ROUTE_QWEN_VL_FLASH: ROUTE_QWEN_VL_FLASH,
    ROUTE_QWEN_122B: ROUTE_QWEN_122B,
    ROUTE_QWEN_PLUS: ROUTE_QWEN_PLUS,
    ROUTE_QWEN_FLASH: ROUTE_QWEN_FLASH,
    "openrouter-qwen-235b": ROUTE_QWEN_VL_PLUS,
    "openrouter-qwen-32b": ROUTE_QWEN_VL_FLASH,
    "openrouter-qwen-8b": ROUTE_QWEN_VL_FLASH,
    "openrouter-qwen-122b": ROUTE_QWEN_122B,
    "openrouter-qwen-30b-thinking": ROUTE_QWEN_VL_PLUS,
    "openrouter-deepseek-flash": ROUTE_QWEN_FLASH,
    "openrouter-deepseek": ROUTE_QWEN_FLASH,
    "qwen/qwen3-vl-235b-a22b-thinking": ROUTE_QWEN_VL_PLUS,
    "qwen/qwen3-vl-32b-instruct": ROUTE_QWEN_VL_FLASH,
    "qwen/qwen3.5-122b-a10b": ROUTE_QWEN_122B,
    "deepseek/deepseek-v4.1-flash": ROUTE_QWEN_FLASH,
}

TIER_LABELS = {
    ROUTE_DOUBAO_MINI: "豆包 Mini",
    ROUTE_DOUBAO_LITE: "豆包 Lite",
    ROUTE_DOUBAO_TURBO: "豆包 Turbo",
    ROUTE_DOUBAO_PRO: "豆包 Pro",
    ROUTE_QWEN_VL_PLUS: "通义千问",
    ROUTE_QWEN_VL_FLASH: "通义千问",
    ROUTE_QWEN_122B: "通义千问",
    ROUTE_QWEN_PLUS: "通义千问",
    ROUTE_QWEN_FLASH: "通义千问",
    ROUTE_DEEPSEEK_FLASH: "DeepSeek 官方",
    TIER_GOOD: "通义千问",
    TIER_MEDIUM: "通义千问",
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


def format_route_label(route: ModelRoute) -> str:
    return f"{route.vendor} · {route.model}（{route.trait}）"


def route_options() -> list[tuple[str, str, str]]:
    return [(route.route_id, route.vendor, f"{route.model}（{route.trait}）") for route in MODEL_ROUTES.values()]


def tier_options() -> list[tuple[str, str, str]]:
    return route_options()


@dataclass(frozen=True)
class ModelChoice:
    tier: str
    label: str
    provider: str
    model: str
    deepseek_model: str
    qwen_model: str
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
    has_qwen: bool,
    has_doubao: bool = False,
) -> ModelChoice:
    route_id = normalize_model_tier(tier)
    route = MODEL_ROUTES[route_id]
    has_provider = {
        "doubao": has_doubao,
        "qwen": has_qwen,
        "deepseek": has_deepseek,
    }
    qwen_model = QWEN_VL_PLUS_MODEL
    if has_provider.get(route.provider):
        provider = route.provider
        model = route.model
        if provider == "qwen":
            qwen_model = model
    else:
        provider = "none"
        model = ""
    if model and not is_chinese_model(model):
        provider = "none"
        model = ""
    label = format_route_label(route)
    if model:
        vendor = PROVIDER_LABELS.get(provider, provider)
        display_name = f"{vendor} / {model}（{route.trait}）"
    else:
        display_name = f"{route.vendor} / 未配置 Key"
    doubao_model = route.model if route.provider == "doubao" else DOUBAO_VISION_MODEL
    return ModelChoice(
        tier=route_id,
        label=label,
        provider=provider,
        model=model,
        deepseek_model=DEEPSEEK_VISION_MODEL,
        qwen_model=qwen_model,
        display_name=display_name,
        route=route_id,
        doubao_model=doubao_model,
    )
