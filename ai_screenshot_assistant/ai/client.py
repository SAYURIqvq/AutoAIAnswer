from __future__ import annotations

import base64
import io
import json
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from typing import Any

import requests
from PIL import Image, UnidentifiedImageError

from ai_screenshot_assistant.ai.models import (
    DEFAULT_MODEL_TIER,
    DOUBAO_VISION_MODEL,
    DOUBAO_CHAT_COMPLETIONS_MODELS,
    ModelChoice,
    PROVIDER_LABELS,
    resolve_model_choice,
)
from ai_screenshot_assistant.ai.prompt import VISION_PROMPT
from ai_screenshot_assistant.core.conversation import cap_conversation_memory

_QUESTION_HEADING = re.compile(r"【第\d+题】")
AI_IMAGE_MAX_SIDE = 1400
AI_IMAGE_JPEG_QUALITY = 78
AI_IMAGE_COMPRESS_THRESHOLD_BYTES = 650_000
ALBUM_IMAGE_MAX_SIDE = 2880
ALBUM_IMAGE_JPEG_QUALITY = 92
ALBUM_IMAGE_MAX_BYTES = 2_400_000


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
        yield from self.analyze_images_stream([png_bytes], user_text=user_text, conversation=conversation)

    def uses_responses_api(self) -> bool:
        model = self.provider.model.lower()
        if model in {item.lower() for item in DOUBAO_CHAT_COMPLETIONS_MODELS} or "turbo" in model:
            return False
        return self._is_doubao() or "seed-1-6-vision" in model

    def _is_doubao(self) -> bool:
        return "doubao" in self.provider.name.lower() or "volces.com" in self.provider.base_url.lower()

    def analyze_images_stream(
        self,
        png_images: list[bytes],
        user_text: str | None = None,
        conversation: list[dict[str, str]] | None = None,
    ) -> Iterator[str]:
        if not self.provider.api_key:
            raise RuntimeError(f"{self.provider.name} API Key 不能为空")
        prompt = _build_user_prompt(user_text, conversation)
        images: list[tuple[bytes, str]] = [prepare_image_for_ai(png_bytes) for png_bytes in png_images]
        payload = self._request_payload(prompt, images)
        headers = {
            "Authorization": f"Bearer {self.provider.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost",
            "X-Title": "AI Screenshot Assistant",
        }
        path = "/responses" if self.uses_responses_api() else "/chat/completions"
        with requests.post(
            f"{self.provider.base_url.rstrip('/')}{path}",
            headers=headers,
            json=payload,
            stream=True,
            timeout=self.provider.timeout_seconds,
        ) as response:
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                raise self._friendly_http_error(exc) from exc
            for raw_line in response.iter_lines(chunk_size=1, decode_unicode=False):
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

    def _request_payload(self, prompt: str, images: list[tuple[bytes, str]]) -> dict[str, Any]:
        if self.uses_responses_api():
            content: list[dict[str, Any]] = []
            for image_bytes, mime_type in images:
                image_b64 = base64.b64encode(image_bytes).decode("ascii")
                content.append(
                    {
                        "type": "input_image",
                        "image_url": f"data:{mime_type};base64,{image_b64}",
                    }
                )
            content.append({"type": "input_text", "text": prompt})
            payload = {
                "model": self.provider.model,
                "stream": True,
                "input": [{"role": "user", "content": content}],
            }
            if self._is_doubao():
                payload["thinking"] = {"type": "disabled"}
            return payload
        content: list[dict[str, Any]] = []
        for image_bytes, mime_type in images:
            image_b64 = base64.b64encode(image_bytes).decode("ascii")
            content.append({"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}})
        content.append({"type": "text", "text": prompt})
        payload: dict[str, Any] = {
            "model": self.provider.model,
            "stream": True,
            "messages": [{"role": "user", "content": content}],
        }
        if self._is_doubao():
            payload["thinking"] = {"type": "disabled"}
        elif "openrouter.ai" in self.provider.base_url and "thinking" not in self.provider.model.lower():
            payload["reasoning_effort"] = "none"
        return payload

    def _friendly_http_error(self, exc: requests.HTTPError) -> Exception:
        response = exc.response
        if response is None:
            return exc
        if response.status_code == 402:
            return exc
        detail = ""
        try:
            payload = response.json()
            error = payload.get("error") if isinstance(payload, dict) else None
            if isinstance(error, dict):
                detail = str(error.get("code") or error.get("message") or "")
        except ValueError:
            detail = (response.text or "")[:180]
        if response.status_code == 404 and (
            self.uses_responses_api()
            or "doubao" in self.provider.name.lower()
            or "volces.com" in self.provider.base_url.lower()
        ):
            model = self.provider.model
            return RuntimeError(
                f"豆包模型未开通或无权调用（{model}）。"
                "请到火山方舟开通该模型，或改用已开通的视觉模型后再试。"
            )
        if detail:
            return RuntimeError(f"{self.provider.name} 调用失败：{detail}")
        return exc

    @staticmethod
    def _extract_delta(data: str) -> str:
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            return ""
        event_type = str(parsed.get("type") or "")
        event_delta = parsed.get("delta")
        if event_type == "response.output_text.delta" and isinstance(event_delta, str):
            return event_delta
        choices = parsed.get("choices") or []
        if not choices:
            return ""
        first = choices[0] or {}
        delta = first.get("delta") or {}
        content = delta.get("content")
        if isinstance(content, str) and content:
            return content
        message = first.get("message") or {}
        message_content = message.get("content")
        return message_content if isinstance(message_content, str) else ""


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


def _open_image(image_bytes: bytes) -> Image.Image | None:
    try:
        return Image.open(io.BytesIO(image_bytes))
    except (UnidentifiedImageError, OSError, ValueError):
        return None


def _resize_to_max_side(image: Image.Image, max_side: int) -> Image.Image:
    width, height = image.size
    longest = max(width, height)
    if longest <= max_side:
        return image
    scale = max_side / longest
    return image.resize(
        (max(1, int(width * scale)), max(1, int(height * scale))),
        Image.Resampling.LANCZOS,
    )


def _encode_jpeg(image: Image.Image, quality: int, *, subsampling: int | None = None) -> bytes:
    if image.mode not in {"RGB", "L"}:
        image = image.convert("RGB")
    buffer = io.BytesIO()
    options: dict[str, Any] = {"format": "JPEG", "quality": quality, "optimize": True}
    if subsampling is not None:
        options["subsampling"] = subsampling
    image.save(buffer, **options)
    return buffer.getvalue()


def _original_mime(image: Image.Image) -> str:
    if image.format == "JPEG":
        return "image/jpeg"
    return "image/png"


def prepare_image_for_ai(image_bytes: bytes) -> tuple[bytes, str]:
    image = _open_image(image_bytes)
    if image is None:
        return image_bytes, "image/png"

    longest = max(image.size)
    needs_resize = longest > AI_IMAGE_MAX_SIDE
    needs_compress = len(image_bytes) > AI_IMAGE_COMPRESS_THRESHOLD_BYTES or needs_resize
    if not needs_compress:
        return image_bytes, "image/png"

    return _encode_jpeg(_resize_to_max_side(image, AI_IMAGE_MAX_SIDE), AI_IMAGE_JPEG_QUALITY), "image/jpeg"


def prepare_image_for_album(image_bytes: bytes) -> tuple[bytes, str]:
    image = _open_image(image_bytes)
    if image is None:
        return image_bytes, "image/png"

    longest = max(image.size)
    if longest <= ALBUM_IMAGE_MAX_SIDE and len(image_bytes) <= ALBUM_IMAGE_MAX_BYTES:
        return image_bytes, _original_mime(image)

    image = _resize_to_max_side(image, ALBUM_IMAGE_MAX_SIDE)
    quality = ALBUM_IMAGE_JPEG_QUALITY
    encoded = _encode_jpeg(image, quality, subsampling=0)
    while len(encoded) > ALBUM_IMAGE_MAX_BYTES and quality > 80:
        quality -= 6
        encoded = _encode_jpeg(image, quality, subsampling=0)
    return encoded, "image/jpeg"


_prepare_image_for_ai = prepare_image_for_ai
_prepare_image_for_album = prepare_image_for_album


def _format_conversation(conversation: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for item in cap_conversation_memory(conversation):
        role = item.get("role")
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        label = "用户" if role == "user" else "AI"
        lines.append(f"{label}：{content}")
    return "\n".join(lines)


class FailoverVisionClient:
    """Routes an explicit Chinese vision model, with a one-shot 402 failover."""

    _FAILOVER_ORDER = ("openrouter", "deepseek", "doubao")

    def __init__(
        self,
        deepseek: ProviderConfig,
        openrouter: ProviderConfig,
        on_provider_changed: Callable[[str], None] | None = None,
        model_tier: str = DEFAULT_MODEL_TIER,
        doubao: ProviderConfig | None = None,
    ) -> None:
        self.deepseek = VisionClient(deepseek)
        self.openrouter = VisionClient(openrouter)
        self.doubao = VisionClient(
            doubao
            or ProviderConfig(
                name="Doubao",
                api_key="",
                base_url="https://ark.cn-beijing.volces.com/api/v3",
                model=DOUBAO_VISION_MODEL,
            )
        )
        self.on_provider_changed = on_provider_changed or (lambda _name: None)
        self._deepseek_has_key = self._has_key(self.deepseek)
        self._openrouter_has_key = self._has_key(self.openrouter)
        self._doubao_has_key = self._has_key(self.doubao)
        self.current_provider = self._initial_provider()
        self.model_choice = self.apply_model_tier(model_tier)

    @staticmethod
    def _has_key(client: VisionClient) -> bool:
        return bool(client.provider.api_key and client.provider.api_key.strip())

    @staticmethod
    def _stream_from_client(
        client: Any,
        png_images: list[bytes],
        user_text: str | None,
        conversation: list[dict[str, str]] | None,
    ) -> Iterator[str]:
        if hasattr(client, "analyze_images_stream"):
            yield from client.analyze_images_stream(png_images, user_text=user_text, conversation=conversation)
            return
        if len(png_images) != 1:
            raise RuntimeError("当前 AI 客户端不支持多张截图")
        yield from client.analyze_image_stream(png_images[0], user_text=user_text, conversation=conversation)

    def _has_provider(self, name: str) -> bool:
        return {
            "openrouter": self._openrouter_has_key,
            "deepseek": self._deepseek_has_key,
            "doubao": self._doubao_has_key,
        }.get(name, False)

    def _client_for(self, name: str) -> VisionClient:
        return {
            "openrouter": self.openrouter,
            "deepseek": self.deepseek,
            "doubao": self.doubao,
        }[name]

    def _initial_provider(self) -> str:
        if self._openrouter_has_key:
            return "openrouter"
        if self._deepseek_has_key:
            return "deepseek"
        if self._doubao_has_key:
            return "doubao"
        return "none"

    def current_model_id(self) -> str:
        if self.current_provider == "openrouter":
            provider = getattr(self.openrouter, "provider", None)
        elif self.current_provider == "deepseek":
            provider = getattr(self.deepseek, "provider", None)
        elif self.current_provider == "doubao":
            provider = getattr(self.doubao, "provider", None)
        else:
            provider = None
        return str(getattr(provider, "model", "") or "")

    def apply_model_tier(self, tier: str, *, notify: bool = False) -> ModelChoice:
        choice = resolve_model_choice(
            tier,
            has_deepseek=self._deepseek_has_key,
            has_openrouter=self._openrouter_has_key,
            has_doubao=self._doubao_has_key,
        )
        deepseek_provider = getattr(self.deepseek, "provider", None)
        openrouter_provider = getattr(self.openrouter, "provider", None)
        doubao_provider = getattr(self.doubao, "provider", None)
        if isinstance(deepseek_provider, ProviderConfig):
            self.deepseek = VisionClient(replace(deepseek_provider, model=choice.deepseek_model))
        if isinstance(openrouter_provider, ProviderConfig):
            self.openrouter = VisionClient(replace(openrouter_provider, model=choice.openrouter_model))
        if isinstance(doubao_provider, ProviderConfig):
            self.doubao = VisionClient(replace(doubao_provider, model=choice.doubao_model))
        previous = self.current_provider
        self.current_provider = choice.provider
        self.model_choice = choice
        if notify and choice.provider not in {previous, "none"}:
            self.on_provider_changed(choice.provider)
        return choice

    def analyze_image_stream(
        self,
        png_bytes: bytes,
        user_text: str | None = None,
        conversation: list[dict[str, str]] | None = None,
    ) -> Iterator[str]:
        yield from self.analyze_images_stream([png_bytes], user_text=user_text, conversation=conversation)

    def analyze_images_stream(
        self,
        png_images: list[bytes],
        user_text: str | None = None,
        conversation: list[dict[str, str]] | None = None,
    ) -> Iterator[str]:
        if not self._deepseek_has_key and not self._openrouter_has_key and not self._doubao_has_key:
            raise RuntimeError("请至少填写 DeepSeek、OpenRouter 或豆包其中一把 API Key")
        if self.current_provider == "none":
            raise RuntimeError("当前路线未配置 Key")
        try:
            yield from self._stream_from_client(
                self._client_for(self.current_provider),
                png_images,
                user_text,
                conversation,
            )
            return
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code != 402:
                raise
        failed = self.current_provider
        for name in self._FAILOVER_ORDER:
            if name == failed or not self._has_provider(name):
                continue
            self.current_provider = name
            self.on_provider_changed(name)
            yield from self._stream_from_client(self._client_for(name), png_images, user_text, conversation)
            return
        vendor = PROVIDER_LABELS.get(failed, failed)
        raise RuntimeError(f"{vendor} 额度不足（HTTP 402），且没有其他可用 Key")


# Backward-compatible name for older imports and static delta parser tests.
OpenRouterVisionClient = VisionClient
