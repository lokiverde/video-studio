"""Drawing primitives for the Army format (docs/army.md): the navy grain canvas,
Anton display type with a two-tone gradient, and rounded framed pictures.

Everything here is plain Pillow (no numpy: the Mac mini's system Python has none) and
deterministic for a given seed, so a restage redraws the identical frame. The face is bundled (assets/fonts/Anton,
OFL) for the same reason captions bundle DejaVu: the Linux server and the Mac mini must render the
same glyphs as the Mac."""
import math
import random
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ANTON = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "Anton-Regular.ttf"

# Brokerage: navy, white lettering, light blue (Tony, 2026-10-17). A theme can
# override any of these through its "army_style" block.
DEFAULT_STYLE = {
    "bg": "#1d3557",         # Brokerage navy, centre of the canvas
    "bg_deep": "#00121f",    # vignette edge
    "text": "#ffffff",
    "accent": "#29a8d6",     # Brokerage light blue
    "accent_hi": "#9fe3fb",  # top of the accent gradient
    "dim": "#3d6380",        # faded headline and sibling cards
}


def style_of(theme_style=None):
    return {**DEFAULT_STYLE, **(theme_style or {})}


def rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def font(size):
    if not ANTON.exists():
        raise RuntimeError(f"Army display face missing: {ANTON} (git checkout assets/fonts)")
    return ImageFont.truetype(str(ANTON), max(8, int(size)),
                              layout_engine=ImageFont.Layout.BASIC)


