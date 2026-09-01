from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Event:
    type: str
    session_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: str = field(default_factory=utc_now_iso)
    event_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {
            "type": self.type,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "timestamp": self.timestamp,
            "payload": self.payload,
        }
        if self.event_id is not None:
            data["event_id"] = self.event_id
        return data

