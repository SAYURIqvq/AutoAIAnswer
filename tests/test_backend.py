from fastapi.testclient import TestClient

from ai_screenshot_assistant.backend.app import app


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
