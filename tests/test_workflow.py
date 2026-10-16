import base64
import io
from dataclasses import replace

from PIL import Image

from ai_screenshot_assistant.config import settings
from ai_screenshot_assistant.core.conversation import MAX_CONVERSATION_MESSAGES, MAX_TURN_CHARS
from ai_screenshot_assistant.core.workflow import AssistantWorkflow
from ai_screenshot_assistant.capture.roi import Roi


class FakeCapture:
    def __init__(self):
        self.fullscreen_args = None

    def capture_png(self, roi, debug_path=None):
        return b"png"

    def capture_fullscreen_png(self, x=None, y=None, debug_path=None):
        self.fullscreen_args = (x, y)
        return b"fullpng"


class LargeImageCapture(FakeCapture):
    def capture_fullscreen_png(self, x=None, y=None, debug_path=None):
        self.fullscreen_args = (x, y)
        image = Image.effect_noise((2200, 1600), 100).convert("RGB")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()


class FakeAI:
    def __init__(self):
        self.calls = []

    def analyze_image_stream(self, png_bytes, user_text=None, conversation=None):
        self.calls.append(
            {
                "png_bytes": png_bytes,
                "user_text": user_text,
                "conversation": conversation,
            }
        )
        yield '{"answer":"B",'
        yield '"reason":"TCP reliable",'
        yield '"confidence":"0.95"}'

    def analyze_images_stream(self, png_images, user_text=None, conversation=None):
        self.calls.append(
            {
                "png_images": png_images,
                "user_text": user_text,
                "conversation": conversation,
            }
        )
        if len(png_images) == 1:
            yield '{"answer":"B",'
            yield '"reason":"TCP reliable",'
            yield '"confidence":"0.95"}'
        else:
            yield '{"answer":"A",'
            yield '"reason":"multi image",'
            yield '"confidence":"0.91"}'


class SqlAI:
    def analyze_images_stream(self, png_images, user_text=None, conversation=None):
        yield "答案：SELECT name, age FROM users WHERE age > 18 ORDER BY age DESC;\n"
        yield "解析：查询成年用户。"


class FailingAI:
    def analyze_images_stream(self, png_images, user_text=None, conversation=None):
        raise RuntimeError("provider rejected request")
        yield ""


class FakePublisher:
    def __init__(self):
        self.events = []

    def send_sync(self, event):
        self.events.append(event)


def test_workflow_streams_and_completes() -> None:
    publisher = FakePublisher()
    result_holder = {}
    stream_chunks = []
    stream_states = []
    workflow = AssistantWorkflow(
        session_id="s1",
        capture=FakeCapture(),
        ai_client=FakeAI(),
        publisher=publisher,
        app_settings=replace(settings, save_debug_image=False),
    )
    workflow.on_result = result_holder.update
    workflow.on_stream_started = lambda: stream_states.append("started")
    workflow.on_stream_delta = stream_chunks.append
    workflow.on_stream_completed = lambda text: stream_states.append(("completed", text))

    workflow.process_roi(Roi(left=1, top=2, width=30, height=40))

    assert [event["type"] for event in publisher.events] == [
        "screenshot.captured",
        "selection.status",
        "answer.started",
        "answer.delta",
        "answer.delta",
        "answer.delta",
        "answer.completed",
        "selection.status",
    ]
    assert publisher.events[0]["payload"]["save_to_album"] is True
    assert publisher.events[0]["payload"]["add_to_buffer"] is False
    assert result_holder["answer"] == "B"
    assert result_holder["reason"] == "TCP reliable"
    assert stream_states == [
        "started",
        ("completed", "答案：B\n解析：TCP reliable"),
    ]
    assert stream_chunks == ['{"answer":"B",', '"reason":"TCP reliable",', '"confidence":"0.95"}']


def test_selection_statuses_are_published() -> None:
    publisher = FakePublisher()
    workflow = AssistantWorkflow(
        session_id="s1",
        capture=FakeCapture(),
        ai_client=FakeAI(),
        publisher=publisher,
        app_settings=replace(settings, save_debug_image=False),
    )

    workflow.start_capture()
    workflow.left_up(10, 20)

    statuses = [event["payload"] for event in publisher.events if event["type"] == "selection.status"]
    assert statuses == [
        {"state": "waiting", "message": "左键长按 2 秒框选，或右键长按 2 秒全屏"},
        {"state": "p1_ready", "message": "左键 2 秒已识别，请再左键框选终点"},
    ]


