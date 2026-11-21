"""Storyboard reel: every frame. Assets are prepared once per run, then each shot kind
draws a float RGB frame at time t into a shot of length d.

Ported from the Shop Wizard build (jobs/20261017-222408-wizard/wizard_ad.py); the
numbers that were tuned by eye there are the defaults in sr_lib.SHOT_DEFAULTS and LOOK."""
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import sr_lib
import sr_matte

W, H, FPS = 1080, 1920, 30
ROOT = Path(__file__).resolve().parent.parent
FONTS = {"title": ROOT / "assets" / "fonts" / "Anton-Regular.ttf",
         "body": ROOT / "assets" / "fonts" / "DejaVuSans-Bold.ttf"}


ease, ramp = sr_lib.ease, sr_lib.ramp


def cut_path(jdir, fig):
    """The cutout a figure renders from: the feet-repaired one when the job asks for it."""
    stem = Path(fig["src"]).stem
    path = Path(jdir) / "work" / "cut" / (f"{stem}_fixed.png" if fig.get("feet") else f"{stem}.png")
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing, run: storyboard_reel.py cutouts <job>")
    return path


# ---------- drawing helpers ----------

def over(base, rgba, x, y, opacity=1.0):
    """Alpha-composite rgba onto base (in place) with its top-left at (x, y)."""
    h, w = rgba.shape[:2]
    x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, W), min(y + h, H)
    if x1 <= x0 or y1 <= y0:
        return
    src = rgba[y0 - y:y1 - y, x0 - x:x1 - x]
    a = src[..., 3:4] * opacity
    base[y0:y1, x0:x1] = base[y0:y1, x0:x1] * (1 - a) + src[..., :3] * a


def opaque(rgb):
    return np.dstack([rgb, np.ones(rgb.shape[:2], np.float32)])


def cover(rgb, w, h):
    sh, sw = rgb.shape[:2]
    s = max(w / sw, h / sh)
    big = cv2.resize(rgb, (int(np.ceil(sw * s)), int(np.ceil(sh * s))), interpolation=cv2.INTER_AREA)
    y, x = (big.shape[0] - h) // 2, (big.shape[1] - w) // 2
    return big[y:y + h, x:x + w]


