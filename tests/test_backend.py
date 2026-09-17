from fastapi.testclient import TestClient

from ai_screenshot_assistant.backend.app import app
from ai_screenshot_assistant.backend.session_manager import MAX_SESSION_EVENTS, MAX_STORED_TEXT_CHARS, SessionManager


def test_create_session_and_mobile_page() -> None:
    client = TestClient(app)

    response = client.post("/sessions")
    assert response.status_code == 200
    session = response.json()

    page = client.get(session["pair_url"])
    assert page.status_code == 200
    assert session["session_id"] in page.text


def test_desktop_events_reach_mobile_websocket() -> None:
    client = TestClient(app)
    session = client.post("/sessions").json()
    session_id = session["session_id"]

    with client.websocket_connect(f"/ws/mobile/{session_id}") as mobile:
        mobile.receive_json()
        with client.websocket_connect(f"/ws/desktop/{session_id}") as desktop:
            mobile.receive_json()
            desktop.send_json(
                {
                    "type": "answer.delta",
                    "session_id": session_id,
                    "request_id": "r1",
                    "timestamp": "now",
                    "payload": {"delta": "B"},
                }
            )
            received = mobile.receive_json()

    assert received["type"] == "answer.delta"
    assert received["payload"]["delta"] == "B"
    assert received["event_id"] == 1


def test_mobile_fullscreen_command_reaches_desktop_command_socket() -> None:
    client = TestClient(app)
    session = client.post("/sessions").json()
    session_id = session["session_id"]

    with client.websocket_connect(f"/ws/desktop-commands/{session_id}") as desktop_commands:
        with client.websocket_connect(f"/ws/mobile/{session_id}") as mobile:
            mobile.receive_json()
            mobile.send_text('{"type":"command.fullscreen"}')
            command = desktop_commands.receive_json()

    assert command["type"] == "command.fullscreen"
    assert command["payload"] == {"source": "mobile"}


def test_mobile_fullscreen_command_forwards_question_payload() -> None:
    client = TestClient(app)
    session = client.post("/sessions").json()
    session_id = session["session_id"]

    with client.websocket_connect(f"/ws/desktop-commands/{session_id}") as desktop_commands:
        with client.websocket_connect(f"/ws/mobile/{session_id}") as mobile:
            mobile.receive_json()
            mobile.send_text(
                '{"type":"command.fullscreen","payload":{"text":"解释第 2 题","conversation":true}}'
            )
            command = desktop_commands.receive_json()

    assert command["type"] == "command.fullscreen"
    assert command["payload"] == {
        "source": "mobile",
        "text": "解释第 2 题",
        "conversation": True,
    }


def test_mobile_fullscreen_command_forwards_chat_payload() -> None:
    client = TestClient(app)
    session = client.post("/sessions").json()
    session_id = session["session_id"]

    with client.websocket_connect(f"/ws/desktop-commands/{session_id}") as desktop_commands:
        with client.websocket_connect(f"/ws/mobile/{session_id}") as mobile:
            mobile.receive_json()
            mobile.send_text(
                '{"type":"command.fullscreen","payload":{"text":"看一下这个空怎么填","conversation":true,"chat":true}}'
            )
            command = desktop_commands.receive_json()

    assert command["type"] == "command.fullscreen"
    assert command["payload"] == {
        "source": "mobile",
        "text": "看一下这个空怎么填",
        "conversation": True,
        "chat": True,
    }


def test_mobile_fullscreen_command_forwards_client_request_id() -> None:
    client = TestClient(app)
    session = client.post("/sessions").json()
    session_id = session["session_id"]

    with client.websocket_connect(f"/ws/desktop-commands/{session_id}") as desktop_commands:
        with client.websocket_connect(f"/ws/mobile/{session_id}") as mobile:
            mobile.receive_json()
            mobile.send_text(
                '{"type":"command.fullscreen","payload":{"client_request_id":"fullscreen-123"}}'
            )
            command = desktop_commands.receive_json()

    assert command["type"] == "command.fullscreen"
    assert command["payload"] == {
        "source": "mobile",
        "client_request_id": "fullscreen-123",
    }


def test_mobile_capture_fullscreen_command_reaches_desktop_command_socket() -> None:
    client = TestClient(app)
    session = client.post("/sessions").json()
    session_id = session["session_id"]

    with client.websocket_connect(f"/ws/desktop-commands/{session_id}") as desktop_commands:
        with client.websocket_connect(f"/ws/mobile/{session_id}") as mobile:
            mobile.receive_json()
            mobile.send_text('{"type":"command.capture_fullscreen"}')
            command = desktop_commands.receive_json()

    assert command["type"] == "command.capture_fullscreen"
    assert command["payload"] == {"source": "mobile"}


