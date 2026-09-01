from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget


class ResultWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AI 搜题结果")
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.setWindowOpacity(0.96)
        self.setMinimumWidth(420)

        self.answer = QLabel("--")
        self.answer.setAlignment(Qt.AlignCenter)
        self.answer.setWordWrap(True)
        self.answer.setStyleSheet("font-size: 40px; font-weight: 800; color: #1fbf9a;")
        self.confidence = QLabel("置信度：--")
        self.reason = QTextEdit()
        self.reason.setReadOnly(True)

        copy_button = QPushButton("复制答案")
        copy_button.clicked.connect(self.copy_answer)
        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.close)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("答案"))
        layout.addWidget(self.answer)
        layout.addWidget(self.confidence)
        layout.addWidget(QLabel("解析"))
        layout.addWidget(self.reason)
        layout.addWidget(copy_button)
        layout.addWidget(close_button)
        self.setLayout(layout)

    def show_result(self, result: dict[str, Any]) -> None:
        self.answer.setText(str(result.get("answer") or "完成"))
        self.confidence.setText(f"置信度：{result.get('confidence') or '--'}")
        self.reason.setPlainText(str(result.get("reason") or result.get("text") or ""))
        self.show()
        self.raise_()

    def copy_answer(self) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.answer.text())

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)
