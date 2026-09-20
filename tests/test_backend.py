import asyncio

import pytest
from fastapi.testclient import TestClient

from ai_screenshot_assistant.backend.app import _handle_mobile_message, app
from ai_screenshot_assistant.backend.session_manager import MAX_SESSION_EVENTS, MAX_STORED_TEXT_CHARS, SessionManager


class _Recorder:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, event: dict) -> None:
        self.messages.append(event)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _forward_mobile_command(client: TestClient, session: dict, message: str) -> dict:
    session_id = session["session_id"]
    with client.websocket_connect(f"/ws/desktop-commands/{session_id}") as desktop_commands:
        with client.websocket_connect(f"/ws/mobile/{session_id}") as mobile:
            mobile.receive_json()
            mobile.send_text(message)
            return desktop_commands.receive_json()


def test_create_session_and_mobile_page(client: TestClient) -> None:
    response = client.post("/sessions")
    assert response.status_code == 200
    session = response.json()

    page = client.get(session["pair_url"])
    assert page.status_code == 200
    assert session["session_id"] in page.text


def test_create_session_reuses_requested_pair_token(client: TestClient) -> None:
    token = "stable_pair_token_1234567890"

    first = client.post("/sessions", json={"pair_token": token}).json()
    second = client.post("/sessions", json={"pair_token": token}).json()

    assert first["pair_url"] == second["pair_url"] == f"/pair?t={token}"
    assert first["session_id"] == second["session_id"]
    assert client.get(first["mobile_url"]).status_code == 200
    assert client.get(second["pair_url"]).status_code == 200


def test_create_session_rejects_weak_requested_pair_token(client: TestClient) -> None:
    session = client.post("/sessions", json={"pair_token": "too-short"}).json()

    assert session["pair_token"] != "too-short"
    assert len(session["pair_token"]) >= 24


def test_pair_page_waits_when_desktop_session_is_missing(client: TestClient) -> None:
    token = "waiting_pair_token_abcdef123456"

    waiting = client.get(f"/pair?t={token}")
    lookup = client.get(f"/session?t={token}")

    assert waiting.status_code == 200
    assert 'window.SESSION_ID = ""' in waiting.text
    assert token in waiting.text
    assert lookup.json() == {"ok": False}

    created = client.post("/sessions", json={"pair_token": token}).json()
    ready = client.get(f"/session?t={token}")

    assert ready.json()["ok"] is True
    assert ready.json()["session_id"] == created["session_id"]
    assert created["session_id"] in client.get(f"/pair?t={token}").text


def test_pair_cookie_reconnects_without_new_scan(client: TestClient) -> None:
    token = "cookie_pair_token_abcdef123456"
    client.post("/sessions", json={"pair_token": token})
    client.get(f"/pair?t={token}")

    home = client.get("/", follow_redirects=False)
    stale_mobile = client.get("/mobile?session_id=dead-session", follow_redirects=False)

    assert home.status_code == 302
    assert home.headers["location"] == f"/pair?t={token}"
    assert stale_mobile.status_code == 302
    assert stale_mobile.headers["location"] == f"/pair?t={token}"


def test_idle_expired_session_is_dropped() -> None:
    from datetime import datetime, timedelta, timezone

    manager = SessionManager()
    session = manager.create_session(ttl_minutes=1)
    session.expire_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    assert manager.get(session.session_id) is None


def test_connected_session_does_not_expire() -> None:
    from datetime import datetime, timedelta, timezone

    manager = SessionManager()
    session = manager.create_session(ttl_minutes=1)
    session.expire_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    session.desktop = object()  # type: ignore[assignment]

    assert manager.get(session.session_id) is session
    assert session.expire_at > datetime.now(timezone.utc)


def test_desktop_events_reach_mobile_websocket(client: TestClient) -> None:
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


def test_handle_mobile_message_forwards_when_desktop_commands_connected() -> None:
    session = SessionManager().create_session()
    recorder = _Recorder()
    session.desktop_commands = recorder  # type: ignore[assignment]

    asyncio.run(_handle_mobile_message(session, '{"type":"command.fullscreen"}'))

    assert recorder.messages[0]["type"] == "command.fullscreen"
    assert recorder.messages[0]["payload"] == {"source": "mobile"}


def test_mobile_fullscreen_command_reaches_desktop_command_socket(client: TestClient) -> None:
    session = client.post("/sessions").json()
    command = _forward_mobile_command(client, session, '{"type":"command.fullscreen"}')

    assert command["type"] == "command.fullscreen"
    assert command["payload"] == {"source": "mobile"}


def test_mobile_fullscreen_command_forwards_question_payload(client: TestClient) -> None:
    session = client.post("/sessions").json()
    command = _forward_mobile_command(
        client,
        session,
        '{"type":"command.fullscreen","payload":{"text":"解释第 2 题","conversation":true}}',
    )

    assert command["type"] == "command.fullscreen"
    assert command["payload"] == {
        "source": "mobile",
        "text": "解释第 2 题",
        "conversation": True,
    }