def test_mobile_submit_screenshots_forwards_images_without_text() -> None:
    client = TestClient(app)
    session = client.post("/sessions").json()
    session_id = session["session_id"]

    with client.websocket_connect(f"/ws/desktop-commands/{session_id}") as desktop_commands:
        with client.websocket_connect(f"/ws/mobile/{session_id}") as mobile:
            mobile.receive_json()
            mobile.send_text(
                '{"type":"command.submit_screenshots","payload":{"images":["img1","img2"],"conversation":true,"chat":true}}'
            )
            command = desktop_commands.receive_json()

    assert command["type"] == "command.submit_screenshots"
    assert command["payload"] == {
        "source": "mobile",
        "conversation": True,
        "chat": True,
        "images": ["img1", "img2"],
    }


def test_mobile_submit_screenshots_forwards_client_request_id() -> None:
    client = TestClient(app)
    session = client.post("/sessions").json()
    session_id = session["session_id"]

    with client.websocket_connect(f"/ws/desktop-commands/{session_id}") as desktop_commands:
        with client.websocket_connect(f"/ws/mobile/{session_id}") as mobile:
            mobile.receive_json()
            mobile.send_text(
                '{"type":"command.submit_screenshots","payload":{"text":"继续","client_request_id":"chat-456"}}'
            )
            command = desktop_commands.receive_json()

    assert command["type"] == "command.submit_screenshots"
    assert command["payload"] == {
        "source": "mobile",
        "text": "继续",
        "client_request_id": "chat-456",
    }


def test_session_events_are_bounded() -> None:
    manager = SessionManager()
    session = manager.create_session()

    for index in range(MAX_SESSION_EVENTS + 25):
        manager.append_event(session, {"type": "selection.status", "payload": {"state": str(index)}})

    assert len(session.events) == MAX_SESSION_EVENTS
    assert session.events[0]["event_id"] == 26
    assert session.events[-1]["event_id"] == MAX_SESSION_EVENTS + 25


def test_answer_deltas_are_not_persisted_in_session_history() -> None:
    manager = SessionManager()
    session = manager.create_session()

    live = manager.append_event(session, {"type": "answer.delta", "payload": {"delta": "A" * 5000}})

    assert live["event_id"] == 1
    assert live["payload"]["delta"].startswith("A")
    assert session.events == []


def test_screenshot_images_are_stripped_before_session_storage() -> None:
    manager = SessionManager()
    session = manager.create_session()

    live = manager.append_event(
        session,
        {"type": "screenshot.captured", "payload": {"image": "data:image/jpeg;base64,abc", "size": 12}},
    )

    assert live["payload"]["image"].startswith("data:image")
    assert session.events[0]["payload"]["image_omitted"] is True
    assert "image" not in session.events[0]["payload"]


def test_clear_events_releases_session_history() -> None:
    manager = SessionManager()
    session = manager.create_session()
    manager.append_event(session, {"type": "answer.completed", "payload": {"result": {"text": "答案"}}})

    manager.clear_events(session)

    assert session.events == []
    assert session.next_event_id == 2


def test_mobile_clear_conversation_command_reaches_desktop() -> None:
    client = TestClient(app)
    session = client.post("/sessions").json()
    session_id = session["session_id"]

    with client.websocket_connect(f"/ws/desktop-commands/{session_id}") as desktop_commands:
        with client.websocket_connect(f"/ws/mobile/{session_id}") as mobile:
            mobile.receive_json()
            mobile.send_text('{"type":"command.clear_conversation"}')
            command = desktop_commands.receive_json()

    assert command["type"] == "command.clear_conversation"
    assert command["payload"] == {"source": "mobile"}


def test_mobile_set_model_tier_command_forwards_tier() -> None:
    client = TestClient(app)
    session = client.post("/sessions").json()
    session_id = session["session_id"]

    with client.websocket_connect(f"/ws/desktop-commands/{session_id}") as desktop_commands:
        with client.websocket_connect(f"/ws/mobile/{session_id}") as mobile:
            mobile.receive_json()
            mobile.send_text('{"type":"command.set_model_tier","payload":{"tier":"medium"}}')
            command = desktop_commands.receive_json()

    assert command["type"] == "command.set_model_tier"
    assert command["payload"] == {"source": "mobile", "tier": "medium"}


def test_completed_answer_text_is_truncated_in_session_storage() -> None:
    manager = SessionManager()
    session = manager.create_session()

    live = manager.append_event(
        session,
        {"type": "answer.completed", "payload": {"result": {"text": "答" * (MAX_STORED_TEXT_CHARS + 50)}}},
    )

    assert len(live["payload"]["result"]["text"]) == MAX_STORED_TEXT_CHARS + 50
    assert len(session.events[0]["payload"]["result"]["text"]) == MAX_STORED_TEXT_CHARS
