from ai_screenshot_assistant.ui.macos_capture import (
    NSWindowSharingNone,
    apply_capture_exclusion,
    keep_overlay_fronted,
    overlay_window_level,
)
from ai_screenshot_assistant.ui.native_capture import apply_capture_exclusion as native_apply
from ai_screenshot_assistant.ui.native_capture import keep_overlay_fronted as native_keep_fronted


def test_empty_hwnd_is_rejected() -> None:
    ok, message = apply_capture_exclusion(0, True)
    assert ok is False
    assert "句柄" in message


def test_sharing_none_value() -> None:
    assert NSWindowSharingNone == 0


def test_native_dispatcher_rejects_empty_handle() -> None:
    ok, message = native_apply(0, True)
    assert ok is False
    assert "句柄" in message


def test_keep_overlay_fronted_is_exported() -> None:
    keep_overlay_fronted(0)
    native_keep_fronted(0)
    assert overlay_window_level() == 3


def test_empty_hwnd_is_rejected() -> None:
    ok, message = apply_capture_exclusion(0, True)
    assert ok is False
    assert "句柄" in message


def test_sharing_none_value() -> None:
    assert NSWindowSharingNone == 0


def test_native_dispatcher_rejects_empty_handle() -> None:
    ok, message = native_apply(0, True)
    assert ok is False
    assert "句柄" in message
