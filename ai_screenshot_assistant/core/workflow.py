from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from ai_screenshot_assistant.ai.client import parse_ai_result
from ai_screenshot_assistant.config import Settings, settings
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
        self.mobile_conversation: list[dict[str, str]] = []

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
            image_b64 = base64.b64encode(png).decode("ascii")
            self._publish(
                "screenshot.captured",
                request_id,
                {
                    "image": f"data:image/png;base64,{image_b64}",
                    "size": len(png),
                },
            )
            self._publish_selection_status("completed", "截图已添加到手机端缓冲区，可继续截图或发送")
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

    def _debug_path(self) -> Path | None:
        return Path("debug/image.png") if self.settings.save_debug_image else None

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
        try:
            self._publish_selection_status("analyzing", "截图成功，AI 正在分析全部题目")
            self.on_stream_started()
            self._publish("answer.started", request_id, started_payload)
            chunks: list[str] = []
            conversation = list(self.mobile_conversation) if use_conversation else None
            if hasattr(self.ai_client, "analyze_images_stream"):
                stream = self.ai_client.analyze_images_stream(png_images, user_text=user_text, conversation=conversation)
            else:
                stream = self.ai_client.analyze_image_stream(png_images[0], user_text=user_text, conversation=conversation)
            for delta in stream:
                chunks.append(delta)
                self.on_stream_delta(delta)
                self._publish("answer.delta", request_id, {"delta": delta})
            text = "".join(chunks)
            if use_conversation:
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
            self._publish("answer.completed", request_id, payload)
            self.on_stream_completed(text)
            self.on_result(payload["result"])
            self._publish_selection_status("completed", "答案已生成，可以继续框选或全屏截题")
        except Exception as exc:
            self._fail(str(exc), request_id=request_id)

    def _remember_mobile_turn(self, user_text: str, assistant_text: str) -> None:
        self.mobile_conversation.extend(
            [
                {"role": "user", "content": user_text},
                {"role": "assistant", "content": assistant_text},
            ]
        )
        self.mobile_conversation = self.mobile_conversation[-12:]

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
