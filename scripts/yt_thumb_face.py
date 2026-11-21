#!/usr/bin/env python3
"""Tony on the thumbnail (review 2026-10-19): a frame from his footage, cut out with
macOS Vision or rembg (vision.subject_cutout), given the white outline + soft shadow sticker
look, and parked on the right of the frame while the words keep the left 55%.

The block's "face" is a footage timestamp in seconds (8.8) or a PNG path relative to the
job folder or the repo (the pose library in assets/faces/ for jobs without Tony footage).
A PNG that already has transparency is used as is; anything else is cut out.
Where Vision is missing (the Linux server, the Mac mini) or finds nobody, the frame is used as a portrait card
with the same outline, so the variant still shows a face.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageFilter

import common
import vision

OUTLINE = 10                  # white sticker ring, px at thumbnail scale
SHADOW_BLUR = 18
SHADOW_STRENGTH = 0.6
HEAD_ROWS = 0.15              # top share of the cutout that counts as the head
CARD_ASPECT = 3 / 4           # fallback card when there is no cutout


def parse_face(value) -> float | str:
    """Seconds into the footage (a number or a numeric string) or a PNG path."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = float(value)
    else:
        text = str(value).strip()
        try:
            seconds = float(text)
        except ValueError:
            return text
    if seconds < 0:
        raise ValueError(f"face time {seconds} is before the start of the footage")
    return seconds


def grab_frame(footage: Path, seconds: float, dest: Path) -> Path:
    """One full-resolution frame from the footage."""
    if not Path(footage).exists():
        raise RuntimeError(f"no footage at {footage} to take the face frame from")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.unlink(missing_ok=True)
    done = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{seconds:.3f}",
                           "-i", str(footage), "-frames:v", "1", str(dest)],
                          capture_output=True, text=True, timeout=120)
    if done.returncode != 0 or not dest.exists():
        raise RuntimeError(f"no frame at {seconds}s in {Path(footage).name} "
                           f"({done.stderr.strip()[:160] or 'past the end?'})")
    return dest


def cutout(frame: Path) -> Image.Image | None:
    """The subject lifted off the frame, cached beside it as <stem>_cut.png. None where
    Vision is unavailable or finds nobody (same contract as gen_images.subject_cutout)."""
    cut = frame.with_name(frame.stem + "_cut.png")
    if not cut.exists() or cut.stat().st_mtime < frame.stat().st_mtime:
        ok, why = vision.subject_cutout(frame, cut)
        if not ok:
            print(f"[yt_thumb] {frame.name}: no cutout ({why}), face drawn as a framed card")
            return None
    return Image.open(cut).convert("RGBA")


def has_transparency(image: Image.Image) -> bool:
    return image.getchannel("A").getextrema()[0] < 255


def card(frame: Image.Image) -> Image.Image:
    """Fallback: a centered portrait crop of the frame, fully opaque."""
    width = min(frame.width, round(frame.height * CARD_ASPECT))
    left = (frame.width - width) // 2
    return frame.convert("RGBA").crop((left, 0, left + width, frame.height))


def load_face(value, base: Path, footage: Path | None, work: Path) -> Image.Image:
    """The face as an RGBA cutout (or framed card), ready for sticker()."""
    face = parse_face(value)
    if isinstance(face, float):
        if footage is None:
            raise RuntimeError(f"face time {face}s needs footage")
        frame = work / f"face_{face:g}.png"
        stale = (not frame.exists()
                 or (Path(footage).exists() and Path(footage).stat().st_mtime > frame.stat().st_mtime))
        if stale:
            grab_frame(Path(footage), face, frame)
    else:
        frame = next((path for path in (base / face, common.ROOT / face) if path.exists()), None)
        if frame is None:
            raise RuntimeError(f"no face image at {base / face} or {common.ROOT / face}")
        ready = Image.open(frame).convert("RGBA")
        if has_transparency(ready):
            if ready.getchannel("A").getbbox() is None:
                raise RuntimeError(f"{frame.name} is fully transparent, nobody to show")
            return ready
    cut = cutout(frame)
    if cut is None or cut.getbbox() is None:
        return card(Image.open(frame))
    return cut


def pad_for(outline: int) -> int:
    """Room around the cutout so the ring and the shadow are never clipped."""
    return outline + 2 * SHADOW_BLUR


def sticker(cut: Image.Image, outline: int = OUTLINE) -> Image.Image:
    """White outline + soft shadow around a cutout, the standard YouTube sticker look:
    the alpha grown with a MaxFilter in white, the same shape blurred underneath."""
    pad = pad_for(outline)
    subject = Image.new("RGBA", (cut.width + 2 * pad, cut.height + 2 * pad), (0, 0, 0, 0))
    subject.paste(cut, (pad, pad))
    grown = subject.getchannel("A").filter(ImageFilter.MaxFilter(outline * 2 + 1))
    out = Image.new("RGBA", subject.size, (0, 0, 0, 0))
    shadow = Image.new("RGBA", subject.size, (0, 0, 0, 255))
    shadow.putalpha(grown.filter(ImageFilter.GaussianBlur(SHADOW_BLUR))
                    .point(lambda v: round(v * SHADOW_STRENGTH)))
    out.alpha_composite(shadow)
    ring = Image.new("RGBA", subject.size, (255, 255, 255, 255))
    ring.putalpha(grown)
    out.alpha_composite(ring)
    out.alpha_composite(subject)
    return out


def head_center_x(cut: Image.Image) -> float:
    """Horizontal center of the opaque pixels in the top rows of the cutout, so the
    head (not the shoulders) is what lands on the mark."""
    alpha = cut.getchannel("A")
    left, top, right, bottom = alpha.getbbox()
    rows = max(1, round((bottom - top) * HEAD_ROWS))
    band = alpha.crop((left, top, right, top + rows))
    weights = list(band.resize((band.width, 1), Image.BOX).tobytes())   # column means
    total = sum(weights)
    if not total:
        return (left + right) / 2
    return left + sum((i + 0.5) * w for i, w in enumerate(weights)) / total


def place(canvas: Image.Image, cut: Image.Image, height: int, center_x: int,
          top: int) -> tuple[int, int, int, int]:
    """Scale the cutout so the subject is `height` tall, put its head center on
    center_x with the top of the head at `top`, and composite it with the sticker look.
    Returns the subject's box on the canvas."""
    subject = cut.crop(cut.getchannel("A").getbbox())
    scale = height / subject.height
    subject = subject.resize((max(1, round(subject.width * scale)), height), Image.LANCZOS)
    pad = pad_for(OUTLINE)
    x = round(center_x - head_center_x(subject))
    composite_at(canvas, sticker(subject), x - pad, top - pad)
    return (x, top, x + subject.width, top + height)


def composite_at(canvas: Image.Image, layer: Image.Image, x: int, y: int) -> None:
    """alpha_composite that accepts a layer hanging off any edge of the canvas
    (Pillow refuses negative offsets, so the part that falls off is skipped)."""
    canvas.alpha_composite(layer, (max(0, x), max(0, y)), (max(0, -x), max(0, -y)))
