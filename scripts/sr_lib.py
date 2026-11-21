"""Storyboard reel: the pure logic (no ffmpeg, no images), so it can be tested.

A storyboard reel is a fixed-length 9:16 shirt ad drawn from Tony's storyboard. The shot
list is a sequence of kinds:
  logo   brand logo on black          black / white   solid frames between beats
  dolly  camera pushes in on a figure cutout standing on the plate
  pose   a figure cutout held on the plate (before a clip it holds Kling's own first frame)
  clip   the Kling start/end clip that moves the figure from one pose to the next
  glow   the prop's light gathers and blows the frame out to white
  shirt  the blank tee on white, the design fades in, title under it
  card   product card: title, mockup, price/sizes/colours, the site in red
  still  a full-frame generated key frame (close-ups, POV): optional push, fade in, flash cut

A clip moves between two figures on the plate (`from`/`to`) or between two full-frame
stills (`start`/`end`, image paths); a still clip follows the still of its start frame.

Every shot has `dur` in seconds, or "clip" (the prepared clip's own length) or "fill"
(one shot only: it absorbs whatever the others leave of `length`, so the music bed and
the ending stay put when Kling hands back a 3.03 s clip instead of 3.0).
"""
import math
import re
from urllib.parse import urlparse

KINDS = ("logo", "black", "white", "dolly", "pose", "clip", "glow", "shirt", "card", "still", "scan")
FIGURE_KINDS = ("dolly", "pose", "glow")
FEET_OPS = ("rebuild", "add", "drop")       # applied in this order
REQUIRED = ("title", "length", "product", "shots")
CLIP_DEFAULT = 3.0      # seconds a clip shot stands in for before Kling has delivered
MIN_FILL = 0.5
MIN_GLOW = 2.0          # the bloom and white-out use the last 1.6 s of a glow
TOLERANCE = 0.01
SEP = "   ·   "
PREVIEW_PAD = (0.6, 0.8)  # seconds of context either side of the clip in `preview`
OSD_TEXT = "PLAY \u25B6"   # the VHS on-screen readout over the opening

LOOK = {
    "horizon": 0.55,                 # where the plate's floor meets the sky, frame fraction
    "tint": [0.95, 0.92, 1.0],       # cools studio-lit renders toward a violet plate
    "body_h": 1416,                  # hood-to-feet height of pose figures, px
    "feet_y": 0.91,                  # where pose figures stand, frame fraction
    "shadow_rgb": [0.05, 0.0, 0.12],
    "colors": {"red": [178, 18, 30], "cream": [242, 234, 216], "ink": [14, 14, 14]},
}

SHOT_DEFAULTS = {
    "logo": {"width": 0.84, "grow": 0.06, "y": 0.47, "fade_in": 0.3, "fade_out": 0.8},
    "dolly": {"height": 0.50, "cx": 0.5, "feet": 0.80, "push": 0.48, "parallax": 0.35, "fade_in": 0.9},
    "clip": {"clip_default": CLIP_DEFAULT, "in": 0.0, "gain": 1.0, "lights_out": None,
             "fade_in": 0.0, "flash": 0.0, "scope": None},
    "still": {"push": 0.0, "anchor": [0.5, 0.5], "fade_in": 0.0, "fade_out": 0.0, "flash": 0.0},
    "scan": {"span": 0.25, "settle": 0.4, "scope": {}, "live": None},
    "glow": {"push": 0.12, "anchor": [0.5, 0.30], "settle": 0.25,
             "light": {"rgb": [1.0, 0.42, 1.0], "find": "magenta"}},
    "shirt": {"width": 1.06, "y": 0.40, "grow": 0.035, "blank_box": [0.33, 0.25, 0.67, 0.625],
              "design_in": [1.2, 3.0], "text_in": [3.2, 3.9], "from_white": 0.8, "from_black": 0.0,
              "lines": [{"text": "{title}", "font": "title", "size": 84, "color": "ink", "y": 1405},
                        {"text": "AVAILABLE NOW", "font": "body", "size": 44, "color": "red", "y": 1492}]},
    "card": {"tee": 940, "tee_y": 762, "slam": 0.1, "slam_time": 0.18, "drift": 0.03, "flash": 0.12,
             "fade_out": 0.6, "bg": 0.035,
             "lines": [{"text": "{title}", "font": "title", "size": 96, "color": "cream", "y": 215},
                       {"text": "{details}", "font": "body", "size": 44, "color": "cream", "y": 1335},
                       {"text": "{site}", "font": "title", "size": 104, "color": "red", "y": 1450}]},
}