def text_layer(lines, product, colors):
    """Shot `lines` [{text, font, size, color, y}] -> full-frame RGBA float layer."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for line in lines:
        font = ImageFont.truetype(str(FONTS.get(line["font"], line["font"])), line["size"])
        text = sr_lib.fill_text(line["text"], product)
        rgb = tuple(colors[line["color"]] if isinstance(line["color"], str) else line["color"])
        x0, y0, x1, y1 = d.textbbox((0, 0), text, font=font)
        d.text(((W - (x1 - x0)) / 2 - x0, line["y"] - (y1 - y0) / 2 - y0), text, font=font, fill=rgb + (255,))
    return np.asarray(im).astype(np.float32) / 255.0


def zoom_plate(plate, z, ax, ay):
    m = np.float32([[z, 0, ax * (1 - z)], [0, z, ay * (1 - z)]])
    return cv2.warpAffine(plate, m, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def contact_shadow(frame, fx, fy, hpx, rgb):
    shadow = np.zeros((H, W), np.float32)
    cv2.ellipse(shadow, (int(fx), int(fy)), (int(hpx * 0.2), int(hpx * 0.026)), 0, 0, 360, 1.0, -1)
    shadow = cv2.GaussianBlur(shadow, (0, 0), hpx * 0.012)[..., None] * 0.62
    return frame * (1 - shadow) + np.asarray(rgb, np.float32) * shadow


def stage(a, fig, p, z):
    """Plate + contact shadow + a cropped figure (dolly), camera pushed in by z about the
    horizon. height/feet/cx are frame fractions at z=1."""
    ax, ay = W / 2, H * a.look["horizon"]
    frame = zoom_plate(a.plate, 1 + (z - 1) * p["parallax"], ax, ay)
    hpx = H * p["height"] * z
    fx, fy = ax + (W * p["cx"] - ax) * z, ay + (H * p["feet"] - ay) * z
    img = fig["img"]
    s = hpx / img.shape[0]
    img = cv2.resize(img, (max(1, int(img.shape[1] * s)), max(1, int(hpx))), interpolation=cv2.INTER_AREA)
    frame = contact_shadow(frame, fx, fy - hpx * 0.004, hpx, a.look["shadow_rgb"])
    over(frame, img, int(round(fx - fig["cx"] * img.shape[1])), int(round(fy - img.shape[0])))
    return frame


def pose_stage(a, pose, z=1.0, anchor=None, parallax=0.35):
    """A pose figure on the plate at the shared body height, pushed in by z about anchor
    (pixels). Returns (frame, figure box)."""
    body_h, feet_y = a.look["body_h"], a.look["feet_y"]
    ax, ay = anchor if anchor else (W / 2, H * a.look["horizon"])
    s = body_h / pose["body"] * z
    w, h = int(pose["src_w"] * s), int(pose["src_h"] * s)
    left = ax + (W / 2 - pose["cx"] * body_h / pose["body"] - ax) * z
    top = ay + (H * feet_y - pose["feet"] * body_h / pose["body"] - ay) * z
    fx, fy = ax + (W / 2 - ax) * z, ay + (H * feet_y - ay) * z
    frame = zoom_plate(a.plate, 1 + (z - 1) * parallax, ax, ay)
    frame = contact_shadow(frame, fx, fy, body_h * z, a.look["shadow_rgb"])
    img = cv2.resize(pose["img"], (w, h), interpolation=cv2.INTER_AREA)
    over(frame, img, int(round(left)), int(round(top)))
    return frame, (left, top, w, h)


class ClipReader:
    """Sequential frame access to a prepared 30 fps clip; seeks only when asked to jump.
    Frames come at the reel's size, or the clip's own with `native`."""
    def __init__(self, path, native=False):
        self.cap = cv2.VideoCapture(str(path))
        self.count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.size = (int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))) if native else (W, H)
        self.pos, self.last = -1, None

    def frame(self, i):
        i = min(max(i, 0), self.count - 1)
        if i == self.pos and self.last is not None:
            return self.last
        if i != self.pos + 1:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, bgr = self.cap.read()
        if not ok:
            return self.last
        self.pos = i
        self.last = cv2.cvtColor(cv2.resize(bgr, self.size, interpolation=cv2.INTER_AREA),
                                 cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        return self.last


def glow_light(frame, cx, cy, r, g, rgb):
    """Additive light: white core, coloured halo, wide spill."""
    yy, xx = np.ogrid[:H, :W]
    d2 = ((xx - cx) ** 2 + (yy - cy) ** 2).astype(np.float32)
    core = np.exp(-d2 / (r * 0.9) ** 2)[..., None]
    halo = np.exp(-d2 / (r * 3.2) ** 2)[..., None]
    wide = np.exp(-d2 / (r * 11) ** 2)[..., None]
    light = core * 1.4 + halo * rgb * 0.9 + wide * rgb * 0.35
    return frame + light * g


# ---------- assets ----------

class Assets:
    """Everything the shots draw from, prepared once. resolve(path) finds a job.json path.
    vhs is a tape pass (sr_vhs.VHSPass) or None for a clean picture."""
    def __init__(self, jdir, job, rows, resolve, vhs=None):
        self.jdir, self.job, self.rows, self.resolve = Path(jdir), job, rows, resolve
        self.vhs, self.vhs_cfg = vhs, sr_lib.vhs_config(job, rows)
        self.handheld_cfg = sr_lib.handheld_config(job, rows)
        self.stamp_cfg = sr_lib.stamp_config(job, rows)
        self.stamp = load_stamp(resolve(self.stamp_cfg["src"]), self.stamp_cfg) if self.stamp_cfg else None
        self.look = sr_lib.look(job)
        self.product = job["product"]
        self.plate = None
        if sr_lib.needs_plate([shot for shot, _, _ in rows]):
            self.plate = cover(sr_matte.load_rgba(resolve(job["plate"]["src"]))[..., :3], W, H)
        self._figs, self._clips, self._stills, self.prep = {}, {}, {}, {}
        for i, (shot, _, _) in enumerate(rows):
            prev = rows[i - 1][0] if i else None
            nxt = rows[i + 1][0] if i + 1 < len(rows) else None
            self.prep[shot["id"]] = PREP.get(shot["kind"], lambda *_: None)(self, sr_lib.params(shot), prev, nxt)

    def figure(self, name, mode):
        key = (name, mode)
        if key not in self._figs:
            fig = self.job["figures"][name]
            rgba = sr_matte.load_rgba(cut_path(self.jdir, fig))
            tint = self.look["tint"]
            self._figs[key] = (sr_matte.dolly_figure(rgba, tint) if mode == "dolly"
                               else sr_matte.pose_figure(rgba, tint, fig.get("centre_on", "red")))
        return self._figs[key]

    def still(self, path):
        """A full-frame key frame, cover-fitted to 9:16 once."""
        if path not in self._stills:
            rgb = np.asarray(Image.open(self.resolve(path)).convert("RGB")).astype(np.float32) / 255.0
            self._stills[path] = cover(rgb, W, H)
        return self._stills[path]

    def clip(self, shot):
        """The shot's prepared clip, or None before Kling has delivered it."""
        path = self.resolve(shot["clip"])
        if not path.exists():
            return None
        if path not in self._clips:
            self._clips[path] = ClipReader(path)
        return self._clips[path]


