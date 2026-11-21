"""Real-photograph source for a scene, as an alternative to FLUX generation.

A scene (or a shots entry) may carry a "photo" key instead of relying on
image_prompt. The file is ingested, oriented, and cover-cropped to the exact
canvas the rest of the pipeline expects, so Ken Burns, captions, the vertical
cut and the contact sheet all behave identically to a generated still.

Why this is a separate path and not a theme: a generated still is always born
at IMG_W x IMG_H, but a real photo arrives at whatever size and aspect the
source published. Feeding that straight into zoompan letterboxes it.
"""
import io
import shutil
from pathlib import Path
from urllib.parse import urlparse

import common

PHOTO_DIR = common.ROOT / "assets" / "photos"

# Where to anchor the crop when the source aspect does not match the target.
# A portrait source cropped dead-centre into a landscape frame cuts foreheads
# off, because faces sit in the upper third of a headshot. Everything else
# centres.
PORTRAIT_ANCHOR = 0.35

FOCUS_ANCHORS = {"top": 0.0, "upper": 0.25, "center": 0.5, "lower": 0.75, "bottom": 1.0}


def resolve(src):
    """A photo reference is a URL, an absolute path, a path relative to the
    pipeline's assets/photos/, or a path relative to the cwd."""
    if urlparse(str(src)).scheme in ("http", "https"):
        return str(src)
    path = Path(src).expanduser()
    for candidate in (path, PHOTO_DIR / src, Path.cwd() / src):
        if candidate.is_file():
            return candidate
    common.die(f"photo not found: {src} (looked in {PHOTO_DIR} and the working directory)")


def load_bytes(ref):
    if isinstance(ref, str):
        return common.http_get(ref, timeout=60)
    return Path(ref).read_bytes()


def anchor_for(image, target_w, target_h, focus):
    if focus in FOCUS_ANCHORS:
        return FOCUS_ANCHORS[focus]
    source_taller = image.height / image.width > target_h / target_w
    return PORTRAIT_ANCHOR if source_taller else 0.5


def cover_crop(image, target_w, target_h, focus="auto"):
    """Scale to cover, then crop, mirroring ffmpeg's
    force_original_aspect_ratio=increase + crop so a photo scene and a
    generated scene are pixel-compatible downstream."""
    from PIL import Image

    scale = max(target_w / image.width, target_h / image.height)
    new = image.resize((max(target_w, round(image.width * scale)),
                        max(target_h, round(image.height * scale))),
                       Image.LANCZOS)
    anchor = anchor_for(image, target_w, target_h, focus)
    left = round((new.width - target_w) * 0.5)
    top = round((new.height - target_h) * anchor)
    return new.crop((left, top, left + target_w, top + target_h))


def ingest(src, out_path, target_w, target_h, focus="auto"):
    """Write one source photograph to out_path at exactly target_w x target_h."""
    from PIL import Image, ImageOps

    ref = resolve(src)
    data = load_bytes(ref)
    if len(data) < 1000:
        common.die(f"photo {src} is only {len(data)} bytes, that is not an image")
    image = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    if min(image.width, image.height) < 480:
        print(f"[photos] WARNING: {src} is only {image.width}x{image.height}; "
              f"upscaling to {target_w}x{target_h} will look soft under Ken Burns")
    cover_crop(image, target_w, target_h, focus).save(out_path)
    print(f"[photos] {out_path.name}: {src} "
          f"({image.width}x{image.height} -> {target_w}x{target_h}, focus={focus})")
    return {"source": str(src), "src_w": image.width, "src_h": image.height}


def stash(job_id, src):
    """Keep a copy of every source photo with the job, so a video can be
    re-cut months later without re-resolving a URL that may have moved."""
    ref = resolve(src)
    originals = common.job_dir(job_id) / "work" / "photos"
    originals.mkdir(parents=True, exist_ok=True)
    name = Path(urlparse(str(ref)).path if isinstance(ref, str) else ref).name
    dest = originals / name
    if isinstance(ref, str):
        dest.write_bytes(load_bytes(ref))
    elif not dest.exists():
        shutil.copy2(ref, dest)
    return dest
