"""macOS only: exclude an NSWindow from screen capture via sharingType = .none."""

from __future__ import annotations

import ctypes
import ctypes.util
from ctypes import c_char_p, c_long, c_ubyte, c_ulong, c_void_p

NSWindowSharingNone = 0
NSWindowSharingReadOnly = 1

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


def nsview_from_widget(widget: object) -> int:
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


def nswindow_from_view(view: int) -> int:
    if not view:
        return 0
    window = _msg(view, "window", restype=c_void_p)
    return int(window or 0)


def _set_sharing_type(window: int, sharing_type: int) -> None:
    _msg(window, "setSharingType:", c_ulong(sharing_type), restype=None, argtypes=(c_ulong,))


def sharing_type(window: int) -> int:
    return int(_msg(window, "sharingType", restype=c_ulong) or 0)


def prepare_overlay_window(window: int) -> None:
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
    _msg(window, "setLevel:", c_long(NSFloatingWindowLevel), restype=None, argtypes=(c_long,))


def apply_capture_exclusion(widget: object, enabled: bool = True) -> tuple[bool, str]:
    view = nsview_from_widget(widget)
    if not view:
        return False, "窗口句柄尚未创建"
    window = nswindow_from_view(view)
    if not window:
        return False, "尚未挂到 NSWindow"
    sharing = NSWindowSharingNone if enabled else NSWindowSharingReadOnly
    prepare_overlay_window(window)
    _set_sharing_type(window, sharing)
    _set_sharing_type(window, sharing)
    current = sharing_type(window)
    if enabled and current != NSWindowSharingNone:
        return False, f"sharingType 未生效 ({current})"
    if enabled:
        return True, "sharingType = none，已请求从捕获中排除"
    return True, "sharingType = readOnly，允许被捕获"


def is_excluded_from_capture(widget: object) -> bool:
    view = nsview_from_widget(widget)
    window = nswindow_from_view(view)
    if not window:
        return False
    return sharing_type(window) == NSWindowSharingNone
