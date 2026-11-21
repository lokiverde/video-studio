"""Army format graphics (docs/army.md): six shot layouts drawn over the navy canvas.

A shots entry carries a "graphic" block. FLUX renders the pictures a layout needs
(gen_images.graphic_one); this module only draws, so every layout works in both
cuts and a restage redraws it without another FLUX call.

  frame    a picture in a rounded light-blue frame, optional punch line under it
  trading  a countdown trading card (rank badge, title, picture) over a faded headline
  words    full-frame punch type, white with light-blue accent lines
  stamp    giant type BEHIND a cut-out subject
  agenda   a stack of lines that builds across consecutive shots
  tiles    2 to 4 picture tiles joined by arrows: a chain, or a tree from one root
"""
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

import army_draw as d

TYPES = ("frame", "trading", "words", "stamp", "agenda", "tiles")
NEEDS_PROMPT = ("frame", "trading", "stamp")

CARD_PICTURE = (576, 832)   # trading card art, portrait, shared by both cuts
TILE_PICTURE = (768, 432)   # tile art, 16:9, shared by both cuts
# Keep content above this fraction of a 9:16 frame: the caption band and the
# platform UI start just under it (see gen_images._vertical_guides).
PORTRAIT_SAFE = 0.74
# The 16:9 caption box (two lines, 90px margin) starts about 76% down: keep graphics above.
LANDSCAPE_SAFE = 0.74


def validate(graphic, prompt=""):
    """Raise ValueError with a plain message when a graphic block cannot render."""
    if not isinstance(graphic, dict):
        raise ValueError(f"graphic must be an object, got {graphic!r}")
    kind = graphic.get("type")
    if kind not in TYPES:
        raise ValueError(f"graphic type {kind!r} unknown (have: {', '.join(TYPES)})")
    if kind in NEEDS_PROMPT and not (prompt or "").strip():
        raise ValueError(f"a '{kind}' graphic needs a 'prompt' for its picture")
    if kind in ("words", "stamp") and not str(graphic.get("text") or "").strip():
        raise ValueError(f"a '{kind}' graphic needs 'text'")
    if kind == "trading":
        if not str(graphic.get("title") or "").strip() or graphic.get("number") in (None, ""):
            raise ValueError("a 'trading' card needs a 'number' and a 'title'")
    if kind == "agenda":
        lines = graphic.get("lines")
        if not isinstance(lines, list) or not 1 <= len(lines) <= 5:
            raise ValueError("an 'agenda' needs 'lines': a list of 1 to 5 strings")
        show = graphic.get("show", len(lines))
        if not isinstance(show, int) or not 1 <= show <= len(lines):
            raise ValueError(f"agenda 'show' must be 1 to {len(lines)}, got {show!r}")
    if kind == "tiles":
        items = graphic.get("items")
        if not isinstance(items, list) or not 2 <= len(items) <= 4:
            raise ValueError("'tiles' needs 'items': 2 to 4 of {\"prompt\", \"label\"}")
        if any(not isinstance(i, dict) or not str(i.get("prompt") or "").strip() for i in items):
            raise ValueError("every tile item needs a 'prompt'")
        if graphic.get("layout", "chain") not in ("chain", "tree"):
            raise ValueError("tiles 'layout' is 'chain' or 'tree'")
        if graphic.get("layout") == "tree" and len(items) < 3:
            raise ValueError("a tiles 'tree' needs a root and at least 2 branches")


# Graphics are drawn at the resolution assemble outputs, so the type stays crisp
# instead of being upscaled from the 1280x720 FLUX canvas.
FINAL_LANDSCAPE = (1920, 1080)
FINAL_PORTRAIT = (1080, 1920)


def has_backdrop(graphic, prompt=""):
    """True when the graphic sits on a full-canvas FLUX picture a later hold can punch
    into (frame, stamp, words with a prompt). The others leave nothing to hold on."""
    return any(not shared for _, _, _, shared in pictures(graphic, prompt, (16, 9)))


