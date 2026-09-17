from __future__ import annotations

import io

from PIL import Image
from qrcode import QRCode
from qrcode.constants import ERROR_CORRECT_M

QR_BOX_SIZE = 8
QR_MODULE_BORDER = 6
QR_EXTRA_QUIET_PX = 16
QR_DISPLAY_PX = 188


def pair_qr_image(url: str) -> Image.Image:
    qr = QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=QR_BOX_SIZE,
        border=QR_MODULE_BORDER,
    )
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    if hasattr(image, "convert"):
        image = image.convert("RGB")
    else:
        image = Image.open(io.BytesIO(_raw_png(image))).convert("RGB")
    extra = QR_EXTRA_QUIET_PX
    width, height = image.size
    padded = Image.new("RGB", (width + extra * 2, height + extra * 2), (255, 255, 255))
    padded.paste(image, (extra, extra))
    return padded


def pair_qr_png_bytes(url: str) -> bytes:
    buffer = io.BytesIO()
    pair_qr_image(url).save(buffer, format="PNG")
    return buffer.getvalue()


def quiet_zone_thickness(image: Image.Image, threshold: int = 240) -> tuple[int, int, int, int]:
    pixels = image.convert("RGB").load()
    width, height = image.size

    def row_is_white(y: int) -> bool:
        return all(min(pixels[x, y]) >= threshold for x in range(width))

    def column_is_white(x: int) -> bool:
        return all(min(pixels[x, y]) >= threshold for y in range(height))

    top = 0
    while top < height and row_is_white(top):
        top += 1
    bottom = 0
    while bottom < height and row_is_white(height - 1 - bottom):
        bottom += 1
    left = 0
    while left < width and column_is_white(left):
        left += 1
    right = 0
    while right < width and column_is_white(width - 1 - right):
        right += 1
    return top, right, bottom, left


def _raw_png(image: object) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer)  # type: ignore[attr-defined]
    return buffer.getvalue()
