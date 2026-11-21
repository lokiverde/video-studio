"""Shop Surfer pre-pass: a skull drawing over the wearer's face, and an optional waist slim.

  sr_skull.py track <job>     pose + person matte (Apple Vision, or MediaPipe off a Mac; see vision.py) for every
                              source frame the cuts use, cached in work/track/<clip>/
  sr_skull.py check <job>     work/skull_check.jpg: 8 frames from every cut of a skull clip,
                              and before/after pairs for each slim cut
  sr_skull.py apply <job>     work/<clip>_skull.mp4 at source size and frame timing, and
                              job.json "clips" pointed at it (originals kept under "sources")

job.json:
  "skull": {"image": "assets/skull_grin.png", "clips": ["wear"],
            "anchor": [0.5, 0.40], "width": 1.45, "turn": true, "blur": true}
      anchor: the skull's eye line in the image (fractions); width: skull width as a
      multiple of the head width measured on the matte at eye level; turn: wrap the drawing
      round the head and turn it to where he looks; blur: blur the head under the drawing.
  "slim": [{"clip": "wear", "a": 33.2, "b": 35.0, "amount": 0.12}]
      pulls both sides of the torso in by `amount` of its half-width around the waist.

Every face gets a skull: a frame gets one wherever the pose shows a person's nose or an eye
(the face is toward camera, profiles included), held HOLD frames either side, and each head is
followed on its own. Backs of heads stay as they are.
Per cut: "skull": false turns it off, "skull": "full" keeps it on for the whole cut, and
"skull_keys": [[t, x, y, head_w], ...] places it by hand where the pose misses the face.
"""
import argparse
import json
import math
import subprocess

import cv2
import numpy as np

import common
import vision
import sr_skull_draw as skull_draw
from surfer_reel import load_job, resolve

TRACK_W = 864                 # tracking frame width (half the DJI vertical frame)
MARGIN = 0.2                  # seconds tracked either side of each cut
HOLD = 4                      # frames the skull stays on either side of a face sighting
LINK_GAP = 2 * HOLD + 1       # frames a head can go unseen and still be the same head
LINK_REACH = 1.5              # how far a head can move between sightings, in head widths
FACE_CONF = 0.3
MIN_CONF = 0.15
EYES = ("left_eye_joint", "right_eye_joint")
EARS = ("left_ear_joint", "right_ear_joint")
HIPS = ("left_upLeg_joint", "right_upLeg_joint")
SHOULDERS = ("left_shoulder_1_joint", "right_shoulder_1_joint")


def run(cmd):
    subprocess.run(cmd, check=True)


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate,nb_frames", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout.strip().split(",")
    num, den = out[2].split("/")
    return int(out[0]), int(out[1]), float(num) / float(den), out[2], int(out[3])


def source_of(job, clip):
    return job.get("sources", {}).get(clip) or job["clips"][clip]


def frame_spans(job, clip, fps, margin=MARGIN):
    """(first, last) source frame numbers of every cut of this clip, with a margin."""
    return [(max(0, round((c["a"] - margin) * fps)), round((c["b"] + margin) * fps), i)
            for i, c in enumerate(job["cuts"]) if c["clip"] == clip]


def needed_clips(job):
    return sorted(set(job.get("skull", {}).get("clips", [])) | {s["clip"] for s in job.get("slim", [])})


# ---------- tracking ----------

def track_clip(jdir, job, clip):
    src = source_of(job, clip)
    w, h, fps, _, total = probe(src)
    tdir = jdir / "work" / "track" / clip
    cache = tdir / "pose.json"
    pose = {int(k): v for k, v in json.loads(cache.read_text()).items()} if cache.exists() else {}
    want = sorted({n for a, b, _ in frame_spans(job, clip, fps) for n in range(a, min(b, total - 1) + 1)}
                  - set(pose))
    if not want:
        return pose
    frames = tdir / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    for f in frames.glob("*.jpg"):
        f.unlink()
    runs, start = [], want[0]
    for prev, n in zip(want, want[1:] + [None]):
        if n != prev + 1:
            runs.append((start, prev))
            start = n
    pick = "+".join(f"between(n\\,{a}\\,{b})" for a, b in runs)
    run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf",
         f"select='{pick}',scale={TRACK_W}:-2", "-fps_mode", "passthrough", "-q:v", "2",
         str(frames / "%06d.jpg")])
    names = sorted(frames.glob("*.jpg"))
    if len(names) != len(want):
        common.die(f"[skull] {clip}: extracted {len(names)} frames, wanted {len(want)}")
    for f, n in zip(names, want):                    # renumber to source frame numbers
        f.replace(frames / f"n{n:06d}.jpg")
    for name, joints in vision.track_bodies(frames, tdir / "mattes").items():
        pose[int(name[1:7])] = joints
    for f in frames.glob("*.jpg"):
        f.unlink()
    cache.write_text(json.dumps(pose))
    print(f"[skull] {clip}: tracked {len(want)} frames")
    return pose


