from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image

from ai_screenshot_assistant.capture.roi import Roi
from ai_screenshot_assistant.utils.display import scale_roi, screen_scale_at

FULLSCREEN_MAX_SIDE = 2880


def point_in_monitor(monitor: dict[str, int], x: int, y: int) -> bool:
    left = monitor["left"]
    top = monitor["top"]
    return left <= x < left + monitor["width"] and top <= y < top + monitor["height"]


def monitor_containing_point(
    monitors: list[dict[str, int]],
    x: int | None = None,
    y: int | None = None,
    scale: float = 1.0,
) -> dict[str, int]:
    physical = monitors[1:] if len(monitors) > 1 else monitors
    if not physical:
        raise RuntimeError("No display is available for fullscreen capture")
    if x is None or y is None:
        return physical[0]
    candidates = [(int(x), int(y))]
    if scale > 1.0001:
        candidates.append((int(round(x * scale)), int(round(y * scale))))
    for cx, cy in candidates:
        for monitor in physical:
            if point_in_monitor(monitor, cx, cy):
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

        scale = self._coordinate_scale(roi.left, roi.top)
        region = scale_roi(roi, scale)
        with mss.mss() as sct:
            shot = sct.grab(region.to_mss_monitor())
            image = Image.frombytes("RGB", shot.size, shot.rgb)
        return self._encode(image, debug_path)

    def capture_fullscreen_png(
        self,
        x: int | None = None,
        y: int | None = None,
        debug_path: Path | None = None,
    ) -> bytes:
        import mss

        scale = self._coordinate_scale(x, y)
        with mss.mss() as sct:
            monitor = monitor_containing_point(sct.monitors, x, y, scale=scale)
            shot = sct.grab(monitor)
            image = Image.frombytes("RGB", shot.size, shot.rgb)
        return self._encode(fit_image(image), debug_path)

    @staticmethod
    def _coordinate_scale(x: int | None = None, y: int | None = None) -> float:
        # mouse.get_position() and mss use the same physical desktop coordinates
        # on Windows. Applying Qt's logical-to-physical ratio again shifts ROI.
        if sys.platform == "win32":
            return 1.0
        return screen_scale_at(x, y)

    def _encode(self, image: Image.Image, debug_path: Path | None = None) -> bytes:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        png = buffer.getvalue()
        if debug_path is not None:
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(debug_path)
        return png
