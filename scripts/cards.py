"""Number cards for countdown videos: a plain card with a big number and an optional
title, drawn here rather than generated, because FLUX cannot render a legible "7".

A card is a shots entry: {"card": 10} or {"card": {"number": 10, "title": "The lowball
offer"}}. Colours come from the theme's "card_style" ({"bg", "text", "title"})."""
import textwrap

from PIL import Image, ImageDraw

import captions

DEFAULT_STYLE = {"bg": "#ffffff", "text": "#111111", "title": "#55555c"}


def parse(card):
    """(number text, title) from a card spec. Raises ValueError when there is no number."""
    if isinstance(card, dict):
        number, title = card.get("number"), (card.get("title") or "").strip()
    else:
        number, title = card, ""
    if isinstance(number, bool) or number is None or str(number).strip() == "":
        raise ValueError(f"card needs a number, got {card!r}")
    return str(number).strip(), title


def render(card, size, style=None):
    number, title = parse(card)
    style = {**DEFAULT_STYLE, **(style or {})}
    width, height = size
    img = Image.new("RGB", size, captions.hex_rgba(style["bg"])[:3])
    draw = ImageDraw.Draw(img)
    unit = min(width, height)

    big = captions.load_font(round(unit * 0.42))
    box = draw.textbbox((0, 0), number, font=big)
    centre_y = height * (0.44 if title else 0.5)
    draw.text(((width - (box[2] - box[0])) / 2 - box[0],
               centre_y - (box[3] - box[1]) / 2 - box[1]),
              number, font=big, fill=captions.hex_rgba(style["text"])[:3])

    if title:
        small = captions.load_font(round(unit * 0.075))
        lines = textwrap.wrap(title, width=26 if width > height else 18)
        line_h = round(unit * 0.095)
        y = centre_y + (box[3] - box[1]) / 2 + unit * 0.07
        for line in lines:
            lb = draw.textbbox((0, 0), line, font=small)
            draw.text(((width - (lb[2] - lb[0])) / 2, y), line, font=small,
                      fill=captions.hex_rgba(style["title"])[:3])
            y += line_h
    return img
