"""Stickman Swordfish graphics (docs/swordfish.md): doodle shots on white paper.

A shots entry carries a "graphic" block in a theme with "graphics": "doodle". FLUX draws
the objects (one isolated thing on white, gen_images.graphic_one); this module draws the
page round them, the red X / green check marks and the hand-lettered labels, so both
cuts and a restage redraw it without another FLUX call.

  icon   one object, an optional mark (x, check, no, arrow, question, star), a label
  pair   two objects side by side (stacked on 9:16), each with a mark and a label,
         joined by vs, arrow, updown or equals
  chain  2 to 5 objects in a row joined by red arrowheads: a food chain, a sequence
  cycle  3 or 4 objects round a loop of red arrows
  bars   a hand-drawn bar chart, the big bar called out ("10X") with a red arrow
  line   a hand-drawn line graph, notes on points, one point circled in red
  meter  a progress bar filled to a percent, the number big under it
  words  hand-lettered punch type, the accent line in red

Any shot, graphic or not, can also carry "tag" (a date label, top right) and "note"
(a small disclaimer, top left): overlay() draws them.
"""
import math
import random

from PIL import Image, ImageDraw

import doodle_draw as d

TYPES = ("icon", "pair", "chain", "cycle", "bars", "line", "meter", "words")
MARKS = ("x", "check", "no", "arrow", "question", "star")
JOINS = ("none", "vs", "arrow", "updown", "equals")
TONES = {"good": "green", "bad": "red", "warn": "orange", "neutral": "blue"}
ICON_PICTURE = (768, 768)    # every object, shared by both cuts
# Phrased positively: FLUX ignores negations (docs/leg-watch.md).
ISOLATE = ("one single object alone, centred on a plain flat pure white background, "
           "wide empty white margins all around it")
FINAL_LANDSCAPE = (1920, 1080)
FINAL_PORTRAIT = (1080, 1920)
# Captions are off on 16:9 in this format; on 9:16 the caption band and the platform UI
# start just under this fraction of the frame, so nothing is drawn below it.
PORTRAIT_SAFE = 0.78
LABEL_MAX, TAG_MAX, NOTE_MAX, WORDS_MAX = 24, 14, 300, 48
LABEL_SIZE = 66          # points at 1080: label type under a picture
FILL = 0.82              # how much of its box an object fills


# ---- validation -----------------------------------------------------------------------

def _need(ok, message):
    if not ok:
        raise ValueError(message)


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _short(text, what="label", limit=LABEL_MAX):
    _need(text is None or isinstance(text, str), f"{what} must be text, got {text!r}")
    _need(len(text or "") <= limit,
          f"{what} {text!r} is too long: keep it to 1 to 3 words, {limit} characters at most")


def _mark_ok(mark):
    _need(mark in (None, "") + MARKS, f"mark {mark!r} unknown (have: {', '.join(MARKS)})")


def _index_ok(value, count, what):
    _need(value is None or (isinstance(value, int) and not isinstance(value, bool)
                            and 1 <= value <= count),
          f"{what} must be a position from 1 to {count}, got {value!r}")


def _items_ok(g, lo, hi):
    items = g.get("items")
    _need(isinstance(items, list) and lo <= len(items) <= hi,
          f"'{g['type']}' needs 'items': {lo}{'' if lo == hi else f' to {hi}'} of "
          f"{{\"prompt\", \"label\"}}")
    for item in items:
        _need(isinstance(item, dict) and str(item.get("prompt") or "").strip(),
              f"every {g['type']} item needs a 'prompt'")
        _short(item.get("label"))
        _mark_ok(item.get("mark"))


def _check_icon(g, prompt):
    _need(prompt, "an 'icon' needs a 'prompt' for its object")
    _mark_ok(g.get("mark"))
    _short(g.get("label"))


def _check_pair(g, _prompt):
    _items_ok(g, 2, 2)
    _need(g.get("join", "none") in JOINS, f"pair 'join' must be one of {', '.join(JOINS)}")


