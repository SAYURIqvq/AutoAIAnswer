from __future__ import annotations

from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QLabel, QVBoxLayout, QWidget


class StreamingOverlay(QWidget):
    def __init__(self, app_settings: QSettings) -> None:
        super().__init__()
        self.app_settings = app_settings
        self._drag_offset: QPoint | None = None
        self._buffer = ""
        self.setWindowTitle("AI 流式答案")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumWidth(160)
        self.setMaximumWidth(480)

        self.label = QLabel("")
        self.label.setWordWrap(True)
        self.label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.label.setStyleSheet(
            "color: rgba(255, 255, 255, 46);"
            "font-size: 11px; font-weight: 500;"
            "background: transparent; padding: 2px;"
        )
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(3)
        shadow.setOffset(1, 1)
        shadow.setColor(Qt.black)
        self.label.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
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

    def start_stream(self) -> None:
        self._buffer = ""
        self.label.setText("分析中…")
        self.adjustSize()

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

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton and self._drag_offset is not None:
            self._drag_offset = None
            self.app_settings.setValue("overlay/position", self.pos())
            event.accept()
            return
        super().mouseReleaseEvent(event)
