#!/usr/bin/env python3
"""YouTube thumbnail: one full-bleed photo of the subject, 2 to 4 words in two sizes,
ONE accent banner behind the key phrase, the brand mark small in the same corner every
time (California Insider shape, reviewed 2026-09-27). No bill numbers.

The Test & compare standard (thumbnail review, docs/thumbnail-review-2026-10-19.md):
about 4 in 5 niche winners show the host, but no causal study exists, so every long-form
16:9 upload ships three thumbnails and YouTube Test & compare picks the winner on our
own data. A block with a "face" renders, in out/thumb_variants/:
  thumbnail_A.jpg   Tony cut out on the right, the layers, the words in the left 55%
  thumbnail_B.jpg   exactly A without the face (one variable only)
  thumbnail_C.jpg   the plain faceless version: same words (or "plain" overrides),
                    no face, no layers, the classic full-width layout
  phone_sizes.jpg   all three at phone home-feed (360 px) and search (168 px) width
and copies A to out/thumbnail.jpg, the one that goes up with the video. Read the phone
sheet before calling it done. A block without a face renders one out/thumbnail.jpg.

  yt_thumb.py --job <job>          (job.json "thumbnail", or thumbnail.json for jobs
                                    without a job.json: faceless, listing)
  yt_thumb.py --lines "OGDENVILLE" "RENT CAPPED" --accent 1 --prompt "..." --out thumb.jpg
  yt_thumb.py --lines ... --bg photo.jpg --face tony.png --out thumb.jpg

The block: {"lines": [...], "accent": 1, "bg": "public/x.jpg" | "prompt": "...",
"seed": n, "mark": "EXAMPLE REALTY", "font": "anton", "face": 2.6 | "assets/faces/x.png",
"face_height": 820, "text_y": 40, "layers": [...], "plain": {...}, "variants": [...]}.
"face" is seconds into public/footage.mp4 or a PNG (yt_thumb_face.py). "layers" are the
stamp / chat window / PNG that carry the story, drawn above the face (yt_thumb_layers.py).
"text_y" pins the top of the word stack (default: centered). "variants" replaces the
standard set with up to 3 hand-made overrides of the base block; in a variant,
"face": false keeps the face layout and leaves the face out.

"style": "alert" (Epic Real Estate breakdown, a breakdown note) swaps the
word stack for our own homeowner alert lower third: a Brokerage navy headline bar across
the bottom (1 or 2 lines, 3 to 7 words, one size), a light-blue label strip on top of it
("label", default CALIFORNIA HOMEOWNER ALERT), the face standing behind the bar. Never a
network lookalike: a label with NEWS or a network name is flagged. An alert block with a
face and no "plain" renders A and B only (C would repeat B); give "plain":
{"style": "classic", "lines": [...], "accent": 1} to test the alert against the classic.
  yt_thumb.py --style alert --lines "NO RENT CONTROL IN TORRANCE" "STATE CAP STILL APPLIES"
              --bg photo.jpg --out thumb.jpg
Text is drawn with Pillow in the bundled Anton (or DejaVu Sans Bold with "font": "dejavu"),
never by the image model.
"""
from __future__ import annotations

import argparse
import io
import json
import random
import re
import shutil
import sys
from pathlib import Path
from typing import NamedTuple

from PIL import Image, ImageDraw, ImageFont

import common
import yt_thumb_face
import yt_thumb_layers


class Typeface(NamedTuple):
    path: Path
    small: int                # the two type sizes
    big: int


