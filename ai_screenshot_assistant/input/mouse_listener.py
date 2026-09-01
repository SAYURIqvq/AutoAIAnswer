from __future__ import annotations

from collections.abc import Callable
import threading
import time


class MouseRoiListener:
    def __init__(
        self,
        on_long_left: Callable[[int, int], None],
        on_short_left: Callable[[int, int], None],
    ) -> None:
        self.on_long_left = on_long_left
        self.on_short_left = on_short_left
        self._left_down_at: float | None = None
        self._left_down_position: tuple[int, int] | None = None
        self.long_press_seconds = 2.0
        self._enabled = True
        self._state_lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        with self._state_lock:
            return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        with self._state_lock:
            self._enabled = enabled
            self._left_down_at = None
            self._left_down_position = None

    def start(self) -> None:
        import mouse

        mouse.on_button(self._handle_left_down, buttons=("left",), types=("down",))
        mouse.on_button(self._handle_left_up, buttons=("left",), types=("up",))

    def stop(self) -> None:
        import mouse

        mouse.unhook_all()

    def _handle_left_down(self) -> None:
        import mouse

        x, y = mouse.get_position()
        with self._state_lock:
            if not self._enabled:
                return
            self._left_down_at = time.monotonic()
            self._left_down_position = (int(x), int(y))

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
