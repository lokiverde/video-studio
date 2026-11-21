"""First-frame rules for Shorts: the opener card, the banner look, and the lint.

Tony, 2026-11-14: "the first frame of my videos all look the same with my picture." Twelve
Shorts in a row opened on one template (yellow banner, navy panel, Tony in a box). In the
Shorts feed frame 1 autoplays and decides the swipe; on the channel grid, in search and on
the Shorts shelf it is the thumbnail. So a Short can open on its own payoff:

    "opener": {"type": "number", "text": "100,000,000\\nSQ FT", "sub": "PLANNED", "seconds": 1.2}
    "opener": {"type": "photo", "image": "public/sat.jpg", "fit": "blur", "text": "SPACE IS COLD"}
    "opener": {"type": "location"}         Tony's own frame, no card (the set itself is new)

Types: number (a card, needs text), photo / broll / archive / receipt / prop (need an image,
path relative to the job folder; text optional), location / closeup (Tony's own frame).
The card plays full frame over Tony's audio for `seconds` (default 1.2), then the Short cuts
to him. A card with text is the hook, so the banner defaults to none on it.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent.parent
ANTON = ROOT / "assets/fonts/Anton-Regular.ttf"
W, H = 1080, 1920
CARD_BG = "#0B1220"
WHITE = "#FFFFFF"
OPENER_SECONDS, MIN_OPENER_S, MAX_OPENER_S = 1.2, 0.6, 2.5
IMAGE_TYPES = ("photo", "broll", "archive", "receipt", "prop")
TONY_TYPES = ("location", "closeup")
TYPES = ("number", *IMAGE_TYPES, *TONY_TYPES)
TEXT_MAX_W = W - 140
CENTER_Y = 860                 # text block center: clear of the Shorts UI top and bottom
MAX_HOOK_WORDS = 6
BAND_ALPHA = 150               # the dark band behind words on a photo, out of 255
FILLERS = {"so", "um", "uh", "okay", "ok", "alright", "and", "well", "yeah", "like", "but",
           "now", "anyway", "basically", "right"}


def hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def opener_seconds(opener: dict | None) -> float:
    """How long the card holds. Tony's own frame needs no hold."""
    if not opener or opener.get("type") in TONY_TYPES:
        return 0
    return min(max(float(opener.get("seconds", OPENER_SECONDS)), MIN_OPENER_S), MAX_OPENER_S)


def banner_name(short: dict, job: dict) -> str:
    """Short's own look, else none on a card that carries text, else the job's, else the layout's."""
    if short.get("banner"):
        return short["banner"]
    if (short.get("opener") or {}).get("text"):
        return "none"
    if job.get("shorts_banner"):
        return job["shorts_banner"]
    return "brokerage" if job.get("layout") == "split" else "default"


def cover_name(n: int) -> str:
    """The frame-1 still Tony uploads as the Short's custom thumbnail in desktop Studio."""
    return f"short_{n}_cover.jpg"


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(ANTON), size, layout_engine=ImageFont.Layout.BASIC)


def _fit(draw: ImageDraw.ImageDraw, line: str, start: int) -> ImageFont.FreeTypeFont:
    size = start
    while size > 60 and draw.textlength(line, font=_font(size)) > TEXT_MAX_W:
        size -= 6
    return _font(size)


def _draw_text(image: Image.Image, text: str, sub: str | None, accent: str, start: int,
               band: bool = False) -> Image.Image:
    """First line is the payoff at poster size, the rest a size down, sub in the accent color.
    The block centers on CENTER_Y, clear of the Shorts UI at the top and the bottom. On a
    photo (`band`) a dark see-through band sits behind the words so they read on any picture."""
    draw = ImageDraw.Draw(image)
    lines = [line for line in text.upper().split("\n") if line.strip()]
    rows = [(line, _fit(draw, line, start if i == 0 else start * 2 // 3), WHITE) for i, line in enumerate(lines)]
    if sub:
        rows.append((sub.upper(), _fit(draw, sub.upper(), 84), accent))
    heights = [int(face.size * 1.12) for _, face, _ in rows]
    y = CENTER_Y - sum(heights) // 2
    if band:
        shade = Image.new("RGBA", image.size)
        ImageDraw.Draw(shade).rectangle([0, y - 50, W, y + sum(heights) + 40], fill=(0, 0, 0, BAND_ALPHA))
        image = Image.alpha_composite(image.convert("RGBA"), shade).convert("RGB")
        draw = ImageDraw.Draw(image)
    for (line, face, color), height in zip(rows, heights):
        width = draw.textlength(line, font=face)
        draw.text(((W - width) / 2, y), line, font=face, fill=color,
                  stroke_width=max(4, face.size // 28), stroke_fill="#000000")
        y += height
    return image


def _photo(path: Path, fit: str, focus: tuple[float, float]) -> Image.Image:
    source = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    if fit == "blur":
        back = ImageOps.fit(source, (W, H)).filter(ImageFilter.GaussianBlur(40))
        front = ImageOps.contain(source, (W, H))
        back.paste(front, ((W - front.width) // 2, (H - front.height) // 2))
        return back
    return ImageOps.fit(source, (W, H), centering=focus)


def opener_png(opener: dict | None, jdir: Path, path: Path, accent: str = "#FACC15") -> Path | None:
    """1080x1920 card for the first seconds of a Short, or None when Tony's frame opens it."""
    if not opener:
        return None
    kind = opener.get("type")
    if kind not in TYPES:
        raise ValueError(f"unknown opener type '{kind}' (use one of {', '.join(TYPES)})")
    if kind in TONY_TYPES:
        return None
    text = opener.get("text", "")
    if kind == "number":
        if not text.strip():
            raise ValueError("a number opener needs text, the number itself")
        card = Image.new("RGB", (W, H), CARD_BG)
        card = _draw_text(card, text, opener.get("sub"), accent, 360)
    else:
        image = jdir / opener.get("image", "")
        if not opener.get("image") or not image.is_file():
            raise ValueError(f"opener image not found: {image}")
        focus = tuple(opener.get("focus", (0.5, 0.5)))
        card = _photo(image, opener.get("fit", "cover"), focus)
        if text.strip():
            card = _draw_text(card, text, opener.get("sub"), accent, 300, band=True)
    card.save(path)
    return path


def lint(shorts: list[dict]) -> list[tuple[int, str]]:
    """(short number, warning) for each habit that makes Shorts look alike or open slow."""
    warnings = []
    previous = None
    for n, short in enumerate(shorts, 1):
        first = (short.get("start", "").split() or [""])[0].lower().strip(",.!?")
        if first in FILLERS:
            warnings.append((n, f"starts on the lead-in '{first}': start one word later, mid-thought"))
        words = len(short.get("hook", "").split())
        if words > MAX_HOOK_WORDS:
            warnings.append((n, f"hook is {words} words: 2 to {MAX_HOOK_WORDS} read in a glance"))
        kind = (short.get("opener") or {}).get("type")
        if not kind:
            warnings.append((n, "no opener: frame 1 is the shared template. Open on the payoff "
                                "(number, photo, receipt) or Tony on a new set (location)"))
        shown = kind or "template"
        if previous == shown:
            warnings.append((n, f"opens the same way as #{n - 1} ({shown}): rotate the opener type"))
        previous = shown
    return warnings