def test_workflow_fullscreen_streams_and_completes() -> None:
    publisher = FakePublisher()
    capture = FakeCapture()
    result_holder = {}
    workflow = AssistantWorkflow(
        session_id="s1",
        capture=capture,
        ai_client=FakeAI(),
        publisher=publisher,
        app_settings=replace(settings, save_debug_image=False),
    )
    workflow.on_result = result_holder.update
    workflow.roi.left_up(3, 4)

    workflow.process_fullscreen(120, 240)

    assert capture.fullscreen_args == (120, 240)
    assert workflow.roi.p1 is None
    assert result_holder["answer"] == "B"
    screenshot_events = [event for event in publisher.events if event["type"] == "screenshot.captured"]
    started = next(event for event in publisher.events if event["type"] == "answer.started")
    assert screenshot_events[0]["payload"]["save_to_album"] is True
    assert screenshot_events[0]["payload"]["add_to_buffer"] is False
    assert started["payload"] == {"mode": "fullscreen"}


def test_workflow_fullscreen_uses_supplied_request_id() -> None:
    publisher = FakePublisher()
    workflow = AssistantWorkflow(
        session_id="s1",
        capture=FakeCapture(),
        ai_client=FakeAI(),
        publisher=publisher,
        app_settings=replace(settings, save_debug_image=False),
    )

    workflow.process_fullscreen(120, 240, request_id="fullscreen-abc")

    answer_events = [event for event in publisher.events if event["type"].startswith("answer.")]
    assert {event["request_id"] for event in answer_events} == {"fullscreen-abc"}


def test_workflow_fullscreen_question_uses_conversation_context() -> None:
    publisher = FakePublisher()
    capture = FakeCapture()
    ai_client = FakeAI()
    workflow = AssistantWorkflow(
        session_id="s1",
        capture=capture,
        ai_client=ai_client,
        publisher=publisher,
        app_settings=replace(settings, save_debug_image=False),
    )
    workflow.mobile_conversation = [
        {"role": "user", "content": "先看第 1 题"},
        {"role": "assistant", "content": "答案：A"},
    ]

    workflow.process_fullscreen(10, 20, user_text="第 2 题为什么选 B？", use_conversation=True, is_chat=True)

    assert ai_client.calls[0]["png_images"] == [b"fullpng"]
    assert ai_client.calls[0]["user_text"] == "第 2 题为什么选 B？"
    assert ai_client.calls[0]["conversation"] == [
        {"role": "user", "content": "先看第 1 题"},
        {"role": "assistant", "content": "答案：A"},
    ]
    assert workflow.mobile_conversation[-2:] == [
        {"role": "user", "content": "第 2 题为什么选 B？"},
        {
            "role": "assistant",
            "content": "答案：B\n解析：TCP reliable",
        },
    ]
    started = next(event for event in publisher.events if event["type"] == "answer.started")
    assert started["payload"] == {
        "mode": "fullscreen",
        "has_user_text": True,
        "conversation_turns": 2,
        "chat": True,
    }


def test_mobile_fullscreen_preview_publishes_screenshot() -> None:
    publisher = FakePublisher()
    workflow = AssistantWorkflow(
        session_id="s1",
        capture=FakeCapture(),
        ai_client=FakeAI(),
        publisher=publisher,
        app_settings=replace(settings, save_debug_image=False),
    )

    workflow.capture_fullscreen_for_mobile(10, 20)

    assert publisher.events[0]["type"] == "screenshot.captured"
    assert publisher.events[0]["payload"]["image"].startswith("data:image/png;base64,")
    assert publisher.events[0]["payload"]["size"] == len(b"fullpng")
    assert publisher.events[0]["payload"]["save_to_album"] is True
    assert publisher.events[0]["payload"]["add_to_buffer"] is True