def test_mobile_fullscreen_command_forwards_chat_payload(client: TestClient) -> None:
    session = client.post("/sessions").json()
    command = _forward_mobile_command(
        client,
        session,
        '{"type":"command.fullscreen","payload":{"text":"看一下这个空怎么填","conversation":true,"chat":true}}',
    )

    assert command["type"] == "command.fullscreen"
    assert command["payload"] == {
        "source": "mobile",
        "text": "看一下这个空怎么填",
        "conversation": True,
        "chat": True,
    }


def test_mobile_fullscreen_command_forwards_client_request_id(client: TestClient) -> None:
    session = client.post("/sessions").json()
    command = _forward_mobile_command(
        client,
        session,
        '{"type":"command.fullscreen","payload":{"client_request_id":"fullscreen-123"}}',
    )

    assert command["type"] == "command.fullscreen"
    assert command["payload"] == {
        "source": "mobile",
        "client_request_id": "fullscreen-123",
    }


def test_mobile_capture_fullscreen_command_reaches_desktop_command_socket(client: TestClient) -> None:
    session = client.post("/sessions").json()
    command = _forward_mobile_command(client, session, '{"type":"command.capture_fullscreen"}')

    assert command["type"] == "command.capture_fullscreen"
    assert command["payload"] == {"source": "mobile"}


def test_mobile_command_without_desktop_reports_error(client: TestClient) -> None:
    session = client.post("/sessions").json()
    session_id = session["session_id"]

    with client.websocket_connect(f"/ws/mobile/{session_id}") as mobile:
        mobile.receive_json()
        mobile.send_text(
            '{"type":"command.fullscreen","payload":{"client_request_id":"fullscreen-1","chat":true}}'
        )
        event = mobile.receive_json()

    assert event["type"] == "answer.error"
    assert event["request_id"] == "fullscreen-1"
    assert "命令通道" in event["payload"]["message"]


def test_session_lookup_reports_desktop_ready_flag(client: TestClient) -> None:
    token = "desktop_ready_token_abcdef123456"
    created = client.post("/sessions", json={"pair_token": token}).json()
    lookup = client.get(f"/session?t={token}").json()

    assert lookup["ok"] is True
    assert lookup["session_id"] == created["session_id"]
    assert lookup["desktop_ready"] is False

    with client.websocket_connect(f"/ws/desktop-commands/{created['session_id']}"):
        assert client.get(f"/session?t={token}").json()["desktop_ready"] is True


def test_mobile_submit_screenshots_forwards_images_without_text(client: TestClient) -> None:
    session = client.post("/sessions").json()
    command = _forward_mobile_command(
        client,
        session,
        '{"type":"command.submit_screenshots","payload":{"images":["img1","img2"],"conversation":true,"chat":true}}',
    )

    assert command["type"] == "command.submit_screenshots"
    assert command["payload"] == {
        "source": "mobile",
        "conversation": True,
        "chat": True,
        "images": ["img1", "img2"],
    }


def test_mobile_submit_screenshots_forwards_client_request_id(client: TestClient) -> None:
    session = client.post("/sessions").json()
    command = _forward_mobile_command(
        client,
        session,
        '{"type":"command.submit_screenshots","payload":{"text":"继续","client_request_id":"chat-456"}}',
    )

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


def test_mobile_clear_conversation_command_reaches_desktop(client: TestClient) -> None:
    session = client.post("/sessions").json()
    command = _forward_mobile_command(client, session, '{"type":"command.clear_conversation"}')

    assert command["type"] == "command.clear_conversation"
    assert command["payload"] == {"source": "mobile"}


def test_mobile_set_model_tier_command_forwards_tier(client: TestClient) -> None:
    session = client.post("/sessions").json()
    command = _forward_mobile_command(
        client,
        session,
        '{"type":"command.set_model_tier","payload":{"tier":"openrouter-qwen-32b","route":"openrouter-qwen-32b"}}',
    )

    assert command["type"] == "command.set_model_tier"
    assert command["payload"]["source"] == "mobile"
    assert command["payload"]["tier"] == "openrouter-qwen-32b"
    assert command["payload"]["route"] == "openrouter-qwen-32b"


def test_completed_answer_text_is_truncated_in_session_storage() -> None:
    manager = SessionManager()
    session = manager.create_session()

    live = manager.append_event(
        session,
        {"type": "answer.completed", "payload": {"result": {"text": "答" * (MAX_STORED_TEXT_CHARS + 50)}}},
    )

    assert len(live["payload"]["result"]["text"]) == MAX_STORED_TEXT_CHARS + 50
    assert len(session.events[0]["payload"]["result"]["text"]) == MAX_STORED_TEXT_CHARS