def _check_bars(g, _prompt):
    bars = g.get("bars")
    _need(isinstance(bars, list) and 2 <= len(bars) <= 5,
          "'bars' needs 'bars': 2 to 5 of {\"label\", \"value\"}")
    for bar in bars:
        _need(isinstance(bar, dict) and _number(bar.get("value")) and bar["value"] >= 0,
              f"every bar needs a 'value' of 0 or more, got {bar!r}")
        _short(bar.get("label"))
    _need(max(bar["value"] for bar in bars) > 0, "at least one bar needs a value above 0")
    _index_ok(g.get("highlight"), len(bars), "bars 'highlight'")
    _short(g.get("callout"), "callout")


def _check_line(g, _prompt):
    points = g.get("points")
    _need(isinstance(points, list) and 2 <= len(points) <= 12 and all(map(_number, points)),
          "'line' needs 'points': 2 to 12 numbers")
    _index_ok(g.get("circle"), len(points), "line 'circle'")
    for note in g.get("notes") or []:
        _need(isinstance(note, dict), f"a line note is {{\"at\", \"text\"}}, got {note!r}")
        _index_ok(note.get("at"), len(points), "a line note's 'at'")
        _short(note.get("text"), "note text")
    _short(g.get("x_label"), "x_label")
    _short(g.get("y_label"), "y_label")


def _check_meter(g, _prompt):
    _need(_number(g.get("value")) and 0 <= g["value"] <= 100, "a 'meter' needs a 'value' from 0 to 100")
    _need(g.get("tone", "good") in TONES, f"meter 'tone' must be one of {', '.join(TONES)}")
    _short(g.get("text"), "meter text")


def _check_words(g, _prompt):
    text = str(g.get("text") or "")
    _need(text.replace("|", "").strip(), "a 'words' graphic needs 'text'")
    _need(len(text.replace("|", "")) <= WORDS_MAX, f"'words' text is over {WORDS_MAX} characters")
    _index_ok(g.get("accent"), len(_lines(text)), "words 'accent'")


_CHECKS = {"icon": _check_icon, "pair": _check_pair, "chain": lambda g, _p: _items_ok(g, 2, 5),
           "cycle": lambda g, _p: _items_ok(g, 3, 4), "bars": _check_bars, "line": _check_line,
           "meter": _check_meter, "words": _check_words}


def validate(graphic, prompt=""):
    """Raise ValueError with a plain message when a doodle graphic cannot render."""
    _need(isinstance(graphic, dict), f"graphic must be an object, got {graphic!r}")
    kind = graphic.get("type")
    _need(kind in TYPES, f"doodle graphic type {kind!r} unknown (have: {', '.join(TYPES)})")
    _CHECKS[kind](graphic, (prompt or "").strip())


def validate_overlays(spec):
    tag, note = spec.get("tag"), spec.get("note")
    _need(tag is None or (isinstance(tag, str) and tag.strip()), f"'tag' must be text, got {tag!r}")
    _short(tag, "tag", TAG_MAX)
    _need(note is None or isinstance(note, str), f"'note' must be text, got {note!r}")
    _short(note, "note", NOTE_MAX)


# ---- what FLUX draws ------------------------------------------------------------------

def _isolated(prompt):
    return f"{prompt.strip().rstrip('.,')}, {ISOLATE}"


def pictures(graphic, prompt, size):
    """[(name, prompt, (w, h), shared)]: the objects this graphic needs. All are shared
    by both cuts; none is canvas-shaped, so there is never a backdrop to hold on."""
    kind = graphic["type"]
    if kind == "icon" or (kind == "meter" and (prompt or "").strip()):
        return [("icon", _isolated(prompt), ICON_PICTURE, True)]
    if kind in ("pair", "chain", "cycle"):
        return [(f"item{i + 1}", _isolated(item["prompt"]), ICON_PICTURE, True)
                for i, item in enumerate(graphic["items"])]
    return []


def has_backdrop(graphic, prompt=""):
    return False


# ---- drawing --------------------------------------------------------------------------

def render(graphic, size, style=None, pics=(), cutout=None, seed=0):
    """Draw one doodle shot at size. pics follow the order of pictures(). cutout is unused
    (the signature matches army.render, gen_images calls either)."""
    style = d.style_of(style)
    base = d.canvas(size, style)
    _LAYOUTS[graphic["type"]](base, graphic, style, list(pics), random.Random(seed))
    return base


