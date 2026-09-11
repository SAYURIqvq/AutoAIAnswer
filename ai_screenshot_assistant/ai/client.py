from __future__ import annotations

import base64
import json
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import requests

from ai_screenshot_assistant.ai.prompt import VISION_PROMPT

_QUESTION_HEADING = re.compile(r"【第\d+题】")


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
        return _parse_structured_text(text)
    if isinstance(data, dict) and isinstance(data.get("questions"), list):
        return _parse_questions_payload(text, data["questions"])
    if not isinstance(data, dict):
        return _parse_structured_text(text)
    return AIResult(
        text=text,
        answer=_optional(data.get("answer")),
        reason=_optional(data.get("reason")),
        confidence=_optional(data.get("confidence")),
    )


def _parse_structured_text(text: str) -> AIResult:
    multi = _parse_multi_question_text(text)
    if multi is not None:
        return multi
    return _parse_answer_first_text(text)


def _parse_questions_payload(text: str, questions: list[Any]) -> AIResult:
    answers: list[str] = []
    reasons: list[str] = []
    for index, item in enumerate(questions, start=1):
        if not isinstance(item, dict):
            continue
        answer = _optional(item.get("answer")) or ""
        reason = _optional(item.get("reason"))
        heading = _optional(item.get("question")) or f"第{index}题"
        answers.append(f"{heading} {answer}".strip())
        if reason:
            reasons.append(f"{heading}：{reason}")
    return AIResult(
        text=text,
        answer="；".join(answers) or None,
        reason="\n".join(reasons) or None,
    )


def _parse_multi_question_text(text: str) -> AIResult | None:
    if not _QUESTION_HEADING.search(text):
        return None
    parts = re.split(r"(?=【第\d+题】)", text.strip())
    answers: list[str] = []
    reasons: list[str] = []
    for part in parts:
        part = part.strip()
        if not part.startswith("【第"):
            continue
        lines = [line for line in part.splitlines() if line.strip()]
        heading = lines[0]
        parsed = _parse_answer_first_text("\n".join(lines[1:]))
        answers.append(f"{heading} {parsed.answer or ''}".strip())
        if parsed.reason:
            reasons.append(f"{heading}\n{parsed.reason}")
    if not answers:
        return None
    return AIResult(text=text, answer="；".join(answers), reason="\n\n".join(reasons) or None)


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

    def analyze_image_stream(
        self,
        png_bytes: bytes,
        user_text: str | None = None,
        conversation: list[dict[str, str]] | None = None,
    ) -> Iterator[str]:
        if not self.provider.api_key:
            raise RuntimeError(f"{self.provider.name} API Key 不能为空")
        image_b64 = base64.b64encode(png_bytes).decode("ascii")
        content = [
            {"type": "text", "text": _build_user_prompt(user_text, conversation)},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
        ]
        payload = {
            "model": self.provider.model,
            "stream": True,
            "messages": [
                {
                    "role": "user",
                    "content": content,
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


def _build_user_prompt(user_text: str | None, conversation: list[dict[str, str]] | None) -> str:
    parts = [VISION_PROMPT]
    history = _format_conversation(conversation or [])
    if history:
        parts.append(
            "以下是手机端此前围绕同一任务的对话上下文。请结合上下文回答，但当前截图仍是最新依据：\n"
            + history
        )
    cleaned_text = (user_text or "").strip()
    if cleaned_text:
        parts.append(
            "手机端用户补充/追问：\n"
            + cleaned_text
            + "\n\n请优先回答这条补充/追问；如果是选择题，仍先输出选项再给极简解析。"
        )
    return "\n\n".join(parts)


def _format_conversation(conversation: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for item in conversation[-12:]:
        role = item.get("role")
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        label = "用户" if role == "user" else "AI"
        lines.append(f"{label}：{content[:2000]}")
    return "\n".join(lines)


class FailoverVisionClient:
    """Uses whichever Key is configured. If both exist, DeepSeek is first and 402 fails over."""

    def __init__(
        self,
        deepseek: ProviderConfig,
        openrouter: ProviderConfig,
        on_provider_changed: Callable[[str], None] | None = None,
    ) -> None:
        self.deepseek = VisionClient(deepseek)
        self.openrouter = VisionClient(openrouter)
        self.on_provider_changed = on_provider_changed or (lambda _name: None)
        self._deepseek_has_key = self._has_key(self.deepseek)
        self._openrouter_has_key = self._has_key(self.openrouter)
        self.current_provider = self._initial_provider()

    @staticmethod
    def _has_key(client: VisionClient) -> bool:
        return bool(client.provider.api_key and client.provider.api_key.strip())

    def _initial_provider(self) -> str:
        if self._deepseek_has_key:
            return "deepseek"
        if self._openrouter_has_key:
            return "openrouter"
        return "none"

    def analyze_image_stream(
        self,
        png_bytes: bytes,
        user_text: str | None = None,
        conversation: list[dict[str, str]] | None = None,
    ) -> Iterator[str]:
        if not self._deepseek_has_key and not self._openrouter_has_key:
            raise RuntimeError("请至少填写 DeepSeek 或 OpenRouter 其中一把 API Key")
        if self.current_provider == "openrouter" or not self._deepseek_has_key:
            yield from self.openrouter.analyze_image_stream(png_bytes, user_text=user_text, conversation=conversation)
            return
        try:
            yield from self.deepseek.analyze_image_stream(png_bytes, user_text=user_text, conversation=conversation)
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code != 402:
                raise
            if not self._openrouter_has_key:
                raise RuntimeError("DeepSeek 额度不足（HTTP 402），且未配置 OpenRouter Key") from exc
            self.current_provider = "openrouter"
            self.on_provider_changed("openrouter")
            yield from self.openrouter.analyze_image_stream(png_bytes, user_text=user_text, conversation=conversation)


# Backward-compatible name for older imports and static delta parser tests.
OpenRouterVisionClient = VisionClient
