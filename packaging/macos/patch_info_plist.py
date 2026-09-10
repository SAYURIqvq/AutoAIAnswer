#!/usr/bin/env python3
from __future__ import annotations

import plistlib
import sys
from pathlib import Path


def patch_info_plist(app_path: Path) -> None:
    plist_path = app_path / "Contents" / "Info.plist"
    with plist_path.open("rb") as handle:
        info = plistlib.load(handle)
    info["CFBundleDisplayName"] = "AutoAIAnswer"
    info["CFBundleName"] = "AutoAIAnswer"
    info["CFBundleIdentifier"] = "com.sayuriqvq.AutoAIAnswer"
    info["CFBundleShortVersionString"] = "0.2.3"
    info["LSMinimumSystemVersion"] = "12.0"
    info["NSHighResolutionCapable"] = True
    info["NSScreenCaptureUsageDescription"] = "截取当前屏幕或框选区域中的题目，发送给 AI 分析并返回答案。"
    info["NSAppleEventsUsageDescription"] = "用于在本机完成截图搜题相关的系统协作。"
    with plist_path.open("wb") as handle:
        plistlib.dump(info, handle)


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: patch_info_plist.py dist/AutoAIAnswer.app", file=sys.stderr)
        return 2
    app_path = Path(sys.argv[1])
    patch_info_plist(app_path)
    print(f"Patched {app_path / 'Contents' / 'Info.plist'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
