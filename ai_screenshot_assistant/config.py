from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _load_env() -> None:
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / ".env")
        bundle_dir = getattr(sys, "_MEIPASS", None)
        if bundle_dir:
            candidates.append(Path(bundle_dir) / ".env")
    candidates.append(Path.cwd() / ".env")
    candidates.append(Path(__file__).resolve().parents[1] / ".env")
    for path in candidates:
        if path.exists():
            load_dotenv(path)
            return
    load_dotenv()


_load_env()


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
    qwen_api_key: str = os.getenv("DASHSCOPE_API_KEY", "")
    qwen_base_url: str = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    qwen_model: str = os.getenv("QWEN_MODEL", "qwen3-vl-plus")
    doubao_api_key: str = os.getenv("ARK_API_KEY", "")
    doubao_base_url: str = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    doubao_model: str = os.getenv("ARK_MODEL", "doubao-seed-1-6-vision-250815")
    model_tier: str = os.getenv("MODEL_TIER", "qwen-vl-plus")
    backend_url: str = os.getenv("BACKEND_URL", "auto")
    backend_port: int = int(os.getenv("BACKEND_PORT", "8000"))
    embedded_backend: bool = _bool_env("EMBEDDED_BACKEND", True)
    request_timeout_seconds: float = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "90"))
    save_debug_image: bool = _bool_env("SAVE_DEBUG_IMAGE", False)


settings = Settings()
