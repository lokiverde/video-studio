"""Face privacy pass for tribute_reel: every face in a cut is blurred before anything else.

prep_cut() renders one cut's source span to a 1080x1920 30fps clip, runs the Apple Vision
detector (bin/facedetect: faces plus heads from upper-body boxes, tiled for small crowd
faces) on every DETECT_EVERY-th frame, holds each box for HOLD frames either side so a
missed frame never flashes a face, adds any manual masks, and writes <key>_blur.mp4.
Results are cached by the cut's source span, so re-timing an edit does not re-detect.
"""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np

import vision

W, H, FPS = 1080, 1920, 30
DETECT_EVERY = 2          # run the detector on every 2nd frame
HOLD = 6                  # frames a box persists either side of the frame it was seen on
FACE_GROW = 1.6           # face boxes are tight; grow to cover hair, ears, chin
HEAD_GROW = 1.15
GRID = 5                  # finest detector tile grid (see scripts/facedetect.swift)


def run(cmd):
    subprocess.run(cmd, check=True)


def cut_key(cut, span):
    raw = json.dumps([cut["clip"], cut["a"], span, cut.get("speed", 1.0), cut.get("cx", 0.5),
                      cut.get("cy", 0.5), cut.get("zoom", 1.0)])
    return hashlib.sha1(raw.encode()).hexdigest()[:10]


def crop_filter(src_w, src_h, cut):
    """9:16 window around (cx, cy), optionally tighter by `zoom`, scaled to 1080x1920."""
    zoom = cut.get("zoom", 1.0)
    ch = src_h / zoom
    cw = ch * 9 / 16
    if cw > src_w:                       # source narrower than 9:16: crop height instead
        cw, ch = src_w / zoom, src_w / zoom * 16 / 9
    y = min(max(cut.get("cy", 0.5) * src_h - ch / 2, 0), src_h - ch)
    return f"crop={int(cw)}:{int(ch)}:'{track_x(cut.get('cx', 0.5), src_w, cw)}':{int(y)},scale={W}:{H}:flags=lanczos,setsar=1"


def track_x(cx, src_w, cw):
    """Crop x: a fixed center, or [[t, cx], ...] keyframes (t = seconds into the cut's
    source) for a tracking crop that follows a subject, e.g. a helicopter across the sky."""
    def px(c):
        return min(max(c * src_w - cw / 2, 0), src_w - cw)
    if not isinstance(cx, list):
        return str(int(px(cx)))
    keys = sorted(cx)
    expr = f"{px(keys[-1][1]):.1f}"
    for (t0, c0), (t1, c1) in reversed(list(zip(keys, keys[1:]))):
        x0, x1 = px(c0), px(c1)
        expr = f"if(lt(t,{t1}),{x0:.1f}+({x1 - x0:.1f})*(t-{t0})/{t1 - t0},{expr})"
    return f"if(lt(t,{keys[0][0]}),{px(keys[0][1]):.1f},{expr})"


