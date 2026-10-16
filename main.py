from __future__ import annotations

import os
import faulthandler
import traceback
import sys
import threading
from datetime import datetime
from pathlib import Path

# PyInstaller's windowed mode sets these streams to None. Some dependencies,
# including Uvicorn's logging setup, expect file-like streams to exist.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from PySide6.QtCore import QLockFile, QStandardPaths
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from ai_screenshot_assistant.backend.embedded import EmbeddedBackend
from ai_screenshot_assistant.config import settings
from ai_screenshot_assistant.resources import app_icon_path
from ai_screenshot_assistant.ui.main_window import MainWindow

_crash_log = None


def _install_crash_logging() -> None:
    global _crash_log
    if sys.platform == "darwin":
        log_dir = Path.home() / "Library" / "Logs" / "QQMusic"
    elif sys.platform == "win32":
        local_app_data = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        log_dir = local_app_data / "QQMusic" / "Logs"
    else:
        log_dir = Path(os.getenv("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "QQMusic"
    log_dir.mkdir(parents=True, exist_ok=True)
    _crash_log = (log_dir / "crash.log").open("a", encoding="utf-8")
    _crash_log.write(f"\n--- launch {datetime.now().isoformat()} pid={os.getpid()} ---\n")
    _crash_log.flush()
    faulthandler.enable(_crash_log, all_threads=True)

    def report_exception(exc_type, exc_value, exc_traceback) -> None:
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=_crash_log)
        _crash_log.flush()
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = report_exception
    threading.excepthook = lambda args: report_exception(
        args.exc_type, args.exc_value, args.exc_traceback
    )


def main() -> int:
    _install_crash_logging()
    app = QApplication(sys.argv)
    lock_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation)
    instance_lock = QLockFile(str(Path(lock_dir) / "com.sayuriqvq.QQMusic.lock"))
    if not instance_lock.tryLock(250):
        QMessageBox.information(None, "QQMusic", "QQMusic 已经在运行，请从菜单栏恢复窗口。")
        return 0

    icon_path = app_icon_path()
    if icon_path is not None:
        icon = QIcon(str(icon_path))
        if not icon.isNull():
            app.setWindowIcon(icon)
    app.setQuitOnLastWindowClosed(False)
    backend = None
    try:
        backend_url = settings.backend_url
        public_url = backend_url
        if settings.embedded_backend or settings.backend_url == "auto":
            backend = EmbeddedBackend(settings.backend_port)
            public_url = backend.start()
            backend_url = backend.local_url
        window = MainWindow(backend_url=backend_url, public_url=public_url)
        window.show()
        return app.exec()
    except Exception as exc:
        sys.excepthook(type(exc), exc, exc.__traceback__)
        QMessageBox.critical(
            None,
            "QQMusic 启动失败",
            f"无法启动固定端口 {settings.backend_port}。请确认没有旧进程占用该端口。\n\n{exc}",
        )
        return 1
    finally:
        if backend is not None:
            backend.stop()
        instance_lock.unlock()


if __name__ == "__main__":
    raise SystemExit(main())