def pictures(graphic, prompt, size):
    """[(name, prompt, (w, h), shared)] FLUX pictures this graphic needs on a canvas of
    size. shared=True pictures (card art, tiles) do not depend on the cut, so the 9:16
    pass reuses the landscape ones; canvas-shaped ones are rendered per cut."""
    kind = graphic["type"]
    if kind in ("frame", "stamp") or (kind == "words" and (prompt or "").strip()):
        return [("bg", prompt, size, False)]
    if kind == "trading":
        return [("card", prompt, CARD_PICTURE, True)]
    if kind == "tiles":
        return [(f"tile{i + 1}", item["prompt"], TILE_PICTURE, True)
                for i, item in enumerate(graphic["items"])]
    return []


def render(graphic, size, style=None, pics=(), cutout=None, seed=0):
    """Draw one graphic shot at size. pics follow the order of pictures(); cutout is
    the stamp subject as RGBA (None draws the stamp without the depth trick)."""
    style = d.style_of(style)
    draw = {"frame": _frame, "trading": _trading, "words": _words, "stamp": _stamp,
            "agenda": _agenda, "tiles": _tiles}[graphic["type"]]
    return draw(graphic, size, style, list(pics), cutout, seed)


def _portrait(size):
    return size[1] > size[0]


def frame_boxes(size, has_text):
    """Where a frame shot puts its picture and its punch line: (box, text_area), each
    (x0, y0, x1, y1). The talking-head army style puts Tony's inset in the same box."""
    w, h = size
    if _portrait(size):
        box = (w * 0.06, h * 0.07, w * 0.94, h * (0.45 if has_text else 0.62))
        text_area = (w * 0.08, h * 0.49, w * 0.92, h * PORTRAIT_SAFE)
    else:
        box = (w * (0.22 if has_text else 0.08), h * 0.04, w * (0.78 if has_text else 0.92),
               h * (0.53 if has_text else LANDSCAPE_SAFE))
        text_area = (w * 0.08, h * 0.57, w * 0.92, h * LANDSCAPE_SAFE)
    return box, text_area


def _frame(g, size, style, pics, _cutout, seed):
    base = d.canvas(size, style, seed)
    text = str(g.get("text") or "").strip()
    box, text_area = frame_boxes(size, bool(text))
    d.paste_framed(base, pics[0], box, style)
    if text:
        _punch_lines(base, text, text_area, style, g.get("accent"))
    return base


def punch_overlay(text, size, style=None, accent=None):
    """A frame shot's punch line alone on a transparent layer the size of the frame, in
    the frame's text area. The talking-head army style lays it under Tony's inset."""
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    _, area = frame_boxes(size, True)
    _punch_lines(layer, text, area, d.style_of(style), accent, layer=True)
    return layer


def _punch_lines(base, text, area, style, accent=None, layer=False):
    """Fit a punch line into area (x0, y0, x1, y1), centred, accent lines light blue."""
    x0, y0, x1, y1 = area
    lines = d.split_lines(text, 14)
    accents = _accent_index(lines, accent)
    if _portrait(base.size):
        # A 9:16 frame is narrow: rewrap each scripted line short, so the type gets
        # big instead of shrinking to fit one long line. Accents follow their line.
        lines, accents = _rewrap(lines, accents, 11)
    size = d.fit_size(lines, x1 - x0, y1 - y0)
    top = y0 + (y1 - y0 - d.stack_height(lines, size)) / 2
    d.draw_stack(base, lines, (x0 + x1) / 2, top, size, style, accents, layer=layer)


def _rewrap(lines, accents, max_chars):
    """Split each line longer than max_chars into two even halves (no orphan words)."""
    out, marks = [], set()
    for i, line in enumerate(lines):
        for part in d.balanced_lines(line, single_up_to=max_chars):
            if i in accents:
                marks.add(len(out))
            out.append(part)
    return out, marks


