import threading
import time

from PySide6.QtCore import QObject, QThread, Slot
from PySide6.QtWidgets import QApplication

from ai_screenshot_assistant.ui.main_window import UiSignals


class CommandReceiver(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.command = None
        self.thread = None

    @Slot(dict)
    def receive(self, command: dict) -> None:
        self.command = command
        self.thread = QThread.currentThread()


def test_desktop_command_signal_returns_to_qt_main_thread() -> None:
    app = QApplication.instance() or QApplication([])
    signals = UiSignals()
    receiver = CommandReceiver()
    signals.desktop_command_received.connect(receiver.receive)

    worker = threading.Thread(
        target=lambda: signals.desktop_command_received.emit({"type": "command.capture_fullscreen"})
    )
    worker.start()
    worker.join()

    deadline = time.monotonic() + 1
    while receiver.command is None and time.monotonic() < deadline:
        app.processEvents()

    assert receiver.command == {"type": "command.capture_fullscreen"}
    assert receiver.thread is app.thread()
