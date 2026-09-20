from __future__ import annotations

import os
import sys
import threading
from datetime import datetime
from pathlib import Path

_LOCK = threading.Lock()


def logs_directory() -> Path:
    if sys.platform == "darwin":
        path = Path.home() / "Library" / "Logs" / "QQMusic"
    elif sys.platform == "win32":
        local_app_data = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        path = local_app_data / "QQMusic" / "Logs"
    else:
        path = Path(os.getenv("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "QQMusic"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_app_log(message: str) -> None:
    line = f"{datetime.now().isoformat()} {message}".rstrip()
    with _LOCK:
        with (logs_directory() / "app.log").open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