def _accent_index(lines, accent):
    """1-based line numbers in the script; the last line is the accent by default."""
    if accent is None:
        return {len(lines) - 1} if len(lines) > 1 else set()
    picks = accent if isinstance(accent, list) else [accent]
    return {int(n) - 1 for n in picks if str(n).lstrip("-").isdigit()}


def _words(g, size, style, pics, _cutout, seed):
    w, h = size
    if pics:
        dim = ImageEnhance.Brightness(d.cover(pics[0].convert("RGB"), size)).enhance(0.32)
        navy = Image.new("RGB", size, d.rgb(style["bg_deep"]))
        base = Image.blend(dim, navy, 0.35)
    else:
        base = d.canvas(size, style, seed)
    if _portrait(size):
        area = (w * 0.07, h * 0.14, w * 0.93, h * 0.66)
    else:
        area = (w * 0.07, h * 0.08, w * 0.93, h * 0.72)
    _punch_lines(base, g["text"], area, style, g.get("accent"))
    return base


def _agenda(g, size, style, _pics, _cutout, seed):
    w, h = size
    base = d.canvas(size, style, seed)
    lines = [str(line).upper() for line in g["lines"]]
    show = int(g.get("show", len(lines)))
    portrait = _portrait(size)
    max_w = w * (0.86 if portrait else 0.7)
    max_h = h * (0.46 if portrait else 0.56)
    size_px = d.fit_size(lines, max_w, max_h, gap=0.32, cap=h * (0.075 if portrait else 0.12))
    block = d.stack_height(lines, size_px, gap=0.32)
    top = (h * (0.4 if portrait else 0.44)) - block / 2
    title = str(g.get("title") or "").strip().upper()
    if title:
        tsize = round(size_px * 0.5)
        d.draw_stack(base, [title], w / 2, top - tsize * 1.9, tsize, style, {0}, shadow=False)
    fnt = d.font(size_px)
    y = top
    for i, line in enumerate(lines):
        line_h = d.text_size(line, fnt)[1]
        if i < show:
            newest = i == show - 1
            d.draw_stack(base, [line], w / 2, y, size_px, style, {0} if newest else set(),
                         opacity=1.0 if newest else 0.82)
        y += line_h + 0.32 * size_px
    return base


def _trading(g, size, style, pics, _cutout, seed):
    w, h = size
    base = d.canvas(size, style, seed)
    portrait = _portrait(size)
    if portrait:
        card_w = w * 0.68
        card_h = card_w / 0.66
        top = h * 0.13
    else:
        card_h = h * 0.7
        card_w = card_h * 0.66
        top = h * 0.04
    headline = str(g.get("headline") or "").strip()
    if headline:
        lines = d.split_lines(headline, 16 if portrait else 34)[:2]
        hsize = d.fit_size(lines, w * 0.94, h * (0.1 if portrait else 0.16))
        d.draw_stack(base, lines, w / 2, h * 0.02, hsize, style, opacity=0.2, shadow=False)
    number = str(g.get("number")).strip()
    _siblings(base, g, number, card_w, card_h, top, style)
    x0 = (w - card_w) / 2
    _card(base, (x0, top, x0 + card_w, top + card_h), number, g["title"], pics[0], style)
    return base


def _siblings(base, g, number, card_w, card_h, top, style):
    """The other cards of the countdown, dimmed, peeking out either side."""
    total = g.get("of")
    if not str(number).isdigit() or not isinstance(total, int) or total < 2:
        return
    n, w = int(number), base.width
    scale = 0.78
    sw, sh = card_w * scale, card_h * scale
    sy = top + (card_h - sh) / 2
    gap = card_w * (0.72 if base.height > base.width else 0.86)
    draw = ImageDraw.Draw(base, "RGBA")
    radius = round(sw * 0.06)
    for side, other in ((-1, n + 1), (1, n - 1)):
        if not 1 <= other <= total:
            continue
        cx = w / 2 + side * gap
        box = (cx - sw / 2, sy, cx + sw / 2, sy + sh)
        draw.rounded_rectangle(box, radius, fill=d.rgb(style["bg_deep"]) + (235,),
                               outline=d.rgb(style["dim"]) + (255,), width=max(2, round(sw * 0.01)))
        badge = sw * 0.17
        bx, by = box[0] + sw * 0.07, box[1] + sw * 0.07
        draw.ellipse([bx, by, bx + badge, by + badge], outline=d.rgb(style["dim"]) + (255,),
                     width=max(2, round(badge * 0.06)))
        fnt = d.font(badge * 0.62)
        tw, th, bb = d.text_size(str(other), fnt)
        draw.text((bx + (badge - tw) / 2 - bb[0], by + (badge - th) / 2 - bb[1]), str(other),
                  font=fnt, fill=d.rgb(style["dim"]) + (255,))


