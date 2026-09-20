import os
import sys

import pytest
from PySide6.QtWidgets import QMainWindow

from ai_screenshot_assistant.ui.native_capture import apply_window_capture_exclusion
from ai_screenshot_assistant.ui.win32_capture import WDA_EXCLUDEFROMCAPTURE, apply_capture_exclusion


def test_empty_hwnd_is_rejected() -> None:
    ok, message = apply_capture_exclusion(0, True)
    assert ok is False
    assert "句柄" in message


def test_exclude_flag_value() -> None:
    assert WDA_EXCLUDEFROMCAPTURE == 0x00000011


@pytest.mark.skipif(sys.platform != "win32", reason="requires a real Windows HWND")
@pytest.mark.skipif(os.getenv("GITHUB_ACTIONS") == "true", reason="GitHub-hosted Windows has no interactive desktop")
def test_native_console_exclusion_accepts_qt_window(qapp) -> None:
    window = QMainWindow()
    window.show()
    qapp.processEvents()
    try:
        ok, message = apply_window_capture_exclusion(window, True)
        assert ok, message
    finally:
        apply_window_capture_exclusion(window, False)
        window.close()
