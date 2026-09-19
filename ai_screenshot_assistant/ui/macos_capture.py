"""macOS capture-exclusion helpers via NSWindow.sharingType = .none."""

from __future__ import annotations

import ctypes
import ctypes.util
import sys
from ctypes import c_char_p, c_long, c_ubyte, c_ulong, c_void_p

NSWindowSharingNone = 0
NSWindowSharingReadOnly = 1
NSWindowSharingReadWrite = 2

NSWindowCollectionBehaviorCanJoinAllSpaces = 1 << 0
NSWindowCollectionBehaviorStationary = 1 << 4
NSWindowCollectionBehaviorIgnoresCycle = 1 << 6
NSWindowCollectionBehaviorFullScreenAuxiliary = 1 << 8
OVERLAY_COLLECTION_BEHAVIOR = (
    NSWindowCollectionBehaviorCanJoinAllSpaces
    | NSWindowCollectionBehaviorStationary
    | NSWindowCollectionBehaviorIgnoresCycle
    | NSWindowCollectionBehaviorFullScreenAuxiliary
)

NSNormalWindowLevel = 0
NSFloatingWindowLevel = 3
NSStatusWindowLevel = 25  # status/menu level; never apply this to the overlay or main console
NSWindowStyleMaskNonactivatingPanel = 1 << 7
CHROMA_KEY_RGB = (1, 2, 3)
OVERLAY_WINDOW_LEVEL = NSFloatingWindowLevel
MAIN_WINDOW_LEVEL = NSNormalWindowLevel


def overlay_target_is_safe(window_id: int, main_window_ids: set[int] | None = None) -> bool:
    """True only for a real overlay NSWindow that is not the QMainWindow."""
    if not window_id:
        return False
    return window_id not in set(main_window_ids or ())


def overlay_window_level() -> int:
    return OVERLAY_WINDOW_LEVEL


def main_window_level() -> int:
    return MAIN_WINDOW_LEVEL


def collect_main_window_ids(widgets, resolve_window) -> set[int]:
    from PySide6.QtWidgets import QMainWindow

    ids: set[int] = set()
    for widget in widgets:
        if isinstance(widget, QMainWindow):
            handle = int(resolve_window(widget) or 0)
            if handle:
                ids.add(handle)
    return ids


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


if sys.platform != "darwin":
    def apply_window_capture_exclusion(target: object, enabled: bool = True) -> tuple[bool, str]:
        return False, "仅 macOS 支持捕获排除"

    def apply_capture_exclusion(hwnd: int, enabled: bool = True) -> tuple[bool, str]:
        if not hwnd:
            return False, "窗口句柄尚未创建"
        return False, "仅 macOS 支持捕获排除"

    def is_excluded_from_capture(hwnd: int) -> bool:
        return False

    def set_click_through(hwnd: int, enabled: bool) -> None:
        return

    def keep_overlay_fronted(target: object) -> None:
        return

    def set_no_activate(hwnd: int, enabled: bool = True) -> None:
        return

    def set_color_key_opacity(
        hwnd: int,
        alpha: int,
        rgb: tuple[int, int, int] = CHROMA_KEY_RGB,
    ) -> None:
        return