def _card(base, box, number, title, picture, style):
    x0, y0, x1, y1 = (round(v) for v in box)
    cw, ch = x1 - x0, y1 - y0
    radius = round(cw * 0.06)
    d.glow(base, (x0, y0, x1, y1), radius, style["accent"], strength=0.6)
    card = Image.new("RGBA", (cw, ch), d.rgb(style["bg"]) + (255,))
    band = round(ch * 0.2)
    art = d.cover(picture.convert("RGB"), (cw, ch - band), anchor_y=0.4)
    card.paste(art, (0, band))
    shade = Image.new("L", (1, band), 0)
    for y in range(band):          # navy fade from the band into the picture
        shade.putpixel((0, y), round(255 * max(0, 1 - y / band) ** 2))
    card.paste(Image.new("RGB", (cw, band), d.rgb(style["bg"])), (0, band),
               shade.resize((cw, band)))
    badge = round(cw * 0.17)
    bx = by = round(cw * 0.06)
    cdraw = ImageDraw.Draw(card)
    cdraw.ellipse([bx, by, bx + badge, by + badge], fill=d.rgb(style["accent"]),
                  outline=d.rgb(style["text"]), width=max(2, round(badge * 0.05)))
    fnt = d.font(badge * 0.62)
    tw, th, bb = d.text_size(number, fnt)
    cdraw.text((bx + (badge - tw) / 2 - bb[0], by + (badge - th) / 2 - bb[1]), number, font=fnt,
               fill=d.rgb(style["text"]))
    lines = d.balanced_lines(title)
    area_x0 = bx + badge + cw * 0.04
    area_w = cw - area_x0 - cw * 0.05
    tsize = d.fit_size(lines, area_w, band * 0.74, cap=band * 0.4)
    ttop = (band - d.stack_height(lines, tsize)) / 2
    d.draw_stack(card, lines, area_x0 + area_w / 2, ttop, tsize, style, shadow=False)
    card.putalpha(d.rounded_mask((cw, ch), radius))
    ImageDraw.Draw(card).rounded_rectangle([0, 0, cw - 1, ch - 1], radius,
                                           outline=d.rgb(style["accent"]),
                                           width=max(3, round(cw * 0.012)))
    base.paste(card, (x0, y0), card)


