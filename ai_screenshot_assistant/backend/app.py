from __future__ import annotations

from pathlib import Path
import json
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from ai_screenshot_assistant.backend.session_manager import manager, valid_pair_token
from ai_screenshot_assistant.core.messages import utc_now_iso


STATIC_DIR = Path(__file__).resolve().parents[1] / "web" / "static"

app = FastAPI(title="AI Screenshot Assistant Backend")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
PAIR_COOKIE = "qqmusic_pair"


def _render_mobile(session_id: str, pair_token: str) -> HTMLResponse:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    html = html.replace("__SESSION_ID__", session_id or "")
    html = html.replace("__PAIR_TOKEN__", pair_token or "")
    response = HTMLResponse(html)
    if valid_pair_token(pair_token):
        response.set_cookie(
            PAIR_COOKIE,
            pair_token,
            max_age=60 * 60 * 24 * 30,
            httponly=False,
            samesite="lax",
            path="/",
        )
    return response


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/sessions")
async def create_session(payload: dict[str, Any] | None = Body(default=None)) -> dict[str, str]:
    pair_token = valid_pair_token((payload or {}).get("pair_token"))
    session = manager.create_session(pair_token=pair_token)
    return {
        "session_id": session.session_id,
        "pair_token": session.pair_token,
        "pair_url": f"/pair?t={session.pair_token}",
        "mobile_url": f"/mobile?session_id={session.session_id}",
    }


@app.get("/session")
async def session_lookup(t: str = Query("")) -> dict[str, Any]:
    token = valid_pair_token(t)
    if token is None:
        return {"ok": False}
    session = manager.get_by_token(token)
    if session is None:
        return {"ok": False}
    return {
        "ok": True,
        "session_id": session.session_id,
        "pair_token": session.pair_token,
        "desktop_ready": session.desktop_commands is not None,
    }


@app.get("/pair")
async def pair(request: Request, t: str = Query("")):
    if t:
        token = valid_pair_token(t)
        if token is None:
            raise HTTPException(status_code=404, detail="Pair token is invalid or expired")
    else:
        token = valid_pair_token(request.cookies.get(PAIR_COOKIE))
        if token:
            return RedirectResponse(f"/pair?t={token}", status_code=302)
        raise HTTPException(status_code=404, detail="Pair token is invalid or expired")
    session = manager.get_by_token(token)
    return _render_mobile(session.session_id if session else "", token)


@app.get("/mobile")
async def mobile(request: Request, session_id: str) -> HTMLResponse:
    session = manager.get(session_id)
    if session is None:
        cookie_token = valid_pair_token(request.cookies.get(PAIR_COOKIE))
        if cookie_token:
            return RedirectResponse(f"/pair?t={cookie_token}", status_code=302)
        raise HTTPException(status_code=404, detail="Session is invalid or expired")
    return _render_mobile(session.session_id, session.pair_token)


@app.get("/")
async def root(request: Request):
    token = valid_pair_token(request.cookies.get(PAIR_COOKIE)) or valid_pair_token(request.query_params.get("t"))
    if token:
        return RedirectResponse(f"/pair?t={token}", status_code=302)
    return FileResponse(STATIC_DIR / "index.html")


@app.websocket("/ws/desktop/{session_id}")
async def desktop_ws(websocket: WebSocket, session_id: str) -> None:
    session = manager.get(session_id)
    if session is None:
        await websocket.close(code=4404)
        return
    session.desktop = websocket
    await websocket.accept()
    await _send_mobile(session, _system_event(session_id, "device.connected", {"device": "desktop"}))
    try:
        while True:
            event = await websocket.receive_json()
            saved = manager.append_event(session, event)
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
    session.desktop_commands = websocket
    await websocket.accept()
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
    session.mobile = websocket
    await websocket.accept()
    for event in manager.since(session, last_event_id):
        await websocket.send_json(event)
    await websocket.send_json(_system_event(session_id, "device.connected", {"device": "mobile"}))
    try:
        while True:
            message = await websocket.receive_text()
            await _handle_mobile_message(session, message)
    except WebSocketDisconnect:
        if session.mobile is websocket:
            session.mobile = None


async def _send_mobile(session: Any, event: dict[str, Any]) -> None:
    if session.mobile is not None:
        await session.mobile.send_json(event)


async def _handle_mobile_message(session: Any, message: str) -> None:
    try:
        data = json.loads(message)
    except json.JSONDecodeError:
        return
    command_type = data.get("type")
    if command_type not in {
        "command.fullscreen",
        "command.capture_fullscreen",
        "command.submit_screenshots",
        "command.clear_conversation",
        "command.set_model_tier",
    }:
        return
    payload = _mobile_command_payload(data)
    if session.desktop_commands is not None:
        await session.desktop_commands.send_json(
            _system_event(session.session_id, command_type, payload)
        )
        return
    await _send_mobile(
        session,
        _system_event(
            session.session_id,
            "answer.error",
            {
                "message": "电脑端命令通道未连接。请只保留一个 QQMusic 窗口，然后刷新手机页。",
            },
            request_id=str(payload.get("client_request_id") or "system"),
        ),
    )


def _mobile_command_payload(data: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {"source": "mobile"}
    source_payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
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


def _system_event(
    session_id: str,
    event_type: str,
    payload: dict[str, Any],
    request_id: str = "system",
) -> dict[str, Any]:
    return {
        "type": event_type,
        "session_id": session_id,
        "request_id": request_id,
        "timestamp": utc_now_iso(),
        "payload": payload,
    }
