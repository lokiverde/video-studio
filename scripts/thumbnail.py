"""Build a 1280x720 YouTube thumbnail from a frame of a finished video.

Runs automatically at the end of `fv.py finish`, writing `out/thumbnail.jpg` beside
the mp4s. Text is composited with Pillow from the repo's bundled DejaVuSans-Bold and
the pinned layout engine, never asked of the image model (house rule 9), so it renders
identically on the Mac, the Mac mini and the Linux server.

Per-video settings live in a `thumbnail` block in scenes.json:

    "thumbnail": {
      "headline": ["YOUR HOA", "CAN'T SAY NO"],
      "seconds": 12,
      "accent": "#059669",
      "site": "sitetwo.com",
      "eyebrow": "SACRAMENTO WATCH"
    }

Every field is optional. A theme can set `thumbnail_accent`, `thumbnail_site` and
`thumbnail_eyebrow` as defaults for its brand, and with no headline at all the first
scene's caption is used, since that is already written as a short on-screen takeaway.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess

from PIL import Image, ImageDraw, ImageFont

import common

FONT_PATH = common.ROOT / "assets/fonts/DejaVuSans-Bold.ttf"

W, H = 1280, 720
ART_H = 500              # the frame sits above the band, never cropped into the character
HEAD_SIZE = 72
LINE_STEP = 84
MAX_LINE_CHARS = 20      # longer than this and 72pt runs off a 1280 canvas
DEFAULT_ACCENT = "#0F172A"


def load_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_PATH), size, layout_engine=ImageFont.Layout.BASIC)


def split_headline(text: str) -> list[str]:
    """Balance a single string across two lines without breaking a word."""
    words = text.upper().split()
    if not words:
        return ["SACRAMENTO WATCH"]
    best, best_gap = [" ".join(words)], 10**6
    for cut in range(1, len(words)):
        first, second = " ".join(words[:cut]), " ".join(words[cut:])
        if max(len(first), len(second)) > MAX_LINE_CHARS:
            continue
        gap = abs(len(first) - len(second))
        if gap < best_gap:
            best, best_gap = [first, second], gap
    return best


def resolve(job_id: str) -> dict:
    """Merge the per-video thumbnail block over the theme's defaults."""
    jdir = common.job_dir(job_id)
    data = json.loads((jdir / "scenes.json").read_text())
    theme = common.load_theme(data.get("theme", "sketch"))
    block = data.get("thumbnail") or {}

    headline = block.get("headline")
    if not headline:
        first_caption = (data["scenes"][0].get("caption") or data.get("title", "")).strip()
        headline = split_headline(first_caption)

    return {
        "headline": [line.upper() for line in headline][:2],
        "seconds": float(block.get("seconds", 1.0)),
        "accent": block.get("accent") or theme.get("thumbnail_accent") or DEFAULT_ACCENT,
        "site": block.get("site") or theme.get("thumbnail_site") or "",
        "eyebrow": block.get("eyebrow") or theme.get("thumbnail_eyebrow") or "",
    }


def base_frame(job_id: str, seconds: float) -> Image.Image:
    """Grab a frame, drop the bottom quarter so the burned-in caption never shows, then
    fit it above the band. The band sits BELOW the art rather than over it, because
    overlaying it sliced the character in half."""
    jdir = common.job_dir(job_id)
    video = jdir / "out" / "final_16x9.mp4"
    if not video.exists():
        video = jdir / "out" / "final_9x16.mp4"
    if not video.exists():
        common.die("final_16x9.mp4 / final_9x16.mp4 missing (run assemble first)")

    raw = jdir / "work" / "_thumb_frame.png"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", str(seconds), "-i", str(video), "-frames:v", "1",
         "-vf", "crop=iw:ih*0.75:0:0", str(raw), "-y"], check=True)

    art = Image.open(raw).convert("RGB")
    art = art.resize((W, round(art.height * W / art.width)), Image.LANCZOS)
    art = art.crop((0, 0, W, ART_H))
    raw.unlink(missing_ok=True)

    canvas = Image.new("RGB", (W, H), "white")
    canvas.paste(art, (0, 0))
    return canvas


def run(job_id: str) -> pathlib.Path | None:
    """Write out/thumbnail.jpg. Never fatal: a thumbnail is not worth losing a render over.
    Once yt_thumb.py has made the Test & compare set, thumbnail.jpg is its variant A and
    is left alone."""
    try:
        import yt_thumb                   # lazy: the Test & compare set lives there
        jdir = common.job_dir(job_id)
        for problem in yt_thumb.kit_problems(jdir):
            print(f"[thumbnail] KIT: {problem}")
        if (jdir / "out" / yt_thumb.SETS_DIR / "thumbnail_A.jpg").exists():
            print("[thumbnail] keeping out/thumbnail.jpg: it is variant A of the Test & compare set")
            return jdir / "out" / "thumbnail.jpg"
        spec = resolve(job_id)
        image = base_frame(job_id, spec["seconds"])
        draw = ImageDraw.Draw(image, "RGBA")

        draw.rectangle([0, ART_H, W, H], fill=spec["accent"])
        draw.rectangle([0, ART_H - 7, W, ART_H], fill="#0F172A")

        head = load_font(HEAD_SIZE)
        y = ART_H + 22
        for line in spec["headline"]:
            draw.text((46, y), line, font=head, fill="white",
                      stroke_width=5, stroke_fill="black")
            y += LINE_STEP

        if spec["eyebrow"]:
            eb = load_font(30)
            width = draw.textlength(spec["eyebrow"], font=eb)
            draw.rectangle([40, 34, 40 + width + 34, 86], fill="#0F172AE6")
            draw.text((57, 46), spec["eyebrow"], font=eb, fill="white")

        if spec["site"]:
            tag = load_font(26)
            width = draw.textlength(spec["site"], font=tag)
            draw.text((W - width - 46, H - 40), spec["site"], font=tag, fill="#FFFFFFCC")

        out = common.job_dir(job_id) / "out" / "thumbnail.jpg"
        image.save(out, quality=92)
        print(f"[thumbnail] {out.name} {out.stat().st_size // 1024}KB  {spec['headline']}")
        return out
    except Exception as error:
        print(f"[thumbnail] skipped ({error})")
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job")
    args = parser.parse_args()
    run(args.job)


if __name__ == "__main__":
    main()
