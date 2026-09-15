"""Windows capture-exclusion helpers for a top-level HWND."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

WDA_NONE = 0x00000000
WDA_MONITOR = 0x00000001
WDA_EXCLUDEFROMCAPTURE = 0x00000011

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_FRAMECHANGED = 0x0020

LWA_COLORKEY = 0x00000001
LWA_ALPHA = 0x00000002
CHROMA_KEY_RGB = (1, 2, 3)

if sys.platform != "win32":
    def hwnd_from_widget(widget: object) -> int:
        return 0

    def apply_capture_exclusion(hwnd: int, enabled: bool = True) -> tuple[bool, str]:
        return False, "仅 Windows 支持捕获排除"

    def is_excluded_from_capture(hwnd: int) -> bool:
        return False

    def set_click_through(hwnd: int, enabled: bool) -> None:
        return

    def set_no_activate(hwnd: int, enabled: bool = True) -> None:
        return

    def set_color_key_opacity(hwnd: int, alpha: int, rgb: tuple[int, int, int] = CHROMA_KEY_RGB) -> None:
        return
else:
    user32 = ctypes.WinDLL("user32", use_last_error=True)

    user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.SetWindowDisplayAffinity.restype = wintypes.BOOL
    user32.GetWindowDisplayAffinity.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetWindowDisplayAffinity.restype = wintypes.BOOL
    user32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.SetLayeredWindowAttributes.argtypes = [
        wintypes.HWND,
        wintypes.COLORREF,
        wintypes.BYTE,
        wintypes.DWORD,
    ]
    user32.SetLayeredWindowAttributes.restype = wintypes.BOOL

    _LONG_PTR = ctypes.c_int64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        _get_window_long = user32.GetWindowLongPtrW
        _set_window_long = user32.SetWindowLongPtrW
    else:
        _get_window_long = user32.GetWindowLongW
        _set_window_long = user32.SetWindowLongW
    _get_window_long.argtypes = [wintypes.HWND, ctypes.c_int]
    _get_window_long.restype = _LONG_PTR
    _set_window_long.argtypes = [wintypes.HWND, ctypes.c_int, _LONG_PTR]
    _set_window_long.restype = _LONG_PTR

    def hwnd_from_widget(widget: object) -> int:
        handle = getattr(widget, "windowHandle", lambda: None)()
        if handle is None:
            create = getattr(widget, "createWinId", None)
            if create is not None:
                create()
            handle = getattr(widget, "windowHandle", lambda: None)()
        if handle is not None:
            return int(handle.winId())
        win_id = getattr(widget, "winId", None)
        if win_id is None:
            return 0
        return int(win_id())

    def apply_capture_exclusion(hwnd: int, enabled: bool = True) -> tuple[bool, str]:
        if not hwnd:
            return False, "窗口句柄尚未创建"
        affinity = WDA_EXCLUDEFROMCAPTURE if enabled else WDA_NONE
        ok = bool(user32.SetWindowDisplayAffinity(wintypes.HWND(hwnd), affinity))
        if not ok:
            err = ctypes.get_last_error()
            return False, f"SetWindowDisplayAffinity 失败 (Win32 {err})"
        current = wintypes.DWORD()
        user32.GetWindowDisplayAffinity(wintypes.HWND(hwnd), ctypes.byref(current))
        if enabled and current.value != WDA_EXCLUDEFROMCAPTURE:
            if current.value == WDA_MONITOR:
                return False, "系统回退成黑块模式，需要 Windows 10 2004 或更高"
            return False, f"affinity 未生效 (0x{current.value:X})"
        return True, "已从捕获中排除" if enabled else "已允许被捕获"

    def is_excluded_from_capture(hwnd: int) -> bool:
        if not hwnd:
            return False
        current = wintypes.DWORD()
        ok = user32.GetWindowDisplayAffinity(wintypes.HWND(hwnd), ctypes.byref(current))
        return bool(ok) and current.value == WDA_EXCLUDEFROMCAPTURE

    def _set_exstyle_flag(hwnd: int, flag: int, enabled: bool) -> None:
        if not hwnd:
            return
        style = int(_get_window_long(wintypes.HWND(hwnd), GWL_EXSTYLE))
        style = (style | flag) if enabled else (style & ~flag)
        _set_window_long(wintypes.HWND(hwnd), GWL_EXSTYLE, style)
        user32.SetWindowPos(
            wintypes.HWND(hwnd),
            wintypes.HWND(0),
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED,
        )

    def set_click_through(hwnd: int, enabled: bool) -> None:
        if not hwnd:
            return
        style = int(_get_window_long(wintypes.HWND(hwnd), GWL_EXSTYLE))
        if enabled:
            style |= WS_EX_TRANSPARENT | WS_EX_LAYERED
        else:
            style &= ~WS_EX_TRANSPARENT
        _set_window_long(wintypes.HWND(hwnd), GWL_EXSTYLE, style)
        user32.SetWindowPos(
            wintypes.HWND(hwnd),
            wintypes.HWND(0),
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED,
        )

    def set_no_activate(hwnd: int, enabled: bool = True) -> None:
        _set_exstyle_flag(hwnd, WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW, enabled)

    def set_color_key_opacity(
        hwnd: int,
        alpha: int,
        rgb: tuple[int, int, int] = CHROMA_KEY_RGB,
    ) -> None:
        if not hwnd:
            return
        _set_exstyle_flag(hwnd, WS_EX_LAYERED, True)
        colorref = rgb[0] | (rgb[1] << 8) | (rgb[2] << 16)
        user32.SetLayeredWindowAttributes(
            wintypes.HWND(hwnd),
            colorref,
            max(15, min(255, alpha)),
            LWA_COLORKEY | LWA_ALPHA,
        )
