from __future__ import annotations

from ai_screenshot_assistant.capture.roi import Roi


def scale_roi(roi: Roi, scale: float) -> Roi:
    if scale <= 1.0001:
        return roi
    return Roi(
        left=max(0, int(round(roi.left * scale))),
        top=max(0, int(round(roi.top * scale))),
        width=max(1, int(round(roi.width * scale))),
        height=max(1, int(round(roi.height * scale))),
    )


def screen_scale_at(x: int | None = None, y: int | None = None) -> float:
    try:
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QGuiApplication

        app = QGuiApplication.instance()
        if app is None:
            return 1.0
        screen = None
        if x is not None and y is not None:
            screen = app.screenAt(QPoint(int(x), int(y)))
        if screen is None:
            screen = app.primaryScreen()
        if screen is None:
            return 1.0
        ratio = float(screen.devicePixelRatio())
        return ratio if ratio > 0 else 1.0
    except Exception:
        return 1.0
