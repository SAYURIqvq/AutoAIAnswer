from __future__ import annotations

import sys
from pathlib import Path


def resource_path(relative_path: str) -> Path:
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base_path / relative_path


def app_icon_path() -> Path | None:
    candidates = (
        "assets/app.ico",
        "assets/app.png",
        "assets/app.icns",
    )
    for candidate in candidates:
        path = resource_path(candidate)
        if path.exists():
            return path
    return None
