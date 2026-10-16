from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import WebSocket

MAX_SESSION_EVENTS = 80
MAX_STORED_TEXT_CHARS = 120000
SKIP_PERSIST_EVENT_TYPES = frozenset({"answer.delta"})


@dataclass
class Session:
    session_id: str
    pair_token: str
    created_at: datetime
    expire_at: datetime
    ttl_minutes: int = 60
    desktop: WebSocket | None = None
    desktop_commands: WebSocket | None = None
    mobiles: set[WebSocket] = field(default_factory=set)
    auto_read: bool = False
    current_model: dict[str, Any] | None = None
    active_streams: dict[str, dict[str, Any]] = field(default_factory=dict)
    pending_screenshots: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    next_event_id: int = 1

    @property
    def paired(self) -> bool:
        return bool(self.mobiles)


def persistable_event(event: dict[str, Any]) -> dict[str, Any] | None:
    event_type = str(event.get("type") or "")
    if event_type in SKIP_PERSIST_EVENT_TYPES:
        return None
    stored = dict(event)
    payload = stored.get("payload")
    if not isinstance(payload, dict):
        return stored
    payload = dict(payload)
    if event_type == "screenshot.captured":
        payload.pop("image", None)
        payload["image_omitted"] = True
    result = payload.get("result")
    if isinstance(result, dict):
        result = dict(result)
        text = str(result.get("text") or "")
        if len(text) > MAX_STORED_TEXT_CHARS:
            result["text"] = text[:MAX_STORED_TEXT_CHARS]
        payload["result"] = result
    stored["payload"] = payload
    return stored


class SessionManager:
    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}
        self.tokens: dict[str, str] = {}

    def create_session(self, ttl_minutes: int = 60, pair_token: str | None = None) -> Session:
        session_id = uuid4().hex
        pair_token = pair_token or secrets.token_urlsafe(18)
        previous_session_id = self.tokens.get(pair_token)
        if previous_session_id:
            self.sessions.pop(previous_session_id, None)
        now = datetime.now(timezone.utc)
        session = Session(
            session_id=session_id,
            pair_token=pair_token,
            created_at=now,
            expire_at=now + timedelta(minutes=ttl_minutes),
            ttl_minutes=ttl_minutes,
        )
        self.sessions[session_id] = session
        self.tokens[pair_token] = session_id
        return session

    def get(self, session_id: str) -> Session | None:
        session = self.sessions.get(session_id)
        if session is None:
            return None
        now = datetime.now(timezone.utc)
        if session.expire_at < now and session.desktop is None and session.desktop_commands is None:
            return None
        session.expire_at = now + timedelta(minutes=session.ttl_minutes)
        return session

    def get_by_token(self, token: str) -> Session | None:
        session_id = self.tokens.get(token)
        return self.get(session_id) if session_id else None

    def append_event(self, session: Session, event: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(event)
        enriched["event_id"] = session.next_event_id
        session.next_event_id += 1
        event_type = enriched.get("type")
        request_id = str(enriched.get("request_id", ""))
        payload = enriched.get("payload") or {}
        if event_type == "model.changed":
            session.current_model = enriched
        if event_type == "answer.started":
            lane = "chat" if payload.get("chat") else "direct"
            session.active_streams[lane] = {
                "type": "answer.snapshot", "request_id": request_id,
                "payload": {"chat": lane == "chat", "text": ""},
            }
        elif event_type == "answer.delta":
            for snapshot in session.active_streams.values():
                if snapshot["request_id"] == request_id:
                    snapshot["payload"]["text"] = (
                        snapshot["payload"]["text"] + str(payload.get("delta", ""))
                    )[-MAX_STORED_TEXT_CHARS:]
        elif event_type in {"answer.completed", "answer.error"}:
            session.active_streams = {
                lane: snapshot for lane, snapshot in session.active_streams.items()
                if snapshot["request_id"] != request_id
            }
        elif event_type == "conversation.cleared":
            session.active_streams.pop("chat", None)
        elif event_type == "mobile.action" and payload.get("command") == "command.clear_direct":
            session.active_streams.pop("direct", None)
        stored = persistable_event(enriched)
        if stored is not None:
            session.events.append(stored)
            if len(session.events) > MAX_SESSION_EVENTS:
                session.events = session.events[-MAX_SESSION_EVENTS:]
        return enriched

    def since(self, session: Session, last_event_id: int) -> list[dict[str, Any]]:
        return [event for event in session.events if int(event.get("event_id", 0)) > last_event_id]

    def clear_events(self, session: Session) -> None:
        session.events.clear()
        session.active_streams.clear()


manager = SessionManager()
