from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from ai_screenshot_assistant.backend.session_manager import manager
from ai_screenshot_assistant.core.messages import utc_now_iso


STATIC_DIR = Path(__file__).resolve().parents[1] / "web" / "static"

app = FastAPI(title="AI Screenshot Assistant Backend")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/sessions")
async def create_session() -> dict[str, str]:
    session = manager.create_session()
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
            await _send_mobile(session, saved)
    except WebSocketDisconnect:
        if session.desktop is websocket:
            session.desktop = None
        await _send_mobile(session, _system_event(session_id, "device.disconnected", {"device": "desktop"}))


@app.websocket("/ws/mobile/{session_id}")
async def mobile_ws(websocket: WebSocket, session_id: str, last_event_id: int = 0) -> None:
    session = manager.get(session_id)
    if session is None:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    session.mobile = websocket
    for event in manager.since(session, last_event_id):
        await websocket.send_json(event)
    await websocket.send_json(_system_event(session_id, "device.connected", {"device": "mobile"}))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if session.mobile is websocket:
            session.mobile = None


async def _send_mobile(session: Any, event: dict[str, Any]) -> None:
    if session.mobile is not None:
        await session.mobile.send_json(event)


def _system_event(session_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": event_type,
        "session_id": session_id,
        "request_id": "system",
        "timestamp": utc_now_iso(),
        "payload": payload,
    }

