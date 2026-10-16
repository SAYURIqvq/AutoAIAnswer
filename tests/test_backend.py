from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from ai_screenshot_assistant.backend.app import app
from ai_screenshot_assistant.backend.session_manager import MAX_SESSION_EVENTS, MAX_STORED_TEXT_CHARS, SessionManager


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def receive_mobile_handshake(mobile):
    assert mobile.receive_json()["type"] == "screenshot.buffer"
    assert mobile.receive_json()["type"] == "voice.mode"
    assert mobile.receive_json()["type"] == "device.connected"


def test_create_session_and_mobile_page(client) -> None:

    response = client.post("/sessions")
    assert response.status_code == 200
    session = response.json()

    page = client.get(session["pair_url"])
    assert page.status_code == 200
    assert session["session_id"] in page.text


def test_mobile_static_assets_are_served_with_expected_content_types(client) -> None:

    css = client.get("/static/style.css?v=0.2.54")
    js = client.get("/static/app.js?v=0.2.54")

    assert css.status_code == 200
    assert css.headers["content-type"].startswith("text/css")
    assert b"--background" in css.content
    assert js.status_code == 200
    assert js.headers["content-type"].split(";", 1)[0] in {"application/javascript", "text/javascript"}
    assert b"function connect" in js.content


def test_create_session_reuses_requested_pair_token(client) -> None:
    token = "stable_pair_token_1234567890"

    first = client.post("/sessions", json={"pair_token": token}).json()
    second = client.post("/sessions", json={"pair_token": token}).json()

    assert first["pair_url"] == second["pair_url"] == f"/pair?t={token}"
    assert first["session_id"] != second["session_id"]
    assert client.get(first["mobile_url"]).status_code == 404
    assert client.get(second["pair_url"]).status_code == 200


def test_create_session_rejects_weak_requested_pair_token(client) -> None:

    session = client.post("/sessions", json={"pair_token": "too-short"}).json()

    assert session["pair_token"] != "too-short"
    assert len(session["pair_token"]) >= 24


def test_active_desktop_keeps_stable_pair_session_alive() -> None:
    local_manager = SessionManager()
    session = local_manager.create_session(ttl_minutes=1, pair_token="stable_pair_token_1234567890")
    session.desktop = object()
    session.expire_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    assert local_manager.get_by_token(session.pair_token) is session
    assert session.expire_at > datetime.now(timezone.utc)


def test_desktop_events_reach_mobile_websocket(client) -> None:
    session = client.post("/sessions").json()
    session_id = session["session_id"]

    with client.websocket_connect(f"/ws/mobile/{session_id}") as mobile:
        receive_mobile_handshake(mobile)
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


def test_mobile_fullscreen_command_reaches_desktop_command_socket(client) -> None:
    session = client.post("/sessions").json()
    session_id = session["session_id"]

    with client.websocket_connect(f"/ws/desktop-commands/{session_id}") as desktop_commands:
        with client.websocket_connect(f"/ws/mobile/{session_id}") as mobile:
            receive_mobile_handshake(mobile)
            mobile.send_text('{"type":"command.fullscreen"}')
            command = desktop_commands.receive_json()

    assert command["type"] == "command.fullscreen"
    assert command["payload"] == {"source": "mobile"}


def test_mobile_fullscreen_command_forwards_question_payload(client) -> None:
    session = client.post("/sessions").json()
    session_id = session["session_id"]

    with client.websocket_connect(f"/ws/desktop-commands/{session_id}") as desktop_commands:
        with client.websocket_connect(f"/ws/mobile/{session_id}") as mobile:
            receive_mobile_handshake(mobile)
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


def test_mobile_fullscreen_command_forwards_chat_payload(client) -> None:
    session = client.post("/sessions").json()
    session_id = session["session_id"]

    with client.websocket_connect(f"/ws/desktop-commands/{session_id}") as desktop_commands:
        with client.websocket_connect(f"/ws/mobile/{session_id}") as mobile:
            receive_mobile_handshake(mobile)
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


def test_mobile_fullscreen_command_forwards_client_request_id(client) -> None:
    session = client.post("/sessions").json()
    session_id = session["session_id"]

    with client.websocket_connect(f"/ws/desktop-commands/{session_id}") as desktop_commands:
        with client.websocket_connect(f"/ws/mobile/{session_id}") as mobile:
            receive_mobile_handshake(mobile)
            mobile.send_text(
                '{"type":"command.fullscreen","payload":{"client_request_id":"fullscreen-123"}}'
            )
            command = desktop_commands.receive_json()

    assert command["type"] == "command.fullscreen"
    assert command["payload"] == {
        "source": "mobile",
        "client_request_id": "fullscreen-123",
    }


def test_mobile_capture_fullscreen_command_reaches_desktop_command_socket(client) -> None:
    session = client.post("/sessions").json()
    session_id = session["session_id"]

    with client.websocket_connect(f"/ws/desktop-commands/{session_id}") as desktop_commands:
        with client.websocket_connect(f"/ws/mobile/{session_id}") as mobile:
            receive_mobile_handshake(mobile)
            mobile.send_text('{"type":"command.capture_fullscreen"}')
            command = desktop_commands.receive_json()

    assert command["type"] == "command.capture_fullscreen"
    assert command["payload"] == {"source": "mobile"}


def test_mobile_submit_screenshots_forwards_images_without_text(client) -> None:
    session = client.post("/sessions").json()
    session_id = session["session_id"]

    with client.websocket_connect(f"/ws/desktop-commands/{session_id}") as desktop_commands:
        with client.websocket_connect(f"/ws/mobile/{session_id}") as mobile:
            receive_mobile_handshake(mobile)
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


