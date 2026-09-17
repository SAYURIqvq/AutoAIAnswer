from __future__ import annotations

import inspect
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QMainWindow, QWidget

from ai_screenshot_assistant.ui import macos_capture
from ai_screenshot_assistant.ui.macos_capture import (
    NSStatusWindowLevel,
    collect_main_window_ids,
    main_window_level,
    overlay_target_is_safe,
    overlay_window_level,
)
from ai_screenshot_assistant.ui.streaming_overlay import StreamingOverlay


ROOT = Path(__file__).resolve().parents[1]


def test_empty_overlay_window_is_not_safe() -> None:
    assert overlay_target_is_safe(0, {11}) is False
    assert overlay_target_is_safe(0, set()) is False


def test_main_console_window_is_not_a_safe_overlay_target() -> None:
    assert overlay_target_is_safe(11, {11, 22}) is False


def test_lyric_window_is_a_safe_overlay_target() -> None:
    assert overlay_target_is_safe(22, {11}) is True


def test_overlay_uses_floating_level_not_status_or_normal() -> None:
    assert overlay_window_level() == 3
    assert overlay_window_level() != NSStatusWindowLevel
    assert main_window_level() == 0
    assert overlay_window_level() != main_window_level()


def test_collect_main_window_ids_ignores_overlay_widget(qapp) -> None:
    main = QMainWindow()
    overlay = QWidget()
    lookup = {main: 100, overlay: 200}

    ids = collect_main_window_ids([main, overlay], lookup.get)

    assert ids == {100}
    assert overlay_target_is_safe(200, ids) is True
    assert overlay_target_is_safe(100, ids) is False
    main.deleteLater()
    overlay.deleteLater()


def test_main_window_source_is_not_always_on_top() -> None:
    source = (ROOT / "ai_screenshot_assistant" / "ui" / "main_window.py").read_text(encoding="utf-8")
    assert "WindowStaysOnTopHint" not in source


def test_macos_capture_never_sets_status_level_on_windows() -> None:
    source = (ROOT / "ai_screenshot_assistant" / "ui" / "macos_capture.py").read_text(encoding="utf-8")
    assert "overlay_window_level()" in source
    assert "setLevel:\", c_long(NSStatusWindowLevel)" not in source
    assert "拒绝修改主窗口" in source
    assert "overlay_target_is_safe" in source
    assert "setHidesOnDeactivate:\", c_ubyte(1)" not in source
    assert "orderWindow:relativeTo:" in source
    assert '"orderFrontRegardless"' not in source


def test_stream_started_does_not_show_or_raise_overlay() -> None:
    from ai_screenshot_assistant.ui.main_window import MainWindow

    source = inspect.getsource(MainWindow._on_stream_started)
    assert "start_stream" in source
    assert "self.overlay.show()" not in source
    assert "self.overlay.raise_()" not in source


def test_main_window_only_shows_overlay_from_visibility_toggle() -> None:
    source = (ROOT / "ai_screenshot_assistant" / "ui" / "main_window.py").read_text(encoding="utf-8")
    assert source.count("self.overlay.show()") == 1
    assert "def set_overlay_visible" in source
    assert "self.overlay.raise_()" not in source


def test_hidden_overlay_stream_does_not_front(qapp, monkeypatch) -> None:
    import ai_screenshot_assistant.ui.streaming_overlay as overlay_mod

    monkeypatch.setattr(overlay_mod, "_IS_MAC", True)
    pinned: list[object] = []
    monkeypatch.setattr(overlay_mod, "keep_overlay_fronted", pinned.append)
    monkeypatch.setattr(StreamingOverlay, "_apply_native_flags", lambda self: pinned.append("flags"))

    overlay = StreamingOverlay(QSettings())
    overlay.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    overlay.start_stream()
    overlay.append_delta("答案")
    overlay.complete_stream("完成")
    overlay.raise_()
    assert pinned == []
    assert overlay._keep_alive is False
    overlay.close()
    overlay.deleteLater()


def test_visible_overlay_stream_pins_without_qt_raise(qapp, monkeypatch) -> None:
    import ai_screenshot_assistant.ui.streaming_overlay as overlay_mod

    monkeypatch.setattr(overlay_mod, "_IS_MAC", True)
    monkeypatch.setattr(StreamingOverlay, "_apply_native_flags", lambda self: None)
    overlay = StreamingOverlay(QSettings())
    overlay.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    overlay.show()
    source = inspect.getsource(StreamingOverlay.raise_)
    assert "super().raise_()" not in source
    overlay.close()
    overlay.deleteLater()


def test_app_state_handler_pins_overlay_without_raising_app() -> None:
    source = inspect.getsource(StreamingOverlay._on_app_state_changed)
    assert "keep_overlay_fronted" in source
    assert "raise_" not in source
    assert "super().show()" not in source
    assert "_restore_if_needed" not in source


def test_overlay_keep_alive_tracks_user_show_and_hide(qapp, monkeypatch) -> None:
    monkeypatch.setattr(StreamingOverlay, "_apply_native_flags", lambda self: None)
    overlay = StreamingOverlay(QSettings())
    overlay.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)

    assert overlay._keep_alive is False
    overlay.show()
    assert overlay._keep_alive is True
    overlay.hide()
    assert overlay._keep_alive is False
    overlay.close()
    overlay.deleteLater()


def test_overlay_window_flags_are_tool_and_on_top(qapp, monkeypatch) -> None:
    monkeypatch.setattr(StreamingOverlay, "_apply_native_flags", lambda self: None)
    overlay = StreamingOverlay(QSettings())
    flags = overlay.windowFlags()
    assert flags & Qt.WindowType.WindowStaysOnTopHint
    assert flags & Qt.WindowType.Tool
    assert flags & Qt.WindowType.WindowDoesNotAcceptFocus
    assert flags & Qt.WindowType.FramelessWindowHint
    overlay.deleteLater()


def test_app_state_change_only_pins_overlay_when_user_wants_it(qapp, monkeypatch) -> None:
    import ai_screenshot_assistant.ui.streaming_overlay as overlay_mod

    monkeypatch.setattr(overlay_mod, "_IS_MAC", True)
    monkeypatch.setattr(StreamingOverlay, "_apply_native_flags", lambda self: None)
    pinned: list[object] = []
    monkeypatch.setattr(overlay_mod, "keep_overlay_fronted", pinned.append)

    overlay = StreamingOverlay(QSettings())
    overlay.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    overlay._on_app_state_changed(None)
    assert pinned == []

    overlay.show()
    pinned.clear()
    overlay._on_app_state_changed(None)
    assert pinned == [overlay]

    overlay.hide()
    pinned.clear()
    overlay._on_app_state_changed(None)
    assert pinned == []
    overlay.close()
    overlay.deleteLater()


def test_hidden_overlay_does_not_get_fronted_after_close(qapp, monkeypatch) -> None:
    import ai_screenshot_assistant.ui.streaming_overlay as overlay_mod

    monkeypatch.setattr(overlay_mod, "_IS_MAC", True)
    monkeypatch.setattr(StreamingOverlay, "_apply_native_flags", lambda self: None)
    pinned: list[object] = []
    monkeypatch.setattr(overlay_mod, "keep_overlay_fronted", pinned.append)

    overlay = StreamingOverlay(QSettings())
    overlay.show()
    overlay.close()
    pinned.clear()
    overlay._on_app_state_changed(None)
    assert pinned == []
    overlay.deleteLater()
