from __future__ import annotations

from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPalette, QShowEvent
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QLabel, QVBoxLayout, QWidget

from win32_capture import (
    CHROMA_KEY_RGB,
    apply_capture_exclusion,
    hwnd_from_widget,
    is_excluded_from_capture,
    set_color_key_opacity,
    set_no_activate,
)


class CaptureExcludedOverlay(QWidget):
    """Transparent always-on-top lyric window excluded from capture on Windows."""

    def __init__(self) -> None:
        super().__init__()
        self._drag_offset: QPoint | None = None
        self._opacity_percent = 70
        self._native_retry = QTimer(self)
        self._native_retry.setSingleShot(True)
        self._native_retry.timeout.connect(self.apply_native_flags)
        self.setWindowTitle("桌面字幕")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setMinimumWidth(200)
        self.setMaximumWidth(720)
        key = QColor(*CHROMA_KEY_RGB)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, key)
        self.setPalette(palette)
        self.setStyleSheet(
            f"CaptureExcludedOverlay {{ background-color: rgb{CHROMA_KEY_RGB}; border: none; }}"
        )

        self.label = QLabel("本机可见的测试字幕\n屏幕共享里应看不到这一行")
        self.label.setWordWrap(True)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.label.setStyleSheet(
            "color: #ffffff; font-size: 22px; font-weight: 700;"
            "background: transparent; border: none; padding: 8px;"
        )
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(6)
        shadow.setOffset(0, 1)
        shadow.setColor(QColor(0, 0, 0, 180))
        self.label.setGraphicsEffect(shadow)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.label)
        self.adjustSize()

    def set_opacity_percent(self, percent: int) -> None:
        self._opacity_percent = max(20, min(100, int(percent)))
        self.apply_native_flags()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._schedule_native_flags()

    def raise_(self) -> None:
        super().raise_()
        self._schedule_native_flags()

    def _schedule_native_flags(self) -> None:
        self.apply_native_flags()
        self._native_retry.start(120)

    def apply_native_flags(self) -> tuple[bool, str]:
        hwnd = hwnd_from_widget(self)
        if not hwnd:
            return False, "窗口句柄尚未创建"
        apply_capture_exclusion(hwnd, True)
        set_no_activate(hwnd, True)
        set_color_key_opacity(hwnd, int(round(self._opacity_percent * 2.55)))
        return apply_capture_exclusion(hwnd, True)

    def exclusion_status(self) -> str:
        ok, message = self.apply_native_flags()
        hwnd = hwnd_from_widget(self)
        excluded = is_excluded_from_capture(hwnd)
        prefix = "已排除" if excluded else "未排除"
        return f"{prefix} | {message}" if ok or message else message

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = None
            event.accept()
            return
        super().mouseReleaseEvent(event)
