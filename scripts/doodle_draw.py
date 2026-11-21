"""Drawing kit for the Stickman Swordfish doodle graphics (doodle.py): hand-lettered type,
marker strokes with a slight wobble, the red X / green check marks, and the clean-up
that lets a FLUX object on "white" sit on a truly white page. Pure Pillow: the Mac mini's
system python has no numpy."""
import math
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

# Patrick Hand (SIL OFL, assets/fonts/LICENSE-PatrickHand-OFL.txt): the closest open
# match to the reference channel's lettering. A stroke the colour of the fill thickens it
# into the marker weight the reference uses.
FONT = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "PatrickHand-Regular.ttf"

DEFAULT_STYLE = {
    "paper": "#ffffff", "ink": "#151515", "red": "#d6302a", "green": "#2ea043",
    "orange": "#f08c28", "yellow": "#f5c518", "blue": "#4a8fd6", "pink": "#ef8f7f",
    "teal": "#3fb0a6", "grey": "#9a9a9a",
}

# FLUX's "pure white" comes back between about 238 and 250. Anything whose darkest
# channel clears WHITE_HI becomes paper; WHITE_LO to WHITE_HI fades into it.
WHITE_LO, WHITE_HI = 226, 242
CONTENT_THRESHOLD = 235


def style_of(theme_style=None):
    return {**DEFAULT_STYLE, **(theme_style or {})}


def rgb(color):
    if isinstance(color, (tuple, list)):
        return tuple(color[:3])
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def unit(size):
    """Pixels per point of a 1080-line frame: every size in doodle.py is written for 1080."""
    return min(size) / 1080


@lru_cache(maxsize=64)
def font(size):
    return ImageFont.truetype(str(FONT), max(8, int(size)))


def stroke_for(size):
    return max(1, round(size * 0.035))


def text_box(text, size):
    """(width, height) of text drawn at size, stroke included."""
    left, top, right, bottom = font(size).getbbox(text, stroke_width=stroke_for(size))
    return right - left, bottom - top


def line_pitch(size, gap=0.12):
    return size * (1.0 + gap)


def fit_size(lines, max_w, max_h, cap, gap=0.12, floor=14):
    """Largest size (at most cap) at which every line fits max_w and the stack max_h."""
    lines = [line for line in lines if line] or [" "]
    lo, hi = floor, max(floor, int(cap))
    while lo < hi:
        mid = (lo + hi + 1) // 2
        wide = max(text_box(line, mid)[0] for line in lines)
        tall = line_pitch(mid, gap) * (len(lines) - 1) + text_box("HQgy", mid)[1]
        if wide <= max_w and tall <= max_h:
            lo = mid
        else:
            hi = mid - 1
    return lo


def draw_text(draw, text, xy, size, colour, anchor="mm"):
    draw.text(xy, text, font=font(size), fill=colour, anchor=anchor,
              stroke_width=stroke_for(size), stroke_fill=colour)


def _wobble(points, rng, amount):
    """A marker line is never ruler straight: bow each segment by a smooth sine whose
    phase is seeded, so a restage draws the same wobble again."""
    if not rng or amount <= 0:
        return list(points)
    out = [points[0]]
    for (ax, ay), (bx, by) in zip(points, points[1:]):
        length = math.hypot(bx - ax, by - ay)
        steps = max(2, int(length / 18))
        nx, ny = (-(by - ay) / length, (bx - ax) / length) if length else (0.0, 0.0)
        phase, waves = rng.uniform(0, math.tau), rng.uniform(0.6, 1.4)
        for k in range(1, steps + 1):
            t = k / steps
            off = amount * math.sin(math.pi * t) * math.sin(math.tau * waves * t + phase) * 0.6
            out.append((ax + (bx - ax) * t + nx * off, ay + (by - ay) * t + ny * off))
    return out


def stroke(draw, points, colour, width, rng=None, wobble=0.0):
    """A round-capped marker stroke through points."""
    pts = _wobble([tuple(map(float, p)) for p in points], rng, wobble)
    width = max(1, round(width))
    draw.line(pts, fill=colour, width=width, joint="curve")
    for x, y in (pts[0], pts[-1]):
        r = width / 2
        draw.ellipse([x - r, y - r, x + r, y + r], fill=colour)


def triangle(draw, centre, size, angle, colour, outline=None, width=0):
    """A filled arrowhead of the given size pointing at angle (radians, y down)."""
    cx, cy = centre
    pts = [(cx + size * math.cos(angle + a), cy + size * math.sin(angle + a))
           for a in (0.0, 2.45, -2.45)]
    draw.polygon(pts, fill=colour)
    if outline and width:
        draw.line(pts + [pts[0]], fill=outline, width=width, joint="curve")


