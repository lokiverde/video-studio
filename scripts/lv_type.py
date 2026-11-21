"""Kinetic typography for the listing video: words rise into place one after another,
hold, and lift away. Text carries a soft shadow instead of a box, so it sits on the
photo like editorial type rather than a template chip.

Each word is rendered once with Pillow and cached as float arrays; per frame it is
only alpha-blended into the numpy frame at an animated offset.
"""
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import lv_cards

RISE = 0.34     # seconds for a word to rise in
STAGGER = 0.07  # seconds between words
LEAVE = 0.22    # seconds to lift away


def ease_out(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return 1 - (1 - t) ** 3


@dataclass(frozen=True)
class Line:
    text: str
    weight: str = "bold"
    size: int = 72
    color: str = "white"      # brand colour key
    tracking: float = 0.0     # extra px between letters (kicker style)
    gap: int = 10             # px below this line
    count: int | None = None  # count up to this number (price, sqft); text is a format like "${:,}"
    strike: bool = False      # a line through it (the old price after a reduction)


@dataclass
class Block:
    lines: list[Line]
    start: float              # seconds, shot-local
    end: float
    x: int = 96
    bottom: int | None = None  # px from top where the block's last line ends
    top: int | None = None
    align: str = "left"
    width: int = 0            # frame width (for centring)
    cache: dict = field(default_factory=dict)


@lru_cache(maxsize=512)
def word_sprite(text: str, weight: str, size: int, color: tuple, tracking: float, brand_key: str,
                strike: bool = False):
    """(rgb float32 HxWx3, alpha float32 HxW) with a soft shadow baked in."""
    brand = _BRANDS[brand_key]
    f = lv_cards.font(brand, weight, size)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    if tracking:
        tw = lv_cards.spaced_width(probe, text, f, tracking)
    else:
        tw = round(probe.textlength(text, font=f))
    pad = max(8, size // 5)
    h = f.getbbox("Hg")[3] + 2 * pad
    w = tw + 2 * pad
    shadow = Image.new("L", (w, h), 0)
    sd = ImageDraw.Draw(shadow)
    glyph = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glyph)
    for d, fill in ((sd, 150), (gd, color)):
        if tracking:
            lv_cards.spaced(d, (pad, pad), text, f, fill, tracking)
        else:
            d.text((pad, pad), text, font=f, fill=fill)
    if strike:
        mid = pad + f.getbbox("0")[1] + (f.getbbox("0")[3] - f.getbbox("0")[1]) // 2
        thick = max(3, size // 14)
        sd.rectangle([pad - 4, mid - thick // 2, pad + tw + 4, mid + thick // 2], fill=150)
        gd.rectangle([pad - 4, mid - thick // 2, pad + tw + 4, mid + thick // 2], fill=color)
    shadow = shadow.filter(ImageFilter.GaussianBlur(max(3, size // 9)))
    base = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    base.putalpha(shadow)
    base = Image.alpha_composite(base, glyph)
    arr = np.asarray(base).astype(np.float32) / 255.0
    return arr[:, :, :3] * 255.0, arr[:, :, 3], pad


_BRANDS: dict = {}


def register_brand(brand: dict) -> str:
    key = brand.get("name", "brand")
    _BRANDS[key] = brand
    return key


def blend(frame: np.ndarray, rgb: np.ndarray, alpha: np.ndarray, x: int, y: int, opacity: float) -> None:
    """In-place alpha blend of a sprite onto the frame (frame is owned by the caller)."""
    if opacity <= 0.003:
        return
    fh, fw = frame.shape[:2]
    h, w = alpha.shape
    x0, y0, x1, y1 = max(0, x), max(0, y), min(fw, x + w), min(fh, y + h)
    if x0 >= x1 or y0 >= y1:
        return
    a = alpha[y0 - y:y1 - y, x0 - x:x1 - x, None] * opacity
    region = frame[y0:y1, x0:x1].astype(np.float32)
    frame[y0:y1, x0:x1] = (region * (1 - a) + rgb[y0 - y:y1 - y, x0 - x:x1 - x] * a).astype(np.uint8)


def draw(frame: np.ndarray, block: Block, t: float, brand: dict) -> None:
    """Draw a block at shot-local time t. Words enter staggered, leave together."""
    if t < block.start or t > block.end:
        return
    key = register_brand(brand)
    colors = brand["colors"]
    laid = []  # (sprite, pad, x, y, word_index)
    heights = []
    for line in block.lines:
        f_h = lv_cards.font(brand, line.weight, line.size).getbbox("Hg")[3]
        heights.append(f_h + line.gap)
    total = sum(heights)
    y = (block.bottom - total) if block.bottom is not None else (block.top or 0)
    k = 0
    for line, lh in zip(block.lines, heights):
        color = lv_cards.rgba(colors.get(line.color, line.color))
        text = line.text
        if line.count is not None:
            grow = ease_out((t - block.start - k * STAGGER) / 0.9)
            # Round to $1,000s only while counting; the last frames show the exact figure ($599,900, not $600,000).
            value = line.count if grow >= 0.999 else (
                round(line.count * grow / 1000) * 1000 if line.count > 5000 else round(line.count * grow))
            text = line.text.format(value)
        words = [text] if line.tracking or line.count is not None else text.split(" ")
        sprites = [word_sprite(wd, line.weight, line.size, color, line.tracking, key, line.strike) for wd in words]
        space = lv_cards.font(brand, line.weight, line.size).getlength(" ")
        widths = [s[1].shape[1] - 2 * s[2] for s in sprites]
        line_w = sum(widths) + space * (len(words) - 1)
        x = block.x if block.align == "left" else (block.width - line_w) / 2
        for sprite, wdt in zip(sprites, widths):
            laid.append((sprite, x, y, k))
            x += wdt + space
            k += 1
        y += lh
    leave = ease_out((t - (block.end - LEAVE)) / LEAVE) if t > block.end - LEAVE else 0.0
    for (rgb, alpha, pad), x, y, idx in laid:
        enter = ease_out((t - block.start - idx * STAGGER) / RISE)
        opacity = enter * (1 - leave)
        dy = (1 - enter) * 36 - leave * 18
        blend(frame, rgb, alpha, int(x - pad), int(y - pad + dy), opacity)