def matte(jdir, clip, n):
    path = jdir / "work" / "track" / clip / "mattes" / f"n{n:06d}.png"
    return cv2.imread(str(path), cv2.IMREAD_GRAYSCALE) if path.exists() else None


def people(v):
    """Every person's joints in a frame. Caches from the one-person tracker hold a single map."""
    return v if isinstance(v, list) else [v] if v else []


def joint(j, name, conf=MIN_CONF):
    p = j.get(name)
    return (p[0], p[1]) if p and p[2] >= conf else None


# ---------- series helpers ----------

EXTRAPOLATE = 8               # frames a trend is carried past the last sighting, then held


def fill(series, frames, cap=EXTRAPOLATE):
    """Linear interpolation inside, linear extrapolation (fit of 6 nearest) past the ends,
    carried `cap` frames and then held (cap=None: carried all the way)."""
    known = [n for n in frames if series.get(n) is not None]
    if not known:
        return None
    scalar = np.ndim(series[known[0]]) == 0
    xs = np.array(known, float)
    ys = np.array([np.atleast_1d(np.asarray(series[n], float)) for n in known])
    out = {}
    for n in frames:
        if known[0] <= n <= known[-1]:
            v = np.array([np.interp(n, xs, ys[:, k]) for k in range(ys.shape[1])])
        elif len(known) >= 3:
            side = slice(0, 6) if n < known[0] else slice(-6, None)
            at = n if cap is None else \
                max(n, known[0] - cap) if n < known[0] else min(n, known[-1] + cap)
            v = np.array([np.polyval(np.polyfit(xs[side], ys[side, k], 1), at) for k in range(ys.shape[1])])
        else:
            v = ys[0] if n < known[0] else ys[-1]
        out[n] = float(v[0]) if scalar else v
    return out


