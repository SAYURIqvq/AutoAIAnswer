from ai_screenshot_assistant.ui.win32_capture import WDA_EXCLUDEFROMCAPTURE, apply_capture_exclusion


def test_empty_hwnd_is_rejected() -> None:
    ok, message = apply_capture_exclusion(0, True)
    assert ok is False
    assert "句柄" in message


def test_exclude_flag_value() -> None:
    assert WDA_EXCLUDEFROMCAPTURE == 0x00000011
