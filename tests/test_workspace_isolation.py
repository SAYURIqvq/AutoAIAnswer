import threading

from ai_screenshot_assistant.core.workflow import AssistantWorkflow


def test_replacement_and_clear_are_lane_local():
    workflow = AssistantWorkflow("test", None, None)
    direct, direct_token = workflow._begin_analysis("direct")
    chat, chat_token = workflow._begin_analysis("chat")
    newer, _ = workflow._begin_analysis("direct")
    assert direct_token.cancelled
    assert not chat_token.cancelled
    assert workflow._is_active(chat)
    assert not workflow._is_active(direct)
    workflow.clear_conversation()
    assert chat_token.cancelled
    assert workflow._is_active(newer)


def test_queued_old_ui_callback_cannot_restore_cleared_answer():
    workflow = AssistantWorkflow("test", None, None)
    queued, output = [], []
    workflow.dispatch_local = queued.append
    old, _ = workflow._begin_analysis()
    workflow._run_if_active(old, lambda: output.append("old"))
    new, _ = workflow._begin_analysis()
    workflow._run_if_active(new, lambda: output.append("new"))
    for callback in queued:
        callback()
    assert output == ["new"]


def test_chat_and_direct_streams_complete_independently():
    started, release = threading.Event(), threading.Event()
    events = []

    class AI:
        def analyze_images_stream(self, images, **kwargs):
            if images == [b"chat"]:
                started.set()
                assert release.wait(2)
                yield "答案：对话"
            else:
                yield "答案：搜题"

    class Publisher:
        def send_sync(self, event):
            events.append(event)

    workflow = AssistantWorkflow("test", None, AI(), Publisher())
    worker = threading.Thread(target=lambda: workflow.process_mobile_images(
        [b"chat"], is_chat=True, use_conversation=True, request_id="chat-1"))
    worker.start()
    try:
        assert started.wait(1)
        workflow.process_mobile_images([b"direct"], request_id="fullscreen-1")
    finally:
        release.set()
        worker.join(3)
    completed = {e["request_id"] for e in events if e["type"] == "answer.completed"}
    assert completed == {"chat-1", "fullscreen-1"}
    assert "对话" in workflow.mobile_conversation[-1]["content"]