else:
    _objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc") or "/usr/lib/libobjc.A.dylib")
    _objc.sel_registerName.argtypes = [c_char_p]
    _objc.sel_registerName.restype = c_void_p
    _objc.objc_getClass.argtypes = [c_char_p]
    _objc.objc_getClass.restype = c_void_p
    ctypes.cdll.LoadLibrary("/System/Library/Frameworks/AppKit.framework/AppKit")

    def _sel(name: str) -> int:
        return int(_objc.sel_registerName(name.encode("utf-8")))

    def _msg(obj: int, selector: str, *args, restype=c_void_p, argtypes=()):
        _objc.objc_msgSend.restype = restype
        _objc.objc_msgSend.argtypes = [c_void_p, c_void_p, *argtypes]
        return _objc.objc_msgSend(c_void_p(obj), c_void_p(_sel(selector)), *args)

    def _view_from_target(target: object) -> int:
        if target is None or target == 0:
            return 0
        if isinstance(target, int):
            return target
        return hwnd_from_widget(target)

    def _nswindow_from_view(view: int) -> int:
        if not view:
            return 0
        window = _msg(view, "window", restype=c_void_p)
        return int(window or 0)

    def _window_from_target(target: object) -> int:
        return _nswindow_from_view(_view_from_target(target))

    def _main_nswindows() -> set[int]:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            return set()
        return collect_main_window_ids(app.topLevelWidgets(), _window_from_target)

    def _is_main_nswindow(window: int) -> bool:
        return bool(window) and window in _main_nswindows()

    def _reset_main_windows(except_window: int = 0) -> None:
        for window in _main_nswindows():
            if except_window and window == except_window:
                continue
            _msg(window, "setLevel:", c_long(main_window_level()), restype=None, argtypes=(c_long,))
            # Keep the console a normal background window. hidesOnDeactivate=YES would
            # hide it when focus leaves, then unhide/pop it when the overlay is pinned.
            _msg(window, "setHidesOnDeactivate:", c_ubyte(0), restype=None, argtypes=(c_ubyte,))

    def _set_sharing_type(window: int, sharing_type: int) -> None:
        _msg(window, "setSharingType:", c_ulong(sharing_type), restype=None, argtypes=(c_ulong,))

    def _sharing_type(window: int) -> int:
        return int(_msg(window, "sharingType", restype=c_ulong) or 0)

    def _configure_overlay_window(window: int) -> bool:
        if not overlay_target_is_safe(window, _main_nswindows()):
            _reset_main_windows()
            return False
        _reset_main_windows(except_window=window)
        ns_color = int(_objc.objc_getClass(b"NSColor") or 0)
        if ns_color:
            clear = _msg(ns_color, "clearColor", restype=c_void_p)
            if clear:
                _msg(window, "setBackgroundColor:", c_void_p(clear), restype=None, argtypes=(c_void_p,))
        _msg(window, "setOpaque:", c_ubyte(0), restype=None, argtypes=(c_ubyte,))
        _msg(window, "setHasShadow:", c_ubyte(0), restype=None, argtypes=(c_ubyte,))
        _msg(
            window,
            "setCollectionBehavior:",
            c_ulong(OVERLAY_COLLECTION_BEHAVIOR),
            restype=None,
            argtypes=(c_ulong,),
        )
        style = int(_msg(window, "styleMask", restype=c_ulong) or 0)
        _msg(
            window,
            "setStyleMask:",
            c_ulong(style | NSWindowStyleMaskNonactivatingPanel),
            restype=None,
            argtypes=(c_ulong,),
        )
        ns_panel = int(_objc.objc_getClass(b"NSPanel") or 0)
        if ns_panel and _msg(window, "isKindOfClass:", c_void_p(ns_panel), restype=c_ubyte, argtypes=(c_void_p,)):
            _msg(window, "setFloatingPanel:", c_ubyte(1), restype=None, argtypes=(c_ubyte,))
            _msg(window, "setBecomesKeyOnlyIfNeeded:", c_ubyte(1), restype=None, argtypes=(c_ubyte,))
        _msg(window, "setHidesOnDeactivate:", c_ubyte(0), restype=None, argtypes=(c_ubyte,))
        _msg(window, "setLevel:", c_long(overlay_window_level()), restype=None, argtypes=(c_long,))
        return True

    def apply_capture_exclusion(target: object, enabled: bool = True) -> tuple[bool, str]:
        view = _view_from_target(target)
        if not view:
            return False, "窗口句柄尚未创建"
        window = _nswindow_from_view(view)
        if not window:
            return False, "尚未挂到 NSWindow"
        if not _configure_overlay_window(window):
            return False, "拒绝修改主窗口"
        sharing = NSWindowSharingNone if enabled else NSWindowSharingReadOnly
        _set_sharing_type(window, sharing)
        _set_sharing_type(window, sharing)
        current = _sharing_type(window)
        if enabled and current != NSWindowSharingNone:
            return False, f"sharingType 未生效 ({current})"
        return True, "已从捕获中排除" if enabled else "已允许被捕获"

    def apply_window_capture_exclusion(target: object, enabled: bool = True) -> tuple[bool, str]:
        """Change capture sharing only; do not give normal windows overlay styling."""
        window = _window_from_target(target)
        if not window:
            return False, "窗口尚未挂到 NSWindow"
        sharing = NSWindowSharingNone if enabled else NSWindowSharingReadOnly
        _set_sharing_type(window, sharing)
        current = _sharing_type(window)
        if current != sharing:
            return False, f"sharingType 未生效 ({current})"
        return True, "控制台已从捕获中排除" if enabled else "控制台可被捕获"

    def is_excluded_from_capture(target: object) -> bool:
        window = _window_from_target(target)
        if not window or _is_main_nswindow(window):
            return False
        return _sharing_type(window) == NSWindowSharingNone

    def keep_overlay_fronted(target: object) -> None:
        window = _window_from_target(target)
        if not _configure_overlay_window(window):
            return
        # Stack only the lyric window without activating the application.
        _msg(
            window,
            "orderWindow:relativeTo:",
            c_long(1),  # NSWindowAbove
            c_ulong(0),
            restype=None,
            argtypes=(c_long, c_ulong),
        )

    def set_click_through(target: object, enabled: bool) -> None:
        window = _window_from_target(target)
        if not window or _is_main_nswindow(window):
            return
        _msg(
            window,
            "setIgnoresMouseEvents:",
            c_ubyte(1 if enabled else 0),
            restype=None,
            argtypes=(c_ubyte,),
        )

    def set_no_activate(target: object, enabled: bool = True) -> None:
        window = _window_from_target(target)
        if not window or not enabled or _is_main_nswindow(window):
            _reset_main_windows()
            return
        _configure_overlay_window(window)

    def set_color_key_opacity(
        target: object,
        alpha: int,
        rgb: tuple[int, int, int] = CHROMA_KEY_RGB,
    ) -> None:
        window = _window_from_target(target)
        if not window or _is_main_nswindow(window):
            return
        _configure_overlay_window(window)
        _ = alpha
        _ = rgb
