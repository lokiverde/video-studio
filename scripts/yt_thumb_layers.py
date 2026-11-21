#!/usr/bin/env python3
"""The one concrete object that carries a thumbnail's story (review 2026-10-19): a
rubber stamp, a chat window, or any PNG. Listed under "layers" in the thumbnail block and
drawn ABOVE the face cutout, so Tony's shoulder never covers them.

  {"type": "stamp", "text": "EVIDENCE", "x": 250, "y": 470, "size": 104, "angle": -12,
   "color": "#D62828", "strike": false}
  {"type": "chat", "text": "Here's what really happened...", "x": 40, "y": 330,
   "width": 520, "angle": 4}
  {"type": "image", "path": "public/lease.png", "x": 60, "y": 380, "height": 300,
   "angle": 0, "outline": true}

x and y are the layer's top-left corner on the 1280x720 canvas after rotation; a layer
may hang off the edge. angle is in degrees, positive tilts counter-clockwise. No brand
names or logos in a chat window: it is a generic one on purpose.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import common
import yt_thumb_face

ANTON = common.ROOT / "assets/fonts/Anton-Regular.ttf"
SANS = common.ROOT / "assets/fonts/DejaVuSans-Bold.ttf"
STAMP_RED = "#D62828"
STAMP_FILL = (255, 255, 255, 215)
CHAT_W, CHAT_H = 520, 300     # the reference card; other widths scale from it
CHAT_BAR = (30, 41, 59, 255)
CHAT_PAPER = (246, 247, 250, 255)
CHAT_BUBBLE = (41, 168, 214, 255)
CHAT_LINE = (203, 213, 225, 255)
CHAT_DOTS = [(239, 68, 68, 255), (250, 204, 21, 255), (34, 197, 94, 255)]
STRIKE = (15, 23, 42, 255)


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size, layout_engine=ImageFont.Layout.BASIC)


def stamp(text: str, size: int = 104, color: str = STAMP_RED, strike: bool = False) -> Image.Image:
    """A rubber stamp: the word in a rounded red border on a near-white card."""
    face = _font(ANTON, size)
    left, top, right, bottom = ImageDraw.Draw(Image.new("RGBA", (8, 8))).textbbox(
        (0, 0), text.upper(), font=face)
    pad, border = round(size * 0.25), max(4, round(size * 0.1))
    w, h = right - left + 2 * pad, bottom - top + 2 * pad
    card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle([0, 0, w - 1, h - 1], radius=round(size * 0.15), fill=STAMP_FILL,
                           outline=color, width=border)
    draw.text((pad - left, pad - top), text.upper(), font=face, fill=color)
    if strike:
        draw.line([(-10, h - 20), (w + 10, 20)], fill=STRIKE, width=max(8, round(size * 0.25)))
    return card


def _fit(draw: ImageDraw.ImageDraw, text: str, size: int, room: int) -> ImageFont.FreeTypeFont:
    while size > 12 and draw.textlength(text, font=_font(SANS, size)) > room:
        size -= 2
    return _font(SANS, size)


def chat(text: str, width: int = CHAT_W) -> Image.Image:
    """A generic chat window: one readable message bubble, the rest grey bars."""
    k = width / CHAT_W

    def s(value: float) -> int:                                   # reference px to this width
        return round(value * k)

    card = Image.new("RGBA", (width, s(CHAT_H)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle([0, 0, width - 1, s(CHAT_H) - 1], radius=s(26), fill=CHAT_PAPER)
    draw.rounded_rectangle([0, 0, width - 1, s(54)], radius=s(26), fill=CHAT_BAR)
    draw.rectangle([0, s(30), width - 1, s(54)], fill=CHAT_BAR)
    for i, dot in enumerate(CHAT_DOTS):
        draw.ellipse([s(22 + i * 30), s(18), s(40 + i * 30), s(36)], fill=dot)
    face = _fit(draw, text, s(30), width - s(110))
    text_w = draw.textlength(text, font=face)
    bubble = [width - text_w - s(66), s(78), width - s(22), s(136)]
    draw.rounded_rectangle(bubble, radius=s(22), fill=CHAT_BUBBLE)
    _, top, _, bottom = draw.textbbox((0, 0), text, font=face)
    text_y = (bubble[1] + bubble[3]) / 2 - (top + bottom) / 2
    draw.text((width - text_w - s(44), text_y), text, font=face, fill="white")
    for y, w in [(160, 380), (204, 300), (248, 340)]:
        draw.rounded_rectangle([s(22), s(y), s(22 + w), s(y + 30)], radius=s(15), fill=CHAT_LINE)
    return card


def picture(path: Path, height: int = 300, outline: bool = True) -> Image.Image:
    """Any PNG, scaled to `height`, in the same white sticker outline as the face."""
    image = Image.open(path).convert("RGBA")
    box = image.getchannel("A").getbbox()
    if box is None:
        raise ValueError(f"{path.name} is fully transparent")
    image = image.crop(box)
    image = image.resize((max(1, round(image.width * height / image.height)), height), Image.LANCZOS)
    return yt_thumb_face.sticker(image) if outline else image


def resolve(path: str, base: Path) -> Path:
    """A layer path is relative to the job folder, then to the repo (shared assets)."""
    for candidate in (base / path, common.ROOT / path):
        if candidate.exists():
            return candidate
    raise RuntimeError(f"no layer image at {base / path}")


def make_layer(spec: dict, base: Path) -> Image.Image:
    kind = spec.get("type")
    if kind == "stamp":
        layer = stamp(spec.get("text", "EVIDENCE"), int(spec.get("size", 104)),
                      spec.get("color", STAMP_RED), bool(spec.get("strike", False)))
        angle = spec.get("angle", -12)
    elif kind == "chat":
        layer = chat(spec.get("text", "Here's what really happened..."),
                     int(spec.get("width", CHAT_W)))
        angle = spec.get("angle", 4)
    elif kind == "image":
        layer = picture(resolve(spec["path"], base), int(spec.get("height", 300)),
                        bool(spec.get("outline", True)))
        angle = spec.get("angle", 0)
    else:
        raise ValueError(f"layer type '{kind}' is not one of stamp, chat, image")
    if angle:
        layer = layer.rotate(float(angle), expand=True, resample=Image.BICUBIC)
    return layer


def draw_layers(canvas: Image.Image, layers: list[dict], base: Path) -> None:
    """Composite every layer onto the RGBA canvas in list order."""
    for spec in layers or []:
        layer = make_layer(spec, base)
        yt_thumb_face.composite_at(canvas, layer, int(spec.get("x", 0)), int(spec.get("y", 0)))