def _portrait(size):
    return size[1] > size[0]


def _area(size):
    w, h = size
    if _portrait(size):
        return (w * 0.07, h * 0.08, w * 0.93, h * PORTRAIT_SAFE)
    return (w * 0.06, h * 0.07, w * 0.94, h * 0.93)


def _c(style, name):
    return d.rgb(style[name])


def _lines(text):
    return [line.strip() for line in str(text).split("|") if line.strip()]


def _label(draw, text, centre_x, top, max_w, style, cap):
    """Hand-lettered caps, centred under something. Returns the bottom edge."""
    text = (text or "").strip().upper()
    if not text:
        return top
    size = d.fit_size([text], max_w, cap * 1.4, cap)
    d.draw_text(draw, text, (centre_x, top), size, _c(style, "ink"), anchor="mt")
    return top + d.text_box(text, size)[1]


def _mark(draw, mark, box, style, rng, frame):
    """Draw a mark over an object's box. Returns the lowest y the mark reaches."""
    if not mark:
        return box[3]
    x0, y0, x1, y1 = box
    s = min(x1 - x0, y1 - y0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    width = max(6, s * 0.05)
    red, fw, fh = _c(style, "red"), frame[0], frame[1]

    def corner(r):
        return (min(x1 - s * 0.04, fw - r - fw * 0.02), max(y0 + s * 0.10, r + fh * 0.02))

    if mark == "x":
        d.mark_x(draw, box, red, width, rng)
    elif mark == "no":
        r = s * 0.64
        d.mark_no(draw, (cx, cy), r, red, width, rng)
        return cy + r + width
    elif mark == "check":
        d.mark_check(draw, corner(s * 0.26), s * 0.34, _c(style, "green"), width * 1.2, rng)
    elif mark == "question":
        d.draw_text(draw, "?", corner(s * 0.20), round(s * 0.40), red)
    elif mark == "star":
        d.mark_star(draw, corner(s * 0.17), s * 0.16, _c(style, "yellow"), _c(style, "ink"), width * 0.5)
    elif mark == "arrow":
        start = (min(x1 + s * 0.30, fw * 0.96), max(y0 - s * 0.02, fh * 0.05))
        d.arrow(draw, start, (x1 - s * 0.10, cy - s * 0.08), red, width, rng)
    return box[3]


def _square(cx, cy, side):
    return (cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2)


def _rect(cx, cy, w, h):
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


WIDE = 1.7   # a box may be this much wider than tall, so a house or a slab fills the width


def _place_object(base, draw, pic, box, mark, style, rng):
    """One object and its mark inside box. Returns the lowest y either reaches, which is
    where the label goes."""
    if mark == "no":     # the ring sits round a square, with room inside it
        side = min(box[2] - box[0], box[3] - box[1]) * 0.78
        box = _square((box[0] + box[2]) / 2, (box[1] + box[3]) / 2, side)
    placed = d.place(base, pic, box)
    return max(placed[3], _mark(draw, mark, box if mark == "no" else placed, style, rng, base.size))


def _labels_under(draw, items, centres, bottoms, max_w, style, u, shared=True):
    """Labels under a row of objects: on one shared baseline (a row reads as a row), or
    each under its own object (a column)."""
    line = max(bottoms) if shared else None
    for item, (cx, _), bottom in zip(items, centres, bottoms):
        _label(draw, item.get("label"), cx, (line if shared else bottom) + 14 * u, max_w, style,
               LABEL_SIZE * u)


def _icon(base, g, style, pics, rng):
    draw = ImageDraw.Draw(base)
    x0, y0, x1, y1 = _area(base.size)
    u = d.unit(base.size)
    label_h = 110 * u if (g.get("label") or "").strip() else 0
    h = (y1 - y0 - label_h) * FILL
    box = _rect((x0 + x1) / 2, y0 + (y1 - y0 - label_h) / 2, min((x1 - x0) * 0.9, h * WIDE), h)
    bottom = _place_object(base, draw, pics[0], box, g.get("mark"), style, rng)
    _label(draw, g.get("label"), (x0 + x1) / 2, bottom + 14 * u, x1 - x0, style, LABEL_SIZE * u)


def _pair(base, g, style, pics, rng):
    draw = ImageDraw.Draw(base)
    x0, y0, x1, y1 = _area(base.size)
    u = d.unit(base.size)
    items = g["items"]
    label_h = 110 * u if any((i.get("label") or "").strip() for i in items) else 0
    portrait = _portrait(base.size)
    if portrait:
        join_h = (y1 - y0) * 0.10
        row_h = (y1 - y0 - join_h) / 2
        h = (row_h - label_h) * FILL
        w, label_w = min((x1 - x0) * 0.9, h * WIDE), x1 - x0
        centres = [((x0 + x1) / 2, y0 + (row_h - label_h) / 2 + k * (row_h + join_h)) for k in (0, 1)]
        join_at = ((x0 + x1) / 2, y0 + row_h + join_h / 2)
    else:
        join_w = (x1 - x0) * 0.14
        label_w = (x1 - x0 - join_w) / 2
        h = (y1 - y0 - label_h) * FILL
        w = min(label_w * 0.92, h * WIDE)
        cy = y0 + (y1 - y0 - label_h) / 2
        centres = [(x0 + label_w / 2, cy), (x1 - label_w / 2, cy)]
        join_at = ((x0 + x1) / 2, cy)
    bottoms = [_place_object(base, draw, pic, _rect(cx, cy, w, h), item.get("mark"), style, rng)
               for item, pic, (cx, cy) in zip(items, pics, centres)]
    _labels_under(draw, items, centres, bottoms, label_w, style, u, shared=not portrait)
    _join(draw, g.get("join", "none"), join_at, min(w, h), style, rng, portrait, u)


def _join(draw, join, at, side, style, rng, portrait, u):
    cx, cy = at
    red, width = _c(style, "red"), 12 * u
    span = min(side * 0.36, 180 * u)
    if join == "vs":
        d.draw_text(draw, "VS", at, round(84 * u), _c(style, "ink"))
    elif join == "arrow":
        start, end = ((cx, cy - span), (cx, cy + span)) if portrait else ((cx - span, cy), (cx + span, cy))
        d.arrow(draw, start, end, red, width, rng)
    elif join == "updown":
        d.arrow(draw, (cx, cy), (cx, cy - span), red, width, rng)
        d.arrow(draw, (cx, cy), (cx, cy + span), red, width, rng)
    elif join == "equals":
        for dy in (-span * 0.18, span * 0.18):
            d.stroke(draw, [(cx - span * 0.45, cy + dy), (cx + span * 0.45, cy + dy)], red, width, rng, 2 * u)


def _chain(base, g, style, pics, rng):
    draw = ImageDraw.Draw(base)
    x0, y0, x1, y1 = _area(base.size)
    u = d.unit(base.size)
    items, n = g["items"], len(g["items"])
    label_h = 100 * u if any((i.get("label") or "").strip() for i in items) else 0
    portrait = _portrait(base.size)
    red = _c(style, "red")
    if portrait:
        gap = 70 * u
        row_h = (y1 - y0 - (n - 1) * gap) / n
        h = (row_h - label_h) * 0.92
        w, label_w = min((x1 - x0) * 0.8, h * 2.2), x1 - x0
        centres = [((x0 + x1) / 2, y0 + k * (row_h + gap) + (row_h - label_h) / 2) for k in range(n)]
        heads = [(((x0 + x1) / 2, y0 + (k + 1) * row_h + k * gap + gap / 2), math.pi / 2)
                 for k in range(n - 1)]
    else:
        gap = 90 * u
        slot = (x1 - x0 - (n - 1) * gap) / n
        h = min((y1 - y0 - label_h) * 0.62, slot)
        w, label_w = slot * 0.94, slot
        cy = y0 + (y1 - y0 - label_h) / 2
        centres = [(x0 + slot / 2 + k * (slot + gap), cy) for k in range(n)]
        heads = [((x0 + (k + 1) * slot + k * gap + gap / 2, cy), 0.0) for k in range(n - 1)]
    bottoms = [_place_object(base, draw, pic, _rect(cx, cy, w, h), item.get("mark"), style, rng)
               for item, pic, (cx, cy) in zip(items, pics, centres)]
    _labels_under(draw, items, centres, bottoms, label_w, style, u, shared=not portrait)
    for mid, angle in heads:
        d.triangle(draw, mid, 34 * u, angle, red)


def _cycle(base, g, style, pics, rng):
    draw = ImageDraw.Draw(base)
    x0, y0, x1, y1 = _area(base.size)
    u = d.unit(base.size)
    items, n = g["items"], len(g["items"])
    label_h = 90 * u if any((i.get("label") or "").strip() for i in items) else 0
    dim = min(x1 - x0, y1 - y0 - label_h)
    side = dim * (0.30 if n == 3 else 0.27)
    radius = dim * (0.36 if n == 3 else 0.34)
    angles = [-90 + k * 360 / n for k in range(n)]
    spots = [(radius * math.cos(math.radians(a)), radius * math.sin(math.radians(a))) for a in angles]
    top = min(y for _, y in spots) - side / 2
    bottom = max(y for _, y in spots) + side / 2 + label_h
    cx = (x0 + x1) / 2
    cy = y0 + ((y1 - y0) - (bottom - top)) / 2 - top
    red, width = _c(style, "red"), 12 * u
    gap_deg = math.degrees(math.asin(min(1.0, side * 0.66 / radius)))
    ring = [cx - radius, cy - radius, cx + radius, cy + radius]
    for k, a in enumerate(angles):
        start, end = a + gap_deg, angles[(k + 1) % n] + (360 if k == n - 1 else 0) - gap_deg
        draw.arc(ring, start, end, fill=red, width=round(width))
        tip = math.radians(end)
        d.triangle(draw, (cx + radius * math.cos(tip), cy + radius * math.sin(tip)), 28 * u,
                   tip + math.pi / 2, red)
    for item, pic, (sx, sy) in zip(items, pics, spots):
        box = _square(cx + sx, cy + sy, side)
        draw.rectangle(box, fill=_c(style, "paper"))
        bottom = _place_object(base, draw, pic, box, item.get("mark"), style, rng)
        _label(draw, item.get("label"), cx + sx, bottom + 14 * u, side * 1.4, style, LABEL_SIZE * u)


def _bars(base, g, style, pics, rng):
    draw = ImageDraw.Draw(base)
    x0, y0, x1, y1 = _area(base.size)
    u = d.unit(base.size)
    bars, n = g["bars"], len(g["bars"])
    values = [b["value"] for b in bars]
    hi = (g.get("highlight") or values.index(max(values)) + 1) - 1
    callout = (g.get("callout") or "").strip().upper()
    head = 190 * u if callout else 40 * u
    px0, px1 = x0 + (x1 - x0) * 0.12, x1 - (x1 - x0) * 0.12
    py0, base_y = y0 + head, y1 - 100 * u
    slot = (px1 - px0) / n
    ink, width = _c(style, "ink"), 9 * u
    cycle = [_c(style, name) for name in ("blue", "pink", "teal", "grey")]
    tops = []
    for k, bar in enumerate(bars):
        h = (base_y - py0) * bar["value"] / max(values)
        bx = px0 + slot * (k + 0.5)
        rect = (bx - slot * 0.28, base_y - max(h, 3 * u if bar["value"] else 0), bx + slot * 0.28, base_y)
        colour = _c(style, "red") if k == hi else cycle[(k if k < hi else k - 1) % len(cycle)]
        draw.rectangle(rect, fill=colour, outline=ink, width=round(width * 0.8))
        tops.append((bx, rect[1]))
        _label(draw, bar.get("label"), bx, base_y + 18 * u, slot * 0.94, style, 56 * u)
    d.stroke(draw, [(px0 - 30 * u, base_y), (px1 + 30 * u, base_y)], ink, width, rng, 3 * u)
    d.stroke(draw, [(px0 - 30 * u, base_y), (px0 - 30 * u, py0 - 20 * u)], ink, width, rng, 3 * u)
    if callout:
        bx, top = tops[hi]
        size = d.fit_size([callout], (x1 - x0) * 0.5, 120 * u, 110 * u)
        tw, th = d.text_box(callout, size)
        tx = min(max(bx, x0 + tw / 2), x1 - tw / 2)
        ty = max(y0 + th / 2, top - 130 * u)
        d.draw_text(draw, callout, (tx, ty), size, ink)
        d.arrow(draw, (tx + tw * 0.15, ty + th * 0.6), (bx + slot * 0.08, top - 12 * u),
                _c(style, "red"), 11 * u, rng)


def _line(base, g, style, pics, rng):
    draw = ImageDraw.Draw(base)
    x0, y0, x1, y1 = _area(base.size)
    u = d.unit(base.size)
    ink, red = _c(style, "ink"), _c(style, "red")
    points = g["points"]
    px0, px1 = x0 + 90 * u, x1 - 40 * u
    py0, py1 = y0 + 40 * u, y1 - 90 * u
    d.arrow(draw, (px0, py1), (px0, py0 - 10 * u), ink, 9 * u, rng)
    d.arrow(draw, (px0, py1), (px1, py1), ink, 9 * u, rng)
    lo, hi = min(points), max(points)
    hi = hi if hi > lo else lo + 1
    span_x, span_y = (px1 - px0) * 0.84, (py1 - py0) * 0.78
    xy = [(px0 + (px1 - px0) * 0.06 + span_x * k / (len(points) - 1),
           py1 - (py1 - py0) * 0.10 - span_y * (v - lo) / (hi - lo)) for k, v in enumerate(points)]
    d.stroke(draw, xy, ink, 11 * u, rng, 3 * u)
    for note in g.get("notes") or []:
        nx, ny = xy[note["at"] - 1]
        size = d.fit_size([note["text"].upper()], (px1 - px0) * 0.3, 70 * u, 54 * u)
        d.draw_text(draw, note["text"].upper(), (nx + 14 * u, ny - 26 * u), size, ink, anchor="lb")
    if g.get("circle"):
        cx, cy = xy[g["circle"] - 1]
        r = 46 * u
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=red, width=round(8 * u))
    if g.get("x_label"):
        d.draw_text(draw, g["x_label"].upper(), (px1, py1 + 24 * u), round(54 * u), ink, anchor="rt")
    if g.get("y_label"):
        tile = d.rotated_text(g["y_label"].upper(), round(54 * u), ink)
        base.paste(tile, (round(px0 - 30 * u - tile.width), round(py0)), tile)


