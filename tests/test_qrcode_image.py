from io import BytesIO

from PIL import Image

from ai_screenshot_assistant.utils.qrcode_image import (
    QR_DISPLAY_PX,
    QR_EXTRA_QUIET_PX,
    pair_qr_image,
    pair_qr_png_bytes,
    quiet_zone_thickness,
)


def test_pair_qr_keeps_white_quiet_zone_on_all_sides() -> None:
    image = pair_qr_image("http://192.168.1.8:8000/pair?t=example")
    top, right, bottom, left = quiet_zone_thickness(image)

    assert top >= QR_EXTRA_QUIET_PX
    assert bottom >= QR_EXTRA_QUIET_PX
    assert left >= QR_EXTRA_QUIET_PX
    assert right >= QR_EXTRA_QUIET_PX
    assert image.getpixel((0, 0)) == (255, 255, 255)
    assert image.getpixel((image.width - 1, 0)) == (255, 255, 255)
    assert image.getpixel((0, image.height - 1)) == (255, 255, 255)
    assert image.getpixel((image.width - 1, image.height - 1)) == (255, 255, 255)


def test_pair_qr_png_bytes_are_square_enough_for_display() -> None:
    png = pair_qr_png_bytes("http://10.0.0.2:8000/pair?t=abc")
    image = Image.open(BytesIO(png))

    assert image.size[0] == image.size[1]
    assert image.size[0] >= QR_DISPLAY_PX
    top, _right, bottom, _left = quiet_zone_thickness(image)
    assert top == bottom
