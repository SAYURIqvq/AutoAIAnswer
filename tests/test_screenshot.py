from PIL import Image

from ai_screenshot_assistant.capture.screenshot import fit_image, monitor_containing_point


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


def test_fit_image_shrinks_long_side() -> None:
    image = Image.new("RGB", (4096, 2160), color=(0, 0, 0))

    fitted = fit_image(image, max_side=2048)

    assert max(fitted.size) == 2048
    assert fitted.size[0] > fitted.size[1]
