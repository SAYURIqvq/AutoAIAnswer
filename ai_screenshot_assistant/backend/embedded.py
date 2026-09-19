from __future__ import annotations

import threading
import time

import uvicorn

from ai_screenshot_assistant.backend.app import app
from ai_screenshot_assistant.utils.network import get_lan_ip


class EmbeddedBackend:
    def __init__(self, preferred_port: int) -> None:
        # Keep the pairing address stable. A second instance must not silently
        # move the service to 8001, 8002, and so on.
        self.port = preferred_port
        self.lan_ip = get_lan_ip()
        self.url = f"http://{self.lan_ip}:{self.port}"
        self.local_url = f"http://127.0.0.1:{self.port}"
        self._server = uvicorn.Server(
            uvicorn.Config(
                app,
                host="0.0.0.0",
                port=self.port,
                log_level="warning",
                use_colors=False,
                ws_max_size=64 * 1024 * 1024,
            )
        )
        self._thread = threading.Thread(target=self._server.run, daemon=True)

    def start(self) -> str:
        self._thread.start()
        deadline = time.monotonic() + 10.0
        while not self._server.started and self._thread.is_alive():
            if time.monotonic() >= deadline:
                raise TimeoutError("Embedded backend did not start within 10 seconds")
            time.sleep(0.05)
        if not self._server.started:
            raise RuntimeError("Embedded backend stopped before it was ready")
        return self.url

    def stop(self) -> None:
        self._server.should_exit = True
        if self._thread.is_alive():
            self._thread.join(timeout=5)
