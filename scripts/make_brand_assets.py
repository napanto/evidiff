# SPDX-License-Identifier: AGPL-3.0-only
"""Render the evidiff icons and social previews from the SVG sources in brand/.

Usage (needs `rsvg-convert` from librsvg, and Pillow for the .ico file):

    uv run --with pillow python scripts/make_brand_assets.py

The sources are pure geometry (no fonts, no third-party assets), so the output
depends only on the SVG files and the renderer.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "brand"
STATIC = ROOT / "app" / "static"
BACKGROUND = "#17684e"  # full-bleed for the Apple touch icon, which iOS rounds itself


def render(svg, out, width, height=None, background=None):
    command = ["rsvg-convert", "--width", str(width), "--height", str(height or width)]
    if background:
        command += ["--background-color", background]
    subprocess.run([*command, "--output", str(out), str(svg)], check=True)


def main():
    if not shutil.which("rsvg-convert"):
        sys.exit("rsvg-convert (librsvg) is required")
    mark, og = BRAND / "mark.svg", BRAND / "og.svg"
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for size in (512, 192, 32):
            render(mark, tmp / f"{size}.png", size)
        shutil.copyfile(tmp / "512.png", STATIC / "icon-512.png")
        shutil.copyfile(tmp / "192.png", STATIC / "icon-192.png")
        shutil.copyfile(tmp / "32.png", STATIC / "favicon-32.png")
        render(mark, tmp / "apple.png", 180, background=BACKGROUND)
        Image.open(tmp / "apple.png").convert("RGB").save(STATIC / "apple-touch-icon.png")
        render(mark, tmp / "48.png", 48)
        Image.open(tmp / "48.png").save(
            STATIC / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)]
        )
        render(og, tmp / "og.png", 1200, 630)
        preview = Image.open(tmp / "og.png").convert("RGB")
        for lang in ("en", "it"):
            preview.save(STATIC / f"og-image-{lang}.png")


if __name__ == "__main__":
    main()