def _meter(base, g, style, pics, rng):
    draw = ImageDraw.Draw(base)
    w, h = base.size
    u = d.unit(base.size)
    portrait = _portrait(base.size)
    bar_w, bar_h = (w * 0.84, h * 0.06) if portrait else (w * 0.66, h * 0.13)
    cy = h * ((0.46 if pics else 0.40) if portrait else (0.58 if pics else 0.46))
    box = (w / 2 - bar_w / 2, cy - bar_h / 2, w / 2 + bar_w / 2, cy + bar_h / 2)
    if pics:
        side = h * (0.24 if portrait else 0.30)
        d.place(base, pics[0], _rect(w / 2, box[1] - 40 * u - side / 2, side * WIDE, side))
    pad = 12 * u
    inner = (box[0] + pad, box[1] + pad, box[2] - pad, box[3] - pad)
    filled = inner[0] + (inner[2] - inner[0]) * g["value"] / 100
    if filled - inner[0] > 2:
        draw.rounded_rectangle((inner[0], inner[1], filled, inner[3]),
                               radius=min((inner[3] - inner[1]) / 2, (filled - inner[0]) / 2),
                               fill=_c(style, TONES[g.get("tone", "good")]))
    draw.rounded_rectangle(box, radius=bar_h / 2, outline=_c(style, "ink"), width=round(8 * u))
    text = (g.get("text") or f"{g['value']:g}%").upper()
    size = d.fit_size([text], w * 0.8, (h * (0.09 if portrait else 0.16)), 170 * u)
    d.draw_text(draw, text, (w / 2, box[3] + 36 * u), size, _c(style, "ink"), anchor="mt")


