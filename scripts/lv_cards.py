"""Pillow overlays for the listing video: the facts card over the opening photo, the
room label chip, and the closing "Contact Your Team" placard, each at 1920x1080
and 1080x1920.

Everything is a full-frame RGBA image so the renderer only ever alpha-composites.
Portrait layouts keep text between 10% and 76% of the height: above that sits the
phone status bar, below it Instagram's caption and buttons.
"""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

import captions
import common
import lv_mls

BRANDS_DIR = common.ROOT / "brands"
PORTRAIT_SAFE_TOP = 0.10
PORTRAIT_SAFE_BOTTOM = 0.76


def load_brand(name: str) -> dict:
    path = BRANDS_DIR / f"{name}.json"
    if not path.exists():
        raise RuntimeError(f"no brand file {path}")
    return json.loads(path.read_text())


def asset(path: str) -> Path:
    p = Path(path).expanduser()
    return p if p.is_absolute() else common.ROOT / p


def font(brand: dict, weight: str, size: int):
    path = brand.get("fonts", {}).get(weight)
    if path:
        try:
            return ImageFont.truetype(str(asset(path)), size, layout_engine=ImageFont.Layout.BASIC)
        except OSError:
            pass
    return captions.load_font(size)


def rgba(color: str, opacity: float = 1.0):
    return captions.hex_rgba(color, opacity)


def fit(draw, text: str, brand: dict, weight: str, size: int, max_w: int):
    """Largest font at or below `size` that fits `text` in max_w."""
    while size > 18:
        f = font(brand, weight, size)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 2
    return font(brand, weight, size)