def probe_size(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout.strip()
    w, h = (int(v) for v in out.split(",")[:2])
    return w, h


def render_raw(src, cut, span, out):
    speed = cut.get("speed", 1.0)
    sw, sh = probe_size(src)
    vf = [crop_filter(sw, sh, cut), f"setpts=PTS/{speed}"]
    if speed < 1.0:                      # slow motion: interpolate the in-between frames
        vf.append(f"minterpolate=fps={FPS}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir")
    vf.append(f"fps={FPS}")
    run(["ffmpeg", "-v", "error", "-y", "-ss", str(cut["a"]), "-t", str(span * speed), "-i", str(src),
         "-vf", ",".join(vf), "-an", "-c:v", "libx264", "-crf", "12", "-preset", "fast",
         "-pix_fmt", "yuv420p", str(out)])


def detect(raw, workdir):
    frames = workdir / "frames"
    shutil.rmtree(frames, ignore_errors=True)
    frames.mkdir(parents=True)
    run(["ffmpeg", "-v", "error", "-i", str(raw), "-vf", f"select='not(mod(n\\,{DETECT_EVERY}))'",
         "-fps_mode", "passthrough", "-q:v", "2", str(frames / "%06d.jpg")])
    found = vision.detect_faces(frames, GRID)
    shutil.rmtree(frames)
    # files are numbered 1.. in order of the selected frames
    return {(int(Path(k).stem) - 1) * DETECT_EVERY: v for k, v in found.items()}


def grow(box):
    x, y, w, h, conf = box
    g = HEAD_GROW if conf >= 2 else FACE_GROW
    cx, cy = x + w / 2, y + h / 2
    w, h = w * g, h * g * (1.15 if conf < 2 else 1.0)
    return [cx - w / 2, cy - h / 2, w, h]


def boxes_for(n, dets, masks, t):
    found = []
    for m in range(n - HOLD, n + HOLD + 1):
        found += [grow(b) for b in dets.get(m, [])]
    for m in masks:                      # manual: [x, y, w, h] or [x, y, w, h, t0, t1]
        if len(m) == 4 or m[4] <= t <= m[5]:
            found.append(m[:4])
    return found


def blur_frame(img, boxes):
    if not boxes:
        return img
    k = max(31, (min(W, H) // 18) | 1)
    soft = cv2.GaussianBlur(cv2.GaussianBlur(img, (k, k), 0), (k, k), 0)
    mask = np.zeros((H, W), np.float32)
    for x, y, w, h in boxes:
        center = (int((x + w / 2) * W), int((y + h / 2) * H))
        axes = (max(4, int(w * W / 2)), max(4, int(h * H / 2)))
        cv2.ellipse(mask, center, axes, 0, 0, 360, 1.0, -1)
    feather = max(9, (int(min(W, H) * 0.02)) | 1)
    mask = cv2.GaussianBlur(mask, (feather, feather), 0)
    mask = np.clip(mask * 1.6, 0, 1)[..., None]
    return (img * (1 - mask) + soft * mask).astype(np.uint8)


def write_blurred(raw, dets, masks, out):
    cap = cv2.VideoCapture(str(raw))
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
                            "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "14",
                            "-preset", "fast", "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    n = 0
    while True:
        ok, img = cap.read()
        if not ok:
            break
        enc.stdin.write(blur_frame(img, boxes_for(n, dets, masks, n / FPS)).tobytes())
        n += 1
    cap.release()
    enc.stdin.close()
    if enc.wait() != 0:
        raise RuntimeError(f"encoding {out.name} failed")
    return n


def prep_cut(jdir, src, cut, span, force=False):
    """Blurred 1080x1920 clip for one cut. Returns its path."""
    cache = jdir / "work" / "cuts"
    cache.mkdir(parents=True, exist_ok=True)
    key = cut_key(cut, span)
    raw, dets_file = cache / f"{key}_raw.mp4", cache / f"{key}_faces.json"
    out = cache / f"{key}_blur.mp4"
    if not raw.exists() or force:
        render_raw(src, cut, span, raw)
    if cut.get("faces", True) is False:          # no people in shot (sky, helicopter)
        dets = {}
    elif dets_file.exists() and not force:
        dets = {int(k): v for k, v in json.loads(dets_file.read_text()).items()}
    else:
        dets = detect(raw, cache / key)
        dets_file.write_text(json.dumps(dets))
    masks = cut.get("masks", [])
    stamp = cache / f"{key}_blur.json"
    want = json.dumps({"masks": masks, "faces": cut.get("faces", True), "hold": HOLD})
    if not out.exists() or force or not stamp.exists() or stamp.read_text() != want:
        n = write_blurred(raw, dets, masks, out)
        stamp.write_text(want)
        found = sum(len(v) for v in dets.values())
        print(f"[blur] {cut['clip']} @{cut['a']}s: {n} frames, {found} detections")
    return out
