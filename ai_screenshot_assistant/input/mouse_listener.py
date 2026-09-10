from __future__ import annotations

from collections.abc import Callable
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
            from pynput import mouse as pynput_mouse

            def on_click(x: int, y: int, button: object, pressed: bool) -> None:
                position = (int(x), int(y))
                if button == pynput_mouse.Button.left:
                    if pressed:
                        self._handle_left_down(position)
                    else:
                        self._handle_left_up()
                    return
                if button == pynput_mouse.Button.right:
                    if pressed:
                        self._handle_right_down(position)
                    else:
                        self._handle_right_up()

            self._mac_listener = pynput_mouse.Listener(on_click=on_click)
            self._mac_listener.start()
            return

        import mouse

        mouse.on_button(self._handle_left_down, buttons=("left",), types=("down",))
        mouse.on_button(self._handle_left_up, buttons=("left",), types=("up",))
        mouse.on_button(self._handle_right_down, buttons=("right",), types=("down",))
        mouse.on_button(self._handle_right_up, buttons=("right",), types=("up",))

    def stop(self) -> None:
        if self._mac_listener is not None:
            self._mac_listener.stop()
            self._mac_listener = None
            return

        import mouse

        mouse.unhook_all()

    def _current_position(self, position: tuple[int, int] | None) -> tuple[int, int]:
        if isinstance(position, tuple) and len(position) == 2:
            return (int(position[0]), int(position[1]))
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
            self.on_long_left(*position)
        else:
            self.on_short_left(*position)

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
