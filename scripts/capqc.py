"""Caption QC for talking-head jobs: no caption over Tony's mouth or chin, and every
caption readable against what is behind it. Runs with the contact sheets, before Tony
approves, so a bad spot is fixed before the long render.

From Nate Herk's edit kit (reviewed 2026-10-29): "never over the mouth or chin, least of
all in the first second, when the viewer decides whether the person on screen is real",
and "never white on light: measure the pixels behind every caption".

How it finds the caption without knowing the style: each chosen frame is rendered twice,
as approved and with no captions and no phrases (talking-head/qc-stills.mjs, one bundle
for all of them). Phrases count because in board style 16:9 they ARE the caption line,
same place and type. The pixels that differ are the caption, box and shadow included,
wherever the layout put it. Apple Vision (or OpenCV off a Mac, see vision.py) finds the lips and chin on the captions-off frame.

Contrast is measured on what the viewer sees: the caption's text pixels against the
pixels just around them (the box, or the shadow over the footage). Captions are light
text in every style; a frame whose caption has no light text is not judged.

  capqc.py <job>        both cuts (th.py sheet runs it too)
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import common
import platform_util
import vision

TEMPLATE = common.ROOT / "talking-head"
STILLS = TEMPLATE / "qc-stills.mjs"

FPS = 30
SCALE = 0.5            # half size is plenty for Vision and for contrast, and twice as fast
DIFF = 30              # per-channel difference (0-255) that counts as a caption pixel
MIN_PIXELS = 150       # fewer changed pixels than this at SCALE: no caption on that frame
MOUTH_COVER = 0.02     # share of the mouth-to-chin zone a caption may touch
MIN_FACE = 0.06        # faces narrower than this share of the frame (receipts, crowds) are not Tony's
MIN_CONTRAST = 3.0     # WCAG AA for large text
OPENING = 2.5          # seconds checked closely: where viewers decide if the person is real
OPENING_STEP = 5       # frames between opening checks (6 a second)
MAX_FRAMES = 48        # per cut; each costs two renders of about 0.8 s


# --- pure: pixels ------------------------------------------------------------------

def caption_mask(on, off, diff=DIFF):
    """Pixels the caption changed: max channel difference between the two renders."""
    return np.abs(on.astype(np.int16) - off.astype(np.int16)).max(axis=2) > diff


def luminance(rgb):
    """WCAG relative luminance, 0 (black) to 1 (white), per pixel."""
    c = rgb.astype(np.float64) / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return lin @ np.array([0.2126, 0.7152, 0.0722])


def dilate(mask, r):
    """Square dilation by r pixels, numpy only."""
    out = mask.copy()
    h, w = mask.shape
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            ys, yd = (slice(dy, h), slice(0, h - dy)) if dy >= 0 else (slice(0, h + dy), slice(-dy, h))
            xs, xd = (slice(dx, w), slice(0, w - dx)) if dx >= 0 else (slice(0, w + dx), slice(-dx, w))
            out[yd, xd] |= mask[ys, xs]
    return out


def contrast(on, mask):
    """(ratio, text luminance, around luminance) of the caption in `on`, or None when the
    caption has no light text to judge. Text = the light pixels of the caption; around =
    the ring 2 to 3 pixels outside them, as the viewer sees it."""
    lum = luminance(on)
    vals = lum[mask]
    if vals.size == 0:
        return None
    top = np.percentile(vals, 95)
    if top < 0.4:
        return None
    core = mask & (lum >= 0.6 * top)
    ring = dilate(core, 3) & ~dilate(core, 1)
    if not core.any() or not ring.any():
        return None
    text, around = float(np.percentile(lum[core], 20)), float(np.median(lum[ring]))
    return (text + 0.05) / (around + 0.05), text, around


def mouth_zone(face, w, h):
    """Pixel box from just above the lips to the bottom of the chin, a little wider than
    the lips, or None without lips."""
    lips = face.get("lips")
    if not lips:
        return None
    lx, ly, lw, lh = lips
    chin = max(face.get("chin", 0), ly + 2 * lh)
    return (int((lx - 0.15 * lw) * w), int((ly - 0.6 * lh) * h), int((lx + 1.15 * lw) * w), int(chin * h))


def zone_cover(mask, zone):
    x0, y0, x1, y1 = (max(0, v) for v in zone)
    box = mask[y0:y1, x0:x1]
    return float(box.mean()) if box.size else 0.0


def main_face(faces):
    """The biggest face with lips, if it is big enough to be the speaker."""
    found = [f for f in faces if f.get("lips") and f["face"][2] >= MIN_FACE]
    return max(found, key=lambda f: f["face"][2] * f["face"][3]) if found else None


def frame_problems(t, on, off, faces):
    """Problems on one frame (strings), empty when the caption is fine or absent."""
    mask = caption_mask(on, off)
    if mask.sum() < MIN_PIXELS:
        return []
    out = []
    face = main_face(faces)
    if face:
        h, w = mask.shape
        cover = zone_cover(mask, mouth_zone(face, w, h))
        if cover > MOUTH_COVER:
            when = " (opening seconds)" if t < OPENING else ""
            out.append(f"{t:.1f}s caption over the mouth or chin{when}, {cover:.0%} of that zone")
    c = contrast(on, mask)
    if c and c[0] < MIN_CONTRAST:
        out.append(f"{t:.1f}s caption hard to read, contrast {c[0]:.1f}:1 (needs {MIN_CONTRAST:g}:1)")
    return out


# --- pure: which frames ------------------------------------------------------------

def _showing(captions, t):
    return any(c["s"] <= t < c["e"] for c in captions)


def pick_frames(captions, moments, max_frames=MAX_FRAMES):
    """Frames worth checking, all while a caption is up: the opening every OPENING_STEP
    frames, every contact-sheet moment (each layout as it lands), then caption starts
    spread evenly over the video to fill up to max_frames."""
    opening = [f for f in range(0, int(OPENING * FPS) + 1, OPENING_STEP) if _showing(captions, f / FPS)]
    layout = [round(t * FPS) for t in moments if _showing(captions, t)]
    chosen = list(dict.fromkeys(opening + layout))[:max_frames]
    starts = [round(c["s"] * FPS) + 3 for c in captions if round(c["s"] * FPS) + 3 not in chosen]
    room = max_frames - len(chosen)
    if room > 0 and starts:
        step = max(1, len(starts) / room)
        chosen += [starts[int(i * step)] for i in range(min(room, len(starts)))]
    return sorted(set(chosen))


# --- I/O -----------------------------------------------------------------------------

def _render(comp, props_path, public_dir, frames, out_dir):
    props = json.loads(Path(props_path).read_text())
    off = Path(out_dir) / "props_off.json"
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    off.write_text(json.dumps({**props, "job": {**props["job"], "captions": [], "phrases": []}}))
    manifest = Path(out_dir) / "manifest.json"
    manifest.write_text(json.dumps({"composition": comp, "publicDir": str(public_dir), "outDir": str(out_dir),
                                    "scale": SCALE, "frames": frames,
                                    "variants": {"on": str(Path(props_path).resolve()), "off": str(off)}}))
    result = subprocess.run([platform_util.tool("node"), str(STILLS), str(manifest)], cwd=TEMPLATE, capture_output=True, text=True,
                            stdin=subprocess.DEVNULL)
    if result.returncode != 0:
        common.die(f"[capqc] still render failed:\n{result.stderr[-1500:]}")


def check(comp, props_path, public_dir, moments, out_dir):
    """Render, detect, judge. Returns problem strings for this cut. The stills are deleted
    afterwards (about 50 MB a cut); each flagged frame is kept as out_dir/flag_<time>s.jpg
    to show Tony."""
    captions = json.loads(Path(props_path).read_text())["job"].get("captions", [])
    frames = pick_frames(captions, moments)
    if not frames:
        return []
    _render(comp, props_path, public_dir, frames, out_dir)
    faces = vision.detect_mouths(Path(out_dir) / "off")
    problems = []
    for old in Path(out_dir).glob("flag_*.jpg"):
        old.unlink()
    for f in frames:
        name = f"{f:06d}.png"
        image = Image.open(Path(out_dir) / "on" / name).convert("RGB")
        found = frame_problems(f / FPS, np.asarray(image), np.asarray(Image.open(Path(out_dir) / "off" / name).convert("RGB")),
                               faces.get(name, []))
        if found:
            image.save(Path(out_dir) / f"flag_{f / FPS:06.1f}s.jpg", quality=85)
        problems += found
    for sub in ("on", "off"):
        shutil.rmtree(Path(out_dir) / sub, ignore_errors=True)
    return problems


def main():
    import th
    job_id = sys.argv[1] if len(sys.argv) > 1 else common.die("usage: capqc.py <job>")
    th.caption_qc(job_id)


if __name__ == "__main__":
    main()