def arrow(draw, start, end, colour, width, rng=None, head=None):
    """A marker arrow from start to end, head on the end."""
    head = head or width * 2.6
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    base = (end[0] - head * 0.9 * math.cos(angle), end[1] - head * 0.9 * math.sin(angle))
    stroke(draw, [start, base], colour, width, rng, wobble=width * 0.25)
    triangle(draw, (end[0] - head * 0.35 * math.cos(angle), end[1] - head * 0.35 * math.sin(angle)),
             head, angle, colour)


def mark_x(draw, box, colour, width, rng=None):
    x0, y0, x1, y1 = box
    inset = 0.08 * min(x1 - x0, y1 - y0)
    stroke(draw, [(x0 + inset, y0 + inset), (x1 - inset, y1 - inset)], colour, width, rng, width * 0.6)
    stroke(draw, [(x1 - inset, y0 + inset), (x0 + inset, y1 - inset)], colour, width, rng, width * 0.6)


def mark_no(draw, centre, radius, colour, width, rng=None):
    """The red ring with a slash: the "never" sign round an object."""
    cx, cy = centre
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], outline=colour,
                 width=round(width))
    r = radius * 0.70
    stroke(draw, [(cx - r, cy - r), (cx + r, cy + r)], colour, width, rng, width * 0.4)


def mark_check(draw, centre, size, colour, width, rng=None):
    cx, cy = centre
    stroke(draw, [(cx - size * 0.48, cy + size * 0.02), (cx - size * 0.12, cy + size * 0.38),
                  (cx + size * 0.52, cy - size * 0.46)], colour, width, rng, width * 0.4)


def mark_star(draw, centre, size, fill, ink, width):
    """A four-point sparkle: the "this is the good one" glint."""
    cx, cy = centre
    pts = []
    for k in range(8):
        r = size if k % 2 == 0 else size * 0.32
        a = -math.pi / 2 + k * math.pi / 4
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    draw.polygon(pts, fill=fill)
    draw.line(pts + [pts[0]], fill=ink, width=max(1, round(width)), joint="curve")


def whiten(picture):
    """Push FLUX's near-white page to pure white so the object sits on the paper with no
    grey box round it. Colour and ink are left alone."""
    img = picture.convert("RGB")
    r, g, b = img.split()
    darkest = ImageChops.darker(ImageChops.darker(r, g), b)
    span = WHITE_HI - WHITE_LO
    mask = darkest.point(lambda v: 0 if v < WHITE_LO else 255 if v >= WHITE_HI
                         else round((v - WHITE_LO) * 255 / span))
    return Image.composite(Image.new("RGB", img.size, (255, 255, 255)), img, mask)


def content_box(picture, margin=0.04):
    """The box round whatever is drawn on the page, with a little air. The whole picture
    when nothing is found."""
    img = picture.convert("RGB")
    r, g, b = img.split()
    darkest = ImageChops.darker(ImageChops.darker(r, g), b)
    box = darkest.point(lambda v: 255 if v < CONTENT_THRESHOLD else 0).getbbox()
    w, h = img.size
    if not box:
        return (0, 0, w, h)
    pad = round(margin * max(w, h))
    return (max(0, box[0] - pad), max(0, box[1] - pad), min(w, box[2] + pad), min(h, box[3] + pad))


def place(base, picture, box):
    """Clean the picture, trim it to its object and fit it, centred, inside box on base.
    Returns the rectangle the object actually occupies."""
    x0, y0, x1, y1 = box
    clean = whiten(picture)
    clean = clean.crop(content_box(clean))
    scale = min((x1 - x0) / clean.width, (y1 - y0) / clean.height)
    w, h = max(1, round(clean.width * scale)), max(1, round(clean.height * scale))
    left, top = round((x0 + x1 - w) / 2), round((y0 + y1 - h) / 2)
    base.paste(clean.resize((w, h), Image.LANCZOS), (left, top))
    return (left, top, left + w, top + h)


def canvas(size, style):
    return Image.new("RGB", size, rgb(style["paper"]))


def rotated_text(text, size, colour):
    """Text on its own transparent tile, turned to read bottom to top (a y-axis label)."""
    w, h = text_box(text, size)
    tile = Image.new("RGBA", (w + 8, h + 8), (0, 0, 0, 0))
    draw_text(ImageDraw.Draw(tile), text, (tile.width / 2, tile.height / 2), size, colour)
    return tile.rotate(90, expand=True)
