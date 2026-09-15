from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from overlay import CaptureExcludedOverlay


def main() -> int:
    if sys.platform != "win32":
        print("这是 Windows 专用工程，请在 Windows 上运行或打包。", file=sys.stderr)
        return 1

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    window = ControlWindow()
    window.show()
    return app.exec()


class ControlWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Windows 悬浮窗打包测试")
        self.setMinimumWidth(420)
        self.overlay = CaptureExcludedOverlay()

        self.status = QLabel("状态：尚未显示悬浮窗")
        self.status.setWordWrap(True)
        self.toggle = QCheckBox("显示悬浮字幕")
        self.toggle.toggled.connect(self.set_overlay_visible)
        self.opacity_label = QLabel("透明度：70%")
        self.opacity = QSlider(Qt.Orientation.Horizontal)
        self.opacity.setRange(20, 100)
        self.opacity.setValue(70)
        self.opacity.valueChanged.connect(self._on_opacity)
        refresh = QPushButton("重新打上 WDA_EXCLUDEFROMCAPTURE")
        refresh.clicked.connect(self._refresh_status)

        hint = QLabel(
            "这个控制窗口会出现在屏幕共享里。\n"
            "白色字幕悬浮窗应被 WDA_EXCLUDEFROMCAPTURE 排除。\n"
            "测试：Win+Shift+S 截图，或 Zoom/腾讯会议共享整个屏幕。"
        )
        hint.setWordWrap(True)

        opacity_row = QHBoxLayout()
        opacity_row.addWidget(self.opacity_label)
        opacity_row.addWidget(self.opacity, 1)

        root_layout = QVBoxLayout()
        root_layout.addWidget(hint)
        root_layout.addWidget(self.toggle)
        root_layout.addLayout(opacity_row)
        root_layout.addWidget(refresh)
        root_layout.addWidget(self.status)
        root = QWidget()
        root.setLayout(root_layout)
        self.setCentralWidget(root)
        self.toggle.setChecked(True)

    def set_overlay_visible(self, visible: bool) -> None:
        if visible:
            self.overlay.show()
            self.overlay.raise_()
        else:
            self.overlay.hide()
        self._refresh_status()

    def _on_opacity(self, percent: int) -> None:
        self.opacity_label.setText(f"透明度：{percent}%")
        self.overlay.set_opacity_percent(percent)
        self._refresh_status()

    def _refresh_status(self) -> None:
        if not self.overlay.isVisible():
            self.status.setText("状态：悬浮窗已隐藏")
            return
        self.status.setText("状态：" + self.overlay.exclusion_status())

    def closeEvent(self, event) -> None:
        self.overlay.close()
        super().closeEvent(event)


if __name__ == "__main__":
    raise SystemExit(main())