def _stamp(g, size, style, pics, cutout, seed):
    """Giant type, then the subject pasted over it. With no cutout (segmentation
    unavailable, e.g. on the Linux server) the picture sits framed under the type instead."""
    w, h = size
    base = d.canvas(size, style, seed)
    portrait = _portrait(size)
    lines = d.split_lines(g["text"], 8 if portrait else 14)
    max_h = h * (0.36 if portrait else 0.5)
    tsize = d.fit_size(lines, w * 0.94, max_h)
    block = d.stack_height(lines, tsize)
    ttop = h * (0.1 if portrait else 0.1)
    if cutout is None:
        d.draw_stack(base, lines, w / 2, ttop, tsize, style, set(range(len(lines))))
        y = ttop + block + h * 0.03
        bottom = h * (PORTRAIT_SAFE if portrait else LANDSCAPE_SAFE)
        bw = min(w * 0.84, (bottom - y) * (1.6 if not portrait else 1.0))
        d.paste_framed(base, pics[0], ((w - bw) / 2, y, (w + bw) / 2, bottom), style)
        return base
    d.draw_stack(base, lines, w / 2, ttop, tsize, style, set(range(len(lines))), shadow=False)
    subject = cutout.crop(cutout.getbbox() or (0, 0, cutout.width, cutout.height))
    target_h = h * (0.82 if portrait else 0.9)
    scale = min(target_h / subject.height, (w * 0.9) / subject.width)
    subject = subject.resize((max(1, round(subject.width * scale)),
                              max(1, round(subject.height * scale))), Image.LANCZOS)
    shadow = Image.new("RGBA", subject.size, (0, 0, 0, 0))
    shadow.putalpha(subject.getchannel("A").point(lambda a: a * 0.6))
    shadow = shadow.filter(ImageFilter.GaussianBlur(max(4, w // 160)))
    sx, sy = round((w - subject.width) / 2), h - subject.height
    base.paste(shadow, (sx + w // 140, sy), shadow)
    base.paste(subject, (sx, sy), subject)
    return base


def _tiles(g, size, style, pics, _cutout, seed):
    w, h = size
    base = d.canvas(size, style, seed)
    portrait = _portrait(size)
    headline = str(g.get("headline") or "").strip()
    top = h * 0.05
    if headline:
        lines = d.split_lines(headline, 14 if portrait else 30)[:2]
        hsize = d.fit_size(lines, w * 0.9, h * (0.1 if portrait else 0.13))
        top = d.draw_stack(base, lines, w / 2, top, hsize, style, set(range(len(lines)))) + h * 0.03
    labels = [str(i.get("label") or "").upper() for i in g["items"]]
    bottom = h * (PORTRAIT_SAFE if portrait else LANDSCAPE_SAFE)
    layout = g.get("layout", "chain")
    result = str(g.get("result") or "").strip().upper() if layout == "chain" else ""
    if layout == "tree":
        boxes = _tree_boxes(len(pics), (w, h), top, bottom, portrait)
    elif portrait:
        boxes = _column_boxes(len(pics), (w, h), top, bottom, bool(result))
    else:
        boxes = _row_boxes(len(pics), (w, h), top, bottom, bool(result))
    _connect(base, boxes, layout, portrait, style)
    for pic, box, label in zip(pics, boxes, labels):
        _tile(base, pic, box, label, style)
    if result:
        _result(base, boxes[-1], result, portrait, style, bottom)
    return base


def _tile(base, picture, box, label, style):
    """A framed tile with its label on a navy strip inside the bottom edge."""
    x0, y0, x1, y1 = (round(v) for v in box)
    tw, th = x1 - x0, y1 - y0
    art = d.cover(picture.convert("RGB"), (tw, th))
    if label:
        strip = round(th * 0.36)
        fade = Image.linear_gradient("L").resize((tw, strip)).point(lambda v: round(v * 0.92))
        art.paste(Image.new("RGB", (tw, strip), d.rgb(style["bg_deep"])), (0, th - strip), fade)
        lsize = d.fit_size([label], tw * 0.86, th * 0.2)
        word = d.word_image(label, d.font(lsize), style)
        art.paste(word, (round((tw - word.width) / 2), round(th - word.height - th * 0.07)), word)
    d.paste_framed(base, art, box, style, radius=round(tw * 0.04))


def _row_boxes(n, size, top, bottom, has_result):
    """A row of 4:3 tiles: taller than 16:9, so a 16:9 frame is not mostly empty."""
    w, h = size
    gap = w * 0.045
    tail = w * 0.13 + gap if has_result else 0
    room = w * 0.95 - gap * (n - 1) - tail
    tw = min(room / n, (bottom - top) * 0.9 * 4 / 3)
    th = tw * 3 / 4
    used = tw * n + gap * (n - 1) + tail
    x = (w - used) / 2
    y = top + ((bottom - top) - th) / 2
    return [(x + i * (tw + gap), y, x + i * (tw + gap) + tw, y + th) for i in range(n)]


def _column_boxes(n, size, top, bottom, has_result=False):
    w, _ = size
    slot = (bottom - top) / (n + (0.45 if has_result else 0))
    th = slot * 0.8
    tw = min(w * 0.86, th * 16 / 9)
    th = tw * 9 / 16
    x = (w - tw) / 2
    return [(x, top + i * slot, x + tw, top + i * slot + th) for i in range(n)]


def _tree_boxes(n, size, top, bottom, portrait):
    """Root centred on top, branches in a row under it, the pair centred in the space."""
    w, _ = size
    kids = n - 1
    gap = w * 0.03
    drop = (bottom - top) * (0.14 if portrait else 0.16)   # connector room
    # Root and branches split the height, so the root never ends up smaller than a branch.
    root_w = min(w * (0.66 if portrait else 0.36), (bottom - top - drop) / 2 * 16 / 9)
    root_h = root_w * 9 / 16
    kid_w = min((w * 0.95 - gap * (kids - 1)) / kids, root_w)
    kid_h = kid_w * 9 / 16
    tall = root_h + drop + kid_h
    y0 = top + max(0, (bottom - top - tall) / 2)
    root = ((w - root_w) / 2, y0, (w + root_w) / 2, y0 + root_h)
    ky = y0 + root_h + drop
    x = (w - (kid_w * kids + gap * (kids - 1))) / 2
    return [root] + [(x + i * (kid_w + gap), ky, x + i * (kid_w + gap) + kid_w, ky + kid_h)
                     for i in range(kids)]


def _line_width(base, portrait):
    return max(4, round(base.width * (0.006 if portrait else 0.004)))


def _connect(base, boxes, layout, portrait, style):
    draw = ImageDraw.Draw(base)
    color = d.rgb(style["accent"])
    width = _line_width(base, portrait)
    pad = width * 3
    if layout == "tree":
        root = boxes[0]
        rx, ry = (root[0] + root[2]) / 2, root[3] + pad
        mid = (ry + boxes[1][1]) / 2
        draw.line([(rx, ry), (rx, mid)], fill=color, width=width)
        xs = [(b[0] + b[2]) / 2 for b in boxes[1:]]
        draw.line([(min(xs), mid), (max(xs), mid)], fill=color, width=width)
        for x, b in zip(xs, boxes[1:]):
            d.arrow(draw, (x, mid), (x, b[1] - pad), color, width)
        return
    for a, b in zip(boxes, boxes[1:]):
        if portrait:
            d.arrow(draw, (base.width / 2, a[3] + pad), (base.width / 2, b[1] - pad), color, width)
        else:
            ymid = (a[1] + a[3]) / 2
            d.arrow(draw, (a[2] + pad, ymid), (b[0] - pad, ymid), color, width)


def _result(base, last, result, portrait, style, bottom):
    """The chain's verdict word: after an arrow to the right (16:9) or below (9:16)."""
    draw = ImageDraw.Draw(base)
    color = d.rgb(style["accent"])
    width = _line_width(base, portrait)
    if portrait:
        y = last[3] + width * 3
        rsize = d.fit_size([result], base.width * 0.6, max(20, (bottom - y) * 0.6))
        word_top = bottom - d.stack_height([result], rsize)
        d.arrow(draw, (base.width / 2, y), (base.width / 2, word_top - width * 3), color, width)
        d.draw_stack(base, [result], base.width / 2, word_top, rsize, style, {0})
        return
    ymid = (last[1] + last[3]) / 2
    gap = base.width * 0.045
    d.arrow(draw, (last[2] + width * 3, ymid), (last[2] + gap - width * 3, ymid), color, width)
    lines = d.balanced_lines(result, single_up_to=7)
    room = base.width * 0.13
    rsize = d.fit_size(lines, room, (last[3] - last[1]) * 0.7, cap=(last[3] - last[1]) * 0.4)
    top = ymid - d.stack_height(lines, rsize) / 2
    d.draw_stack(base, lines, last[2] + gap + room / 2, top, rsize, style,
                 set(range(len(lines))))
