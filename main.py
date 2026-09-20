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
from ai_screenshot_assistant.utils.app_log import logs_directory, write_app_log

_crash_log = None
_windows_mutex = None


def _install_crash_logging() -> None:
    global _crash_log
    log_dir = logs_directory()
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


def _restore_hint() -> str:
    if sys.platform == "darwin":
        return "请从菜单栏恢复窗口。"
    if sys.platform == "win32":
        return "请从系统托盘图标恢复窗口。"
    return "请从托盘恢复窗口。"


def _acquire_windows_mutex() -> bool:
    global _windows_mutex
    if sys.platform != "win32":
        return True
    import ctypes

    kernel32 = ctypes.windll.kernel32
    _windows_mutex = kernel32.CreateMutexW(None, True, "Local\\com.sayuriqvq.QQMusic.single")
    return kernel32.GetLastError() != 183


def main() -> int:
    _install_crash_logging()
    app = QApplication(sys.argv)
    if not _acquire_windows_mutex():
        write_app_log("refused second instance (windows mutex)")
        QMessageBox.information(None, "QQMusic", f"QQMusic 已经在运行，{_restore_hint()}")
        return 0
    lock_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation)
    instance_lock = QLockFile(str(Path(lock_dir) / "com.sayuriqvq.QQMusic.lock"))
    instance_lock.setStaleLockTime(0)
    if not instance_lock.tryLock(250):
        write_app_log("refused second instance (file lock)")
        QMessageBox.information(None, "QQMusic", f"QQMusic 已经在运行，{_restore_hint()}")
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
        if settings.embedded_backend or settings.backend_url == "auto":
            backend = EmbeddedBackend(settings.backend_port)
            backend.start()
            window = MainWindow(backend_url=backend.local_url, public_url=backend.url)
        else:
            window = MainWindow(backend_url=backend_url)
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