FONTS = {
    "anton": Typeface(common.ROOT / "assets/fonts/Anton-Regular.ttf", 112, 168),
    "dejavu": Typeface(common.ROOT / "assets/fonts/DejaVuSans-Bold.ttf", 84, 150),
}
DEFAULT_FONT = "anton"        # condensed: about 40% bigger type in the same width
LABEL_FONT = "dejavu"
W, H = 1280, 720
MARGIN = 60
TEXT_MAX_X = 900              # text column; the right side belongs to the photo
FACE_TEXT_MAX_X = round(W * 0.55)   # with a face, the words keep the left 55%
FACE_HEIGHT = 820             # head and chest fill the frame, the cut edge falls off the bottom
FACE_TOP = 100              # head clears the brand mark in the top right corner
FACE_CENTER_X = round(W * 0.8)
MIN_SIZE = 44
BANNER_PAD_X, BANNER_PAD_Y = 22, 14
STROKE = 4
LINE_GAP = 16
ACCENT = "#FACC15"
INK = "#0F172A"
MARK = "EXAMPLE REALTY"
MIN_WORDS, MAX_WORDS = 2, 4
MAX_BANNER_WORDS = 2
VARIANT_LETTERS = "ABC"       # YouTube Test & compare takes at most 3
LAYOUT_KEYS = ("face", "face_height", "layers", "text_y")   # what the plain C drops
SETS_DIR = "thumb_variants"
PHONE_SHEET = "phone_sizes.jpg"
FOOTAGE = "public/footage.mp4"
PHONE_WIDTHS = (360, 168)     # phone home feed, phone search and sidebar
BILL_RE = re.compile(r"\b(AB|SB|ACA|SCA)[\s-]?\d{2,4}\b", re.IGNORECASE)
PHOTO_STYLE = ("professional real estate photograph, natural light, sharp focus, "
               "wide angle, no people, no text, no signs, no logos")

STYLES = ("classic", "alert")
NAVY = "#1d3557"              # Brokerage navy, same as army_draw.DEFAULT_STYLE
LIGHT_BLUE = "#29a8d6"        # Brokerage light blue
ALERT_LABEL = "CALIFORNIA HOMEOWNER ALERT"
ALERT_MIN_WORDS, ALERT_MAX_WORDS = 3, 7
ALERT_MAX_LINES = 2
ALERT_SIDE, ALERT_BOTTOM = 40, 36       # bar inset from the sides and the bottom edge
ALERT_PAD_X, ALERT_PAD_Y = 28, 20
ALERT_HEAD_SIZE = 104                   # headline starts here and shrinks to fit
ALERT_LINE_GAP = 12
ALERT_RULE = 5                          # light-blue rule along the top of the bar
ALERT_MAX_BAR_H = 250                   # the photo keeps the top of the frame
ALERT_LABEL_H, ALERT_LABEL_SIZE = 54, 34
ALERT_FACE_HEIGHT = 500                 # smaller than classic: the head and chin clear the bar
ALERT_FACE_TOP = 80                     # and the EXAMPLE REALTY mark
NETWORK_RE = re.compile(r"\b(NEWS|FOX|CNN|MSNBC|NBC|CBS|ABC|NEWSMAX)\b", re.IGNORECASE)


def normalize(lines: list[str]) -> list[str]:
    return [line.strip().upper() for line in lines if line.strip()]


def lint(lines: list[str], accent: int | None = None) -> list[str]:
    """Packaging rules. Warnings, not errors: Tony can overrule them."""
    warnings = []
    words = sum(len(line.split()) for line in lines)
    if not MIN_WORDS <= words <= MAX_WORDS:
        warnings.append(f"{words} words; keep it to {MIN_WORDS} to {MAX_WORDS} so it "
                        f"reads at phone size")
    if accent is not None and 0 <= accent < len(lines):
        banner_words = len(lines[accent].split())
        if banner_words > MAX_BANNER_WORDS:
            warnings.append(f"banner line '{lines[accent]}' is {banner_words} words; "
                            f"1 or 2 stay readable at phone search size")
    for line in lines:
        if BILL_RE.search(line):
            warnings.append(f"bill number in '{line}'; put it in the description instead")
    return warnings


def lint_alert(lines: list[str], label: str = ALERT_LABEL) -> list[str]:
    """Alert copy rules, warnings only: the headline names the threat in 3 to 7 words,
    and the label is ours, never a news network's."""
    warnings = []
    words = sum(len(line.split()) for line in lines)
    if not ALERT_MIN_WORDS <= words <= ALERT_MAX_WORDS:
        warnings.append(f"{words} words; an alert headline reads best at "
                        f"{ALERT_MIN_WORDS} to {ALERT_MAX_WORDS}")
    if len(lines) > ALERT_MAX_LINES:
        warnings.append(f"{len(lines)} lines; the alert bar holds {ALERT_MAX_LINES}")
    for line in lines:
        if BILL_RE.search(line):
            warnings.append(f"bill number in '{line}'; put it in the description instead")
    if NETWORK_RE.search(label):
        warnings.append(f"label '{label}' reads like a news network; keep the alert our own")
    return warnings