def test_mobile_submit_screenshots_forwards_client_request_id(client) -> None:
    session = client.post("/sessions").json()
    session_id = session["session_id"]

    with client.websocket_connect(f"/ws/desktop-commands/{session_id}") as desktop_commands:
        with client.websocket_connect(f"/ws/mobile/{session_id}") as mobile:
            receive_mobile_handshake(mobile)
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


def test_mobile_clear_conversation_command_reaches_desktop(client) -> None:
    session = client.post("/sessions").json()
    session_id = session["session_id"]

    with client.websocket_connect(f"/ws/desktop-commands/{session_id}") as desktop_commands:
        with client.websocket_connect(f"/ws/mobile/{session_id}") as mobile:
            receive_mobile_handshake(mobile)
            mobile.send_text('{"type":"command.clear_conversation"}')
            command = desktop_commands.receive_json()

    assert command["type"] == "command.clear_conversation"
    assert command["payload"] == {"source": "mobile"}


def test_mobile_set_model_tier_command_forwards_tier(client) -> None:
    session = client.post("/sessions").json()
    session_id = session["session_id"]

    with client.websocket_connect(f"/ws/desktop-commands/{session_id}") as desktop_commands:
        with client.websocket_connect(f"/ws/mobile/{session_id}") as mobile:
            receive_mobile_handshake(mobile)
            mobile.send_text('{"type":"command.set_model_tier","payload":{"tier":"openrouter-qwen-32b"}}')
            command = desktop_commands.receive_json()

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


def test_two_phones_share_commands_stream_voice_and_disconnect(client):
    sid = client.post('/sessions').json()['session_id']
    with client.websocket_connect(f'/ws/desktop-commands/{sid}') as commands:
        with client.websocket_connect(f'/ws/desktop/{sid}') as desktop:
            with client.websocket_connect(f'/ws/mobile/{sid}') as a:
                receive_mobile_handshake(a)
                with client.websocket_connect(f'/ws/mobile/{sid}') as b:
                    receive_mobile_handshake(b)
                    for command in ('command.fullscreen', 'command.capture_fullscreen', 'command.submit_screenshots', 'command.clear_direct'):
                        a.send_json({'type': command, 'payload': {'client_request_id': 'fullscreen-1', 'text': '题目'}})
                        action = a.receive_json()
                        assert b.receive_json() == action
                        assert action['type'] == 'mobile.action'
                        assert action['payload']['command'] == command
                        assert commands.receive_json()['type'] == command
                    a.send_json({'type': 'command.set_auto_read', 'payload': {'enabled': True}})
                    mode = a.receive_json()
                    assert mode['payload']['enabled'] is True
                    assert b.receive_json() == mode
                    assert commands.receive_json()['type'] == 'command.set_auto_read'
                    for kind, payload in (
                        ('answer.started', {}), ('answer.delta', {'delta': '答案 A'}),
                        ('answer.completed', {'result': {'text': '答案 A'}}),
                        ('model.changed', {'route': 'qwen-122b'}), ('conversation.cleared', {}),
                    ):
                        desktop.send_json({'type': kind, 'request_id': 'fullscreen-2', 'payload': payload})
                        received = a.receive_json()
                        assert b.receive_json() == received
                        assert received['type'] == kind
                desktop.send_json({'type': 'answer.delta', 'payload': {'delta': 'still connected'}})
                assert a.receive_json()['payload']['delta'] == 'still connected'


def test_joining_phone_restores_live_stream_and_screenshot_buffer(client):
    sid = client.post('/sessions').json()['session_id']
    with client.websocket_connect(f'/ws/desktop/{sid}') as desktop:
        with client.websocket_connect(f'/ws/mobile/{sid}') as first:
            receive_mobile_handshake(first)
            events = [
                {'type': 'mobile.action', 'request_id': 'chat-1', 'payload': {'command': 'command.submit_screenshots'}},
                {'type': 'answer.started', 'request_id': 'chat-1', 'payload': {'chat': True}},
                {'type': 'answer.delta', 'request_id': 'chat-1', 'payload': {'delta': '半段答案'}},
                {'type': 'screenshot.captured', 'payload': {'image': 'data:image/png;base64,abc', 'add_to_buffer': True}},
            ]
            for event in events:
                desktop.send_json(event)
                last = first.receive_json()['event_id']
            with client.websocket_connect(f'/ws/mobile/{sid}?last_event_id={last}') as second:
                snapshot = second.receive_json()
                assert snapshot['type'] == 'answer.snapshot'
                assert snapshot['payload'] == {'chat': True, 'text': '半段答案'}
                images = second.receive_json()
                assert images['type'] == 'screenshot.buffer'
                assert images['payload']['screenshots'][0]['image'].startswith('data:image')
                assert second.receive_json()['type'] == 'voice.mode'
                assert second.receive_json()['type'] == 'device.connected'


def test_completed_stream_snapshot_is_removed_and_model_survives_event_limit():
    manager = SessionManager()
    session = manager.create_session()
    manager.append_event(session, {'type': 'model.changed', 'payload': {'route': 'qwen-27b'}})
    manager.append_event(session, {'type': 'answer.started', 'request_id': 'r', 'payload': {}})
    manager.append_event(session, {'type': 'answer.delta', 'request_id': 'r', 'payload': {'delta': 'hello'}})
    assert session.active_streams['direct']['payload']['text'] == 'hello'
    manager.append_event(session, {'type': 'answer.completed', 'request_id': 'r', 'payload': {}})
    assert not session.active_streams
    for _ in range(MAX_SESSION_EVENTS + 1):
        manager.append_event(session, {'type': 'selection.status'})
    assert session.current_model['payload']['route'] == 'qwen-27b'