def canvas(size, style, seed=0):
    """Navy radial gradient, film grain and a scatter of dust specks."""
    w, h = size
    rng = random.Random(seed)
    # radial_gradient is 0 at the centre and 255 at the rim of a 256 square. Stretch it
    # past the frame so the corners are the deep tone and the centre stays navy.
    ramp = Image.radial_gradient("L").resize((round(w * 1.5), round(h * 1.5)))
    left, top = round(w * 0.25), round(h * 0.25 - h * 0.08)
    mask = ramp.crop((left, top, left + w, top + h)).point(
        lambda v: round(255 * min(1.0, v / 200) ** 1.4))
    img = Image.composite(Image.new("RGB", size, rgb(style["bg_deep"])),
                          Image.new("RGB", size, rgb(style["bg"])), mask)
    # Uniform grain of about +-8 levels, seeded so the frame is identical on redraw.
    noise = Image.frombytes("L", size, rng.randbytes(w * h)).point(
        lambda v: 128 + round((v - 128) * 0.065))
    img = ImageChops.add(img, Image.merge("RGB", (noise, noise, noise)), 1.0, -128)
    draw = ImageDraw.Draw(img)
    for _ in range(max(12, w * h // 9000)):
        x, y, lift = rng.randrange(w), rng.randrange(h), rng.randint(25, 70)
        base = img.getpixel((x, y))
        draw.point((x, y), fill=tuple(min(255, c + lift) for c in base))
    return img


def cover(img, size, anchor_y=0.5):
    """Scale to fill size and crop the overflow, anchored on anchor_y vertically."""
    w, h = size
    scale = max(w / img.width, h / img.height)
    scaled = img.resize((max(w, round(img.width * scale)), max(h, round(img.height * scale))),
                        Image.LANCZOS)
    left = (scaled.width - w) // 2
    top = round((scaled.height - h) * anchor_y)
    return scaled.crop((left, top, left + w, top + h))


def rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius, fill=255)
    return mask


def glow(base, box, radius, color, strength=0.55, spread=None):
    """A soft light-blue halo behind a rounded box, painted onto base in place."""
    spread = spread or max(8, round(min(base.size) * 0.02))
    layer = Image.new("L", base.size, 0)
    x0, y0, x1, y1 = box
    ImageDraw.Draw(layer).rounded_rectangle([x0, y0, x1, y1], radius, fill=round(255 * strength))
    layer = layer.filter(ImageFilter.GaussianBlur(spread))
    base.paste(Image.new("RGB", base.size, rgb(color)), (0, 0), layer)


def framed(picture, size, style, radius=None, border=None):
    """picture cover-cropped into a rounded box with a light-blue rule. Returns RGBA."""
    w, h = size
    radius = radius if radius is not None else round(min(w, h) * 0.05)
    border = border if border is not None else max(3, round(min(w, h) * 0.012))
    inner = cover(picture.convert("RGB"), size).convert("RGBA")
    inner.putalpha(rounded_mask(size, radius))
    ImageDraw.Draw(inner).rounded_rectangle([0, 0, w - 1, h - 1], radius,
                                            outline=rgb(style["accent"]), width=border)
    return inner


def paste_framed(base, picture, box, style, radius=None, halo=True):
    """Frame picture into box (x0, y0, x1, y1) on base, with a glow behind it."""
    x0, y0, x1, y1 = (round(v) for v in box)
    size = (x1 - x0, y1 - y0)
    radius = radius if radius is not None else round(min(size) * 0.05)
    if halo:
        glow(base, (x0, y0, x1, y1), radius, style["accent"], strength=0.45)
    tile = framed(picture, size, style, radius)
    base.paste(tile, (x0, y0), tile)


def text_size(text, fnt):
    box = fnt.getbbox(text)
    return box[2] - box[0], box[3] - box[1], box


def fit_size(lines, max_w, max_h, gap=0.12, cap=None):
    """Largest Anton size at which every line fits max_w and the stack fits max_h."""
    lo, hi = 8, int(cap or max_h)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        fnt = font(mid)
        widest = max(text_size(line, fnt)[0] for line in lines)
        tall = sum(text_size(line, fnt)[1] for line in lines) + gap * mid * (len(lines) - 1)
        if widest <= max_w and tall <= max_h:
            lo = mid
        else:
            hi = mid - 1
    return lo


def gradient_word(text, fnt, top, bottom, opacity=1.0):
    """One line of type filled with a vertical gradient. Returns a tight RGBA image."""
    tw, th, box = text_size(text, fnt)
    mask = Image.new("L", (tw, th), 0)
    ImageDraw.Draw(mask).text((-box[0], -box[1]), text, font=fnt, fill=round(255 * opacity))
    ramp = Image.linear_gradient("L").resize((tw, th))       # 0 at the top, 255 at the bottom
    fill = Image.composite(Image.new("RGB", (tw, th), rgb(bottom)),
                           Image.new("RGB", (tw, th), rgb(top)), ramp).convert("RGBA")
    fill.putalpha(mask)
    return fill


def word_image(text, fnt, style, accent=False, opacity=1.0):
    if accent:
        return gradient_word(text, fnt, style["accent_hi"], style["accent"], opacity)
    return gradient_word(text, fnt, style["text"], style["text"], opacity)


def _put(base, img, xy, layer):
    """Paste RGBA img at xy. On a transparent layer, alpha-composite instead, so the type's
    soft edges keep their alpha (a masked paste squares it and thins the letters)."""
    if not layer:
        base.paste(img, xy, img)
        return
    x, y = xy
    src = img.crop((max(0, -x), max(0, -y), img.width, img.height))
    base.alpha_composite(src, (max(0, x), max(0, y)))


def draw_stack(base, lines, centre_x, top, size, style, accents=(), gap=0.12,
               opacity=1.0, shadow=True, layer=False):
    """Centred lines of Anton from y=top. accents: 0-based indexes in light blue.
    layer=True when base is a transparent RGBA layer. Returns the y just below the stack."""
    fnt = font(size)
    y = top
    for i, line in enumerate(lines):
        word = word_image(line, fnt, style, accent=i in accents, opacity=opacity)
        x = round(centre_x - word.width / 2)
        if shadow:
            shade = Image.new("RGBA", word.size, (0, 0, 0, 0))
            shade.putalpha(word.getchannel("A").point(lambda a: a * 0.55))
            shade = shade.filter(ImageFilter.GaussianBlur(max(2, size // 22)))
            _put(base, shade, (x + max(2, size // 30), round(y) + max(2, size // 30)), layer)
        _put(base, word, (x, round(y)), layer)
        y += word.height + gap * size
    return y


def stack_height(lines, size, gap=0.12):
    fnt = font(size)
    return sum(text_size(line, fnt)[1] for line in lines) + gap * size * (len(lines) - 1)


def wrap_words(text, max_chars):
    """Greedy word wrap that never splits a word. Used when the script gives no '|'."""
    lines, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > max_chars:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    return lines + ([line] if line else [])


def split_lines(text, max_chars):
    """'A JOB IN|THEIR HEAD' splits on '|'; otherwise wrap at max_chars. Upper-cased."""
    text = " ".join(str(text).split()).upper()
    if "|" in text:
        return [part.strip() for part in text.split("|") if part.strip()]
    return wrap_words(text, max_chars)


def balanced_lines(text, max_lines=2, single_up_to=11):
    """Short text stays on one line; longer text splits into up to max_lines lines of
    roughly equal length, never inside a word. '|' still forces the breaks."""
    text = " ".join(str(text).split()).upper()
    if "|" in text:
        return [part.strip() for part in text.split("|") if part.strip()][:max_lines]
    words = text.split()
    if len(text) <= single_up_to or len(words) < 2 or max_lines < 2:
        return [text]
    best = None
    for cut in range(1, len(words)):
        head, tail = " ".join(words[:cut]), " ".join(words[cut:])
        score = max(len(head), len(tail))
        if best is None or score < best[0]:
            best = (score, [head, tail])
    return best[1]


def arrow(draw, start, end, color, width):
    """A straight arrow with a filled head, start -> end."""
    (x0, y0), (x1, y1) = start, end
    length = math.hypot(x1 - x0, y1 - y0) or 1.0
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    head = width * 3.2
    bx, by = x1 - ux * head, y1 - uy * head
    draw.line([(x0, y0), (bx, by)], fill=color, width=width)
    nx, ny = -uy * head * 0.62, ux * head * 0.62
    draw.polygon([(x1, y1), (bx + nx, by + ny), (bx - nx, by - ny)], fill=color)
