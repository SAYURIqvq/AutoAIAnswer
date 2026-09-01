from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import WebSocket


@dataclass
class Session:
    session_id: str
    pair_token: str
    created_at: datetime
    expire_at: datetime
    desktop: WebSocket | None = None
    mobile: WebSocket | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    next_event_id: int = 1

    @property
    def paired(self) -> bool:
        return self.mobile is not None


class SessionManager:
    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}
        self.tokens: dict[str, str] = {}

    def create_session(self, ttl_minutes: int = 60) -> Session:
        session_id = uuid4().hex
        pair_token = secrets.token_urlsafe(18)
        now = datetime.now(timezone.utc)
        session = Session(
            session_id=session_id,
            pair_token=pair_token,
            created_at=now,
            expire_at=now + timedelta(minutes=ttl_minutes),
        )
        self.sessions[session_id] = session
        self.tokens[pair_token] = session_id
        return session

    def get(self, session_id: str) -> Session | None:
        session = self.sessions.get(session_id)
        if session is None or session.expire_at < datetime.now(timezone.utc):
            return None
        return session

    def get_by_token(self, token: str) -> Session | None:
        session_id = self.tokens.get(token)
        return self.get(session_id) if session_id else None

    def append_event(self, session: Session, event: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(event)
        enriched["event_id"] = session.next_event_id
        session.next_event_id += 1
        session.events.append(enriched)
        return enriched

    def since(self, session: Session, last_event_id: int) -> list[dict[str, Any]]:
        return [event for event in session.events if int(event.get("event_id", 0)) > last_event_id]


manager = SessionManager()

