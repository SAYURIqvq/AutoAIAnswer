from __future__ import annotations

from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtGui import QMouseEvent, QShowEvent
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from macos_capture import apply_capture_exclusion, is_excluded_from_capture


class CaptureExcludedOverlay(QWidget):
    """Transparent always-on-top lyric window excluded from capture on macOS 14."""

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
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setStyleSheet("CaptureExcludedOverlay { background: transparent; border: none; }")
        self.setMinimumWidth(200)
        self.setMaximumWidth(720)

        self.label = QLabel("本机可见的测试字幕\n屏幕共享里应看不到这一行")
        self.label.setWordWrap(True)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.label.setStyleSheet(
            "color: #ffffff; font-size: 22px; font-weight: 700;"
            "background: transparent; border: none; padding: 8px;"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.label)
        self.adjustSize()

    def set_text(self, text: str) -> None:
        self.label.setText(text)
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
        self.setWindowOpacity(self._opacity_percent / 100.0)
        ok, message = apply_capture_exclusion(self, True)
        return ok, message

    def exclusion_status(self) -> str:
        ok, message = self.apply_native_flags()
        excluded = is_excluded_from_capture(self)
        return f"{'已排除' if excluded else '未排除'} | {message}" if ok or message else message

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
