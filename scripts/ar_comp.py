"""Archive reel: put a generated figure into real archive footage, small and far away.

Tony's rule (2026-09-23): generated footage reads fake when it IS the shot. Treat the
figure like film of Bigfoot or the Loch Ness monster: never clear, far off, fuzzy, inside
a real, locked-off 1924 shot. Per comp in job.json:

  "comps": {"hero": {"clip": "chad_hero_veo.mp4",            # generated clip in public/
                     "plate": {"src": "kriemhild", "at": 5458.2, "size": [960, 720], "dur": 1.6},
                     "feet": [632, 455], "height": 92, "haze": 0.2,    # plate pixels
                     "prop": {"seed": [75, 215], "span": 150, "angle": 0}}}   # optional axe stamp
Writes public/comp_<name>.mp4 at the plate's resolution. A footage shot then uses it with
"dir": "public", "src": "comp_<name>.mp4".
"""
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import ar_film
import common
import vision

MATTE_FPS, OUT_FPS = 12, 24
PLATES = {  # the 720p masters are range-read over HTTP, no full download needed
    "kriemhild": "https://archive.org/download/silent-die-nibelungen-kriemhilds-revenge/"
                 "Die%20Nibelungen%3A%20Kriemhild%27s%20Revenge.mkv",
    "siegfried": str(ar_film.ARCHIVE / "films" / "siegfried_1924.mp4"),  # mkv is a different cut
    "haxan": str(ar_film.ARCHIVE / "films" / "haxan_1922.mp4"),
    "viking": str(ar_film.ARCHIVE / "films" / "viking_1928.mp4"),
}
MATTE_SCRIPT = """
import sys
from pathlib import Path
from rembg import new_session, remove
from PIL import Image
session = new_session("isnet-general-use")
src, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
for f in sorted(src.glob("*.png")):
    remove(Image.open(f), session=session, post_process_mask=True).save(out / f.name)
"""


def matte(jdir, name, clip):
    """rembg cutout of every frame at 12 fps. Cached: about 3 minutes per 4 s clip on CPU."""
    base = jdir / "work" / "matte" / name
    rgba = base / "rgba"
    if rgba.is_dir() and any(rgba.glob("*.png")):
        return sorted(rgba.glob("*.png"))
    rembg_py = vision.rembg_python()
    if rembg_py is None:
        common.die(vision.REMBG_HINT)
    src = base / "src"
    src.mkdir(parents=True, exist_ok=True)
    ar_film.run(["ffmpeg", "-v", "error", "-y", "-i", jdir / "public" / clip, "-vf", f"fps={MATTE_FPS},scale=540:960",
                 src / "%04d.png"])
    subprocess.run([str(rembg_py), "-c", MATTE_SCRIPT, str(src), str(rgba)], check=True, capture_output=True)
    return sorted(rgba.glob("*.png"))