def _words(base, g, style, pics, rng):
    draw = ImageDraw.Draw(base)
    x0, y0, x1, y1 = _area(base.size)
    u = d.unit(base.size)
    lines = [line.upper() for line in _lines(g["text"])]
    accent = g.get("accent") or (len(lines) if len(lines) > 1 else None)
    size = d.fit_size(lines, (x1 - x0) * 0.92, (y1 - y0) * 0.78, 230 * u)
    pitch = d.line_pitch(size)
    top = (y0 + y1) / 2 - (pitch * (len(lines) - 1) + d.text_box("HQ", size)[1]) / 2
    for k, line in enumerate(lines, 1):
        colour = _c(style, "red" if k == accent else "ink")
        y = top + pitch * (k - 1)
        d.draw_text(draw, line, ((x0 + x1) / 2, y), size, colour, anchor="mt")
        if k == accent:
            tw, th = d.text_box(line, size)
            uy = y + th + 14 * u
            d.stroke(draw, [((x0 + x1) / 2 - tw * 0.45, uy), ((x0 + x1) / 2 + tw * 0.45, uy)],
                     colour, 10 * u, rng, 5 * u)


_LAYOUTS = {"icon": _icon, "pair": _pair, "chain": _chain, "cycle": _cycle, "bars": _bars,
            "line": _line, "meter": _meter, "words": _words}


