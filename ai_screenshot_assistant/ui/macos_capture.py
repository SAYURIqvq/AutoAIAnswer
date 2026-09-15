"""macOS capture-exclusion helpers via NSWindow.sharingType = .none."""

from __future__ import annotations

import ctypes
import ctypes.util
import sys
from ctypes import c_char_p, c_ulong, c_void_p

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

NSFloatingWindowLevel = 3
CHROMA_KEY_RGB = (1, 2, 3)


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
    def apply_capture_exclusion(hwnd: int, enabled: bool = True) -> tuple[bool, str]:
        if not hwnd:
            return False, "窗口句柄尚未创建"
        return False, "仅 macOS 支持捕获排除"

    def is_excluded_from_capture(hwnd: int) -> bool:
        return False

    def set_click_through(hwnd: int, enabled: bool) -> None:
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

    def _nswindow_from_view(view: int) -> int:
        if not view:
            return 0
        window = _msg(view, "window", restype=c_void_p)
        return int(window or 0)

    def _set_sharing_type(window: int, sharing_type: int) -> None:
        _msg(
            window,
            "setSharingType:",
            c_ulong(sharing_type),
            restype=None,
            argtypes=(c_ulong,),
        )

    def _sharing_type(window: int) -> int:
        return int(_msg(window, "sharingType", restype=c_ulong) or 0)

    def _prepare_overlay_window(window: int) -> None:
        ns_color = int(_objc.objc_getClass(b"NSColor") or 0)
        if ns_color:
            clear = _msg(ns_color, "clearColor", restype=c_void_p)
            if clear:
                _msg(
                    window,
                    "setBackgroundColor:",
                    c_void_p(clear),
                    restype=None,
                    argtypes=(c_void_p,),
                )
        _msg(window, "setOpaque:", ctypes.c_ubyte(0), restype=None, argtypes=(ctypes.c_ubyte,))
        _msg(window, "setHasShadow:", ctypes.c_ubyte(0), restype=None, argtypes=(ctypes.c_ubyte,))
        _msg(
            window,
            "setCollectionBehavior:",
            c_ulong(OVERLAY_COLLECTION_BEHAVIOR),
            restype=None,
            argtypes=(c_ulong,),
        )
        _msg(
            window,
            "setLevel:",
            ctypes.c_long(NSFloatingWindowLevel),
            restype=None,
            argtypes=(ctypes.c_long,),
        )

    def apply_capture_exclusion(hwnd: int, enabled: bool = True) -> tuple[bool, str]:
        if not hwnd:
            return False, "窗口句柄尚未创建"
        window = _nswindow_from_view(hwnd)
        if not window:
            return False, "尚未挂到 NSWindow"
        sharing = NSWindowSharingNone if enabled else NSWindowSharingReadOnly
        _prepare_overlay_window(window)
        _set_sharing_type(window, sharing)
        # AppKit may reset this during orderFront; pin it last.
        _set_sharing_type(window, sharing)
        current = _sharing_type(window)
        if enabled and current != NSWindowSharingNone:
            return False, f"sharingType 未生效 ({current})"
        return True, "已从捕获中排除" if enabled else "已允许被捕获"

    def is_excluded_from_capture(hwnd: int) -> bool:
        if not hwnd:
            return False
        window = _nswindow_from_view(hwnd)
        if not window:
            return False
        return _sharing_type(window) == NSWindowSharingNone

    def set_click_through(hwnd: int, enabled: bool) -> None:
        window = _nswindow_from_view(hwnd)
        if not window:
            return
        _msg(
            window,
            "setIgnoresMouseEvents:",
            ctypes.c_ubyte(1 if enabled else 0),
            restype=None,
            argtypes=(ctypes.c_ubyte,),
        )

    def set_no_activate(hwnd: int, enabled: bool = True) -> None:
        window = _nswindow_from_view(hwnd)
        if not window or not enabled:
            return
        _msg(
            window,
            "setCollectionBehavior:",
            c_ulong(OVERLAY_COLLECTION_BEHAVIOR),
            restype=None,
            argtypes=(c_ulong,),
        )

    def set_color_key_opacity(
        hwnd: int,
        alpha: int,
        rgb: tuple[int, int, int] = CHROMA_KEY_RGB,
    ) -> None:
        window = _nswindow_from_view(hwnd)
        if not window:
            return
        _prepare_overlay_window(window)
        _ = alpha
        _ = rgb