def test_mobile_fullscreen_preview_compresses_large_screenshot() -> None:
    publisher = FakePublisher()
    workflow = AssistantWorkflow(
        session_id="s1",
        capture=LargeImageCapture(),
        ai_client=FakeAI(),
        publisher=publisher,
        app_settings=replace(settings, save_debug_image=False),
    )

    workflow.capture_fullscreen_for_mobile(10, 20)

    payload = publisher.events[0]["payload"]
    assert payload["image"].startswith("data:image/jpeg;base64,")
    assert payload["size"] < payload["original_size"]
    image_b64 = payload["image"].split(",", 1)[1]
    saved = Image.open(io.BytesIO(base64.b64decode(image_b64)))
    assert max(saved.size) == 2200


def test_mobile_multi_screenshot_submission_uses_all_images() -> None:
    publisher = FakePublisher()
    ai_client = FakeAI()
    workflow = AssistantWorkflow(
        session_id="s1",
        capture=FakeCapture(),
        ai_client=ai_client,
        publisher=publisher,
        app_settings=replace(settings, save_debug_image=False),
    )

    workflow.process_mobile_images(
        [b"one", b"two"],
        user_text="补充条件",
        use_conversation=True,
        is_chat=True,
    )

    assert ai_client.calls[0]["png_images"] == [b"one", b"two"]
    assert ai_client.calls[0]["user_text"] == "补充条件"
    assert publisher.events[1]["type"] == "answer.started"
    assert publisher.events[1]["payload"] == {
        "mode": "mobile_screenshots",
        "image_count": 2,
        "has_user_text": True,
        "conversation_turns": 0,
        "chat": True,
    }


def test_mobile_image_only_chat_is_remembered() -> None:
    publisher = FakePublisher()
    ai_client = FakeAI()
    workflow = AssistantWorkflow(
        session_id="s1",
        capture=FakeCapture(),
        ai_client=ai_client,
        publisher=publisher,
        app_settings=replace(settings, save_debug_image=False),
    )

    workflow.process_mobile_images(
        [b"one", b"two"],
        use_conversation=True,
        is_chat=True,
        request_id="chat-images-only",
    )

    assert workflow.mobile_conversation[-2:] == [
        {"role": "user", "content": "用户发送了 2 张截图"},
        {
            "role": "assistant",
            "content": "答案：A\n解析：multi image",
        },
    ]
    answer_events = [event for event in publisher.events if event["type"].startswith("answer.")]
    assert {event["request_id"] for event in answer_events} == {"chat-images-only"}


def test_mobile_text_only_chat_is_allowed() -> None:
    publisher = FakePublisher()
    ai_client = FakeAI()
    workflow = AssistantWorkflow(
        session_id="s1",
        capture=FakeCapture(),
        ai_client=ai_client,
        publisher=publisher,
        app_settings=replace(settings, save_debug_image=False),
    )

    workflow.process_mobile_images(
        [],
        user_text="继续解释上一题",
        use_conversation=True,
        is_chat=True,
    )

    assert ai_client.calls[0]["png_images"] == []
    assert ai_client.calls[0]["user_text"] == "继续解释上一题"
    assert publisher.events[1]["payload"] == {
        "mode": "mobile_screenshots",
        "image_count": 0,
        "has_user_text": True,
        "conversation_turns": 0,
        "chat": True,
    }


def test_sql_answer_is_formatted_before_completion() -> None:
    publisher = FakePublisher()
    workflow = AssistantWorkflow(
        session_id="s1",
        capture=FakeCapture(),
        ai_client=SqlAI(),
        publisher=publisher,
        app_settings=replace(settings, save_debug_image=False),
    )

    workflow.process_mobile_images([b"one"], request_id="chat-sql")

    completed = [event for event in publisher.events if event["type"] == "answer.completed"][0]
    text = completed["payload"]["result"]["text"]
    assert "```sql" in text
    assert "SELECT\n    name," in text
    assert "\nFROM\n    users" in text
    assert "\nWHERE\n    age > 18" in text


def test_mobile_ai_error_is_published() -> None:
    publisher = FakePublisher()
    workflow = AssistantWorkflow(
        session_id="s1",
        capture=FakeCapture(),
        ai_client=FailingAI(),
        publisher=publisher,
        app_settings=replace(settings, save_debug_image=False),
    )

    workflow.process_mobile_images([b"one"], is_chat=True, request_id="chat-error")

    errors = [event for event in publisher.events if event["type"] == "answer.error"]
    assert len(errors) == 1
    assert errors[0]["session_id"] == "s1"
    assert errors[0]["request_id"] == "chat-error"
    assert errors[0]["payload"] == {"message": "provider rejected request"}