def _prep_shirt(a, p, prev, nxt):
    photo = np.asarray(Image.open(a.resolve(p["src"])).convert("RGB")).astype(np.float32) / 255.0
    return {"photo": photo, "blank": sr_matte.blank_shirt(photo, p["blank_box"]),
            "paper": photo[:20, :20].reshape(-1, 3).mean(axis=0),
            "text": text_layer(p["lines"], a.product, a.look["colors"])}


def _prep_card(a, p, prev, nxt):
    mock = np.asarray(Image.open(a.resolve(p["mockup"])).convert("RGB")).astype(np.float32) / 255.0
    w = p["tee"]
    mock = cv2.resize(mock, (w, int(round(w * mock.shape[0] / mock.shape[1]))), interpolation=cv2.INTER_AREA)
    return {"mock": mock, "text": text_layer(p["lines"], a.product, a.look["colors"])}


def _prep_glow(a, p, prev, nxt):
    fig = a.figure(p["figure"], "pose")
    return {"fig": fig, "light": sr_matte.find_light(fig, p["light"]),
            "after": a.clip(prev) if prev and prev["kind"] == "clip" else None}


def _hold(a, nxt):
    """A pose or still right before a clip holds the clip's first frame (its `in` point)."""
    if not (nxt and nxt["kind"] == "clip"):
        return {"hold": None, "hold_at": 0}
    return {"hold": a.clip(nxt), "hold_at": int(round(sr_lib.params(nxt)["in"] * FPS))}


def _shot_length(a, sid):
    return next(end - start for shot, start, end in a.rows if shot["id"] == sid)


def _prep_clip(a, p, prev, nxt):
    scope = None if p["scope"] is None else sr_lib.scope_cfg(p["scope"])
    if scope and prev and prev["kind"] == "scan":     # the same hand, carrying on across the cut
        scope = {**scope, "phase": _shot_length(a, prev["id"])}
    base = {"reader": a.clip(p), "scope": scope, "glass": scope_glass(scope) if scope else None}
    if sr_lib.is_still_clip(p):
        start = a.still(p["start"])
        return {**base, "from_still": start, "to_still": a.still(p["end"]) if p.get("end") else start}
    return {**base, "from": a.figure(p["from"], "pose"), "to": a.figure(p["to"], "pose")}


def _prep_live(a, p, wide, scale):
    """The clip playing inside the wide still: its frames, where it sits in pixels of the scaled
    still, and its soft edge. None until the clip exists."""
    if p["live"] is None or not a.resolve(p["live"]["clip"]).exists():
        return None
    live = {**sr_lib.LIVE, **p["live"]}
    reader = ClipReader(a.resolve(live["clip"]), native=True)
    x, y, width = live["box"]
    cw, ch = reader.size
    edge = max(cw * live["feather"], 1.0)
    across = np.clip(np.minimum(np.arange(cw), cw - 1 - np.arange(cw)) / edge, 0, 1)
    down = np.clip(np.minimum(np.arange(ch), ch - 1 - np.arange(ch)) / edge, 0, 1)
    return {"reader": reader, "at": live["at"], "fade": live["fade"], "mask": np.outer(down, across).astype(np.float32),
            "left": x * wide.shape[1] * scale, "top": y * wide.shape[0] * scale, "zoom": width * wide.shape[1] * scale / cw}


