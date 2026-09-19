from __future__ import annotations

from collections.abc import Callable
import ctypes
import ctypes.util
import sys
import threading
import time


class MouseRoiListener:
    def __init__(
        self,
        on_long_left: Callable[[int, int], None],
        on_short_left: Callable[[int, int], None],
        on_long_right: Callable[[int, int], None] | None = None,
    ) -> None:
        self.on_long_left = on_long_left
        self.on_short_left = on_short_left
        self.on_long_right = on_long_right
        self._left_down_at: float | None = None
        self._left_down_position: tuple[int, int] | None = None
        self._right_down_at: float | None = None
        self._right_down_position: tuple[int, int] | None = None
        self.long_press_seconds = 2.0
        self._enabled = True
        self._state_lock = threading.Lock()
        self._mac_listener = None
        self._mac_callback = None

    @property
    def enabled(self) -> bool:
        with self._state_lock:
            return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        with self._state_lock:
            self._enabled = enabled
            self._left_down_at = None
            self._left_down_position = None
            self._right_down_at = None
            self._right_down_position = None

    def start(self) -> None:
        if sys.platform == "darwin":
            from AppKit import (
                NSEvent,
                NSEventMaskLeftMouseDown,
                NSEventMaskLeftMouseUp,
                NSEventMaskRightMouseDown,
                NSEventMaskRightMouseUp,
                NSEventTypeLeftMouseDown,
                NSEventTypeLeftMouseUp,
                NSEventTypeRightMouseDown,
                NSEventTypeRightMouseUp,
            )
            from Quartz import CGEventGetLocation

            def on_event(event: object) -> None:
                event_type = event.type()
                location = CGEventGetLocation(event.CGEvent())
                position = (int(location.x), int(location.y))
                if event_type == NSEventTypeLeftMouseDown:
                    self._handle_left_down(position)
                elif event_type == NSEventTypeLeftMouseUp:
                    self._handle_left_up()
                elif event_type == NSEventTypeRightMouseDown:
                    self._handle_right_down(position)
                elif event_type == NSEventTypeRightMouseUp:
                    self._handle_right_up()

            mask = (
                NSEventMaskLeftMouseDown
                | NSEventMaskLeftMouseUp
                | NSEventMaskRightMouseDown
                | NSEventMaskRightMouseUp
            )
            # Keep the callback alive for as long as AppKit owns the monitor.
            self._mac_callback = on_event
            self._mac_listener = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(mask, on_event)
            if self._mac_listener is None:
                raise RuntimeError("macOS global mouse monitor could not be created")
            return

        import mouse

        mouse.on_button(self._handle_left_down, buttons=("left",), types=("down",))
        mouse.on_button(self._handle_left_up, buttons=("left",), types=("up",))
        mouse.on_button(self._handle_right_down, buttons=("right",), types=("down",))
        mouse.on_button(self._handle_right_up, buttons=("right",), types=("up",))

    def stop(self) -> None:
        if sys.platform == "darwin":
            if self._mac_listener is not None:
                from AppKit import NSEvent

                NSEvent.removeMonitor_(self._mac_listener)
                self._mac_listener = None
                self._mac_callback = None
            return

        import mouse

        mouse.unhook_all()

    def _current_position(self, position: tuple[int, int] | None) -> tuple[int, int]:
        if isinstance(position, tuple) and len(position) == 2:
            return (int(position[0]), int(position[1]))
        if sys.platform == "darwin":
            return (0, 0)
        import mouse

        x, y = mouse.get_position()
        return (int(x), int(y))

    def _handle_left_down(self, position: tuple[int, int] | None = None) -> None:
        position = self._current_position(position)
        with self._state_lock:
            if not self._enabled:
                return
            self._left_down_at = time.monotonic()
            self._left_down_position = position

    def _handle_left_up(self) -> None:
        with self._state_lock:
            if not self._enabled:
                return
            started_at = self._left_down_at
            position = self._left_down_position
            self._left_down_at = None
            self._left_down_position = None
        if started_at is None or position is None:
            return
        if time.monotonic() - started_at >= self.long_press_seconds:
            if self.on_long_right is not None and self._is_control_held():
                self.on_long_right(*position)
            else:
                self.on_long_left(*position)
        else:
            self.on_short_left(*position)

    def _is_control_held(self) -> bool:
        if sys.platform != "darwin":
            return False
        library = ctypes.util.find_library("CoreGraphics")
        if not library:
            return False
        try:
            quartz = ctypes.cdll.LoadLibrary(library)
            quartz.CGEventSourceKeyState.argtypes = [ctypes.c_int, ctypes.c_ushort]
            quartz.CGEventSourceKeyState.restype = ctypes.c_bool
            control = 0x3B
            right_control = 0x3E
            session_state = 0
            return bool(
                quartz.CGEventSourceKeyState(session_state, control)
                or quartz.CGEventSourceKeyState(session_state, right_control)
            )
        except Exception:
            return False

    def _handle_right_down(self, position: tuple[int, int] | None = None) -> None:
        position = self._current_position(position)
        with self._state_lock:
            if not self._enabled:
                return
            self._right_down_at = time.monotonic()
            self._right_down_position = position

    def _handle_right_up(self) -> None:
        with self._state_lock:
            if not self._enabled:
                return
            started_at = self._right_down_at
            position = self._right_down_position
            self._right_down_at = None
            self._right_down_position = None
        if started_at is None or position is None or self.on_long_right is None:
            return
        if time.monotonic() - started_at >= self.long_press_seconds:
            self.on_long_right(*position)
