from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from ai_screenshot_assistant.backend.session_manager import manager as backend_manager


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def reset_backend_manager():
    backend_manager.sessions.clear()
    backend_manager.tokens.clear()
    yield
    backend_manager.sessions.clear()
    backend_manager.tokens.clear()