def _prep_scan(a, p, prev, nxt):
    """One wide still and the path the hand takes across it, in pixels of the scaled still."""
    wide = np.asarray(Image.open(a.resolve(p["src"])).convert("RGB")).astype(np.float32) / 255.0
    scale = W / (p["span"] * wide.shape[1])
    aim = [(x * wide.shape[1] * scale, y * wide.shape[0] * scale)
           for x, y in sr_lib.hand_path(p["path"], _shot_length(a, p["id"]), FPS)]
    scope = sr_lib.scope_cfg(p["scope"])
    return {"wide": wide, "scale": scale, "aim": aim, "lag": sr_lib.aim_lag(aim, FPS), "live": _prep_live(a, p, wide, scale),
            "scope": scope, "glass": scope_glass(scope), **_hold(a, nxt)}


PREP = {
    "logo": lambda a, p, prev, nxt: sr_matte.white_keyed(a.resolve(p["src"])),
    "dolly": lambda a, p, prev, nxt: a.figure(p["figure"], "dolly"),
    "pose": lambda a, p, prev, nxt: {"fig": a.figure(p["figure"], "pose"), **_hold(a, nxt)},
    "clip": _prep_clip,
    "still": lambda a, p, prev, nxt: {"img": a.still(p["src"]), **_hold(a, nxt)},
    "scan": _prep_scan,
    "glow": _prep_glow, "shirt": _prep_shirt, "card": _prep_card,
}


# ---------- shots ----------