def plan_sizes(lines: list[str], accent: int, family: str = DEFAULT_FONT) -> list[int]:
    """Two sizes only. The last line punches, unless it is the banner line, in which
    case the first line does."""
    face = typeface(family)
    big_at = len(lines) - 1 if accent != len(lines) - 1 else 0
    return [face.big if i == big_at and len(lines) > 1 else face.small
            for i in range(len(lines))]


def typeface(family: str) -> Typeface:
    if family not in FONTS:
        raise ValueError(f"font '{family}' is not one of {', '.join(FONTS)}")
    return FONTS[family]


def font(size: int, family: str = DEFAULT_FONT) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(typeface(family).path), size,
                              layout_engine=ImageFont.Layout.BASIC)


def cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Scale to fill, crop the overflow from the center."""
    tw, th = size
    scale = max(tw / image.width, th / image.height)
    resized = image.convert("RGB").resize(
        (round(image.width * scale), round(image.height * scale)), Image.LANCZOS)
    left, top = (resized.width - tw) // 2, (resized.height - th) // 2
    return resized.crop((left, top, left + tw, top + th))


def shade(image: Image.Image) -> Image.Image:
    """Dark wash from the left so white type reads on any photo."""
    overlay = Image.new("RGBA", image.size)
    draw = ImageDraw.Draw(overlay)
    for x in range(W):
        alpha = max(0, round(200 * (1 - x / (W * 0.8))))
        draw.line([(x, 0), (x, H)], fill=(8, 18, 40, alpha))
    return Image.alpha_composite(image.convert("RGBA"), overlay)


def fit(draw: ImageDraw.ImageDraw, text: str, size: int, room: int,
        family: str = DEFAULT_FONT) -> ImageFont.FreeTypeFont:
    while size > MIN_SIZE and draw.textbbox((0, 0), text, font=font(size, family))[2] > room:
        size -= 4
    return font(size, family)


def line_height(draw: ImageDraw.ImageDraw, text: str, face, banner: bool) -> int:
    """Ink height of one line, banner padding or outline stroke included."""
    if banner:
        _, top, _, bottom = draw.textbbox((0, 0), text, font=face)
        return bottom - top + 2 * BANNER_PAD_Y
    _, top, _, bottom = draw.textbbox((0, 0), text, font=face, stroke_width=STROKE)
    return bottom - top


def fit_column(draw, lines, accent, family, text_max_x, text_top=None):
    """Fonts that fit the column width, shrunk together until the stack fits the height."""
    room = text_max_x - MARGIN - 2 * BANNER_PAD_X
    room_h = H - MARGIN - (MARGIN if text_top is None else text_top)
    sizes = plan_sizes(lines, accent, family)
    while True:
        fonts = [fit(draw, line, size, room, family) for line, size in zip(lines, sizes)]
        heights = [line_height(draw, line, face, i == accent)
                   for i, (line, face) in enumerate(zip(lines, fonts))]
        total = sum(heights) + LINE_GAP * (len(lines) - 1)
        if total <= room_h or max(sizes) <= MIN_SIZE:
            return fonts, heights, total
        sizes = [max(MIN_SIZE, size - 4) for size in sizes]


def draw_lines(draw, lines, accent, family, text_max_x, text_top=None) -> list[tuple]:
    fonts, heights, total = fit_column(draw, lines, accent, family, text_max_x, text_top)
    if text_top is None:
        y = max(MARGIN, min((H - total) // 2 + 40, H - MARGIN - total))
    else:
        y = int(text_top)
    boxes = []
    for i, (line, face) in enumerate(zip(lines, fonts)):
        if i == accent:
            _, top, right, _ = draw.textbbox((0, 0), line, font=face)
            box = (MARGIN, y, MARGIN + right + 2 * BANNER_PAD_X, y + heights[i])
            draw.rectangle(box, fill=ACCENT)
            draw.text((MARGIN + BANNER_PAD_X, y + BANNER_PAD_Y - top), line, font=face, fill=INK)
        else:
            top = draw.textbbox((0, 0), line, font=face, stroke_width=STROKE)[1]
            draw.text((MARGIN, y - top), line, font=face, fill="white",
                      stroke_width=STROKE, stroke_fill=INK)
            box = draw.textbbox((MARGIN, y - top), line, font=face, stroke_width=STROKE)
        boxes.append(tuple(box))
        y += heights[i] + LINE_GAP
    return boxes


def draw_mark(draw: ImageDraw.ImageDraw, label: str = MARK, family: str = DEFAULT_FONT) -> None:
    mark = font(30, family)
    width = draw.textlength(label, font=mark)
    x, y = W - width - 40, 34
    draw.text((x, y), label, font=mark, fill="white", stroke_width=2, stroke_fill=INK)
    bottom = draw.textbbox((x, y), label, font=mark, stroke_width=2)[3]
    draw.rectangle([x, bottom + 4, x + width, bottom + 9], fill=ACCENT)


def render(bg: Image.Image, lines: list[str], accent: int, mark: str = MARK,
           face: Image.Image | bool | None = None, family: str = DEFAULT_FONT,
           layers: list[dict] | None = None, text_top: int | None = None,
           face_height: int = FACE_HEIGHT, base: Path = Path(".")) -> tuple[Image.Image, list]:
    """Return the thumbnail and each line's box (for tests and QC). `face` is an RGBA
    cutout (yt_thumb_face.load_face), or False for the same layout with the face left
    out. With either, the words keep the left 55%. Order, bottom to top: photo, wash,
    face, layers, words, mark."""
    lines = normalize(lines)
    if not 0 <= accent < len(lines):
        raise ValueError(f"accent line {accent} out of range for {len(lines)} lines")
    typeface(family)
    image = shade(cover(bg, (W, H)))
    text_max_x = TEXT_MAX_X if face is None else FACE_TEXT_MAX_X
    if isinstance(face, Image.Image):
        yt_thumb_face.place(image, face, int(face_height), FACE_CENTER_X, FACE_TOP)
    yt_thumb_layers.draw_layers(image, layers or [], base)
    draw = ImageDraw.Draw(image)
    boxes = draw_lines(draw, lines, accent, family, text_max_x, text_top)
    draw_mark(draw, mark, family)
    return image.convert("RGB"), boxes


def bottom_wash(image: Image.Image) -> Image.Image:
    """Navy wash rising from the bottom, so the bar sits on the photo, not floats over it."""
    overlay = Image.new("RGBA", image.size)
    draw = ImageDraw.Draw(overlay)
    start = round(H * 0.35)
    for y in range(start, H):
        draw.line([(0, y), (W, y)], fill=(0, 18, 31, round(190 * (y - start) / (H - start))))
    return Image.alpha_composite(image.convert("RGBA"), overlay)


def fit_headline(draw: ImageDraw.ImageDraw, lines: list[str], room: int):
    """One size for every line: the biggest that fits the bar's width and height cap.
    Returns the font, each line's ink height and the bar height."""
    size = ALERT_HEAD_SIZE
    while True:
        face = font(size)
        boxes = [draw.textbbox((0, 0), line, font=face) for line in lines]
        heights = [bottom - top for _, top, _, bottom in boxes]
        bar_h = sum(heights) + ALERT_LINE_GAP * (len(lines) - 1) + 2 * ALERT_PAD_Y
        fits = max(right for _, _, right, _ in boxes) <= room and bar_h <= ALERT_MAX_BAR_H
        if fits or size <= MIN_SIZE:
            return face, heights, bar_h
        size -= 4


