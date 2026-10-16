from __future__ import annotations

import base64
import io
import json
import re
import inspect
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from typing import Any

import requests
from PIL import Image, UnidentifiedImageError

from ai_screenshot_assistant.ai.models import (
    DEFAULT_MODEL_TIER,
    DOUBAO_CHAT_COMPLETIONS_MODELS,
    DOUBAO_VISION_MODEL,
    MODEL_ROUTES,
    ModelChoice,
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
    system_prompt: str = VISION_PROMPT


@dataclass(frozen=True)
class AIResult:
    text: str
    answer: str | None = None
    reason: str | None = None
    confidence: str | None = None


class AnalysisCancelled(Exception):
    """Raised internally when a newer screenshot replaces a streaming request."""


class CancellationToken:
    def __init__(self) -> None:
        self._cancelled = threading.Event()
        self._lock = threading.Lock()
        self._response: Any = None

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def attach_response(self, response: Any) -> None:
        with self._lock:
            already_cancelled = self.cancelled
            if not already_cancelled:
                self._response = response
        if already_cancelled:
            response.close()
            raise AnalysisCancelled()

    def detach_response(self, response: Any) -> None:
        with self._lock:
            if self._response is response:
                self._response = None

    def cancel(self) -> None:
        self._cancelled.set()
        with self._lock:
            response = self._response
            self._response = None
        if response is not None:
            response.close()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise AnalysisCancelled()


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
        cancel_token: CancellationToken | None = None,
    ) -> Iterator[str]:
        yield from self.analyze_images_stream(
            [png_bytes], user_text=user_text, conversation=conversation, cancel_token=cancel_token
        )

    def uses_responses_api(self) -> bool:
        model = self.provider.model.lower()
        if model in {item.lower() for item in DOUBAO_CHAT_COMPLETIONS_MODELS} or "turbo" in model:
            return False
        return self._is_doubao()

    def _is_doubao(self) -> bool:
        return "doubao" in self.provider.name.lower() or "volces.com" in self.provider.base_url.lower()

    def analyze_images_stream(
        self,
        png_images: list[bytes],
        user_text: str | None = None,
        conversation: list[dict[str, str]] | None = None,
        cancel_token: CancellationToken | None = None,
    ) -> Iterator[str]:
        if cancel_token is not None:
            cancel_token.raise_if_cancelled()
        if not self.provider.api_key:
            raise RuntimeError(f"{self.provider.name} API Key 不能为空")
        prompt = _build_user_prompt(user_text, conversation, self.provider.system_prompt)
        images = [prepare_image_for_ai(png_bytes) for png_bytes in png_images]
        payload = self._request_payload(prompt, images)
        headers = {
            "Authorization": f"Bearer {self.provider.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost",
            "X-Title": "AI Screenshot Assistant",
        }
        with requests.post(
            f"{self.provider.base_url.rstrip('/')}{'/responses' if self.uses_responses_api() else '/chat/completions'}",
            headers=headers,
            json=payload,
            stream=True,
            timeout=self.provider.timeout_seconds,
        ) as response:
            if cancel_token is not None:
                cancel_token.attach_response(response)
            try:
                try:
                    response.raise_for_status()
                except requests.HTTPError as exc:
                    raise self._friendly_http_error(exc) from exc
                for raw_line in response.iter_lines(chunk_size=1, decode_unicode=False):
                    if cancel_token is not None:
                        cancel_token.raise_if_cancelled()
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
            finally:
                if cancel_token is not None:
                    cancel_token.detach_response(response)

    def _request_payload(self, prompt: str, images: list[tuple[bytes, str]]) -> dict[str, Any]:
        if self.uses_responses_api():
            content: list[dict[str, Any]] = []
            for image_bytes, mime_type in images:
                image_b64 = base64.b64encode(image_bytes).decode("ascii")
                content.append({"type": "input_image", "image_url": f"data:{mime_type};base64,{image_b64}"})
            content.append({"type": "input_text", "text": prompt})
            return {
                "model": self.provider.model,
                "stream": True,
                "input": [{"role": "user", "content": content}],
                "thinking": {"type": "disabled"},
            }
        content = []
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
        return payload

    def _friendly_http_error(self, exc: requests.HTTPError) -> Exception:
        response = exc.response
        if response is None or response.status_code == 429:
            return exc
        detail = ""
        try:
            payload = response.json()
            error = payload.get("error") if isinstance(payload, dict) else None
            if isinstance(error, dict):
                code = str(error.get("code") or "").strip()
                message = str(error.get("message") or "").strip()
                detail = f"{message} ({code})" if message and code else message or code
                metadata = error.get("metadata")
                raw = metadata.get("raw") if isinstance(metadata, dict) else None
                if isinstance(raw, str) and raw.strip() and raw.strip() not in detail:
                    detail = f"{detail}；{raw.strip()[:300]}" if detail else raw.strip()[:300]
        except ValueError:
            detail = (response.text or "")[:180]
        if response.status_code == 404 and self._is_doubao():
            return RuntimeError(
                f"豆包模型未开通或无权调用（{self.provider.model}）。"
                "请到火山方舟开通该模型后再试。"
            )
        if response.status_code == 402:
            vendor = self.provider.name
            return RuntimeError(
                f"{vendor} 额度不足（HTTP 402，模型 {self.provider.model}）。"
                f"{detail[:300] if detail else '请检查该平台的账户余额或 API Key 限额。'}"
            )
        if detail:
            return RuntimeError(f"{self.provider.name} 调用失败（HTTP {response.status_code}，模型 {self.provider.model}）：{detail[:600]}")
        return exc

    @staticmethod
    def _extract_delta(data: str) -> str:
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            return ""
        if parsed.get("type") == "response.output_text.delta" and isinstance(parsed.get("delta"), str):
            return parsed["delta"]
        choices = parsed.get("choices") or []
        if not choices:
            return ""
        first = choices[0] or {}
        content = (first.get("delta") or {}).get("content")
        if isinstance(content, str) and content:
            return content
        message_content = (first.get("message") or {}).get("content")
        return message_content if isinstance(message_content, str) else ""


