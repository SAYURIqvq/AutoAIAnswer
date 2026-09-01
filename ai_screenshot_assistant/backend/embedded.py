from __future__ import annotations

import threading
import time

import uvicorn

from ai_screenshot_assistant.backend.app import app
from ai_screenshot_assistant.utils.network import first_available_port, get_lan_ip


class EmbeddedBackend:
    def __init__(self, preferred_port: int) -> None:
        self.port = first_available_port(preferred_port)
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
