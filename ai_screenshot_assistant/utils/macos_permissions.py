from __future__ import annotations

import ctypes
import ctypes.util
import subprocess
import sys


def is_macos() -> bool:
    return sys.platform == "darwin"


def accessibility_trusted() -> bool:
    if not is_macos():
        return True
    library = ctypes.util.find_library("ApplicationServices")
    if not library:
        return True
    app_services = ctypes.cdll.LoadLibrary(library)
    app_services.AXIsProcessTrusted.restype = ctypes.c_bool
    return bool(app_services.AXIsProcessTrusted())


def screen_recording_allowed() -> bool:
    if not is_macos():
        return True
    library = ctypes.util.find_library("CoreGraphics")
    if not library:
        return True
    quartz = ctypes.cdll.LoadLibrary(library)
    try:
        quartz.CGPreflightScreenCaptureAccess.restype = ctypes.c_bool
        return bool(quartz.CGPreflightScreenCaptureAccess())
    except Exception:
        return True


def request_screen_recording() -> bool:
    if not is_macos():
        return True
    library = ctypes.util.find_library("CoreGraphics")
    if not library:
        return True
    quartz = ctypes.cdll.LoadLibrary(library)
    try:
        quartz.CGPreflightScreenCaptureAccess.restype = ctypes.c_bool
        if quartz.CGPreflightScreenCaptureAccess():
            return True
        quartz.CGRequestScreenCaptureAccess.restype = ctypes.c_bool
        return bool(quartz.CGRequestScreenCaptureAccess())
    except Exception:
        return True


def open_privacy_pane(pane: str) -> None:
    if not is_macos():
        return
    url = f"x-apple.systemsettings:com.apple.preference.security?{pane}"
    subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