def test_conversation_memory_is_capped() -> None:
    ai_client = FakeAI()
    workflow = AssistantWorkflow(
        session_id="s1",
        capture=FakeCapture(),
        ai_client=ai_client,
        publisher=FakePublisher(),
        app_settings=replace(settings, save_debug_image=False),
    )
    workflow.mobile_conversation = [{"role": "user", "content": f"turn-{index}"} for index in range(20)]

    workflow.process_mobile_images(["one"], user_text="追问", use_conversation=True, is_chat=True)

    assert len(ai_client.calls[0]["conversation"]) == MAX_CONVERSATION_MESSAGES
    assert len(workflow.mobile_conversation) == MAX_CONVERSATION_MESSAGES
    assert workflow.mobile_conversation[-2]["content"] == "追问"


def test_long_chat_turns_are_truncated() -> None:
    class LongAI:
        def analyze_images_stream(self, png_images, user_text=None, conversation=None):
            yield "答案：" + ("解析很长" * 200)

    workflow = AssistantWorkflow(
        session_id="s1",
        capture=FakeCapture(),
        ai_client=LongAI(),
        publisher=FakePublisher(),
        app_settings=replace(settings, save_debug_image=False),
    )

    workflow.process_mobile_images([b"one"], user_text="问", use_conversation=True, is_chat=True)

    assert all(len(item["content"]) <= MAX_TURN_CHARS for item in workflow.mobile_conversation)


def test_clear_conversation_releases_memory_and_publishes() -> None:
    publisher = FakePublisher()
    workflow = AssistantWorkflow(
        session_id="s1",
        capture=FakeCapture(),
        ai_client=FakeAI(),
        publisher=publisher,
        app_settings=replace(settings, save_debug_image=False),
    )
    workflow.mobile_conversation = [
        {"role": "user", "content": "上一题"},
        {"role": "assistant", "content": "答案：A"},
    ]

    result = workflow.clear_conversation()

    assert result["released_turns"] == 2
    assert workflow.mobile_conversation == []
    assert publisher.events[-1]["type"] == "conversation.cleared"


def test_set_model_tier_publishes_choice() -> None:
    class TierClient:
        def apply_model_tier(self, tier, notify=True):
            from ai_screenshot_assistant.ai.models import resolve_model_choice

            return resolve_model_choice(tier, has_deepseek=True, has_qwen=True)

    publisher = FakePublisher()
    workflow = AssistantWorkflow(
        session_id="s1",
        capture=FakeCapture(),
        ai_client=TierClient(),
        publisher=publisher,
        app_settings=replace(settings, save_debug_image=False),
    )

    payload = workflow.set_model_tier("中等")

    assert payload["tier"] == "qwen-vl-flash"
    assert payload["route"] == "qwen-vl-flash"
    assert payload["model"] == "qwen3.8-flash"
    assert publisher.events[-1]["type"] == "model.changed"
    assert "通义千问" in publisher.events[-1]["payload"]["display_name"]


def test_overlapping_analysis_replaces_previous_output() -> None:
    import threading

    first_started = threading.Event()
    proceed_first = threading.Event()

    class SlowThenFastAI:
        def __init__(self) -> None:
            self.calls = 0
            self.lock = threading.Lock()

        def analyze_images_stream(self, png_images, user_text=None, conversation=None):
            with self.lock:
                self.calls += 1
                call = self.calls
            if call == 1:
                first_started.set()
                proceed_first.wait(timeout=2)
                yield "答案：旧题"
            else:
                yield "答案：新题"
                yield "\n解析：最新截图"

    overlay: list[str] = []
    publisher = FakePublisher()
    workflow = AssistantWorkflow(
        session_id="s1",
        capture=FakeCapture(),
        ai_client=SlowThenFastAI(),
        publisher=publisher,
        app_settings=replace(settings, save_debug_image=False),
    )
    workflow.on_stream_started = lambda: overlay.append("start")
    workflow.on_stream_delta = overlay.append
    workflow.on_stream_completed = overlay.append
    workflow.on_stream_error = lambda message: overlay.append(f"error:{message}")

    worker = threading.Thread(target=workflow.process_mobile_images, args=([b"one"],), daemon=True)
    worker.start()
    assert first_started.wait(1)
    workflow.process_mobile_images([b"two"])
    proceed_first.set()
    worker.join(timeout=2)

    errors = [event for event in publisher.events if event["type"] == "answer.error"]
    completed = [event for event in publisher.events if event["type"] == "answer.completed"]
    assert not any("上一题仍在分析" in event["payload"]["message"] for event in errors)
    assert completed
    assert completed[-1]["payload"]["result"]["text"].startswith("答案：新题")
    assert "答案：旧题" not in "".join(overlay)
    assert overlay[-1].startswith("答案：新题")
    assert not any(item.startswith("error:") for item in overlay)


