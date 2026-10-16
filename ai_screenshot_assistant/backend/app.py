from __future__ import annotations

from pathlib import Path
import json
import re
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from ai_screenshot_assistant.backend.session_manager import manager
from ai_screenshot_assistant.core.messages import utc_now_iso


STATIC_DIR = Path(__file__).resolve().parents[1] / "web" / "static"

app = FastAPI(title="AI Screenshot Assistant Backend")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
PAIR_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{24,128}$")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/sessions")
async def create_session(payload: dict[str, Any] | None = Body(default=None)) -> dict[str, str]:
    requested_token = str((payload or {}).get("pair_token") or "")
    pair_token = requested_token if PAIR_TOKEN_RE.fullmatch(requested_token) else None
    session = manager.create_session(pair_token=pair_token)
    return {
        "session_id": session.session_id,
        "pair_token": session.pair_token,
        "pair_url": f"/pair?t={session.pair_token}",
        "mobile_url": f"/mobile?session_id={session.session_id}",
    }


@app.get("/pair")
async def pair(t: str = Query(...)) -> HTMLResponse:
    session = manager.get_by_token(t)
    if session is None:
        raise HTTPException(status_code=404, detail="Pair token is invalid or expired")
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html.replace("__SESSION_ID__", session.session_id))


@app.get("/mobile")
async def mobile(session_id: str) -> HTMLResponse:
    session = manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session is invalid or expired")
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html.replace("__SESSION_ID__", session.session_id))


@app.get("/")
async def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.websocket("/ws/desktop/{session_id}")
async def desktop_ws(websocket: WebSocket, session_id: str) -> None:
    session = manager.get(session_id)
    if session is None:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    session.desktop = websocket
    await _send_mobile(session, _system_event(session_id, "device.connected", {"device": "desktop"}))
    try:
        while True:
            event = await websocket.receive_json()
            saved = manager.append_event(session, event)
            if event.get("type") == "screenshot.captured" and isinstance(event.get("payload"), dict):
                if event["payload"].get("add_to_buffer") is True and event["payload"].get("image"):
                    session.pending_screenshots.append(saved)
                    session.pending_screenshots = session.pending_screenshots[-5:]
            await _send_mobile(session, saved)
    except WebSocketDisconnect:
        if session.desktop is websocket:
            session.desktop = None
        await _send_mobile(session, _system_event(session_id, "device.disconnected", {"device": "desktop"}))


@app.websocket("/ws/desktop-commands/{session_id}")
async def desktop_commands_ws(websocket: WebSocket, session_id: str) -> None:
    session = manager.get(session_id)
    if session is None:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    session.desktop_commands = websocket
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if session.desktop_commands is websocket:
            session.desktop_commands = None


@app.websocket("/ws/mobile/{session_id}")
async def mobile_ws(websocket: WebSocket, session_id: str, last_event_id: int = 0) -> None:
    session = manager.get(session_id)
    if session is None:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    session.mobiles.add(websocket)
    for event in manager.since(session, last_event_id):
        await websocket.send_json(event)
    if last_event_id <= 0:
        for event in session.pending_screenshots:
            await websocket.send_json(event)
    await websocket.send_json(_system_event(session_id, "voice.mode", {"enabled": session.auto_read}))
    await websocket.send_json(_system_event(session_id, "device.connected", {"device": "mobile"}))
    try:
        while True:
            message = await websocket.receive_text()
            await _handle_mobile_message(session, message)
    except WebSocketDisconnect:
        session.mobiles.discard(websocket)


async def _send_mobile(session: Any, event: dict[str, Any]) -> None:
    for mobile in tuple(session.mobiles):
        try:
            await mobile.send_json(event)
        except (RuntimeError, WebSocketDisconnect):
            session.mobiles.discard(mobile)


async def _handle_mobile_message(session: Any, message: str) -> None:
    try:
        data = json.loads(message)
    except json.JSONDecodeError:
        return
    command_type = data.get("type")
    if command_type == "command.set_auto_read":
        payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
        session.auto_read = payload.get("enabled") is True
        await _send_mobile(session, manager.append_event(session, _system_event(
            session.session_id, "voice.mode", {"enabled": session.auto_read}
        )))
        return
    if command_type == "command.clear_conversation":
        session.pending_screenshots.clear()
    if command_type not in {
        "command.fullscreen",
        "command.capture_fullscreen",
        "command.submit_screenshots",
        "command.clear_conversation",
        "command.clear_direct",
        "command.get_prompt",
        "command.save_prompt",
        "command.set_model_tier",
    }:
        return
    if session.desktop_commands is not None:
        payload = _mobile_command_payload(data)
        if command_type in {"command.fullscreen", "command.submit_screenshots", "command.capture_fullscreen", "command.clear_direct"}:
            await _send_mobile(session, manager.append_event(session, _system_event(
                session.session_id, "mobile.action", {
                    "command": command_type,
                    "text": payload.get("text", ""),
                    "image_count": len(payload.get("images", [])),
                }, request_id=str(payload.get("client_request_id") or "system")
            )))
            if command_type == "command.submit_screenshots":
                session.pending_screenshots.clear()
        await session.desktop_commands.send_json(
            _system_event(session.session_id, command_type, payload)
        )


def _mobile_command_payload(data: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {"source": "mobile"}
    source_payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    if data.get("type") == "command.save_prompt":
        if isinstance(source_payload.get("text"), str):
            payload["text"] = source_payload["text"]
        return payload
    raw_text = source_payload.get("text") or data.get("text")
    text = str(raw_text or "").strip()
    if text:
        payload["text"] = text[:4000]
    if bool(source_payload.get("conversation") or data.get("conversation")):
        payload["conversation"] = True
    if bool(source_payload.get("chat") or data.get("chat")):
        payload["chat"] = True
    raw_client_request_id = source_payload.get("client_request_id") or data.get("client_request_id")
    client_request_id = str(raw_client_request_id or "").strip()
    if client_request_id:
        payload["client_request_id"] = client_request_id[:120]
    raw_images = source_payload.get("images") or data.get("images")
    if isinstance(raw_images, list):
        payload["images"] = [str(image) for image in raw_images[:5] if isinstance(image, str)]
    raw_tier = source_payload.get("route") or source_payload.get("tier") or data.get("route") or data.get("tier")
    tier = str(raw_tier or "").strip()
    if tier:
        payload["tier"] = tier[:64]
        payload["route"] = tier[:64]
    return payload


def _system_event(session_id: str, event_type: str, payload: dict[str, Any], request_id: str = "system") -> dict[str, Any]:
    return {
        "type": event_type,
        "session_id": session_id,
        "request_id": request_id,
        "timestamp": utc_now_iso(),
        "payload": payload,
    }
