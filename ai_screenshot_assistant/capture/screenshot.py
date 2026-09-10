from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from ai_screenshot_assistant.capture.roi import Roi

FULLSCREEN_MAX_SIDE = 2048


def monitor_containing_point(
    monitors: list[dict[str, int]],
    x: int | None = None,
    y: int | None = None,
) -> dict[str, int]:
    physical = monitors[1:] if len(monitors) > 1 else monitors
    if not physical:
        raise RuntimeError("No display is available for fullscreen capture")
    if x is not None and y is not None:
        for monitor in physical:
            left = monitor["left"]
            top = monitor["top"]
            if left <= x < left + monitor["width"] and top <= y < top + monitor["height"]:
                return monitor
    return physical[0]


def fit_image(image: Image.Image, max_side: int = FULLSCREEN_MAX_SIDE) -> Image.Image:
    width, height = image.size
    longest = max(width, height)
    if longest <= max_side:
        return image
    scale = max_side / longest
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return image.resize(new_size, Image.Resampling.LANCZOS)


class ScreenCapture:
    def capture_png(self, roi: Roi, debug_path: Path | None = None) -> bytes:
        import mss

        with mss.mss() as sct:
            shot = sct.grab(roi.to_mss_monitor())
            image = Image.frombytes("RGB", shot.size, shot.rgb)
        return self._encode(image, debug_path)

    def capture_fullscreen_png(
        self,
        x: int | None = None,
        y: int | None = None,
        debug_path: Path | None = None,
    ) -> bytes:
        import mss

        with mss.mss() as sct:
            monitor = monitor_containing_point(sct.monitors, x, y)
            shot = sct.grab(monitor)
            image = Image.frombytes("RGB", shot.size, shot.rgb)
        return self._encode(fit_image(image), debug_path)

    def _encode(self, image: Image.Image, debug_path: Path | None = None) -> bytes:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        png = buffer.getvalue()
        if debug_path is not None:
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(debug_path)
        return png