def shot_logo(a, p, t, d):
    logo = a.prep[p["id"]]
    frame = np.zeros((H, W, 3), np.float32)
    s = (W * p["width"] / logo.shape[1]) * (1 + p["grow"] * t / d)
    img = cv2.resize(logo, (int(logo.shape[1] * s), int(logo.shape[0] * s)), interpolation=cv2.INTER_AREA)
    op = ramp(t, 0.0, p["fade_in"]) * (1 - ramp(t, d - p["fade_out"], d))
    over(frame, img, (W - img.shape[1]) // 2, int(H * p["y"] - img.shape[0] / 2), op)
    return frame


def shot_dolly(a, p, t, d):
    frame = stage(a, a.prep[p["id"]], p, 1 + p["push"] * ease(t / d))
    return frame * ramp(t, 0.0, p["fade_in"])


def shot_pose(a, p, t, d):
    """Before a clip this holds the clip's own first frame: Kling re-renders the start frame
    a touch brighter, so holding our composite would pop at the cut."""
    prep = a.prep[p["id"]]
    if prep["hold"]:
        return prep["hold"].frame(prep["hold_at"])
    return pose_stage(a, prep["fig"])[0]


def scope_glass(cfg):
    """The lens as a multiplier on the picture: 1 inside the ring, a soft dark rim, black
    outside, with the crosshair (thin lines, heavy outer posts, a centre dot) inked on it."""
    cx, cy, r = W // 2, int(H * cfg["y"]), int(W * cfg["radius"])
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    lens = np.clip((r - np.hypot(xx - cx, yy - cy)) / (r * cfg["rim"]), 0, 1)
    ink = np.full((H, W), 255, np.uint8)
    gap, post = int(r * 0.03), int(r * 0.55)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        cv2.line(ink, (cx + dx * gap, cy + dy * gap), (cx + dx * r, cy + dy * r), 0, 3)
        cv2.line(ink, (cx + dx * post, cy + dy * post), (cx + dx * r, cy + dy * r), 0, 9)
    cv2.circle(ink, (cx, cy), 5, 0, -1)
    return (lens * ink.astype(np.float32) / 255.0)[..., None]


def _beats(t, waves):
    return float(sum(weight * np.sin(2 * np.pi * hz * t + phase) for hz, weight, phase in waves))


# Hz, weight (summing to 1), phase: a breath, a slow correction, then the tremor of a held rifle
_SWAY_X = ((0.31, 0.60, 0.6), (0.83, 0.24, 2.1), (2.3, 0.11, 0.9), (5.1, 0.05, 4.0))
_SWAY_Y = ((0.19, 0.60, 1.9), (0.67, 0.24, 0.3), (1.9, 0.11, 2.6), (4.3, 0.05, 1.2))
_FLOAT_X = ((0.17, 0.7, 2.2), (0.43, 0.3, 0.0))
_FLOAT_Y = ((0.23, 0.7, 4.0), (0.37, 0.3, 1.1))
RING_LAG = (0.1, 46.0)      # share of the aim's lag the ring slides by, and its limit in pixels
EYE_SHADOW = (0.3, 1.18, 0.16)  # share of the lag, and the eye's disc radius and edge (of the ring radius)


def scope_sway(cfg, t):
    """The picture behind the glass in pixels: breathing and tremor, calming to `held` at
    `steady`. A real scope never stops dead."""
    amp = cfg["sway"]
    if cfg["steady"] is not None:
        amp *= 1 - (1 - cfg["held"]) * ramp(t, cfg["steady"], cfg["steady"] + 0.5)
    if not amp:
        return 0.0, 0.0
    t += cfg["phase"]
    return amp * _beats(t, _SWAY_X), 0.7 * amp * _beats(t, _SWAY_Y)


def scope_float(cfg, t):
    """The ring itself in pixels: the eye behind a scope is never dead centre."""
    amp = cfg["sway"] * cfg["float"]
    if not amp:
        return 0.0, 0.0
    t += cfg["phase"]
    return amp * _beats(t, _FLOAT_X), amp * _beats(t, _FLOAT_Y)


def _shifted(img, dx, dy):
    return cv2.warpAffine(img, np.float32([[1, 0, dx], [0, 1, dy]]), (W, H))


def eye_shadow(cfg, dx, dy):
    """The dark crescent when the eye falls off axis: a soft disc around the eye, offset from the ring."""
    cx, cy, r = W / 2 + dx, H * cfg["y"] + dy, W * cfg["radius"]
    yy, xx = np.ogrid[0:H, 0:W]
    reach, edge = r * EYE_SHADOW[1], r * EYE_SHADOW[2]
    return np.clip((reach - np.hypot(xx - cx, yy - cy)) / edge, 0, 1).astype(np.float32)[..., None]


def through_scope(frame, prep, t, lag=(0.0, 0.0)):
    """Picture, ring and shadow all move on their own, as behind a real scope: the hand sways
    the picture, the ring floats, and on a fast move the eye falls behind, so the ring slides
    back and a dark crescent follows the move."""
    cfg = prep["scope"]
    dx, dy = scope_sway(cfg, t)
    if dx or dy:
        frame = _shifted(frame, dx, dy)
    fx, fy = scope_float(cfg, t)
    share, limit = RING_LAG
    fx, fy = fx - np.clip(lag[0] * share, -limit, limit), fy - np.clip(lag[1] * share, -limit, limit)
    glass = _shifted(prep["glass"], fx, fy)[..., None] if fx or fy else prep["glass"]
    if lag[0] or lag[1]:
        glass = glass * eye_shadow(cfg, fx - lag[0] * EYE_SHADOW[0], fy - lag[1] * EYE_SHADOW[0])
    return frame * glass


def _lens_at(prep, x, y, patch, opacity):
    """What the lens sees aimed at x, y: the wide still, with the live clip laid into it."""
    s = prep["scale"]
    view = cv2.warpAffine(prep["wide"], np.float32([[s, 0, W / 2 - x], [0, s, H / 2 - y]]), (W, H))
    if not opacity:
        return view
    live = prep["live"]
    place = np.float32([[live["zoom"], 0, live["left"] + W / 2 - x], [0, live["zoom"], live["top"] + H / 2 - y]])
    mask = cv2.warpAffine(live["mask"], place, (W, H))[..., None] * opacity
    return view * (1 - mask) + cv2.warpAffine(patch, place, (W, H)) * mask


def scan_view(prep, i, patch=None, opacity=0.0):
    """The lens on the wide still, smeared along a fast move like a long lens swung by hand."""
    ax, ay = prep["aim"][i]
    px, py = prep["aim"][max(i - 1, 0)]
    stops = (0.0, 0.33, 0.66) if abs(ax - px) + abs(ay - py) > 8 else (0.0,)
    views = [_lens_at(prep, ax + (px - ax) * k, ay + (py - ay) * k, patch, opacity) for k in stops]
    return sum(views) / len(views)


def shot_scan(a, p, t, d):
    """A lens searching one wide still on a hand-steered path, easing at the end into the next
    clip's first frame so the search runs straight into it. With `live` that clip is already
    playing inside the still, so the lens finds him moving and never lands on a statue."""
    prep = a.prep[p["id"]]
    i = min(int(round(t * FPS)), len(prep["aim"]) - 1)
    live = prep["live"]
    opacity = ramp(t, live["at"], live["at"] + live["fade"]) if live else 0.0
    frame = scan_view(prep, i, live["reader"].frame(int(round((t - live["at"]) * FPS))) if opacity else None, opacity)
    if prep["hold"]:
        k = ramp(t, d - p["settle"], d)
        at = prep["hold_at"] - int(round((d - t) * FPS)) if live else prep["hold_at"]
        frame = frame * (1 - k) + prep["hold"].frame(at) * k
    return through_scope(frame, prep, t, prep["lag"][i])


def clip_picture(a, prep, p, t, d):
    """The Kling clip. Before it exists, a cross-dissolve between the two poses stands in."""
    if prep["reader"]:
        return prep["reader"].frame(int(round((t + p["in"]) * FPS)))
    k = ramp(t, 0.5, d - 0.5)
    if "from_still" in prep:
        return prep["from_still"] * (1 - k) + prep["to_still"] * k
    return pose_stage(a, prep["from"])[0] * (1 - k) + pose_stage(a, prep["to"])[0] * k


def shot_clip(a, p, t, d):
    """A clip with its edit-side knobs: light level, the scope, `fade_in` from black and
    `flash` seconds of white decaying off a flash cut."""
    prep = a.prep[p["id"]]
    frame = clip_picture(a, prep, p, t, d) * sr_lib.light_level(p, t)
    if prep["scope"]:
        frame = through_scope(frame, prep, t)
    frame = frame * ramp(t, 0.0, p["fade_in"])
    flash = 1 - ramp(t, 0.0, p["flash"]) if p["flash"] else 0.0
    return frame * (1 - flash) + flash


def shot_still(a, p, t, d):
    """A full-frame key frame: slow push about `anchor`, fade in from black, fade out, and
    `flash` seconds of white decaying off a flash cut. Before a clip it holds the clip's
    own first frame, like a pose."""
    prep = a.prep[p["id"]]
    if prep["hold"]:
        return prep["hold"].frame(prep["hold_at"])
    frame = prep["img"]
    if p["push"]:
        frame = zoom_plate(frame, 1 + p["push"] * ease(t / d), W * p["anchor"][0], H * p["anchor"][1])
    frame = frame * ramp(t, 0.0, p["fade_in"]) * (1 - ramp(t, d - p["fade_out"], d))
    flash = 1 - ramp(t, 0.0, p["flash"]) if p["flash"] else 0.0
    return frame * (1 - flash) + flash


def shot_glow(a, p, t, d):
    """The light gathers while the camera pushes toward it, then blows out to white."""
    prep = a.prep[p["id"]]
    ox, oy, orr = prep["light"]
    anchor = (W * p["anchor"][0], H * p["anchor"][1])
    frame, (left, top, w, h) = pose_stage(a, prep["fig"], z=1 + p["push"] * ease(t / d), anchor=anchor)
    if prep["after"]:   # ease off the clip's last frame so any drift does not pop
        k = ramp(t, 0.0, p["settle"])
        frame = prep["after"].frame(prep["after"].count - 1) * (1 - k) + frame * k
    cx, cy, r = left + ox * w, top + oy * h, max(orr * h, 6)
    flicker = 1 + 0.05 * np.sin(t * 2 * np.pi * 3.1) + 0.03 * np.sin(t * 2 * np.pi * 7.7)
    g = ramp(t, 0.0, d - 1.4) * flicker
    bloom = 1 + 6 * ramp(t, d - 1.6, d - 0.2) ** 2
    rgb = np.asarray(p["light"]["rgb"], np.float32)
    frame = glow_light(frame, cx, cy, r * bloom, g * (1 + 2 * ramp(t, d - 1.6, d - 0.2)), rgb)
    white = ramp(t, d - 1.1, d - 0.15)
    return np.clip(frame, 0, 1) * (1 - white) + white


def shot_shirt(a, p, t, d):
    """Blank tee on the photo's own paper colour, design fades in, then the title."""
    prep = a.prep[p["id"]]
    design = ramp(t, *p["design_in"])
    frame = np.ones((H, W, 3), np.float32) * prep["paper"]
    shirt = prep["blank"] * (1 - design) + prep["photo"] * design
    w = int(W * p["width"] * (1 + p["grow"] * t / d))
    h = int(round(w * shirt.shape[0] / shirt.shape[1]))
    img = cv2.resize(shirt, (w, h), interpolation=cv2.INTER_AREA)
    over(frame, opaque(img), (W - w) // 2, int(H * p["y"] - h / 2))
    over(frame, prep["text"], 0, 0, ramp(t, *p["text_in"]))
    white = 1 - ramp(t, 0.0, p["from_white"])
    return (frame * (1 - white) + white) * ramp(t, 0.0, p["from_black"])


def shot_card(a, p, t, d):
    """Product card: slams in on the impact (1.1x to 1x), drifts, fades out with the music."""
    prep = a.prep[p["id"]]
    frame = np.ones((H, W, 3), np.float32) * p["bg"]
    slam = 1 + p["slam"] * (1 - ramp(t, 0.0, p["slam_time"])) + p["drift"] * t / d
    mock = prep["mock"]
    w = int(mock.shape[1] * slam)
    h = int(mock.shape[0] * slam)
    img = cv2.resize(mock, (w, h), interpolation=cv2.INTER_AREA)
    over(frame, opaque(img), (W - w) // 2, int(p["tee_y"] - h / 2))
    over(frame, prep["text"], 0, 0)
    flash = 1 - ramp(t, 0.0, p["flash"])
    return (frame * (1 - flash) + flash) * (1 - ramp(t, d - p["fade_out"], d))


DRAW = {"logo": shot_logo, "black": lambda a, p, t, d: np.zeros((H, W, 3), np.float32),
        "white": lambda a, p, t, d: np.ones((H, W, 3), np.float32), "dolly": shot_dolly,
        "pose": shot_pose, "clip": shot_clip, "glow": shot_glow, "shirt": shot_shirt, "card": shot_card,
        "still": shot_still, "scan": shot_scan}


def handheld_matrix(cfg, t):
    """The 2x3 camera move at t (sr_lib.handheld_offset), overscanned so no edge shows."""
    dx, dy, rot = sr_lib.handheld_offset(cfg, t)
    m = cv2.getRotationMatrix2D((W / 2, H / 2), rot, sr_lib.handheld_zoom(cfg["strength"]))
    return m + np.float64([[0, 0, dx * W], [0, 0, dy * H]])


def handheld(img, cfg, t):
    if sr_lib.handheld_offset(cfg, t) is None:
        return img
    return cv2.warpAffine(img, handheld_matrix(cfg, t), (W, H), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_REFLECT)


def load_stamp(path, cfg):
    """The creator stamp, premultiplied and scaled to cfg height, and the frame position of
    its top-left corner."""
    rgba = sr_matte.load_rgba(path)
    h = int(cfg["height"])
    w = max(1, round(rgba.shape[1] * h / rgba.shape[0]))
    pre = cv2.resize(np.dstack([rgba[..., :3] * rgba[..., 3:], rgba[..., 3:]]), (w, h), interpolation=cv2.INTER_AREA)
    mx, my = (int(v) for v in cfg["margin"])
    x = mx if cfg["corner"].endswith("left") else W - w - mx
    y = my if cfg["corner"].startswith("top") else H - h - my
    return pre[..., :3], pre[..., 3:], x, y


def stamp(img, a, t):
    """The stamp over the picture at t (sr_lib.stamp_alpha). It goes on after the handheld
    move, so it stays put, and before the tape, so it wears the VHS look."""
    k = sr_lib.stamp_alpha(a.stamp_cfg, t) if a.stamp else 0.0
    if k <= 0:
        return img
    rgb, alpha, x, y = a.stamp
    h, w = alpha.shape[:2]
    out = img.copy()
    out[y:y + h, x:x + w] = img[y:y + h, x:x + w] * (1 - k * alpha) + k * rgb
    return out


def frame_at(a, t):
    """uint8 RGB frame at t seconds, and the id of the shot it belongs to. The handheld
    camera moves the picture first (the tape does not move with it), then the creator
    stamp goes on, then the VHS pass, when on, is mixed in by sr_lib.vhs_mix (full on the
    character section, fading out across the white)."""
    shot, start, end = sr_lib.shot_at(a.rows, t)
    img = np.clip(DRAW[shot["kind"]](a, sr_lib.params(shot), t - start, end - start), 0, 1)
    img = stamp(handheld(img, a.handheld_cfg, t), a, t)
    m = sr_lib.vhs_mix(a.vhs_cfg, t) if a.vhs else 0.0
    if m > 0:
        img = np.clip(a.vhs(img, t), 0, 1) * m + img * (1 - m)
    return (np.clip(img, 0, 1) * 255).astype(np.uint8), shot["id"]