def draw_alert_label(draw: ImageDraw.ImageDraw, label: str, left: int, bar_top: int) -> tuple:
    """The light-blue strip sitting on the bar's top left corner: a yellow live dot, then
    the label in navy. Returns its box."""
    face = font(ALERT_LABEL_SIZE)
    _, top, right, bottom = draw.textbbox((0, 0), label, font=face)
    dot = ALERT_LABEL_H // 3
    box = (left, bar_top - ALERT_LABEL_H, left + 2 * ALERT_PAD_X + dot + 14 + right, bar_top)
    draw.rectangle(box, fill=LIGHT_BLUE)
    mid = (box[1] + box[3]) // 2
    draw.rectangle((left + ALERT_PAD_X, mid - dot // 2, left + ALERT_PAD_X + dot, mid + dot // 2),
                   fill=ACCENT)
    draw.text((left + ALERT_PAD_X + dot + 14, mid - (bottom - top) // 2 - top), label,
              font=face, fill=NAVY)
    return box


def render_alert(bg: Image.Image, lines: list[str], label: str = ALERT_LABEL,
                 mark: str = MARK, face: Image.Image | bool | None = None,
                 layers: list[dict] | None = None, face_height: int = ALERT_FACE_HEIGHT,
                 base: Path = Path(".")) -> tuple[Image.Image, dict]:
    """The alert lower third. Order, bottom to top: photo, bottom wash, face, layers,
    navy headline bar, label strip, mark. Returns the thumbnail and the "bar", "label"
    and "lines" boxes (for tests and QC)."""
    lines = normalize(lines)
    if not 1 <= len(lines) <= ALERT_MAX_LINES:
        raise ValueError(f"an alert headline is 1 or {ALERT_MAX_LINES} lines, not {len(lines)}")
    image = bottom_wash(cover(bg, (W, H)))
    if isinstance(face, Image.Image):
        yt_thumb_face.place(image, face, int(face_height), FACE_CENTER_X, ALERT_FACE_TOP)
    yt_thumb_layers.draw_layers(image, layers or [], base)
    draw = ImageDraw.Draw(image)
    left, right = ALERT_SIDE, W - ALERT_SIDE
    head, heights, bar_h = fit_headline(draw, lines, right - left - 2 * ALERT_PAD_X)
    bar = (left, H - ALERT_BOTTOM - bar_h, right, H - ALERT_BOTTOM)
    draw.rectangle(bar, fill=NAVY)
    draw.rectangle((left, bar[1], right, bar[1] + ALERT_RULE - 1), fill=LIGHT_BLUE)
    y, boxes = bar[1] + ALERT_PAD_Y, []
    for line, height in zip(lines, heights):
        at = (left + ALERT_PAD_X, y - draw.textbbox((0, 0), line, font=head)[1])
        draw.text(at, line, font=head, fill="white")
        boxes.append(tuple(draw.textbbox(at, line, font=head)))
        y += height + ALERT_LINE_GAP
    label_box = draw_alert_label(draw, label.strip().upper(), left, bar[1])
    draw_mark(draw, mark)
    return image.convert("RGB"), {"bar": bar, "label": label_box, "lines": boxes}


def phone_sheet(thumbs: list[tuple[str, Image.Image]]) -> tuple[Image.Image, list]:
    """Each thumbnail at phone home-feed and search width, side by side, one row per
    thumbnail, on a light feed-grey background. Returns the sheet and each row's two
    slot boxes."""
    pad, gap, label_h = 16, 24, 26
    big_w, small_w = PHONE_WIDTHS
    big_h, small_h = round(big_w * H / W), round(small_w * H / W)
    row_h = label_h + big_h + pad
    sheet = Image.new("RGB", (pad + big_w + gap + small_w + pad, pad + row_h * len(thumbs)),
                      "#f2f2f2")
    draw = ImageDraw.Draw(sheet)
    label_font = font(16, LABEL_FONT)
    slots = []
    for i, (label, thumb) in enumerate(thumbs):
        y = pad + i * row_h
        draw.text((pad, y), label[:60], font=label_font, fill="#111111")
        big = (pad, y + label_h, pad + big_w, y + label_h + big_h)
        small = (big[2] + gap, y + label_h, big[2] + gap + small_w, y + label_h + small_h)
        sheet.paste(thumb.convert("RGB").resize((big_w, big_h), Image.LANCZOS), big[:2])
        sheet.paste(thumb.convert("RGB").resize((small_w, small_h), Image.LANCZOS), small[:2])
        slots.append((big, small))
    return sheet, slots


def has_face(block: dict) -> bool:
    return block.get("face") not in (None, False)


def variant_blocks(block: dict) -> list[tuple[str, dict]]:
    """[(letter, block)]: the hand-made "variants" laid over the base block, else the
    standard A (face) / B (A without the face) / C (plain) set when there is a face,
    else [("", block)]. The input is never changed."""
    base = {key: value for key, value in block.items() if key not in ("variants", "plain")}
    variants = block.get("variants")
    if variants:
        if len(variants) > len(VARIANT_LETTERS):
            raise ValueError(f"{len(variants)} variants; YouTube Test & compare takes at most "
                             f"{len(VARIANT_LETTERS)}")
        if not all(isinstance(variant, dict) for variant in variants):
            raise ValueError('each entry in "variants" is an object, {} for the base block as is')
        return [(letter, {**base, **variant}) for letter, variant in zip(VARIANT_LETTERS, variants)]
    if not has_face(base):
        return [("", base)]
    plain = block.get("plain") or {}
    if not isinstance(plain, dict):
        raise ValueError('"plain" is an object of overrides for the faceless C, like {"lines": [...]}')
    if base.get("style") == "alert" and not plain:      # a faceless alert C would repeat B
        return [("A", base), ("B", {**base, "face": False})]
    stripped = {key: value for key, value in base.items() if key not in LAYOUT_KEYS}
    return [("A", base), ("B", {**base, "face": False}), ("C", {**stripped, **plain})]


def flux_background(prompt: str, seed: int | None = None) -> Image.Image:
    cfg = common.load_config()
    payload = {"prompt": f"{prompt}, {PHOTO_STYLE}", "model": "flux-dev", "guidance": 3.5,
               "width": 1920, "height": 1088, "seed": seed or random.randint(1, 2**31)}
    data = common.http_json(f"{cfg['TIM_MEDIA_URL']}/image", payload, timeout=900)
    if len(data) < 1000:
        raise RuntimeError(f"Tim returned {len(data)} bytes, not an image")
    print(f"[yt_thumb] FLUX seed={payload['seed']}")
    return Image.open(io.BytesIO(data))


def background(spec: dict, base: Path, out: Path, cache: dict) -> Image.Image:
    """The block's photo, or a FLUX render shared by every variant with the same prompt."""
    if spec.get("bg"):
        return Image.open(base / spec["bg"])
    if not spec.get("prompt"):
        raise ValueError("need a prompt (FLUX on Tim) or bg (a photo)")
    key = (spec["prompt"], spec.get("seed"))
    if key not in cache:
        cache[key] = flux_background(spec["prompt"], spec.get("seed"))
        out.parent.mkdir(parents=True, exist_ok=True)   # thumb_variants/ may not exist yet
        cache[key].save(out.with_name(out.stem + "_bg.png"))
    return cache[key]


def build(spec: dict, out: Path, base: Path, work: Path, footage: Path | None = None,
          cache: dict | None = None) -> Image.Image:
    """Render one thumbnail block to `out`. Paths in the block resolve against `base`."""
    style = spec.get("style") or "classic"
    if style not in STYLES:
        raise ValueError(f"style '{style}' is not one of {', '.join(STYLES)}")
    source = background(spec, base, out, {} if cache is None else cache)
    face = spec.get("face")
    if has_face(spec):
        face = yt_thumb_face.load_face(face, base, footage, work)
    if style == "alert":
        image, _ = render_alert(source, spec["lines"], spec.get("label") or ALERT_LABEL,
                                spec.get("mark", MARK), face, spec.get("layers"),
                                spec.get("face_height", ALERT_FACE_HEIGHT), base)
    else:
        image, _ = render(source, spec["lines"], spec.get("accent", 1), spec.get("mark", MARK),
                          face, spec.get("font", DEFAULT_FONT),
                          spec.get("layers"), spec.get("text_y"),
                          spec.get("face_height", FACE_HEIGHT), base)
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out, quality=92)
    print(f"[yt_thumb] {out}  {out.stat().st_size // 1024}KB")
    return image


def warn(spec: dict, seen: set) -> None:
    """Lint each distinct set of words once (A and B share theirs)."""
    alert = spec.get("style") == "alert"
    label = spec.get("label") or ALERT_LABEL
    key = (tuple(spec["lines"]), spec.get("accent", 1), alert, label)
    if key in seen:
        return
    seen.add(key)
    lines = normalize(spec["lines"])
    warnings = lint_alert(lines, label) if alert else lint(lines, spec.get("accent", 1))
    for warning in warnings:
        print(f"[yt_thumb] warning: {warning}")


def label(letter: str, spec: dict) -> str:
    words = " / ".join(normalize(spec["lines"]))
    if has_face(spec):
        return f"{letter}: {words} + face"
    if spec.get("face") is False:
        return f"{letter}: same layout, no face"
    return f"{letter}: {words}" if letter else words


def save_phone_sheet(thumbs: list[tuple[str, Image.Image]], dest: Path) -> Path:
    sheet, _ = phone_sheet(thumbs)
    dest.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dest, quality=90)
    print(f"[yt_thumb] phone check: {dest}")
    return dest


