from PIL import Image

from ai_screenshot_assistant.capture.roi import Roi
from ai_screenshot_assistant.capture.screenshot import ScreenCapture, fit_image, monitor_containing_point
from ai_screenshot_assistant.utils.display import scale_roi


def test_monitor_containing_point_selects_matching_display() -> None:
    monitors = [
        {"left": 0, "top": 0, "width": 3840, "height": 1080},
        {"left": 0, "top": 0, "width": 1920, "height": 1080},
        {"left": 1920, "top": 0, "width": 1920, "height": 1080},
    ]

    chosen = monitor_containing_point(monitors, 2000, 20)

    assert chosen["left"] == 1920
    assert chosen["width"] == 1920


def test_monitor_containing_point_falls_back_to_primary() -> None:
    monitors = [
        {"left": 0, "top": 0, "width": 1920, "height": 1080},
        {"left": 0, "top": 0, "width": 1920, "height": 1080},
    ]

    chosen = monitor_containing_point(monitors, None, None)

    assert chosen == monitors[1]


def test_monitor_containing_point_uses_retina_scale() -> None:
    monitors = [
        {"left": 0, "top": 0, "width": 3024, "height": 1964},
        {"left": 0, "top": 0, "width": 3024, "height": 1964},
    ]

    chosen = monitor_containing_point(monitors, 1400, 800, scale=2.0)

    assert chosen == monitors[1]


def test_fit_image_shrinks_long_side() -> None:
    image = Image.new("RGB", (4096, 2160), color=(0, 0, 0))

    fitted = fit_image(image, max_side=2048)

    assert max(fitted.size) == 2048
    assert fitted.size[0] > fitted.size[1]


def test_fit_image_keeps_retina_width_by_default() -> None:
    image = Image.new("RGB", (3024, 1964), color=(0, 0, 0))

    fitted = fit_image(image)

    assert max(fitted.size) == 2880


def test_scale_roi_for_retina() -> None:
    roi = Roi(left=100, top=80, width=200, height=120)

    scaled = scale_roi(roi, 2.0)

    assert scaled == Roi(left=200, top=160, width=400, height=240)
    assert scale_roi(roi, 1.0) == roi


def test_windows_capture_uses_raw_desktop_coordinates(monkeypatch) -> None:
    monkeypatch.setattr("ai_screenshot_assistant.capture.screenshot.sys.platform", "win32")
    monkeypatch.setattr("ai_screenshot_assistant.capture.screenshot.screen_scale_at", lambda *_: 1.5)

    assert ScreenCapture._coordinate_scale(100, 200) == 1.0


def test_macos_capture_keeps_display_scale(monkeypatch) -> None:
    monkeypatch.setattr("ai_screenshot_assistant.capture.screenshot.sys.platform", "darwin")
    monkeypatch.setattr("ai_screenshot_assistant.capture.screenshot.screen_scale_at", lambda *_: 2.0)

    assert ScreenCapture._coordinate_scale(100, 200) == 2.0
