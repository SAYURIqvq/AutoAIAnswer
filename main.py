from __future__ import annotations

import os
import sys

# PyInstaller's windowed mode sets these streams to None. Some dependencies,
# including Uvicorn's logging setup, expect file-like streams to exist.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from PySide6.QtWidgets import QApplication

from ai_screenshot_assistant.backend.embedded import EmbeddedBackend
from ai_screenshot_assistant.config import settings
from ai_screenshot_assistant.ui.main_window import MainWindow


def main() -> int:
    backend = None
    backend_url = settings.backend_url
    if settings.embedded_backend or settings.backend_url == "auto":
        backend = EmbeddedBackend(settings.backend_port)
        backend_url = backend.start()

    app = QApplication(sys.argv)
    window = MainWindow(backend_url=backend_url)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