def _build_user_prompt(
    user_text: str | None,
    conversation: list[dict[str, str]] | None,
    system_prompt: str = VISION_PROMPT,
) -> str:
    parts = [system_prompt.strip() or VISION_PROMPT]
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
    """Routes requests to the selected Chinese vision provider."""

    def __init__(
        self,
        deepseek: ProviderConfig,
        qwen: ProviderConfig,
        on_provider_changed: Callable[[str], None] | None = None,
        model_tier: str = DEFAULT_MODEL_TIER,
        doubao: ProviderConfig | None = None,
    ) -> None:
        self.deepseek = VisionClient(deepseek)
        self.qwen = VisionClient(qwen)
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
        self._qwen_has_key = self._has_key(self.qwen)
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
        cancel_token: CancellationToken | None = None,
    ) -> Iterator[str]:
        if hasattr(client, "analyze_images_stream"):
            method = client.analyze_images_stream
            kwargs = {"user_text": user_text, "conversation": conversation}
            if "cancel_token" in inspect.signature(method).parameters:
                kwargs["cancel_token"] = cancel_token
            yield from method(png_images, **kwargs)
            return
        if len(png_images) != 1:
            raise RuntimeError("当前 AI 客户端不支持多张截图")
        method = client.analyze_image_stream
        kwargs = {"user_text": user_text, "conversation": conversation}
        if "cancel_token" in inspect.signature(method).parameters:
            kwargs["cancel_token"] = cancel_token
        yield from method(png_images[0], **kwargs)

    def _has_provider(self, name: str) -> bool:
        return {
            "qwen": self._qwen_has_key,
            "deepseek": self._deepseek_has_key,
            "doubao": self._doubao_has_key,
        }.get(name, False)

    def _client_for(self, name: str) -> VisionClient:
        return {
            "qwen": self.qwen,
            "deepseek": self.deepseek,
            "doubao": self.doubao,
        }[name]

    def _initial_provider(self) -> str:
        if self._qwen_has_key:
            return "qwen"
        if self._deepseek_has_key:
            return "deepseek"
        if self._doubao_has_key:
            return "doubao"
        return "none"

    def current_model_id(self) -> str:
        if self.current_provider == "qwen":
            provider = getattr(self.qwen, "provider", None)
        elif self.current_provider == "deepseek":
            provider = getattr(self.deepseek, "provider", None)
        elif self.current_provider == "doubao":
            provider = getattr(self.doubao, "provider", None)
        else:
            provider = None
        return str(getattr(provider, "model", "") or "")

    def available_routes(self) -> list[str]:
        return [route_id for route_id, route in MODEL_ROUTES.items() if self._has_provider(route.provider)]

    def apply_model_tier(self, tier: str, *, notify: bool = False) -> ModelChoice:
        choice = resolve_model_choice(
            tier,
            has_deepseek=self._deepseek_has_key,
            has_qwen=self._qwen_has_key,
            has_doubao=self._doubao_has_key,
        )
        deepseek_provider = getattr(self.deepseek, "provider", None)
        qwen_provider = getattr(self.qwen, "provider", None)
        doubao_provider = getattr(self.doubao, "provider", None)
        if isinstance(deepseek_provider, ProviderConfig):
            self.deepseek = VisionClient(replace(deepseek_provider, model=choice.deepseek_model))
        if isinstance(qwen_provider, ProviderConfig):
            self.qwen = VisionClient(replace(qwen_provider, model=choice.qwen_model))
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
        cancel_token: CancellationToken | None = None,
    ) -> Iterator[str]:
        yield from self.analyze_images_stream(
            [png_bytes], user_text=user_text, conversation=conversation, cancel_token=cancel_token
        )

    def analyze_images_stream(
        self,
        png_images: list[bytes],
        user_text: str | None = None,
        conversation: list[dict[str, str]] | None = None,
        cancel_token: CancellationToken | None = None,
    ) -> Iterator[str]:
        if not self._deepseek_has_key and not self._qwen_has_key and not self._doubao_has_key:
            raise RuntimeError("请至少填写 DeepSeek、Qwen 或豆包其中一把 API Key")
        if self.current_provider == "none":
            raise RuntimeError("当前路线未配置 Key")
        yield from self._stream_from_client(
            self._client_for(self.current_provider),
            png_images,
            user_text,
            conversation,
            cancel_token,
        )


# Backward-compatible name for older imports and static delta parser tests.
QwenVisionClient = VisionClient
