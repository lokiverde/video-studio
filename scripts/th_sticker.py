#!/usr/bin/env python3
"""Stickers for the talking-head news style: transparent PNGs that pop in beside Tony.

  th_sticker.py stamp "PAST DUE" out.png [--color red]     a rubber stamp, drawn, no AI
  th_sticker.py cutout photo.png out.png [--tolerance 28]  drop a plain background

`cutout` is for an object generated or shot on an even backdrop. Best: ask FLUX for
"isolated on a flat solid bright chroma key green background, no shadow". A colored
backdrop is keyed out by hue, shadow included. A white or grey one is flood filled from
the border, which leaves the shadow behind and eats white objects."""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

FONT = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "DejaVuSans-Bold.ttf"
STAMP_COLORS = {"red": (214, 40, 40), "green": (40, 150, 80), "navy": (15, 42, 67), "amber": (226, 150, 30)}
STAMP_FONT_SIZE = 190
STAMP_PAD = 60
STAMP_BORDER = 18
STAMP_TILT = -7
STAMP_PLATE_ALPHA = 225
MAX_STICKER_SIDE = 900
CHROMA_MIN_SAT = 0.3     # a border more saturated than this is a color backdrop
CHROMA_HUE_RANGE = 0.09  # fraction of the hue circle treated as backdrop


def stamp(text: str, color: str) -> Image.Image:
    """A tilted rubber stamp: double border, heavy caps, slightly worn ink."""
    rgb = STAMP_COLORS[color]
    font = ImageFont.truetype(str(FONT), STAMP_FONT_SIZE)
    left, top, right, bottom = font.getbbox(text)
    w, h = right - left + STAMP_PAD * 2, bottom - top + STAMP_PAD * 2
    ink = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(ink)
    draw.rounded_rectangle((0, 0, w - 1, h - 1), radius=34, outline=255, width=STAMP_BORDER)
    inner = STAMP_BORDER + 12
    draw.rounded_rectangle((inner, inner, w - 1 - inner, h - 1 - inner), radius=22, outline=255, width=6)
    draw.text((STAMP_PAD - left, STAMP_PAD - top), text, font=font, fill=255)
    # worn ink: knock small specks out of the mask
    wear = Image.effect_noise((w, h), 90).filter(ImageFilter.GaussianBlur(1.4)).point(lambda v: 255 if v > 78 else 0)
    ink = ImageChops.multiply(ink, wear)
    # a paper plate under the ink, so the stamp reads on any footage
    plate = Image.new("L", (w, h), 0)
    ImageDraw.Draw(plate).rounded_rectangle((0, 0, w - 1, h - 1), radius=34, fill=STAMP_PLATE_ALPHA)
    image = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    image.putalpha(plate)
    image.paste(Image.new("RGBA", (w, h), (*rgb, 255)), (0, 0), ink)
    return image.rotate(STAMP_TILT, expand=True, resample=Image.BICUBIC)


def _flood_mask(rgb: Image.Image, tolerance: int) -> np.ndarray:
    """Plain (white, grey) background: clear what is connected to the border."""
    w, h = rgb.size
    key = (255, 0, 255)
    filled = rgb.copy()
    step_x, step_y = max(1, w // 24), max(1, h // 24)
    seeds = [(x, y) for x in range(0, w, step_x) for y in (0, h - 1)] + [(x, y) for y in range(0, h, step_y) for x in (0, w - 1)]
    corner = rgb.getpixel((0, 0))
    for seed in seeds:
        pixel = rgb.getpixel(seed)
        if max(abs(a - b) for a, b in zip(pixel, corner)) <= tolerance and filled.getpixel(seed) != key:
            ImageDraw.floodfill(filled, seed, key, thresh=tolerance)
    return ~np.all(np.asarray(filled) == key, axis=-1)


def _chroma_mask(hsv: np.ndarray, key_hue: float) -> np.ndarray:
    """Colored backdrop (green screen): clear every pixel of that hue, shadows included."""
    hue, sat, val = hsv[..., 0] / 255, hsv[..., 1] / 255, hsv[..., 2] / 255
    distance = np.minimum(np.abs(hue - key_hue), 1 - np.abs(hue - key_hue))
    return ~((distance < CHROMA_HUE_RANGE) & (sat > CHROMA_MIN_SAT) & (val > 0.12))


def cutout(source: Image.Image, tolerance: int) -> Image.Image:
    """Drop the background. A saturated border color is keyed out by hue everywhere, so
    shadows go with it; a plain one is flood filled from the border inward."""
    rgb = source.convert("RGB")
    pixels = np.asarray(rgb)
    hsv = np.asarray(rgb.convert("HSV")).astype(float)
    border = np.concatenate([hsv[0], hsv[-1], hsv[:, 0], hsv[:, -1]])
    key_hue, key_sat = np.median(border[:, 0]) / 255, np.median(border[:, 1]) / 255
    chroma = key_sat > CHROMA_MIN_SAT
    keep = _chroma_mask(hsv, key_hue) if chroma else _flood_mask(rgb, tolerance)
    if chroma:
        # despill: the key channel never exceeds the other two on what is left
        channel = int(np.argmax(np.median(np.concatenate([pixels[0], pixels[-1]]), axis=0)))
        others = np.delete(pixels, channel, axis=-1).max(axis=-1)
        pixels = pixels.copy()
        pixels[..., channel] = np.minimum(pixels[..., channel], others)
    mask = Image.fromarray((keep * 255).astype("uint8")).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1.2))
    out = Image.fromarray(pixels).convert("RGBA")
    out.putalpha(mask)
    box = mask.point(lambda v: 255 if v > 40 else 0).getbbox()
    if box is None:
        raise ValueError("nothing left after removing the background, lower --tolerance")
    out = out.crop(box)
    out.thumbnail((MAX_STICKER_SIDE, MAX_STICKER_SIDE))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("stamp")
    p.add_argument("text")
    p.add_argument("out")
    p.add_argument("--color", choices=sorted(STAMP_COLORS), default="red")
    p = sub.add_parser("cutout")
    p.add_argument("src")
    p.add_argument("out")
    p.add_argument("--tolerance", type=int, default=28)
    args = parser.parse_args()
    if not args.out.lower().endswith(".png"):
        sys.exit("[sticker] the output must be a .png, stickers need transparency")
    if args.cmd == "stamp":
        image = stamp(args.text.upper(), args.color)
    else:
        if not Path(args.src).exists():
            sys.exit(f"[sticker] no such file: {args.src}")
        image = cutout(Image.open(args.src), args.tolerance)
    image.save(args.out)
    print(f"[sticker] {args.out} {image.size[0]}x{image.size[1]}")


if __name__ == "__main__":
    main()