# Contact sheet samples per kind: (fraction of the shot, label). A shot's `label` replaces
# a single default label; its `sheet` replaces the whole list.
SHEET = {
    "logo": [(0.4, "Logo")], "black": [(0.5, "Black")], "white": [(0.43, "White")],
    "dolly": [(0.2, "Dolly in, start"), (0.96, "Dolly in, end")], "pose": [(0.47, "Pose")],
    "clip": [(0.5, "Clip")], "glow": [(0.59, "Glow")],
    "shirt": [(0.14, "Blank shirt"), (0.83, "Design in")], "card": [(0.6, "Card")],
    "still": [(0.6, "Still")], "scan": [(0.5, "Lens searches")],
}


def ease(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def ramp(t, a, b):
    return ease((t - a) / (b - a)) if b > a else float(t >= a)


def params(shot):
    """A shot with its kind's defaults filled in."""
    return {**SHOT_DEFAULTS.get(shot.get("kind"), {}), **shot}


def look(job):
    return {**LOOK, **(job.get("look") or {})}


# ---------- timing ----------

def durations(job, clip_len):
    """Seconds per shot. clip_len(shot) is the prepared clip's length or None."""
    out = []
    for shot in job["shots"]:
        dur = shot.get("dur")
        if dur == "clip":
            got = clip_len(shot)
            dur = round(got - params(shot)["in"], 3) if got else params(shot)["clip_default"]
        out.append(dur)
    fixed = sum(d for d in out if isinstance(d, (int, float)))
    first_fill = True
    resolved = []
    for d in out:
        if d == "fill":
            d = round(job["length"] - fixed, 3) if first_fill else 0.0
            first_fill = False
        resolved.append(d)
    return resolved


def timeline(job, clip_len):
    """[(shot, start, end)] and the total. Times are rounded to 6 places so a cut at
    9.2 s is the same float as frame 276 / 30."""
    rows, t = [], 0.0
    for shot, dur in zip(job["shots"], durations(job, clip_len)):
        start = round(t, 6)
        t += dur
        rows.append((shot, start, round(t, 6)))
    return rows, round(t, 6)


def music_mutes(job, rows):
    """[(start, end)] where the music bed cuts out: audio.mute names shots (the black
    beat under the gunfire). The sfx still play."""
    spans = {shot["id"]: (start, end) for shot, start, end in rows}
    return [spans[sid] for sid in (job.get("audio") or {}).get("mute", []) if sid in spans]


def frame_count(length, fps):
    return int(round(length * fps))


def shot_at(rows, t):
    """The (shot, start, end) on screen at time t. The last shot holds past the end."""
    for row in rows:
        if row[1] <= t < row[2]:
            return row
    if rows and t >= rows[-1][1]:
        return rows[-1]
    raise ValueError(f"no shot at {t} s")


def sfx_cues(job, rows):
    """[(src, seconds, gain dB)]. A cue sits at `at` seconds, or at `offset` from the
    start of `shot`, so it moves with its shot when the clip length changes."""
    starts = {shot["id"]: start for shot, start, _ in rows}
    cues = []
    for cue in (job.get("audio") or {}).get("sfx", []):
        at = cue["at"] if "at" in cue else starts[cue["shot"]] + cue.get("offset", 0.0)
        cues.append((cue["src"], round(at, 3), cue.get("gain", 0)))
    return cues


def sheet_keys(rows):
    """[(seconds, label)] for the contact sheet, labels prefixed with the storyboard panel."""
    keys = []
    for shot, start, end in rows:
        samples = shot.get("sheet") or SHEET[shot["kind"]]
        if "label" in shot and not shot.get("sheet") and len(samples) == 1:
            samples = [(samples[0][0], shot["label"])]
        prefix = f"{shot['panel']} " if shot.get("panel") is not None else ""
        for frac, label in samples:
            keys.append((round(start + frac * (end - start), 2), prefix + label))
    return keys


def preview_window(rows, total):
    """The stretch around the clip(s) worth watching with sound at the gate: from the
    shot before the first clip to the shot after the last one."""
    idx = [i for i, (shot, _, _) in enumerate(rows) if shot["kind"] == "clip"]
    if not idx:
        return 0.0, total
    before = rows[max(idx[0] - 1, 0)]
    after = rows[min(idx[-1] + 1, len(rows) - 1)]
    return round(max(before[1] - PREVIEW_PAD[0], 0.0), 3), round(min(after[2] + PREVIEW_PAD[1], total), 3)


# ---------- VHS overlay and cover ----------

def vhs_config(job, rows):
    """job.json `vhs`: a strength 0..1, or {strength, fade_on, osd, osd_until}. The tape look
    sits on the character section and fades out across `fade_on` (default: the first white
    shot) so the shirt and the card come back clean; the PLAY readout shows until the end of
    `osd_until` (default: the first black shot)."""
    raw = job.get("vhs") or 0
    cfg = {"strength": raw} if isinstance(raw, (int, float)) else dict(raw)
    spans = {shot["id"]: (start, end) for shot, start, end in rows}

    def first(kind):
        return next((shot["id"] for shot, _, _ in rows if shot["kind"] == kind), None)

    fade_on = cfg.get("fade_on", first("white"))
    osd_until = cfg.get("osd_until", first("black") or (rows[0][0]["id"] if rows else None))
    return {"strength": float(cfg.get("strength", 0)), "fade": spans.get(fade_on),
            "osd": cfg.get("osd", OSD_TEXT), "osd_end": spans[osd_until][1] if osd_until in spans else 0.0}


def vhs_mix(cfg, t):
    """How much of the tape look is on screen at t: 1 until the fade shot, 0 after it."""
    if not cfg["fade"]:
        return 1.0
    return 1 - ramp(t, *cfg["fade"])


# ---------- lights ----------

# The lights dying (Tony, 2026-10-25): fractions of the flicker window and how far the light
# comes back on in each (0 = only the floor is left).
_FLICKER = ((0.00, 0.10, 0.0), (0.10, 0.22, 0.85), (0.22, 0.34, 0.0), (0.34, 0.44, 0.6),
            (0.44, 0.62, 0.0), (0.62, 0.70, 0.35), (0.70, 1.01, 0.0))


def light_level(p, t):
    """Brightness multiplier t seconds into a shot: `gain` dims the whole shot, and
    `lights_out` {at, flicker, floor} flickers the lights at `at` and then leaves `floor`."""
    out = p.get("lights_out")
    level = 1.0
    if out:
        at, flicker, floor = out["at"], out.get("flicker", 0.6), out.get("floor", 0.03)
        if t >= at + flicker:
            level = floor
        elif t >= at:
            frac = (t - at) / flicker
            on = next(v for a, b, v in _FLICKER if a <= frac < b)
            level = floor + (1 - floor) * on
    return p.get("gain", 1.0) * level


# ---------- rifle scope ----------

SCOPE = {"radius": 0.445, "y": 0.5, "rim": 0.05, "sway": 7.0, "steady": None, "held": 0.22,
         "float": 0.4, "phase": 0.0}
HAND = {"stiffness": 16.0, "damping": 0.55, "land": 0.35}    # the spring between his eye and the rifle
EYE_LAG = 0.22      # seconds the eye behind the glass falls behind the rifle
LIVE = {"feather": 0.05, "fade": 0.2}   # a live clip's soft edge (fraction of its width) and its fade up, seconds
LIVE_JOIN = 0.05    # seconds a live clip and the next clip's `in` may disagree by


def scope_cfg(cfg):
    """A shot's `scope` knob with its defaults: `radius` of the ring (fraction of the frame
    width), `y` its centre (fraction of the height), `rim` the soft dark edge (fraction of
    the radius), `sway` pixels of breathing and tremor, `steady` the seconds into the shot
    where he holds his breath, `held` the fraction of the sway left then (a real scope never
    stops dead), `float` how far the ring wanders on its own (fraction of the sway), `phase`
    seconds added to the sway's clock (a shot after a scan carries on from it)."""
    return {**SCOPE, **cfg}


def hand_path(points, dur, fps):
    """A hand steering a heavy rifle: each [t, x, y] is where he wants to look from t on, and
    the aim chases it on a damped spring, so it leans in, overshoots, corrects and settles,
    never a constant-speed pan. One (x, y) per frame, landing exactly on the last point."""
    stiff, damp = HAND["stiffness"], 2 * HAND["damping"] * math.sqrt(HAND["stiffness"])
    substeps, h = 4, 1 / (fps * 4)
    x, y, vx, vy, aim = points[0][1], points[0][2], 0.0, 0.0, []
    frames = int(round(dur * fps))
    for i in range(frames):
        aim.append((x, y))
        goal = [pt for pt in points if pt[0] <= i / fps][-1]
        for _ in range(substeps):
            vx += (stiff * (goal[1] - x) - damp * vx) * h
            vy += (stiff * (goal[2] - y) - damp * vy) * h
            x, y = x + vx * h, y + vy * h
    last, end = (frames - 1) / fps, points[-1]
    return [(ax + (end[1] - ax) * ramp(i / fps, last - HAND["land"], last),
             ay + (end[2] - ay) * ramp(i / fps, last - HAND["land"], last)) for i, (ax, ay) in enumerate(aim)]


def aim_lag(path, fps, tau=EYE_LAG):
    """How far the rifle has run ahead of the eye, per frame, in the path's units."""
    k = 1 - math.exp(-1 / (fps * tau))
    ex, ey, lag = path[0][0], path[0][1], []
    for x, y in path:
        ex, ey = ex + (x - ex) * k, ey + (y - ey) * k
        lag.append((x - ex, y - ey))
    return lag


# ---------- handheld camera ----------

CAMERA_KINDS = ("dolly", "pose", "clip", "glow", "still")
HANDHELD = {"x": 0.014, "y": 0.010, "rot": 0.4}    # at strength 1: frame width, frame height, degrees
ASPECT = 16 / 9                                    # H / W of the 9:16 frame
_WOBBLE = ((0.13, 0.50), (0.29, 0.30), (0.61, 0.13), (1.10, 0.07))   # Hz, weight (weights sum to 1)
_AXES = ((1.00, 0.0), (1.37, 1.7), (0.71, 4.1))    # x, y, rotation: frequency scale, phase


def handheld_config(job, rows):
    """job.json `handheld`: a strength 0..1, or {strength, from, to}. A slow camera-operator
    drift (Tony, 2026-10-25: "like we're watching a movie") over the character section: by
    default the first figure, still or clip shot to the last one before the first white. It
    runs on global time, so it carries straight through the cuts inside the span."""
    raw = job.get("handheld") or 0
    if not isinstance(raw, (int, float, dict)):
        return {"strength": 0.0, "span": None}
    cfg = {"strength": raw} if isinstance(raw, (int, float)) else dict(raw)
    return {"strength": float(cfg.get("strength", 0)), "span": section_span(rows, cfg)}


def section_span(rows, cfg):
    """(start, end) seconds from cfg `from` to `to`, by default the character section: the
    first figure, still or clip shot to the last one before the first white, so the shirt
    and the card stay clean. None when a named shot is missing."""
    spans = {shot["id"]: (start, end) for shot, start, end in rows}
    white = next((i for i, (shot, _, _) in enumerate(rows) if shot["kind"] == "white"), len(rows))
    section = [shot["id"] for shot, _, _ in rows[:white] if shot["kind"] in CAMERA_KINDS]
    first, last = cfg.get("from", section[0] if section else None), cfg.get("to", section[-1] if section else None)
    return (spans[first][0], spans[last][1]) if first in spans and last in spans else None


def _span_problems(name, cfg, job):
    order = [s.get("id") for s in job["shots"]]
    problems = [f"{name} {key}: no shot `{cfg[key]}`" for key in ("from", "to") if key in cfg and cfg[key] not in order]
    if cfg.get("from") in order and cfg.get("to") in order and order.index(cfg["from"]) > order.index(cfg["to"]):
        problems.append(f"{name}: `{cfg['from']}` comes after `{cfg['to']}`")
    return problems


def handheld_offset(cfg, t):
    """(dx, dy, rotation) at t: fractions of the frame width and height, and degrees. None
    outside the span or when the camera is locked off."""
    if not cfg["strength"] or not cfg["span"] or not cfg["span"][0] <= t < cfg["span"][1]:
        return None

    def wobble(scale, phase):
        return sum(w * math.sin(2 * math.pi * f * scale * t + phase * (k + 1)) for k, (f, w) in enumerate(_WOBBLE))

    s = cfg["strength"]
    return tuple(s * HANDHELD[key] * wobble(*axis) for key, axis in zip(("x", "y", "rot"), _AXES))


def handheld_zoom(strength):
    """The overscan that keeps the frame edge out of shot at the drift's extremes."""
    rad = math.radians(HANDHELD["rot"] * strength)
    need_x = 2 * HANDHELD["x"] * strength + rad * ASPECT
    need_y = 2 * HANDHELD["y"] * strength + rad / ASPECT
    return 1 + max(need_x, need_y) + 0.002


def _handheld_problems(job):
    raw = job.get("handheld")
    if raw is None:
        return []
    if not isinstance(raw, (int, float, dict)):
        return ["handheld must be a strength 0..1 or {strength, from, to}"]
    cfg = {"strength": raw} if isinstance(raw, (int, float)) else raw
    problems = []
    strength = cfg.get("strength", 0)
    if not isinstance(strength, (int, float)) or not 0 <= strength <= 1:
        problems.append(f"handheld strength must be 0 (locked off) to 1, got {strength}")
    return problems + _span_problems("handheld", cfg, job)


# ---------- creator stamp ----------

STAMP = {"height": 190, "opacity": 0.7, "corner": "top-right", "margin": [56, 250],
         "fade_in": 0.5, "hold": 3.0, "fade_out": 0.6}
CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right")


def stamp_config(job, rows):
    """job.json `stamp` {src, height, opacity, corner, margin, from, to, fade_in, hold, fade_out}:
    the creator credit (Tony, 2026-10-25: a creator logo, assets/brand/creator,
    "just brief, to show me as the creator"). It sits in a corner under the VHS pass like a
    channel bug on a tape: in at the start of the character section, `hold` seconds, out.
    `hold: null` keeps it on until the cut after the section. `margin` is [x, y] pixels from
    the corner; the default clears the platform buttons at the top of a phone. None when off."""
    raw = job.get("stamp")
    if not isinstance(raw, dict) or not raw.get("src"):
        return None
    cfg = {**STAMP, **raw}
    return {**cfg, "span": section_span(rows, cfg)}


def stamp_alpha(cfg, t):
    """How opaque the stamp is at t: 0 outside its span, `opacity` once it has faded in, and
    back to 0 over `fade_out` after `hold` seconds."""
    if not cfg or not cfg["span"] or not cfg["span"][0] <= t < cfg["span"][1]:
        return 0.0
    shown = cfg["span"][0] + cfg["fade_in"]
    level = cfg["opacity"] * ramp(t, cfg["span"][0], shown)
    if cfg["hold"] is None:
        return level
    out = shown + cfg["hold"]
    return level * (1 - ramp(t, out, out + cfg["fade_out"]))


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _stamp_problems(job, exists):
    raw = job.get("stamp")
    if raw is None:
        return []
    if not isinstance(raw, dict) or not raw.get("src"):
        return ["stamp must be {src, height, opacity, corner, margin, from, to, fade_in, hold, fade_out} with a src image"]
    cfg = {**STAMP, **raw}
    problems = [] if exists(cfg["src"]) else [f"missing file: {cfg['src']} (stamp)"]
    checks = (
        (_number(cfg["height"]) and 20 <= cfg["height"] <= 600, f"stamp height must be 20 to 600 pixels, got {cfg['height']}"),
        (_number(cfg["opacity"]) and 0 < cfg["opacity"] <= 1, f"stamp opacity must be above 0 and at most 1, got {cfg['opacity']}"),
        (cfg["corner"] in CORNERS, f"stamp corner must be one of {', '.join(CORNERS)}, got {cfg['corner']}"),
        (isinstance(cfg["margin"], list) and len(cfg["margin"]) == 2
         and all(_number(v) and v >= 0 for v in cfg["margin"]), f"stamp margin must be [x, y] pixels, got {cfg['margin']}"),
        (_number(cfg["fade_in"]) and cfg["fade_in"] >= 0, f"stamp fade_in must be 0 or more seconds, got {cfg['fade_in']}"),
        (cfg["hold"] is None or (_number(cfg["hold"]) and cfg["hold"] >= 0),
         f"stamp hold must be 0 or more seconds, or null to stay on, got {cfg['hold']}"),
        (_number(cfg["fade_out"]) and cfg["fade_out"] >= 0, f"stamp fade_out must be 0 or more seconds, got {cfg['fade_out']}"),
    )
    return problems + [message for ok, message in checks if not ok] + _span_problems("stamp", cfg, job)


def cover_time(job, rows):
    """out/cover.jpg: post.cover.at, else the glow at full strength (just before the bloom),
    else the middle of the clip, else the middle of the video."""
    at = ((job.get("post") or {}).get("cover") or {}).get("at")
    if at is not None:
        return at
    for kind, frac in (("glow", None), ("clip", 0.5)):
        for shot, start, end in rows:
            if shot["kind"] == kind:
                return round(end - 1.4, 2) if frac is None else round(start + frac * (end - start), 2)
    return round(rows[-1][2] / 2, 2)


def _vhs_problems(job):
    raw = job.get("vhs")
    if raw is None:
        return []
    cfg = {"strength": raw} if isinstance(raw, (int, float)) else raw
    if not isinstance(cfg, dict):
        return ["vhs must be a strength 0..1 or {strength, fade_on, osd, osd_until}"]
    problems = []
    strength = cfg.get("strength", 0)
    if not isinstance(strength, (int, float)) or not 0 <= strength <= 1:
        problems.append(f"vhs strength must be 0 (off) to 1 (full), got {strength}")
    ids = {s.get("id") for s in job["shots"]}
    for key in ("fade_on", "osd_until"):
        if key in cfg and cfg[key] not in ids:
            problems.append(f"vhs {key}: no shot `{cfg[key]}`")
    return problems


# ---------- validation ----------

def _is_box(box):
    return (isinstance(box, list) and len(box) == 4 and all(isinstance(v, (int, float)) for v in box)
            and box[0] < box[2] and box[1] < box[3])


def _figure_problems(job, exists):
    problems = []
    for name, fig in (job.get("figures") or {}).items():
        if not fig.get("src"):
            problems.append(f"figure `{name}`: src is empty (one of Tony's renders in src/)")
        elif not exists(fig["src"]):
            problems.append(f"missing file: {fig['src']} (figure `{name}`)")
        for op, box in (fig.get("feet") or {}).items():
            if op not in FEET_OPS:
                problems.append(f"figure `{name}`: unknown feet repair `{op}` (use {', '.join(FEET_OPS)})")
            elif not _is_box(box):
                problems.append(f"figure `{name}`: feet `{op}` box must be [x0, y0, x1, y1] with x0 < x1 and y0 < y1")
    return problems


def is_still_clip(shot):
    """A clip between two full-frame stills rather than two figures on the plate."""
    return shot.get("kind") == "clip" and ("start" in shot or "end" in shot)


def needs_plate(shots):
    return any(s.get("kind") in FIGURE_KINDS or (s.get("kind") == "clip" and not is_still_clip(s))
               for s in shots)


def _shot_problems(job, exists):
    problems, figures, shots = [], job.get("figures") or {}, job["shots"]
    for i, shot in enumerate(shots):
        sid, kind = shot.get("id", f"#{i}"), shot.get("kind")
        prev = shots[i - 1] if i else None
        if kind not in KINDS:
            problems.append(f"{sid}: kind must be one of {', '.join(KINDS)}")
            continue
        dur = shot.get("dur")
        if dur == "clip" and kind != "clip":
            problems.append(f"{sid}: dur \"clip\" only works on a clip shot")
        elif dur not in ("clip", "fill") and not (isinstance(dur, (int, float)) and dur > 0):
            problems.append(f"{sid}: dur must be seconds > 0, \"clip\" or \"fill\"")
        for key in ("src",) if kind in ("logo", "shirt", "still", "scan") else ("mockup",) if kind == "card" else ():
            if not shot.get(key):
                problems.append(f"{sid}: needs `{key}`")
            elif not exists(shot[key]):
                problems.append(f"missing file: {shot[key]} (shot {sid})")
        if kind in FIGURE_KINDS and shot.get("figure") not in figures:
            problems.append(f"{sid}: figure `{shot.get('figure')}` is not in figures")
        if kind == "clip":
            problems += (_still_clip_problems(sid, shot, prev, exists) if is_still_clip(shot)
                         else _clip_problems(sid, shot, prev, figures))
        nxt = shots[i + 1] if i + 1 < len(shots) else None
        if kind == "scan":
            problems += _scan_problems(sid, shot) + _live_problems(sid, shot, nxt, exists)
        if kind == "still" and nxt and nxt.get("kind") == "clip" and params(shot)["push"]:
            problems.append(f"{sid}: a still before clip `{nxt.get('id')}` holds the clip's first frame, "
                            f"so it cannot push (set push 0)")
        if kind == "glow" and prev and prev.get("kind") == "clip" and shot.get("figure") != prev.get("to"):
            problems.append(f"{sid}: the glow after clip `{prev.get('id')}` must use its end figure "
                            f"`{prev.get('to')}` or the light jumps at the cut")
    return problems


def _dur_ok(shot):
    """Kind and dur are sound enough to do the timing math on."""
    dur = shot.get("dur")
    if shot.get("kind") not in KINDS or (dur == "clip" and shot["kind"] != "clip"):
        return False
    return dur in ("clip", "fill") or (isinstance(dur, (int, float)) and dur > 0)


def _clip_basics(sid, shot):
    problems = []
    if not shot.get("clip"):
        problems.append(f"{sid}: needs `clip`, the prepared 30 fps file (e.g. work/kling/{sid}_30.mp4)")
    if not shot.get("prompt"):
        problems.append(f"{sid}: record the Kling prompt in `prompt`")
    elif re.search(r"<[^>]+>", shot["prompt"]):
        problems.append(f"{sid}: the Kling prompt still has <placeholders> from the template")
    lights = shot.get("lights_out")
    if lights is not None and not (isinstance(lights, dict) and isinstance(lights.get("at"), (int, float))):
        problems.append(f"{sid}: lights_out needs `at`, the seconds into the shot where the lights die")
    problems += _scope_problems(sid, shot.get("scope"))
    locked = not is_still_clip(shot)     # figure poses must line up; a still clip may move the camera
    for p in kling_prompt_problems(shot.get("prompt") or "", locked) if shot.get("prompt") else ():
        problems.append(f"{sid}: Kling prompt {p}")
    return problems


def _scope_problems(sid, scope):
    if scope is None or (isinstance(scope, dict) and 0.2 <= scope_cfg(scope)["radius"] <= 0.48):
        return []
    return [f"{sid}: scope needs a `radius` from 0.2 to 0.48 of the frame width, so the ring stays in frame"]


def _live_problems(sid, shot, nxt, exists):
    """A clip playing inside a scan has to sit on the still and carry on into the next clip."""
    live = params(shot)["live"]
    if live is None:
        return []
    problems = []
    box = live.get("box") or []
    if not (len(box) == 3 and box[0] >= 0 and 0 <= box[1] < 1 and box[2] > 0 and box[0] + box[2] <= 1):
        problems.append(f"{sid}: live needs a `box` of [x, y, width], fractions of the wide still, that fits on it")
    if not (live.get("clip") and exists(live["clip"])):
        problems.append(f"missing file: {live.get('clip')} (shot {sid})")
    at, dur = live.get("at"), shot.get("dur")
    if not (isinstance(at, (int, float)) and isinstance(dur, (int, float)) and 0 <= at < dur):
        return problems + [f"{sid}: live needs `at`, the seconds into the scan where the clip starts"]
    if not (nxt and nxt.get("kind") == "clip"):
        return problems + [f"{sid}: a live scan needs a clip after it to carry on into"]
    if abs(params(nxt)["in"] - (dur - at)) > LIVE_JOIN:
        problems.append(f"{sid}: clip `{nxt.get('id')}` must take up the live clip with `in` {dur - at:.3f}")
    return problems


def _scan_problems(sid, shot):
    path = shot.get("path") or []
    sound = (len(path) >= 2 and all(len(pt) == 3 and 0 <= pt[1] <= 1 and 0 <= pt[2] <= 1 for pt in path)
             and all(a[0] < b[0] for a, b in zip(path, path[1:])))
    problems = [] if sound else [f"{sid}: a scan needs a `path` of two or more [seconds, x, y] points in time "
                                 f"order, x and y as fractions of the wide still"]
    return problems + _scope_problems(sid, params(shot)["scope"])


def _still_clip_problems(sid, shot, prev, exists):
    problems = _clip_basics(sid, shot)
    if not shot.get("start"):
        problems.append(f"{sid}: a still clip needs `start`, the image of its start frame")
    for end in ("start", "end"):
        if shot.get(end) and not exists(shot[end]):
            problems.append(f"missing file: {shot[end]} (clip {sid} {end})")
    if prev and prev.get("kind") == "still" and prev.get("src") != shot.get("start"):
        problems.append(f"{sid}: the still right before a clip holds the clip's first frame, so it must be "
                        f"its start frame `{shot.get('start')}`")
    return problems


def _clip_problems(sid, shot, prev, figures):
    problems = _clip_basics(sid, shot)
    for end in ("from", "to"):
        if shot.get(end) not in figures:
            problems.append(f"{sid}: `{end}` figure `{shot.get(end)}` is not in figures")
    if not (prev and prev.get("kind") == "pose" and prev.get("figure") == shot.get("from")):
        problems.append(f"{sid}: a clip must come right after a pose shot of its start figure "
                        f"`{shot.get('from')}` (that shot holds Kling's first frame)")
    return problems


def _timing_problems(job, clip_len):
    problems, shots, length = [], job["shots"], job["length"]
    fills = [s.get("id") for s in shots if s.get("dur") == "fill"]
    if len(fills) > 1:
        return [f"only one shot can be dur \"fill\" (found {', '.join(map(str, fills))})"]
    durs = durations(job, clip_len)
    total = round(sum(durs), 3)
    for shot, dur in zip(shots, durs):
        if shot.get("dur") == "fill" and dur < MIN_FILL:
            problems.append(f"{shot['id']} (fill): the other shots leave {dur:.3f} s of the {length} s length")
        if shot.get("kind") == "glow" and dur < MIN_GLOW:
            problems.append(f"{shot['id']}: a glow needs at least {MIN_GLOW} s for the blow-out, it has {dur:.3f} s")
    if not fills and abs(total - length) > TOLERANCE:
        problems.append(f"the shots add up to {total} s but length is {length} s (give one shot dur \"fill\")")
    return problems


def _sfx_problems(job, clip_len):
    rows, _ = timeline(job, clip_len)
    starts = {shot["id"]: start for shot, start, _ in rows}
    problems = []
    for cue in (job.get("audio") or {}).get("sfx", []):
        if "at" not in cue and cue.get("shot") not in starts:
            problems.append(f"sfx {cue.get('src')}: no shot `{cue.get('shot')}`")
            continue
        at = cue["at"] if "at" in cue else starts[cue["shot"]] + cue.get("offset", 0.0)
        if not 0 <= at < job["length"]:
            problems.append(f"sfx {cue.get('src')}: lands at {round(at, 3)} s, outside the {job['length']} s video")
    return problems


def _mute_problems(job):
    ids = {s.get("id") for s in job["shots"]}
    return [f"audio.mute: no shot `{sid}`" for sid in (job.get("audio") or {}).get("mute", []) if sid not in ids]


def validate(job, clip_len, exists=lambda path: True):
    """Every problem with a job, as readable strings. Empty list = good to go."""
    problems = [f"job.json is missing `{key}`" for key in REQUIRED if key not in job]
    if problems:
        return problems
    if not isinstance(job["length"], (int, float)) or job["length"] <= 0:
        return ["length must be the video's seconds (the music bed's length)"]
    ids = [s.get("id") for s in job["shots"]]
    if len(set(ids)) != len(ids):
        problems.append("shot ids must be unique")
    if needs_plate(job["shots"]):
        plate = (job.get("plate") or {}).get("src")
        if not plate:
            problems.append("plate.src: pick a plate (storyboard_reel.py plate <job>)")
        elif not exists(plate):
            problems.append(f"missing file: {plate} (plate)")
    problems += _figure_problems(job, exists)
    problems += _vhs_problems(job)
    problems += _handheld_problems(job)
    problems += _stamp_problems(job, exists)
    problems += _shot_problems(job, exists)
    if all(_dur_ok(s) for s in job["shots"]):
        problems += _timing_problems(job, clip_len)
        problems += _sfx_problems(job, clip_len)
    problems += _mute_problems(job)
    music = (job.get("audio") or {}).get("music")
    if music and not exists(music):
        problems.append(f"missing file: {music} (audio.music)")
    return problems


# ---------- Kling prompt rules ----------

_SWING = re.compile(r"\bswing", re.I)
_NEGATION = re.compile(r"\b(never|not|no|without)\b", re.I)
_LOCKED = re.compile(r"\b(static|locked[- ]off)\b", re.I)


def kling_prompt_problems(prompt, locked=True):
    """What is wrong with a Kling start/end prompt, learned on the Wizard (2026-10-17). `locked`
    asks for the static camera that figure clips need; a camera-first still clip (Tony,
    2026-10-25) names its own camera move instead."""
    problems = []
    for match in _SWING.finditer(prompt):
        clause = re.split(r"[.,;:]", prompt[:match.start()])[-1]
        if not _NEGATION.search(clause):
            problems.append("says \"swing\": Kling flails the prop sideways and to the floor. Say \"one single "
                            "slow upward movement\" and \"it never swings sideways\"")
            break
    if locked and not _LOCKED.search(prompt):
        problems.append("must lock the camera (\"static locked-off camera\") or Kling drifts the shot")
    return problems


# ---------- card copy from Shopify ----------

def product_facts(data, url):
    """Title, price, size range and colour count from a Shopify product .json."""
    p = data["product"]
    opts = {o["name"].lower(): o["values"] for o in p.get("options", [])}
    prices = sorted({float(v["price"]) for v in p.get("variants", [])})
    sizes = opts.get("size", [])
    return {"url": url.split("?")[0].rstrip("/"), "title": p["title"].upper(),
            "price": f"${prices[0]:g}" if prices else "",
            "sizes": f"{sizes[0]}-{sizes[-1]}" if len(sizes) > 1 else (sizes[0] if sizes else ""),
            "colors": len(opts.get("color", [])), "color_names": list(opts.get("color", []))}


def details(product):
    """The card's facts line: $35   ·   M-2XL   ·   5 COLORS."""
    colors = product.get("colors") or 0
    bits = [product.get("price"), product.get("sizes"), f"{colors} COLORS" if colors > 1 else ""]
    return SEP.join(b for b in bits if b)


def fill_text(text, product):
    """{title} {details} {site} {price} {sizes} {colors} in on-screen copy."""
    host = urlparse(product.get("url", "")).netloc.lower().removeprefix("www.")
    values = {**{k: product.get(k, "") for k in ("title", "price", "sizes", "colors")},
              "details": details(product), "site": host.upper()}
    return re.sub(r"\{(\w+)\}", lambda m: str(values.get(m.group(1), m.group(0))), text)

