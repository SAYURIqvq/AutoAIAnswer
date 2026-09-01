from __future__ import annotations

import base64
import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import requests

from ai_screenshot_assistant.ai.prompt import VISION_PROMPT


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    api_key: str
    base_url: str
    model: str
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class AIResult:
    text: str
    answer: str | None = None
    reason: str | None = None
    confidence: str | None = None


def parse_ai_result(text: str) -> AIResult:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return _parse_answer_first_text(text)
    if not isinstance(data, dict):
        return AIResult(text=text)
    return AIResult(
        text=text,
        answer=_optional(data.get("answer")),
        reason=_optional(data.get("reason")),
        confidence=_optional(data.get("confidence")),
    )


def _parse_answer_first_text(text: str) -> AIResult:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return AIResult(text=text)
    answer = lines[0]
    for prefix in ("答案：", "答案:"):
        if answer.startswith(prefix):
            answer = answer.removeprefix(prefix).strip()
    reason = "\n".join(lines[1:]).strip() or None
    if reason:
        for prefix in ("解析：", "解析:"):
            if reason.startswith(prefix):
                reason = reason.removeprefix(prefix).strip()
    return AIResult(text=text, answer=answer or None, reason=reason)


def _optional(value: Any) -> str | None:
    return None if value is None else str(value)


class VisionClient:
    def __init__(self, provider: ProviderConfig) -> None:
        self.provider = provider

    def analyze_image_stream(self, png_bytes: bytes) -> Iterator[str]:
        if not self.provider.api_key:
            raise RuntimeError(f"{self.provider.name} API Key 不能为空")
        image_b64 = base64.b64encode(png_bytes).decode("ascii")
        payload = {
            "model": self.provider.model,
            "stream": True,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": VISION_PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                    ],
                }
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.provider.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost",
            "X-Title": "AI Screenshot Assistant",
        }
        with requests.post(
            f"{self.provider.base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json=payload,
            stream=True,
            timeout=self.provider.timeout_seconds,
        ) as response:
            response.raise_for_status()
            for raw_line in response.iter_lines(decode_unicode=False):
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8", errors="replace")
                if not line.startswith("data: "):
                    continue
                data = line.removeprefix("data: ").strip()
                if data == "[DONE]":
                    break
                delta = self._extract_delta(data)
                if delta:
                    yield delta

    @staticmethod
    def _extract_delta(data: str) -> str:
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            return ""
        choices = parsed.get("choices") or []
        if not choices:
            return ""
        content = (choices[0].get("delta") or {}).get("content")
        return content if isinstance(content, str) else ""


class FailoverVisionClient:
    """Uses DeepSeek first and permanently switches this instance on DeepSeek 402."""

    def __init__(
        self,
        deepseek: ProviderConfig,
        openrouter: ProviderConfig,
        on_provider_changed: Callable[[str], None] | None = None,
    ) -> None:
        self.deepseek = VisionClient(deepseek)
        self.openrouter = VisionClient(openrouter)
        self.current_provider = "deepseek"
        self.on_provider_changed = on_provider_changed or (lambda _name: None)

    def analyze_image_stream(self, png_bytes: bytes) -> Iterator[str]:
        if self.current_provider == "openrouter":
            yield from self.openrouter.analyze_image_stream(png_bytes)
            return
        try:
            yield from self.deepseek.analyze_image_stream(png_bytes)
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code != 402:
                raise
            self.current_provider = "openrouter"
            self.on_provider_changed("openrouter")
            yield from self.openrouter.analyze_image_stream(png_bytes)


# Backward-compatible name for older imports and static delta parser tests.
OpenRouterVisionClient = VisionClient
