from __future__ import annotations

import asyncio
import json
import queue
import threading
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any

import websockets


@dataclass
class _PendingEvent:
    event: dict[str, Any]
    future: Future[None]


class DesktopWebSocketPublisher:
    """Publishes ordered events over one WebSocket owned by one event loop."""

    def __init__(self, backend_url: str, session_id: str) -> None:
        ws_base = backend_url.rstrip("/").replace("https://", "wss://").replace("http://", "ws://")
        self.url = f"{ws_base}/ws/desktop/{session_id}"
        self._queue: queue.Queue[_PendingEvent | None] = queue.Queue()
        self._thread = threading.Thread(target=self._thread_main, daemon=True, name="mobile-publisher")
        self._closed = False
        self._thread.start()

    def _thread_main(self) -> None:
        asyncio.run(self._run())

    async def _run(self) -> None:
        websocket: Any = None
        while True:
            pending = await asyncio.to_thread(self._queue.get)
            if pending is None:
                if websocket is not None:
                    await websocket.close()
                return
            try:
                if websocket is None:
                    websocket = await websockets.connect(self.url, proxy=None)
                await websocket.send(json.dumps(pending.event, ensure_ascii=False))
                pending.future.set_result(None)
            except Exception as exc:
                if websocket is not None:
                    try:
                        await websocket.close()
                    except Exception:
                        pass
                websocket = None
                pending.future.set_exception(exc)

    def send_sync(self, event: dict[str, Any]) -> None:
        if self._closed:
            raise RuntimeError("Mobile publisher is closed")
        future: Future[None] = Future()
        self._queue.put(_PendingEvent(event=event, future=future))
        future.result(timeout=15)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._queue.put(None)
        self._thread.join(timeout=3)
