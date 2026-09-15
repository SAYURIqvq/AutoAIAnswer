#!/usr/bin/env python3
from __future__ import annotations

import plistlib
import sys
from pathlib import Path


def patch_info_plist(app_path: Path) -> None:
    plist_path = app_path / "Contents" / "Info.plist"
    with plist_path.open("rb") as handle:
        info = plistlib.load(handle)
    info["CFBundleDisplayName"] = "QQMusicOverlay"
    info["CFBundleName"] = "QQMusicOverlay"
    info["CFBundleIdentifier"] = "com.sayuriqvq.QQMusicOverlay"
    info["CFBundleShortVersionString"] = "0.1.0"
    info["LSMinimumSystemVersion"] = "12.0"
    info["NSHighResolutionCapable"] = True
    info["LSUIElement"] = False
    with plist_path.open("wb") as handle:
        plistlib.dump(info, handle)


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: patch_info_plist.py dist/QQMusicOverlay.app", file=sys.stderr)
        return 2
    app_path = Path(sys.argv[1])
    patch_info_plist(app_path)
    print(f"Patched {app_path / 'Contents' / 'Info.plist'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