def load_block(jdir: Path) -> dict:
    """job.json "thumbnail" (talking-head, countdown), else thumbnail.json (any job)."""
    job = jdir / "job.json"
    block = json.loads(job.read_text()).get("thumbnail") if job.exists() else None
    if not block and (jdir / "thumbnail.json").exists():
        block = json.loads((jdir / "thumbnail.json").read_text())
    return block or {}


def set_files(block: dict) -> list[str]:
    """The files a rendered Test & compare set leaves in out/thumb_variants/."""
    letters = [letter for letter, _ in variant_blocks(block) if letter]
    return [f"thumbnail_{letter}.jpg" for letter in letters] + ([PHONE_SHEET] if letters else [])


def kit_problems(jdir: Path, block: dict | None = None) -> list[str]:
    """Why the Test & compare set is not ready, for the publish kit checks (th.py kit,
    fv.py finish, lv.py finish). Empty when it is."""
    block = load_block(jdir) if block is None else block
    job = jdir.name
    if not block or not block.get("lines"):
        return [f"no thumbnail block: add one to job.json (or thumbnail.json), then "
                f"python3 scripts/yt_thumb.py --job {job}"]
    if not has_face(block) and not block.get("variants"):
        return ["the thumbnail block has no face, so there is no Test & compare set: add "
                "\"face\" (pose seconds in public/footage.mp4, or a PNG from assets/faces/)"]
    missing = [name for name in set_files(block) if not (jdir / "out" / SETS_DIR / name).exists()]
    if missing:
        return [f"Test & compare set not rendered ({', '.join(missing)}): "
                f"python3 scripts/yt_thumb.py --job {job}"]
    return []


