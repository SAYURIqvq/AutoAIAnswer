"""Platform capture-exclusion helpers for the desktop overlay."""

from __future__ import annotations

import sys

if sys.platform == "win32":
    from ai_screenshot_assistant.ui.win32_capture import (
        CHROMA_KEY_RGB,
        apply_capture_exclusion,
        hwnd_from_widget,
        is_excluded_from_capture,
        set_color_key_opacity,
        set_no_activate,
    )
elif sys.platform == "darwin":
    from ai_screenshot_assistant.ui.macos_capture import (
        CHROMA_KEY_RGB,
        apply_capture_exclusion,
        hwnd_from_widget,
        is_excluded_from_capture,
        set_color_key_opacity,
        set_no_activate,
    )
else:
    CHROMA_KEY_RGB = (1, 2, 3)

    def hwnd_from_widget(widget: object) -> int:
        return 0

    def apply_capture_exclusion(hwnd: int, enabled: bool = True) -> tuple[bool, str]:
        if not hwnd:
            return False, "窗口句柄尚未创建"
        return False, "当前平台不支持捕获排除"

    def is_excluded_from_capture(hwnd: int) -> bool:
        return False

    def set_no_activate(hwnd: int, enabled: bool = True) -> None:
        return

    def set_color_key_opacity(
        hwnd: int,
        alpha: int,
        rgb: tuple[int, int, int] = CHROMA_KEY_RGB,
    ) -> None:
        return