# ---- overlays: date tags and corner notes on any shot ------------------------------------

def overlay(img, tag=None, note=None, style=None):
    """A copy of img with the shot's tag (top right) and note (top left) drawn on."""
    out = img.convert("RGB").copy()
    if not (tag or note):
        return out
    style = d.style_of(style)
    if tag:
        _tag(out, str(tag).strip().upper(), style)
    if note:
        out = _note(out, str(note).strip(), style)
    return out


def _tag(base, text, style):
    """A calendar-style date label: red header strip, white face, ink outline."""
    draw = ImageDraw.Draw(base)
    u = d.unit(base.size)
    margin = 0.035 * min(base.size)
    size = round(54 * u)
    tw, th = d.text_box(text, size)
    pad, header = 22 * u, 20 * u
    x1, y0 = base.width - margin, margin
    x0, y1 = x1 - tw - 2 * pad, y0 + header + th + 2 * pad
    radius = 14 * u
    draw.rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=_c(style, "red"))
    draw.rectangle((x0 + 3 * u, y0 + header, x1 - 3 * u, y1 - radius), fill=_c(style, "paper"))
    draw.rounded_rectangle((x0 + 3 * u, y0 + header, x1 - 3 * u, y1 - 3 * u), radius=radius * 0.7,
                           fill=_c(style, "paper"))
    draw.rounded_rectangle((x0, y0, x1, y1), radius=radius, outline=_c(style, "ink"), width=round(5 * u))
    for rx in (x0 + (x1 - x0) * 0.28, x0 + (x1 - x0) * 0.72):
        draw.rounded_rectangle((rx - 5 * u, y0 - 12 * u, rx + 5 * u, y0 + 10 * u), radius=4 * u,
                               fill=_c(style, "ink"))
    d.draw_text(draw, text, ((x0 + x1) / 2, y0 + header + pad + th / 2), size, _c(style, "ink"))


def _note(base, text, style):
    """Small print on a translucent card, top left: the disclaimer slot."""
    u = d.unit(base.size)
    margin = 0.035 * min(base.size)
    width = base.width * (0.62 if _portrait(base.size) else 0.30)
    size, pad = round(30 * u), 16 * u
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if line and d.text_box(trial, size)[0] > width - 2 * pad:
            lines.append(line)
            line = word
        else:
            line = trial
    lines.append(line)
    pitch = d.line_pitch(size, 0.05)
    height = pitch * len(lines) + 2 * pad
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    paper = _c(style, "paper")
    draw.rounded_rectangle((margin, margin, margin + width, margin + height), radius=12 * u,
                           fill=paper + (225,))
    for k, text_line in enumerate(lines):
        d.draw_text(draw, text_line, (margin + width / 2, margin + pad + k * pitch), size,
                    _c(style, "ink") + (255,), anchor="mt")
    return Image.alpha_composite(base.convert("RGBA"), layer).convert("RGB")
