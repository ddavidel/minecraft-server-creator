"""Rasterize ``static/logo.svg`` into the bitmap assets the app ships.

Outputs (in ``src/mcsc_gui/static``):
- ``logo.ico``  multi-size Windows icon (16-256 px), used as the window icon
- ``logo-512.png``  large square icon, for stores/README/installers
- ``logo.png``  800x200 lockup (icon + wordmark), used by the sidebar and About

Run from the repo root:  python scripts/build_logo.py
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

if sys.platform != "win32":  # the offscreen platform on Windows has no system fonts
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

STATIC = Path(__file__).resolve().parents[1] / "src" / "mcsc_gui" / "static"
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
TEXT = QColor("#f0ede6")
TEXT_MUTED = QColor("#a39f95")


def render_icon(renderer: QSvgRenderer, size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return image


def png_bytes(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)


def write_ico(path: Path, images: list[QImage]) -> None:
    """ICO container with PNG-compressed entries (supported since Windows Vista)."""
    blobs = [png_bytes(img) for img in images]
    header = struct.pack("<HHH", 0, 1, len(blobs))
    offset = 6 + 16 * len(blobs)
    entries = b""
    for img, blob in zip(images, blobs):
        dim = img.width() % 256  # 256 is stored as 0
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
    path.write_bytes(header + entries + b"".join(blobs))


def render_lockup(renderer: QSvgRenderer) -> QImage:
    width, height = 800, 200
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    renderer.render(painter, QRectF(0, 8, 184, 184))

    title = QFont("Segoe UI", 1, QFont.Weight.Bold)
    title.setPixelSize(92)
    title.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 97)
    painter.setFont(title)
    painter.setPen(TEXT)
    painter.drawText(QRectF(212, 18, width - 212, 110), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom, "MCSC")

    subtitle = QFont("Segoe UI", 1, QFont.Weight.Medium)
    subtitle.setPixelSize(34)
    painter.setFont(subtitle)
    painter.setPen(TEXT_MUTED)
    painter.drawText(QRectF(216, 130, width - 216, 50), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, "Server Creator")
    painter.end()
    return image


def main() -> int:
    app = QGuiApplication(sys.argv)  # noqa: F841 - needed for fonts
    renderer = QSvgRenderer(str(STATIC / "logo.svg"))
    if not renderer.isValid():
        print("logo.svg could not be parsed", file=sys.stderr)
        return 1

    write_ico(STATIC / "logo.ico", [render_icon(renderer, s) for s in ICO_SIZES])
    render_icon(renderer, 512).save(str(STATIC / "logo-512.png"))
    render_lockup(renderer).save(str(STATIC / "logo.png"))
    print(f"Wrote logo.ico, logo-512.png, logo.png to {STATIC}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
