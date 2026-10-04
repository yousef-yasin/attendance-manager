"""Generate the application icon (PNG + multi-size ICO) from code.

Source design: packaging/assets/app_icon.svg (a rounded blue tile with a white
calendar and check mark). This script renders the same design with Pillow so
no design tools are needed:

    python packaging/make_icon.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ICO = ROOT / "packaging" / "assets" / "app_icon.ico"
PNG = ROOT / "src" / "attendance_manager" / "ui" / "assets" / "app_icon.png"
WIZARD_SMALL = ROOT / "packaging" / "assets" / "wizard_small.bmp"
WIZARD_LARGE = ROOT / "packaging" / "assets" / "wizard_large.bmp"

TOP = (58, 142, 234)
BOTTOM = (28, 92, 171)


def render(size: int = 1024) -> Image.Image:
    s = size / 1024
    base = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gradient = Image.new("RGBA", (size, size))
    gd = ImageDraw.Draw(gradient)
    for y in range(size):
        t = y / max(1, size - 1)
        color = tuple(round(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3))
        gd.line([(0, y), (size, y)], fill=(*color, 255))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [40 * s, 40 * s, 984 * s, 984 * s], radius=220 * s, fill=255
    )
    base.paste(gradient, (0, 0), mask)

    d = ImageDraw.Draw(base)
    white = (255, 255, 255, 255)
    w = max(2, round(58 * s))
    # calendar body
    d.rounded_rectangle([232 * s, 262 * s, 792 * s, 800 * s], radius=90 * s, outline=white, width=w)
    # header band
    d.line([(232 * s, 420 * s), (792 * s, 420 * s)], fill=white, width=w)
    # rings
    for x in (382, 642):
        d.line([(x * s, 200 * s), (x * s, 320 * s)], fill=white, width=w)
        d.ellipse([(x * s - w / 2, 200 * s - w / 2), (x * s + w / 2, 200 * s + w / 2)], fill=white)
        d.ellipse([(x * s - w / 2, 320 * s - w / 2), (x * s + w / 2, 320 * s + w / 2)], fill=white)
    # check mark
    pts = [(380 * s, 610 * s), (475 * s, 700 * s), (650 * s, 520 * s)]
    d.line(pts, fill=white, width=round(66 * s), joint="curve")
    for p in (pts[0], pts[-1]):
        r = 33 * s
        d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=white)
    return base


def main() -> None:
    big = render(1024)
    PNG.parent.mkdir(parents=True, exist_ok=True)
    ICO.parent.mkdir(parents=True, exist_ok=True)
    big.resize((256, 256), Image.LANCZOS).save(PNG)
    big.save(
        ICO,
        sizes=[
            (16, 16),
            (20, 20),
            (24, 24),
            (32, 32),
            (40, 40),
            (48, 48),
            (64, 64),
            (128, 128),
            (256, 256),
        ],
    )
    # Inno Setup wizard images (plain bitmaps, white background).
    for path, size, icon_size in ((WIZARD_SMALL, (138, 140), 110), (WIZARD_LARGE, (410, 797), 260)):
        canvas = Image.new("RGB", size, (255, 255, 255))
        icon = big.resize((icon_size, icon_size), Image.LANCZOS)
        canvas.paste(icon, ((size[0] - icon_size) // 2, (size[1] - icon_size) // 2), icon)
        canvas.save(path)
    print(f"Wrote {ICO}, {PNG}, wizard images")


if __name__ == "__main__":
    main()
