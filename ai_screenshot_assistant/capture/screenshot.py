from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from ai_screenshot_assistant.capture.roi import Roi


class ScreenCapture:
    def capture_png(self, roi: Roi, debug_path: Path | None = None) -> bytes:
        import mss

        with mss.mss() as sct:
            shot = sct.grab(roi.to_mss_monitor())
            image = Image.frombytes("RGB", shot.size, shot.rgb)

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        png = buffer.getvalue()
        if debug_path is not None:
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(debug_path)
        return png