def test_new_analysis_closes_previous_stream() -> None:
    import threading

    first_started = threading.Event()
    first_closed = threading.Event()

    class Response:
        def close(self):
            first_closed.set()

    class CancellableAI:
        def __init__(self) -> None:
            self.calls = 0

        def analyze_images_stream(self, png_images, user_text=None, conversation=None, cancel_token=None):
            self.calls += 1
            if self.calls == 1:
                cancel_token.attach_response(Response())
                first_started.set()
                first_closed.wait(timeout=2)
                cancel_token.raise_if_cancelled()
            yield "答案：新题"

    publisher = FakePublisher()
    workflow = AssistantWorkflow(
        session_id="s1",
        capture=FakeCapture(),
        ai_client=CancellableAI(),
        publisher=publisher,
        app_settings=replace(settings, save_debug_image=False),
    )

    worker = threading.Thread(target=workflow.process_mobile_images, args=([b"one"],), daemon=True)
    worker.start()
    assert first_started.wait(1)

    workflow.process_mobile_images([b"two"])
    worker.join(timeout=2)

    assert first_closed.is_set()
    assert not worker.is_alive()
    completed = [event for event in publisher.events if event["type"] == "answer.completed"]
    assert len(completed) == 1
    assert completed[0]["payload"]["result"]["text"] == "答案：新题"


def test_latest_click_wins_even_when_older_capture_finishes_last() -> None:
    import threading

    first_capture_started = threading.Event()
    release_first_capture = threading.Event()

    class OutOfOrderCapture(FakeCapture):
        def capture_fullscreen_png(self, x=None, y=None, debug_path=None):
            if x == 1:
                first_capture_started.set()
                release_first_capture.wait(timeout=2)
                return b"old"
            return b"new"

    class EchoAI:
        def analyze_images_stream(self, png_images, user_text=None, conversation=None, cancel_token=None):
            yield "答案：" + png_images[0].decode()

    publisher = FakePublisher()
    workflow = AssistantWorkflow(
        session_id="s1",
        capture=OutOfOrderCapture(),
        ai_client=EchoAI(),
        publisher=publisher,
        app_settings=replace(settings, save_debug_image=False),
    )

    older = threading.Thread(target=workflow.process_fullscreen, args=(1, 1), daemon=True)
    older.start()
    assert first_capture_started.wait(1)
    workflow.process_fullscreen(2, 2)
    release_first_capture.set()
    older.join(timeout=2)

    completed = [event for event in publisher.events if event["type"] == "answer.completed"]
    assert len(completed) == 1
    assert completed[0]["payload"]["result"]["text"] == "答案：new"


def test_clear_conversation_cancels_inflight_answer_and_memory_write() -> None:
    import threading

    started = threading.Event()
    release = threading.Event()

    class SlowAI:
        def analyze_images_stream(self, png_images, user_text=None, conversation=None, cancel_token=None):
            started.set()
            release.wait(timeout=2)
            cancel_token.raise_if_cancelled()
            yield "答案：不应出现"

    publisher = FakePublisher()
    workflow = AssistantWorkflow(
        session_id="s1",
        capture=FakeCapture(),
        ai_client=SlowAI(),
        publisher=publisher,
        app_settings=replace(settings, save_debug_image=False),
    )
    worker = threading.Thread(
        target=workflow.process_mobile_images,
        args=([b"one"],),
        kwargs={"user_text": "旧问题", "use_conversation": True},
        daemon=True,
    )
    worker.start()
    assert started.wait(1)

    workflow.clear_conversation()
    release.set()
    worker.join(timeout=2)

    assert workflow.mobile_conversation == []
    assert not any(event["type"] == "answer.completed" for event in publisher.events)