def from_job(job_id: str) -> list[Path]:
    jdir = common.job_dir(job_id)
    block = load_block(jdir)
    if not block.get("lines"):
        common.die('no "thumbnail" block with "lines" in job.json or thumbnail.json')
    out_dir = jdir / "out"
    sets = out_dir / SETS_DIR
    cache, seen, made, thumbs = {}, set(), [], []
    for letter, spec in variant_blocks(block):
        warn(spec, seen)
        out = sets / f"thumbnail_{letter}.jpg" if letter else out_dir / "thumbnail.jpg"
        image = build(spec, out, jdir, jdir / "work" / "thumb", jdir / FOOTAGE, cache)
        made.append(out)
        thumbs.append((label(letter, spec), image))
    for letter in VARIANT_LETTERS:              # an old C must not get uploaded by mistake
        stale = sets / f"thumbnail_{letter}.jpg"
        if stale not in made:
            stale.unlink(missing_ok=True)
    if made[0].name != "thumbnail.jpg":
        shutil.copyfile(made[0], out_dir / "thumbnail.jpg")
        letters = [path.stem[-1] for path in made]
        print("[yt_thumb] thumbnail.jpg = A. In YouTube Studio > Test & compare, upload "
              f"{', '.join(letters[:-1])} and {letters[-1]} from out/thumb_variants/")
    save_phone_sheet(thumbs, sets / PHONE_SHEET)
    for problem in kit_problems(jdir, block):
        print(f"[yt_thumb] KIT: {problem}")
    return made


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--job")
    parser.add_argument("--lines", nargs="+")
    parser.add_argument("--accent", type=int, default=1, help="index of the banner line")
    parser.add_argument("--prompt")
    parser.add_argument("--bg")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--font", choices=sorted(FONTS), default=DEFAULT_FONT)
    parser.add_argument("--mark", default=MARK)
    parser.add_argument("--face", help="PNG cutout or frame, or seconds into --footage")
    parser.add_argument("--footage", help="video to take a --face time from")
    parser.add_argument("--out", default="thumbnail.jpg")
    parser.add_argument("--style", choices=STYLES, default="classic")
    parser.add_argument("--label", default=ALERT_LABEL, help="alert style label strip")
    args = parser.parse_args()
    if args.job:
        from_job(args.job)
    elif args.lines:
        out = Path(args.out)
        spec = {"lines": args.lines, "accent": args.accent, "prompt": args.prompt,
                "bg": args.bg, "seed": args.seed, "font": args.font, "face": args.face,
                "mark": args.mark, "style": args.style, "label": args.label}
        warn(spec, set())
        image = build(spec, out, Path.cwd(), out.parent / f"{out.stem}_work",
                      Path(args.footage) if args.footage else None)
        save_phone_sheet([(label("", spec), image)], out.with_name(out.stem + "_phone.jpg"))
    else:
        parser.error("give --job or --lines")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError) as err:
        print(f"[yt_thumb] {err}", file=sys.stderr)
        sys.exit(1)