def axe_head(span):
    """Double-bladed battle-axe head, blades either side of a vertical haft."""
    w, h = span, int(span * 0.8)
    img = Image.new("RGBA", (w, h))
    d = ImageDraw.Draw(img)
    cx, cy, eye = w // 2, h // 2, max(3, span // 14)
    for side in (-1, 1):
        tip = cx + side * (w // 2 - 2)
        blade = [(cx + side * eye, cy - h * 0.12), (cx + side * w * 0.28, cy - h * 0.2), (tip, cy - h * 0.48),
                 (tip - side * w * 0.04, cy), (tip, cy + h * 0.48), (cx + side * w * 0.28, cy + h * 0.2),
                 (cx + side * eye, cy + h * 0.12)]
        d.polygon(blade, fill=(58, 56, 54, 255))
        d.line([blade[2], blade[3], blade[4]], fill=(170, 168, 160, 255), width=max(2, span // 40))
    d.rectangle([cx - eye, cy - h * 0.22, cx + eye, cy + h * 0.22], fill=(40, 38, 36, 255))
    return img.filter(ImageFilter.GaussianBlur(0.6))


def track(frames, seed, patch=24, search=18):
    """Follow a point by normalized cross-correlation, outward from the middle frame, then smooth."""
    grays = [np.asarray(f.convert("L"), float) for f in frames]
    mid = len(frames) // 2
    pos = [None] * len(frames)
    pos[mid] = tuple(seed)
    for step in (1, -1):
        for i in range(mid + step, len(frames) if step > 0 else -1, step):
            px, py = pos[i - step]
            tpl = grays[i - step][max(0, py - patch):py + patch, max(0, px - patch):px + patch]
            best, best_xy = -2.0, (px, py)
            for dy in range(-search, search + 1, 2):
                for dx in range(-search, search + 1, 2):
                    x, y = px + dx, py + dy
                    win = grays[i][max(0, y - patch):y + patch, max(0, x - patch):x + patch]
                    if win.shape != tpl.shape or win.size == 0:
                        continue
                    a, b = win - win.mean(), tpl - tpl.mean()
                    score = (a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-6)
                    if score > best:
                        best, best_xy = score, (x, y)
            pos[i] = best_xy
    xs = np.convolve([p[0] for p in pos], np.ones(5) / 5, mode="same")
    ys = np.convolve([p[1] for p in pos], np.ones(5) / 5, mode="same")
    return [(int(x), int(y)) for x, y in zip(xs, ys)]


def stamp_prop(frames, prop):
    """Same prop in every shot: track the real one and stamp the canonical head over it."""
    path = track(frames, prop["seed"])
    head = axe_head(prop.get("span", 150)).rotate(prop.get("angle", 0), expand=True)
    ox, oy = prop.get("offset", (0, 0))
    out = []
    for frame, (x, y) in zip(frames, path):
        frame = frame.copy()
        frame.alpha_composite(head, (x + ox - head.width // 2, y + oy - head.height // 2))
        out.append(frame)
    return out


def plate_frames(plate):
    w, h = plate["size"]
    src = PLATES.get(plate["src"], plate["src"])
    for attempt in range(3):  # the 720p masters are read over HTTP, which can drop a request
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{plate['at']}", "-i", src, "-t", f"{plate['dur']}",
                              "-vf", f"fps={OUT_FPS},scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True).stdout
        frames = np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)
        if len(frames) >= int(plate["dur"] * OUT_FPS) - 1:
            return frames
    common.die(f"[ar] plate {plate['src']} @ {plate['at']}s came back with {len(frames)} frames after 3 tries")


def distant(figure, lut, height, haze, backdrop):
    """Archive tones, shrunk, softened, and pulled toward the plate's local brightness."""
    gray = np.asarray(figure, float)[..., :3].mean(axis=2)
    toned = Image.fromarray(lut[np.clip(gray, 0, 255).astype(int)].astype(np.uint8))
    bbox = figure.getchannel("A").getbbox()
    fig = Image.merge("RGBA", [toned] * 3 + [figure.getchannel("A")]).crop(bbox)
    scale = height / fig.height
    fig = fig.resize((max(1, int(fig.width * scale)), height), Image.LANCZOS).filter(ImageFilter.GaussianBlur(0.9))
    f = np.asarray(fig, float)
    f[..., :3] = f[..., :3] * (1 - haze) + backdrop * haze
    return Image.fromarray(f.astype(np.uint8), "RGBA"), bbox, scale


def composite(jdir, name, spec):
    frames = [Image.open(f).convert("RGBA") for f in matte(jdir, name, spec["clip"])]
    if spec.get("prop"):
        frames = stamp_prop(frames, spec["prop"])
    lut_path = ar_film.match_lut(jdir / "public" / spec["clip"], jdir / "work" / f"lut_comp_{name}.cube")
    lut = np.array([float(r.split()[0]) * 255 for r in Path(lut_path).read_text().split("\n")[1:] if r.strip()])
    plates = plate_frames(spec["plate"])
    w, h = spec["plate"]["size"]
    fx, fy = spec["feet"]
    first = int(spec.get("figure_in", 0.3) * MATTE_FPS)
    out = jdir / "public" / f"comp_{name}.mp4"
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                             "-r", str(OUT_FPS), "-i", "-", "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p",
                             str(out)], stdin=subprocess.PIPE)
    anchor = None
    for i, plate in enumerate(plates):
        figure = frames[min(len(frames) - 1, first + i * MATTE_FPS // OUT_FPS)]
        backdrop = plate[max(0, fy - spec["height"]):fy, max(0, fx - 40):fx + 40].mean()
        fig, bbox, scale = distant(figure, lut, spec["height"], spec.get("haze", 0.2), backdrop)
        anchor = anchor or (bbox[0], bbox[3])  # keep the real walking motion, scaled down
        dx, dy = (bbox[0] - anchor[0]) * scale, (bbox[3] - anchor[1]) * scale
        frame = Image.fromarray(plate).convert("RGBA")
        frame.alpha_composite(fig, (int(fx - fig.width / 2 + dx), int(fy - fig.height + dy)))
        proc.stdin.write(np.asarray(frame.convert("RGB")).tobytes())
    proc.stdin.close()
    proc.wait()
    print(f"[ar] comp {name}: {len(plates)} frames -> {out}")
    return out


def composite_all(jdir, job, only=None):
    for name, spec in (job.get("comps") or {}).items():
        if only in (None, name):
            composite(jdir, name, spec)