def smooth(series, frames, sigma):
    """Median of 5 (drops one-frame pose glitches), then a Gaussian of `sigma` frames."""
    arr = np.array([series[n] for n in frames], float)
    if len(arr) >= 5:
        pad5 = np.pad(arr, [(2, 2)] + [(0, 0)] * (arr.ndim - 1), mode="edge")
        arr = np.median(np.stack([pad5[i:i + len(arr)] for i in range(5)]), axis=0)
    k = np.arange(-3 * math.ceil(sigma), 3 * math.ceil(sigma) + 1)
    wts = np.exp(-0.5 * (k / sigma) ** 2)
    pad = np.pad(arr, [(len(k) // 2, len(k) // 2)] + [(0, 0)] * (arr.ndim - 1), mode="edge")
    sm = np.stack([np.tensordot(wts / wts.sum(), pad[i:i + len(k)], axes=(0, 0)) for i in range(len(arr))])
    return dict(zip(frames, sm))


# ---------- skull placement ----------

def head_measure(j, m, w, h):
    """(x, y, head width, roll, yaw, tilt) in source pixels and radians, or None when the face
    is not shown."""
    eyes = [joint(j, e, FACE_CONF) for e in EYES]
    nose = joint(j, "head_joint", FACE_CONF)
    seen = [e for e in eyes if e]
    if not seen and not nose:
        return None
    # A face must sit above the shoulders: the pose model also finds "faces" in a back print.
    shoulders = [s for s in (joint(j, k) for k in SHOULDERS) if s]
    face_y = min([e[1] for e in seen] + ([nose[1]] if nose else []))
    if not shoulders or face_y >= min(s[1] for s in shoulders):
        return None
    if m is None:
        return None
    mh, mw = m.shape
    ex = np.mean([e[0] for e in seen]) if seen else nose[0]
    # eye line from every head point the pose has, weak eyes and ears included
    level = [p[1] for p in (joint(j, k, 0.1) for k in EYES + EARS) if p]
    ey = np.mean(level) if level else nose[1] - 0.02
    # The head itself is the matte run on the eye line: its middle is the centre, its
    # length the width. A dark print reads as a hole in the matte, so no run, no face.
    row = m[min(mh - 1, max(0, int(ey * mh)))] > 127
    cx = min(mw - 1, max(0, int(ex * mw)))
    if not row[cx]:
        return None
    left = cx - np.argmin(row[cx::-1]) if not row[:cx + 1].all() else 0
    right = cx + np.argmin(row[cx:]) if not row[cx:].all() else mw
    # ...and near the top of the person: above real eyes there is only forehead and cap,
    # above a skeleton printed on a shirt there is the rest of the shirt.
    col = m[:max(1, int(ey * mh)), cx][::-1] > 127
    above = np.argmin(col) if not col.all() else len(col)
    if above > 1.5 * (min(s[1] for s in shoulders) - face_y) * mh:
        return None
    roll = 0.0
    if all(joint(j, e, 0.5) for e in EYES):
        (lx, ly), (rx, ry) = eyes
        roll = max(-0.15, min(0.15, math.atan2((ly - ry) * h, (lx - rx) * w)))
    x, width = (left + right) / 2 / mw * w, (right - left) / mw * w
    return (x, ey * h, width, roll, *skull_draw.head_turn(j, x, width, w, h, joint, FACE_CONF))


def distinct(found):
    """One measurement per head: drops a second detection of the same head (the bigger stays)."""
    keep = []
    for m in sorted(found, key=lambda m: -m[2]):
        if all(math.dist(m[:2], k[:2]) > 0.5 * max(m[2], k[2]) for k in keep):
            keep.append(m)
    return keep


def link(frames, found):
    """Face sightings per frame -> one {frame: measurement} per head. Vision lists people in no
    fixed order, so each sighting joins the nearest head seen in the last LINK_GAP frames."""
    heads = []
    for n in frames:
        live = [hd for hd in heads if n - max(hd) <= LINK_GAP]
        pairs = sorted((math.dist(hd[max(hd)][:2], m[:2]), i, k)
                       for i, hd in enumerate(live) for k, m in enumerate(found[n]))
        took_h, took_m = set(), set()
        for d, i, k in pairs:
            if i in took_h or k in took_m:
                continue
            last = live[i][max(live[i])]
            if d > LINK_REACH * max(last[2], found[n][k][2]):
                continue
            live[i][n] = found[n][k]
            took_h.add(i)
            took_m.add(k)
        heads += [{n: m} for k, m in enumerate(found[n]) if k not in took_m]
    return heads


def head_plan(frames, meas, full):
    """{frame: (x, y, width, roll, yaw, tilt)} for one head from its sightings. full: the whole
    cut, the head's path carried out to the cut's ends (a chin at the frame edge, say)."""
    seen = [n for n in frames if meas.get(n)]
    on = frames if full else sorted({m for n in seen for m in range(n - HOLD, n + HOLD + 1)} & set(frames))
    cap = None if full else EXTRAPOLATE
    pos = fill({n: meas[n][:2] if meas.get(n) else None for n in frames}, on, cap)
    wid = fill({n: meas[n][2] if meas.get(n) and meas[n][2] else None for n in frames}, on, cap)
    rol = fill({n: meas[n][3] if meas.get(n) else None for n in frames}, on, cap)
    trn = fill({n: meas[n][4:6] if meas.get(n) else None for n in frames}, on, cap)
    pos, wid, rol = smooth(pos, on, 1.5), smooth(wid, on, 2.5), smooth(rol, on, 2.0)
    trn = smooth(trn, on, 2.5)
    return {n: (*pos[n], float(wid[n]), float(rol[n]), *map(float, trn[n])) for n in on}


def skull_plan(jdir, job, clip, pose, w, h, fps):
    """{frame: [(x, y, width, roll, yaw, tilt), ...]}: a skull on every face in the frame."""
    plan = {}
    for a, b, i in frame_spans(job, clip, fps, margin=0):
        cut = job["cuts"][i]
        mode = cut.get("skull")
        if mode is False:                             # manual override: no skull on this cut
            continue
        frames = list(range(a, b + 1))
        found = {}
        for n in frames:
            m = matte(jdir, clip, n)
            found[n] = distinct([hm for p in people(pose.get(n)) if (hm := head_measure(p, m, w, h))])
        heads = sorted(link(frames, found), key=len, reverse=True)     # most seen first: the wearer
        # manual placements where the pose misses a face only partly in frame, on the most seen
        # head: [source seconds, head x, eye-line y, head width], fractions of the frame
        keys = {round(t * fps): (kx * w, ky * h, kw * w, 0.0, 0.0, 0.0)
                for t, kx, ky, kw in cut.get("skull_keys", []) if a <= round(t * fps) <= b}
        if keys:
            heads = [{**(heads[0] if heads else {}), **keys}] + heads[1:]
        for k, meas in enumerate(heads):
            for n, place in head_plan(frames, meas, full=mode == "full" and k == 0).items():
                plan.setdefault(n, []).append(place)
        if heads:
            print(f"[skull] cut {i + 1}: skull on {sum(n in plan for n in frames)}/{len(frames)} frames, "
                  f"{len(heads)} face{'s' if len(heads) > 1 else ''} "
                  f"(seen in {sum(bool(found[n]) for n in frames)})")
    return plan


def load_skull(jdir, cfg):
    img = cv2.imread(str(resolve(jdir, cfg["image"])), cv2.IMREAD_UNCHANGED)
    if img is None or img.shape[2] != 4:
        common.die(f"[skull] {cfg['image']} must be a PNG with transparency")
    return img


# ---------- waist slim ----------

U = np.linspace(-2.5, 2.5, 21)     # band rows, in sigmas around the waist line
WAIST_LINE = 0.97                  # love handles: just above the hips, as a share of shoulder-to-hip
WAIST_UP, WAIST_DOWN = 0.22, 0.10  # band falloff above and below that line, same units


def torso_edges(m, x0, ys, max_half):
    """Left/right torso edge (matte pixels) on each row, skipping rows where an arm touches."""
    left, right = [], []
    for y in ys:
        yy = int(round(y))
        if not 0 <= yy < m.shape[0] or not 0 <= x0 < m.shape[1]:
            left.append(None), right.append(None)
            continue
        row = m[yy] > 127
        if not row[x0]:
            left.append(None), right.append(None)
            continue
        lx = x0 - np.argmin(row[x0::-1]) if not row[:x0 + 1].all() else None
        rx = x0 + np.argmin(row[x0:]) if not row[x0:].all() else None
        left.append(lx if lx is not None and x0 - lx <= max_half else None)
        right.append(rx if rx is not None and rx - x0 <= max_half else None)
    return left, right


def slim_measure(j, m):
    """Waist line, sigma, centre and edge offsets (all in matte pixels) for one frame."""
    hips = [joint(j, k) for k in HIPS]
    sh = [joint(j, k) for k in SHOULDERS]
    if m is None or not all(hips) or not all(sh):
        return None
    mh, mw = m.shape
    hip_y = (hips[0][1] + hips[1][1]) / 2 * mh
    sh_y = (sh[0][1] + sh[1][1]) / 2 * mh
    torso = hip_y - sh_y
    if torso <= 0:
        return None
    x0 = int((hips[0][0] + hips[1][0]) / 2 * mw)
    yc, sig = sh_y + WAIST_LINE * torso, WAIST_UP * torso
    max_half = 0.62 * abs(sh[0][0] - sh[1][0]) * mw
    left, right = torso_edges(m, x0, yc + U * sig, max_half)

    def fill_rows(vals):
        ok = [k for k, v in enumerate(vals) if v is not None]
        if len(ok) < 4:
            return None
        return np.interp(range(len(vals)), ok, [vals[k] for k in ok])
    lft, rgt = fill_rows(left), fill_rows(right)
    if lft is None or rgt is None:
        return None
    return np.concatenate([[yc, sig, x0], lft - x0, rgt - x0])


def slim_plan(jdir, job, pose, fps):
    """{frame: (cfg, params in matte pixels)} for frames inside a slim cut."""
    plan = {}
    for cfg in job.get("slim", []):
        frames = list(range(round(cfg["a"] * fps), round(cfg["b"] * fps) + 1))
        meas = {n: slim_measure(pose.get(n, {}), matte(jdir, cfg["clip"], n)) for n in frames}
        good = [n for n in frames if meas[n] is not None]
        if not good:
            common.die(f"[skull] slim {cfg['clip']} {cfg['a']}-{cfg['b']}: no torso found")
        series = smooth(fill(meas, frames), frames, 2.5)
        for n in frames:
            plan[n] = (cfg, series[n])
        print(f"[skull] slim {cfg['a']}-{cfg['b']}s: torso found in {len(good)}/{len(frames)} frames")
    return plan


def apply_slim(frame, cfg, params, track_scale):
    """Pull the torso edges in around the waist with a smooth horizontal displacement."""
    yc, sig, x0 = params[:3] * track_scale
    lft = params[3:3 + len(U)] * track_scale + x0
    rgt = params[3 + len(U):] * track_scale + x0
    fh, fw = frame.shape[:2]
    down = sig * WAIST_DOWN / WAIST_UP          # tighter below the line: spare the shorts
    y_lo, y_hi = max(0, int(yc - 2.5 * sig)), min(fh, int(yc + 2.5 * down) + 1)
    if y_hi <= y_lo:
        return frame
    ys = np.arange(y_lo, y_hi, dtype=np.float32)
    u = (ys - yc) / sig
    k = np.where(ys < yc, u, (ys - yc) / down)
    base = math.exp(-0.5 * 2.5 ** 2)
    wy = np.clip((np.exp(-0.5 * k ** 2) - base) / (1 - base), 0, 1)
    xl = np.interp(u, U, lft)[:, None]
    xr = np.interp(u, U, rgt)[:, None]
    half = np.maximum((xr - xl) / 2, 1)
    d = cfg.get("amount", 0.12) * half * wy[:, None]
    s_in, s_out = 0.45 * half, np.maximum(2.0 * d, 3)
    xs = np.arange(fw, dtype=np.float32)[None, :]
    dl = d * np.where(xs >= xl, np.exp(-((xs - xl) / s_in) ** 2), np.exp(-((xl - xs) / s_out) ** 2))
    dr = d * np.where(xs <= xr, np.exp(-((xr - xs) / s_in) ** 2), np.exp(-((xs - xr) / s_out) ** 2))
    map_x = (xs - dl + dr).astype(np.float32)
    map_y = np.repeat(ys[:, None], fw, 1).astype(np.float32) - y_lo
    band = cv2.remap(frame[y_lo:y_hi], map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    out = frame.copy()
    out[y_lo:y_hi] = band
    return out


# ---------- commands ----------

def plans(jdir, job, clip):
    """Everything process() needs for one clip."""
    src = source_of(job, clip)
    w, h, fps, _, _ = probe(src)
    pose = track_clip(jdir, job, clip)
    cfg = job.get("skull", {})
    ctx = {"src": src, "size": (w, h, fps), "cfg": cfg, "tex": None, "plan": {}, "slim": {},
           "track_scale": w / TRACK_W, "jdir": jdir, "clip": clip}
    if clip in cfg.get("clips", []):
        ctx["tex"] = skull_draw.texture(load_skull(jdir, cfg))
        ctx["plan"] = skull_plan(jdir, job, clip, pose, w, h, fps)
    if any(s["clip"] == clip for s in job.get("slim", [])):
        ctx["slim"] = slim_plan(jdir, job, {n: (people(v) or [{}])[0] for n, v in pose.items()}, fps)
    return ctx


def person(ctx, n, w, h):
    """The person matte for frame n at frame size, 0..1, or None if it was not tracked."""
    m = matte(ctx["jdir"], ctx["clip"], n)
    return None if m is None else cv2.resize(m, (w, h), interpolation=cv2.INTER_LINEAR).astype(np.float32) / 255


def process(frame, n, ctx):
    if n in ctx["slim"]:
        frame = apply_slim(frame, *ctx["slim"][n], ctx["track_scale"])
    if n in ctx["plan"]:
        cfg = ctx["cfg"]
        blur = cfg.get("blur", True)
        under = person(ctx, n, frame.shape[1], frame.shape[0]) if blur else None
        for place in ctx["plan"][n]:
            frame = skull_draw.draw(frame, ctx["tex"], cfg.get("anchor", [0.5, 0.40]), cfg.get("width", 1.45),
                                    place, under, turned=cfg.get("turn", True), blur=blur)
    return frame


def grab(src, n, w, h, fps):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{n / fps:.4f}", "-i", str(src), "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw[:w * h * 3], np.uint8).reshape(h, w, 3)


def cmd_track(args):
    jdir, job = load_job(args.job, args.variant)
    for clip in needed_clips(job):
        track_clip(jdir, job, clip)


def cmd_check(args):
    jdir, job = load_job(args.job, args.variant)
    rows = []
    tw, th = 270, 480
    for clip in needed_clips(job):
        ctx = plans(jdir, job, clip)
        src, (w, h, fps), slim = ctx["src"], ctx["size"], ctx["slim"]
        for a, b, i in frame_spans(job, clip, fps, margin=0):
            # every cut of a skull clip, so a missed face shows up here
            if ctx["tex"] is None and not any(n in slim for n in range(a, b + 1)):
                continue
            pick = [round(a + k * (b - a) / 7) for k in range(8)]
            tiles = []
            for n in pick:
                img = grab(src, n, w, h, fps)
                done = process(img, n, ctx)
                tiles.append(cv2.resize(done, (tw, th), interpolation=cv2.INTER_AREA))
                if n in slim:
                    tiles[-1] = np.hstack([cv2.resize(img, (tw, th), interpolation=cv2.INTER_AREA), tiles[-1]])
            row = np.hstack(tiles)
            cv2.putText(row, f"cut {i + 1}", (8, 34), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 0), 6)
            cv2.putText(row, f"cut {i + 1}", (8, 34), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 255), 2)
            rows.append(row)
    width = max(r.shape[1] for r in rows)
    sheet = np.vstack([np.pad(r, ((0, 0), (0, width - r.shape[1]), (0, 0))) for r in rows])
    out = jdir / "work" / "skull_check.jpg"
    cv2.imwrite(str(out), sheet, [cv2.IMWRITE_JPEG_QUALITY, 88])
    print(f"[skull] check {out}")


def cmd_apply(args):
    jdir, job = load_job(args.job, args.variant)
    path = jdir / (f"job.{args.variant}.json" if args.variant else "job.json")
    for clip in needed_clips(job):
        ctx = plans(jdir, job, clip)
        src, (w, h, fps) = ctx["src"], ctx["size"]
        _, _, _, rate, total = probe(src)
        out = jdir / "work" / f"{clip}_skull.mp4"
        dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(src), "-f", "rawvideo",
                                "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE)
        enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
                                "-s", f"{w}x{h}", "-r", rate, "-i", "-", "-c:v", "libx264", "-crf", "11",
                                "-preset", "fast", "-pix_fmt", "yuv420p", "-color_primaries", "bt709",
                                "-color_trc", "bt709", "-colorspace", "bt709", str(out)], stdin=subprocess.PIPE)
        size, n = w * h * 3, 0
        while True:
            raw = dec.stdout.read(size)
            if len(raw) < size:
                break
            frame = np.frombuffer(raw, np.uint8).reshape(h, w, 3)
            enc.stdin.write(process(frame, n, ctx).tobytes())
            n += 1
        enc.stdin.close()
        if dec.wait() != 0 or enc.wait() != 0:
            common.die(f"[skull] {clip}: encode failed")
        if n != total:
            common.die(f"[skull] {clip}: wrote {n} frames, source has {total}")
        job = json.loads(path.read_text())
        job.setdefault("sources", {}).setdefault(clip, job["clips"][clip])
        job["clips"][clip] = str(out)
        path.write_text(json.dumps(job, indent=2) + "\n")
        print(f"[skull] {clip}: {out} ({n} frames, skull on {len(ctx['plan'])}, slim on {len(ctx['slim'])})")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("track", "check", "apply"):
        sp = sub.add_parser(name)
        sp.add_argument("job")
        sp.add_argument("--variant", help="use job.<variant>.json (an alternate cut of the same footage)")
    args = p.parse_args()
    {"track": cmd_track, "check": cmd_check, "apply": cmd_apply}[args.cmd](args)


if __name__ == "__main__":
    main()
