from __future__ import annotations

import sys

from PySide6.QtCore import QPoint, QSettings, QTimer, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPalette, QShowEvent
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QLabel, QVBoxLayout, QWidget

from ai_screenshot_assistant.ui.native_capture import (
    CHROMA_KEY_RGB,
    apply_capture_exclusion,
    hwnd_from_widget,
    set_color_key_opacity,
    set_no_activate,
)

_IS_MAC = sys.platform == "darwin"


class StreamingOverlay(QWidget):
    """Capture-excluded lyric overlay: text only, no black chrome."""

    def __init__(self, app_settings: QSettings) -> None:
        super().__init__()
        self.app_settings = app_settings
        self._drag_offset: QPoint | None = None
        self._buffer = ""
        self._opacity_percent = int(app_settings.value("overlay/opacity_percent", 50) or 50)
        self._font_px = int(app_settings.value("overlay/font_px", 18) or 18)
        self._font_px = max(8, min(22, self._font_px))
        self._native_retry = QTimer(self)
        self._native_retry.setSingleShot(True)
        self._native_retry.timeout.connect(self._apply_native_flags)
        self.setWindowTitle("AI 流式答案")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setMinimumWidth(160)
        self.setMaximumWidth(720)
        if _IS_MAC:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
            self.setAutoFillBackground(False)
            self.setStyleSheet("StreamingOverlay { background: transparent; border: none; }")
        else:
            key = QColor(*CHROMA_KEY_RGB)
            self.setAutoFillBackground(True)
            palette = self.palette()
            palette.setColor(QPalette.ColorRole.Window, key)
            self.setPalette(palette)
            self.setStyleSheet(
                f"StreamingOverlay {{ background-color: rgb{CHROMA_KEY_RGB}; border: none; }}"
            )

        self.label = QLabel("")
        self.label.setWordWrap(True)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._apply_label_style()
        if not _IS_MAC:
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(6)
            shadow.setOffset(0, 1)
            shadow.setColor(QColor(0, 0, 0, 180))
            self.label.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.label)
        self._restore_position()

    def _restore_position(self) -> None:
        saved = self.app_settings.value("overlay/position")
        if isinstance(saved, QPoint):
            self.move(saved)
            return
        screen = QApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            self.move(area.left() + 20, area.bottom() - 180)

    def set_opacity_percent(self, percent: int) -> None:
        self._opacity_percent = max(15, min(100, int(percent)))
        self._apply_native_flags()

    def set_font_px(self, size: int) -> None:
        self._font_px = max(8, min(22, int(size)))
        self._apply_label_style()
        self.adjustSize()

    def _apply_label_style(self) -> None:
        self.label.setStyleSheet(
            f"color: #ffffff; font-size: {self._font_px}px; font-weight: 600;"
            "background: transparent; border: none; padding: 4px;"
        )

    def start_stream(self) -> None:
        self._buffer = ""
        self.label.setText("分析中…")
        self.adjustSize()
        self._apply_native_flags()

    def append_delta(self, delta: str) -> None:
        self._buffer += delta
        self.label.setText(self._buffer)
        self.adjustSize()

    def complete_stream(self, text: str) -> None:
        self._buffer = text
        self.label.setText(text or "分析完成")
        self.adjustSize()

    def show_error(self, message: str) -> None:
        self._buffer = ""
        self.label.setText(f"错误：{message}")
        self.adjustSize()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._schedule_native_flags()

    def raise_(self) -> None:
        super().raise_()
        self._schedule_native_flags()

    def _schedule_native_flags(self) -> None:
        self._apply_native_flags()
        # AppKit may reset sharingType during orderFront; pin it again shortly after.
        self._native_retry.start(120)

    def _apply_native_flags(self) -> None:
        if _IS_MAC:
            self.setWindowOpacity(self._opacity_percent / 100.0)
        hwnd = hwnd_from_widget(self)
        if not hwnd:
            return
        apply_capture_exclusion(hwnd, True)
        set_no_activate(hwnd, True)
        set_color_key_opacity(hwnd, int(round(self._opacity_percent * 2.55)))
        apply_capture_exclusion(hwnd, True)

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
        if event.button() == Qt.MouseButton.LeftButton and self._drag_offset is not None:
            self._drag_offset = None
            self.app_settings.setValue("overlay/position", self.pos())
            event.accept()
            return
        super().mouseReleaseEvent(event)
