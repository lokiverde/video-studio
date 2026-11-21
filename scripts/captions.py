"""Render caption overlays as transparent PNGs with Pillow.

Deliberately avoids ffmpeg's libass/drawtext: minimal ffmpeg builds (like the
one on this Mac) ship without text filters, but every build has `overlay`.

The caption face is bundled in assets/fonts rather than looked up on the host.
A font that exists on this Mac does not exist on Tim or inside a container, and
falling through to a different face would silently change line wrapping and
box width. Bundling it keeps renders identical wherever assembly runs.
"""
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BUNDLED_FONT = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "DejaVuSans-Bold.ttf"

FONT_CANDIDATES = [
    (str(BUNDLED_FONT), 0),                       # ships with the repo, always present
    # Host fonts, kept only so a damaged checkout still renders something.
    ("/System/Library/Fonts/Helvetica.ttc", 1),   # macOS, index 1 = bold
    ("/System/Library/Fonts/Helvetica.ttc", 0),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 0),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 0),
]


def load_font(size):
    for path, index in FONT_CANDIDATES:
        try:
            # Pin the layout engine. the Linux server's Pillow is built with Raqm/HarfBuzz and the
            # Mac's is not, and the two shape identical text to slightly different glyph
            # positions, which shifts the centering and the box width. BASIC is enough
            # for Latin captions and keeps every host byte-identical.
            return ImageFont.truetype(
                path, size, index=index, layout_engine=ImageFont.Layout.BASIC
            )
        except OSError:
            continue
    raise RuntimeError(
        f"no usable caption font found. Expected the bundled face at {BUNDLED_FONT} "
        "(run `git checkout assets/fonts` if it is missing)."
    )


def hex_rgba(color, opacity=1.0):
    color = color.lstrip("#")
    r, g, b = (int(color[i:i + 2], 16) for i in (0, 2, 4))
    return (r, g, b, round(255 * opacity))


def caption_png(text, out_path, width=1920, height=1080, style=None, bottom_margin=90):
    """bottom_margin: distance from frame bottom. Vertical/TikTok renders pass a
    much larger margin so captions clear the platform UI overlay zone."""
    style = style or {}
    if not (text or "").strip():
        # A cut with captions off still needs the overlay input: a fully clear frame.
        Image.new("RGBA", (width, height), (0, 0, 0, 0)).save(out_path)
        return
    size = int(style.get("size", 64))
    font = load_font(size)
    wrap = 32 if width >= 1600 else 24
    lines = textwrap.wrap(text.strip(), width=wrap) or [""]

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    line_h = size + 14
    block_h = line_h * len(lines)
    pad_x, pad_y = 36, 20
    y0 = height - bottom_margin - block_h

    widest = max(draw.textlength(line, font=font) for line in lines)
    x0 = (width - widest) / 2
    draw.rounded_rectangle(
        [x0 - pad_x, y0 - pad_y, x0 + widest + pad_x, y0 + block_h + pad_y],
        radius=18, fill=hex_rgba(style.get("bg", "#000000"), float(style.get("bg_opacity", 0.55))))

    text_fill = hex_rgba(style.get("text", "#ffffff"))
    for i, line in enumerate(lines):
        line_w = draw.textlength(line, font=font)
        draw.text(((width - line_w) / 2, y0 + i * line_h), line, font=font, fill=text_fill)

    Path(out_path).parent.mkdir(exist_ok=True)
    img.save(out_path)
