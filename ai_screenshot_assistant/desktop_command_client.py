from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Callable
from typing import Any

import websockets


class DesktopCommandClient:
    def __init__(self, backend_url: str, session_id: str, on_command: Callable[[dict[str, Any]], None]) -> None:
        ws_base = backend_url.rstrip("/").replace("https://", "wss://").replace("http://", "ws://")
        self.url = f"{ws_base}/ws/desktop-commands/{session_id}"
        self.on_command = on_command
        self._closed = False
        self._thread = threading.Thread(target=self._thread_main, daemon=True, name="desktop-command-listener")
        self._thread.start()

    def _thread_main(self) -> None:
        asyncio.run(self._run())

    async def _run(self) -> None:
        while not self._closed:
            try:
                async with websockets.connect(self.url, proxy=None) as websocket:
                    async for message in websocket:
                        try:
                            data = json.loads(message)
                        except json.JSONDecodeError:
                            continue
                        self.on_command(data)
            except Exception:
                if not self._closed:
                    await asyncio.sleep(1)

    def close(self) -> None:
        self._closed = True
        self._thread.join(timeout=3)
