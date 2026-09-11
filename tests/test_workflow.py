from dataclasses import replace

from ai_screenshot_assistant.config import settings
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
        "selection.status",
        "answer.started",
        "answer.delta",
        "answer.delta",
        "answer.delta",
        "answer.completed",
        "selection.status",
    ]
    assert result_holder["answer"] == "B"
    assert result_holder["reason"] == "TCP reliable"
    assert stream_states == [
        "started",
        ("completed", '{"answer":"B","reason":"TCP reliable","confidence":"0.95"}'),
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
    assert [event["type"] for event in publisher.events[:3]] == [
        "selection.status",
        "selection.status",
        "answer.started",
    ]
    assert publisher.events[2]["payload"] == {"mode": "fullscreen"}


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

    workflow.process_fullscreen(10, 20, user_text="第 2 题为什么选 B？", use_conversation=True)

    assert ai_client.calls[0]["png_bytes"] == b"fullpng"
    assert ai_client.calls[0]["user_text"] == "第 2 题为什么选 B？"
    assert ai_client.calls[0]["conversation"] == [
        {"role": "user", "content": "先看第 1 题"},
        {"role": "assistant", "content": "答案：A"},
    ]
    assert workflow.mobile_conversation[-2:] == [
        {"role": "user", "content": "第 2 题为什么选 B？"},
        {
            "role": "assistant",
            "content": '{"answer":"B","reason":"TCP reliable","confidence":"0.95"}',
        },
    ]
    assert publisher.events[2]["payload"] == {
        "mode": "fullscreen",
        "has_user_text": True,
        "conversation_turns": 2,
    }
