from dataclasses import replace

from ai_screenshot_assistant.config import settings
from ai_screenshot_assistant.core.workflow import AssistantWorkflow
from ai_screenshot_assistant.capture.roi import Roi


class FakeCapture:
    def capture_png(self, roi, debug_path=None):
        return b"png"


class FakeAI:
    def analyze_image_stream(self, png_bytes):
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
        "answer.started",
        "answer.delta",
        "answer.delta",
        "answer.delta",
        "answer.completed",
    ]
    assert result_holder["answer"] == "B"
    assert result_holder["reason"] == "TCP reliable"
    assert stream_states == [
        "started",
        ("completed", '{"answer":"B","reason":"TCP reliable","confidence":"0.95"}'),
    ]
    assert stream_chunks == ['{"answer":"B",', '"reason":"TCP reliable",', '"confidence":"0.95"}']
