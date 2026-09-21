from __future__ import annotations

import base64
import gc
import threading
import time
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from ai_screenshot_assistant.ai.client import parse_ai_result, prepare_image_for_album
from ai_screenshot_assistant.ai.formatting import format_ai_output
from ai_screenshot_assistant.config import Settings, settings
from ai_screenshot_assistant.core.conversation import cap_conversation_memory
from ai_screenshot_assistant.core.messages import Event
from ai_screenshot_assistant.capture.roi import Roi, RoiStateMachine


class CapturePort(Protocol):
    def capture_png(self, roi: Roi, debug_path: Path | None = None) -> bytes: ...

    def capture_fullscreen_png(
        self,
        x: int | None = None,
        y: int | None = None,
        debug_path: Path | None = None,
    ) -> bytes: ...


class AIPort(Protocol):
    def analyze_image_stream(
        self,
        png_bytes: bytes,
        user_text: str | None = None,
        conversation: list[dict[str, str]] | None = None,
    ): ...

    def analyze_images_stream(
        self,
        png_images: list[bytes],
        user_text: str | None = None,
        conversation: list[dict[str, str]] | None = None,
    ): ...


class PublisherPort(Protocol):
    def send_sync(self, event: dict) -> None: ...


class AssistantWorkflow:
    def __init__(
        self,
        session_id: str,
        capture: CapturePort,
        ai_client: AIPort,
        publisher: PublisherPort | None = None,
        app_settings: Settings = settings,
    ) -> None:
        self.session_id = session_id
        self.capture = capture
        self.ai_client = ai_client
        self.publisher = publisher
        self.settings = app_settings
        self.roi = RoiStateMachine()
        self.on_status = lambda message: None
        self.on_result = lambda result: None
        self.on_error = lambda message: None
        self.on_stream_started = lambda: None
        self.on_stream_delta = lambda delta: None
        self.on_stream_completed = lambda text: None
        self.on_stream_error = lambda message: None
        self.on_capture_finished = lambda: None
        self.mobile_conversation: list[dict[str, str]] = []
        self._generation_lock = threading.Lock()
        self._generation = 0

    def start_capture(self) -> None:
        self.roi.start()
        self.on_status("Left 2s to box a region, or right 2s for fullscreen")
        self._publish_selection_status("waiting", "左键长按 2 秒框选，或右键长按 2 秒全屏")

    def left_up(self, x: int, y: int) -> None:
        self.roi.left_up(x, y)
        self.on_status(f"P1: ({x}, {y}); move to P2 and left click to submit")
        self._publish_selection_status("p1_ready", "左键 2 秒已识别，请再左键框选终点")

    def second_left_up(self, x: int, y: int) -> None:
        try:
            roi = self.roi.right_up(x, y)
        except ValueError as exc:
            self._fail(str(exc))
            self.roi.reset()
            return
        if roi is None:
            self.on_status("Hold left button for 2 seconds at P1 before clicking P2")
            self._publish_selection_status("waiting", "请先在起点按住左键 2 秒")
            return
        self.on_status("Selection submitted; analyzing...")
        self._publish_selection_status("capturing", "框选完成，正在截取题目")
        self.process_roi(roi)
        self.roi.reset()

    def process_roi(self, roi: Roi) -> None:
        request_id = uuid4().hex
        started_at = time.perf_counter()
        try:
            png = self.capture.capture_png(roi, debug_path=self._debug_path())
            self._publish_captured_screenshot(png, request_id, add_to_buffer=False)
            self.on_capture_finished()
            self._analyze_png(png, request_id, started_at, {"roi": roi.to_mss_monitor()})
        except Exception as exc:
            self._fail(str(exc), request_id=request_id)

    def process_fullscreen(
        self,
        x: int | None = None,
        y: int | None = None,
        user_text: str | None = None,
        use_conversation: bool = False,
        is_chat: bool = False,
        request_id: str | None = None,
    ) -> None:
        self.roi.reset()
        self.on_status("Fullscreen captured; analyzing...")
        self._publish_selection_status("capturing", "已截取当前屏幕全屏，正在发送给 AI")
        request_id = request_id or uuid4().hex
        started_at = time.perf_counter()
        started_payload: dict[str, Any] = {"mode": "fullscreen"}
        if user_text:
            started_payload["has_user_text"] = True
        if use_conversation:
            started_payload["conversation_turns"] = len(self.mobile_conversation)
        if is_chat:
            started_payload["chat"] = True
        try:
            png = self.capture.capture_fullscreen_png(x, y, debug_path=self._debug_path())
            self._publish_captured_screenshot(png, request_id, add_to_buffer=False)
            self.on_capture_finished()
            self._analyze_png(
                png,
                request_id,
                started_at,
                started_payload,
                user_text=user_text,
                use_conversation=use_conversation,
            )
        except Exception as exc:
            self._fail(str(exc), request_id=request_id)

    def capture_fullscreen_for_mobile(self, x: int | None = None, y: int | None = None) -> None:
        request_id = uuid4().hex
        try:
            png = self.capture.capture_fullscreen_png(x, y, debug_path=self._debug_path())
            self._publish_captured_screenshot(png, request_id, add_to_buffer=True)
            self.on_capture_finished()
            self._publish_selection_status("completed", "截图已添加到手机端，可保存到相册或发送给 AI")
        except Exception as exc:
            self._fail(str(exc), request_id=request_id)

    def process_mobile_images(
        self,
        png_images: list[bytes],
        user_text: str | None = None,
        use_conversation: bool = False,
        is_chat: bool = False,
        request_id: str | None = None,
    ) -> None:
        if not png_images and not (user_text or "").strip():
            self._fail("请输入文字或至少添加 1 张截图")
            return
        started_payload: dict[str, Any] = {
            "mode": "mobile_screenshots",
            "image_count": len(png_images),
        }
        if user_text:
            started_payload["has_user_text"] = True
        if use_conversation:
            started_payload["conversation_turns"] = len(self.mobile_conversation)
        if is_chat:
            started_payload["chat"] = True
        self._analyze_pngs(
            png_images,
            request_id or uuid4().hex,
            time.perf_counter(),
            started_payload,
            user_text=user_text,
            use_conversation=use_conversation,
        )

    def clear_conversation(self) -> dict[str, Any]:
        released_turns = len(self.mobile_conversation)
        self.mobile_conversation = []
        gc.collect()
        payload = {"released_turns": released_turns}
        self._publish("conversation.cleared", uuid4().hex, payload)
        self.on_status("对话记录已清空")
        return payload

    def set_model_tier(self, tier: str) -> dict[str, Any]:
        client = self.ai_client
        apply_tier = getattr(client, "apply_model_tier", None)
        if not callable(apply_tier):
            payload = {"tier": tier, "provider": "unknown", "model": "", "display_name": str(tier)}
            self._publish("model.changed", uuid4().hex, payload)
            return payload
        choice = apply_tier(tier)
        payload = choice.to_payload() if hasattr(choice, "to_payload") else {"tier": str(tier)}
        self._publish("model.changed", uuid4().hex, payload)
        self.on_status(f"模型：{payload.get('display_name') or payload.get('tier')}")
        return payload

    def _debug_path(self) -> Path | None:
        return Path("debug/image.png") if self.settings.save_debug_image else None

    def _publish_captured_screenshot(
        self,
        png: bytes,
        request_id: str,
        *,
        add_to_buffer: bool,
    ) -> None:
        image_bytes, mime_type = prepare_image_for_album(png)
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        self._publish(
            "screenshot.captured",
            request_id,
            {
                "image": f"data:{mime_type};base64,{image_b64}",
                "size": len(image_bytes),
                "original_size": len(png),
                "add_to_buffer": add_to_buffer,
                "save_to_album": True,
            },
        )

    def _analyze_png(
        self,
        png: bytes,
        request_id: str,
        started_at: float,
        started_payload: dict[str, Any],
        user_text: str | None = None,
        use_conversation: bool = False,
    ) -> None:
        self._analyze_pngs(
            [png],
            request_id,
            started_at,
            started_payload,
            user_text=user_text,
            use_conversation=use_conversation,
        )

    def _analyze_pngs(
        self,
        png_images: list[bytes],
        request_id: str,
        started_at: float,
        started_payload: dict[str, Any],
        user_text: str | None = None,
        use_conversation: bool = False,
    ) -> None:
        self.on_capture_finished()
        generation = self._begin_analysis()
        try:
            if not self._run_if_active(generation, self.on_stream_started):
                return
            self._publish_selection_status("analyzing", "截图成功，AI 正在分析全部题目")
            self._publish("answer.started", request_id, started_payload)
            chunks: list[str] = []
            conversation = cap_conversation_memory(self.mobile_conversation) if use_conversation else None
            if hasattr(self.ai_client, "analyze_images_stream"):
                stream = self.ai_client.analyze_images_stream(png_images, user_text=user_text, conversation=conversation)
            elif png_images:
                stream = self.ai_client.analyze_image_stream(png_images[0], user_text=user_text, conversation=conversation)
            else:
                raise RuntimeError("当前 AI 客户端不支持无图追问")
            for delta in stream:
                if not self._is_active(generation):
                    return
                chunks.append(delta)
                self._publish("answer.delta", request_id, {"delta": delta})
                if not self._run_if_active(generation, lambda current=delta: self.on_stream_delta(current)):
                    return
            if not self._is_active(generation):
                return
            text = format_ai_output("".join(chunks))
            if use_conversation and self._is_active(generation):
                self._remember_mobile_turn(
                    user_text.strip() if user_text and user_text.strip() else f"用户发送了 {len(png_images)} 张截图",
                    text,
                )
            result = parse_ai_result(text)
            payload = {
                "result": {
                    "text": result.text,
                    "answer": result.answer,
                    "reason": result.reason,
                    "confidence": result.confidence,
                    "latency_seconds": round(time.perf_counter() - started_at, 3),
                }
            }
            if not self._is_active(generation):
                return
            self._publish("answer.completed", request_id, payload)
            if not self._run_if_active(generation, lambda: self._apply_local_result(text, payload["result"])):
                return
            self._publish_selection_status("completed", "答案已生成，可以继续框选或全屏截题")
        except Exception as exc:
            if self._is_active(generation):
                self._fail(str(exc), request_id=request_id)

    def _begin_analysis(self) -> int:
        with self._generation_lock:
            self._generation += 1
            return self._generation

    def _is_active(self, generation: int) -> bool:
        with self._generation_lock:
            return generation == self._generation

    def _run_if_active(self, generation: int, callback) -> bool:
        with self._generation_lock:
            if generation != self._generation:
                return False
            callback()
            return True

    def _apply_local_result(self, text: str, result: dict[str, Any]) -> None:
        self.on_stream_completed(text)
        self.on_result(result)

    def _remember_mobile_turn(self, user_text: str, assistant_text: str) -> None:
        self.mobile_conversation.extend(
            [
                {"role": "user", "content": user_text},
                {"role": "assistant", "content": assistant_text},
            ]
        )
        self.mobile_conversation = cap_conversation_memory(self.mobile_conversation)

    def _publish(self, event_type: str, request_id: str, payload: dict) -> None:
        event = Event(type=event_type, session_id=self.session_id, request_id=request_id, payload=payload)
        if self.publisher is not None:
            try:
                self.publisher.send_sync(event.to_dict())
            except Exception as exc:
                self.on_status(f"Mobile update failed: {exc}")

    def _fail(self, message: str, request_id: str | None = None) -> None:
        request_id = request_id or uuid4().hex
        self._publish("answer.error", request_id, {"message": message})
        self._publish_selection_status("error", "分析失败，可以重新框选或全屏截题")
        self.on_stream_error(message)
        self.on_error(message)

    def _publish_selection_status(self, state: str, message: str) -> None:
        self._publish("selection.status", uuid4().hex, {"state": state, "message": message})