def spaced(draw, xy, text: str, f, fill, tracking: float) -> int:
    """Letter-spaced caps (the kicker and label style). Returns the drawn width."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=f, fill=fill)
        x += draw.textlength(ch, font=f) + tracking
    return round(x - xy[0] - tracking)


def spaced_width(draw, text: str, f, tracking: float) -> int:
    return round(sum(draw.textlength(ch, font=f) for ch in text) + tracking * (len(text) - 1))


def logo(brand: dict, key: str, width: int) -> Image.Image:
    img = Image.open(asset(brand[key])).convert("RGBA")
    return img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)


def gradient(size, color: str, top: float, peak: float, curve: float = 0.8,
             flip: bool = False) -> Image.Image:
    """Transparent above `top` (fraction of height), ramping to `peak` opacity at the
    bottom. flip=True mirrors it: opaque at the top edge, clear below `top`."""
    w, h = size
    r, g, b, _ = rgba(color)
    mask = Image.new("L", (1, h))
    start = int(h * top)
    for y in range(h):
        a = 0 if y < start else (y - start) / max(h - start, 1)
        mask.putpixel((0, y), round(255 * peak * min(1, a ** curve)))
    if flip:
        mask = ImageOps.flip(mask)
    layer = Image.new("RGBA", size, (r, g, b, 255))
    layer.putalpha(mask.resize(size))
    return layer


def kicker_text(facts: dict) -> str:
    if facts.get("kicker"):
        return facts["kicker"].upper()
    if lv_mls.price_reduced(facts):
        return "NEW PRICE"
    return "FOR LEASE" if facts.get("listing_type") == "lease" else "FOR SALE"


def city_line(facts: dict) -> str:
    return ", ".join(p for p in (facts.get("city"), "CA " + facts["zip"] if facts.get("zip") else None) if p)


def open_overlay(facts: dict, brand: dict, size, branded: bool = True) -> Image.Image:
    """branded=False is the MLS cut: MLS rules bar brokerage logos and agent contact
    info from the virtual tour, so the lockup (and its scrim) are left off."""
    w, h = size
    portrait = h > w
    c = brand["colors"]
    img = gradient(size, c["navy"], 0.34 if portrait else 0.40, 0.94, curve=0.6 if portrait else 0.8)
    d = ImageDraw.Draw(img)
    margin = 70 if portrait else 96
    max_w = w - 2 * margin
    s = 1.0 if portrait else 0.95

    if branded:
        # A light scrim behind the logo so it reads over sky and foliage.
        img.alpha_composite(gradient(size, c["navy"], 0.80 if portrait else 0.72, 0.55, curve=1.6, flip=True))
        mark = logo(brand, "logo_white", 360 if portrait else 300)
        img.alpha_composite(mark, ((w - mark.width) // 2, int(h * 0.075)) if portrait else (w - mark.width - 70, 60))

    lines = [
        ("kicker", kicker_text(facts), font(brand, "semibold", int(34 * s)), c["cyan"]),
        ("address", facts.get("address") or "", fit(d, facts.get("address") or "", brand, "bold", int(92 * s), max_w), c["white"]),
        ("city", city_line(facts), font(brand, "regular", int(46 * s)), c["soft"]),
        ("rule", "", None, c["cyan"]),
        ("price", lv_mls.fmt_price(facts), font(brand, "bold", int(78 * s)), c["white"]),
        ("stats", lv_mls.stat_line(facts), fit(d, lv_mls.stat_line(facts), brand, "semibold", int(44 * s), max_w), c["white"]),
    ]
    gaps = {"kicker": 20, "address": 14, "city": 34, "rule": 30, "price": 16, "stats": 0}
    heights = {k: (8 if k == "rule" else f.getbbox("Hg")[3]) for k, _, f, _ in lines}
    block = sum(heights[k] + gaps[k] for k, *_ in lines)
    bottom = int(h * PORTRAIT_SAFE_BOTTOM) if portrait else h - 90
    y = bottom - block
    for key, text, f, fill in lines:
        if key == "rule":
            d.rectangle([margin, y, margin + 120, y + 8], fill=rgba(fill))
        elif key == "kicker":
            spaced(d, (margin, y), text, f, rgba(fill), 6)
        elif text:
            d.text((margin, y), text, font=f, fill=rgba(fill))
        y += heights[key] + gaps[key]
    return img


def label_overlay(label: str, callout: str, brand: dict, size) -> Image.Image | None:
    """Lower-left chip: room name in spaced caps, optional feature line under it."""
    if not label and not callout:
        return None
    w, h = size
    portrait = h > w
    c = brand["colors"]
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f_label = font(brand, "semibold", 30 if portrait else 28)
    f_call = font(brand, "bold", 50 if portrait else 46)
    pad_x, pad_y, bar = 34, 24, 8
    label_w = spaced_width(d, label.upper(), f_label, 5) if label else 0
    call_w = round(d.textlength(callout, font=f_call)) if callout else 0
    label_h = f_label.getbbox("HG")[3] if label else 0
    call_h = f_call.getbbox("Hg")[3] if callout else 0
    gap = 14 if label and callout else 0
    box_w = bar + 2 * pad_x + max(label_w, call_w)
    box_h = 2 * pad_y + label_h + gap + call_h
    x0 = 60 if portrait else 80
    y1 = int(h * PORTRAIT_SAFE_BOTTOM) if portrait else h - 80
    y0 = y1 - box_h
    d.rounded_rectangle([x0, y0, x0 + box_w, y1], radius=10, fill=rgba(c["navy"], 0.86))
    d.rectangle([x0, y0 + 10, x0 + bar, y1 - 10], fill=rgba(c["cyan"]))
    tx, ty = x0 + bar + pad_x, y0 + pad_y
    if label:
        spaced(d, (tx, ty), label.upper(), f_label, rgba(c["cyan"] if callout else c["white"]), 5)
        ty += label_h + gap
    if callout:
        d.text((tx, ty), callout, font=f_call, fill=rgba(c["white"]))
    return img


def team_card(brand: dict, width: int, height: int) -> Image.Image:
    """The team photo (shot on white) cover-cropped into a rounded white card."""
    photo = ImageOps.exif_transpose(Image.open(asset(brand["team_photo"]))).convert("RGB")
    photo = ImageOps.fit(photo, (width, height), Image.LANCZOS, centering=(0.5, 0.2))
    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, width - 1, height - 1], radius=24, fill=255)
    card = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    card.paste(photo, (0, 0), mask)
    return card


# Tony, 2026-09-30: the DRE lines must be the same size as the smallest text on the card,
# never a fine-print afterthought. So the card has exactly one small size, shared by the
# website, every DRE line, and the MLS# / Equal Housing line.
PLACARD_SMALL = 36


def fine_print(facts: dict, brand: dict) -> str:
    """Office license, MLS#, Equal Housing (agent DREs sit under each agent)."""
    p = brand["placard"]
    parts = [f"{p['office']} DRE #{p['office_dre']}"]
    if facts.get("listing_id"):
        parts.append(f"MLS# {facts['listing_id']}")
    parts.append(p.get("fine_print", ""))
    return "  |  ".join(x for x in parts if x)


def contact_block(d, brand: dict, x: int, y: int, max_w: int, center: bool) -> int:
    """Headline, each agent with phone and DRE, the site. Returns the y under it."""
    c, p = brand["colors"], brand["placard"]
    small_r, small_s = font(brand, "regular", PLACARD_SMALL), font(brand, "semibold", PLACARD_SMALL)

    def put(text, f, fill, y):
        tw = d.textlength(text, font=f)
        d.text((x + (max_w - tw) / 2 if center else x, y), text, font=f, fill=rgba(fill))
        return y + f.getbbox("Hg")[3]

    y = put(p["headline"], fit(d, p["headline"], brand, "bold", 72, max_w), c["white"], y) + 24
    rule_x = x + (max_w - 120) // 2 if center else x
    d.rectangle([rule_x, y, rule_x + 120, y + 8], fill=rgba(c["cyan"]))
    y += 34
    f_name, f_phone = font(brand, "semibold", 44), font(brand, "regular", 44)
    for contact in p["contacts"]:
        y = put(contact["name"], f_name, c["white"], y) + 4
        y = put(contact["phone"], f_phone, c["cyan"], y) + 4
        y = put(f"DRE #{contact['dre']}", small_r, c["soft"], y) + 22
    return put(p["site"], small_s, c["white"], y + 4)


def mls_card(facts: dict, brand: dict, size) -> Image.Image:
    """End card for the MLS cut: the property only. No agent, broker, logo, phone,
    website or license text, so it can sit in the MLS virtual tour field."""
    w, h = size
    portrait = h > w
    c = brand["colors"]
    img = Image.new("RGBA", size, rgba(c["navy"]))
    d = ImageDraw.Draw(img)
    max_w = w - (140 if portrait else 300)
    lines = [
        (kicker_text(facts), font(brand, "semibold", 36), c["cyan"], 26),
        (facts.get("address") or "", fit(d, facts.get("address") or "", brand, "bold", 88, max_w), c["white"], 14),
        (city_line(facts), font(brand, "regular", 46), c["soft"], 44),
        (lv_mls.fmt_price(facts), font(brand, "bold", 76), c["white"], 18),
        (lv_mls.stat_line(facts), fit(d, lv_mls.stat_line(facts), brand, "semibold", 44, max_w), c["white"], 0),
    ]
    heights = [f.getbbox("Hg")[3] + gap for _, f, _, gap in lines]
    y = (int(h * 0.40) if portrait else h // 2) - sum(heights) // 2
    for (text, f, fill, gap), step in zip(lines, heights):
        if text:
            tw = spaced_width(d, text, f, 6) if fill == c["cyan"] else d.textlength(text, font=f)
            if fill == c["cyan"]:
                spaced(d, ((w - tw) / 2, y), text, f, rgba(fill), 6)
            else:
                d.text(((w - tw) / 2, y), text, font=f, fill=rgba(fill))
        y += step
        if fill == c["soft"]:
            d.rectangle([(w - 120) // 2, y - 26, (w + 120) // 2, y - 18], fill=rgba(c["cyan"]))
    return img


def placard(facts: dict, brand: dict, size) -> Image.Image:
    w, h = size
    portrait = h > w
    c = brand["colors"]
    img = Image.new("RGBA", size, rgba(c["navy"]))
    d = ImageDraw.Draw(img)
    f_small = font(brand, "regular", PLACARD_SMALL)
    lines = fine_print(facts, brand).split("  |  ")
    if portrait:
        mark = logo(brand, "logo_white", 440)
        top = int(h * 0.06)
        img.alpha_composite(mark, ((w - mark.width) // 2, top))
        card = team_card(brand, 820, 440)
        top += mark.height + 36
        img.alpha_composite(card, ((w - card.width) // 2, top))
        y = contact_block(d, brand, 70, top + card.height + 40, w - 140, True) + 22
        # Office license first so it sits highest, above Instagram's caption area.
        for line in lines:
            tw = d.textlength(line, font=f_small)
            d.text(((w - tw) / 2, y), line, font=f_small, fill=rgba(c["soft"]))
            y += f_small.getbbox("Hg")[3] + 8
        return img
    card = team_card(brand, 740, 740)
    img.alpha_composite(card, (110, 110))
    x = 110 + card.width + 100
    max_w = w - x - 90
    mark = logo(brand, "logo_white", 400)
    img.alpha_composite(mark, (x, 90))
    contact_block(d, brand, x, 90 + mark.height + 50, max_w, False)
    text = "  |  ".join(lines)
    tw = d.textlength(text, font=f_small)
    d.text(((w - tw) / 2, h - 36 - f_small.getbbox("Hg")[3]), text, font=f_small, fill=rgba(c["soft"]))
    return img
